from __future__ import annotations

import socket
import struct
from contextlib import contextmanager
from typing import Iterator


class GDBRemoteError(RuntimeError):
    """Raised when the melonDS GDB remote endpoint rejects a read."""


def rsp_checksum(payload: bytes) -> int:
    return sum(payload) & 0xFF


def encode_packet(payload: str | bytes) -> bytes:
    raw = payload.encode("ascii") if isinstance(payload, str) else payload
    return b"$" + raw + b"#" + f"{rsp_checksum(raw):02x}".encode("ascii")


def decode_memory_payload(payload: str, expected: int | None = None) -> bytes:
    if payload.startswith("E"):
        raise GDBRemoteError(f"GDB memory read failed: {payload}")
    try:
        result = bytes.fromhex(payload)
    except ValueError as exc:
        raise GDBRemoteError(f"Invalid hex memory response: {payload[:80]!r}") from exc
    if expected is not None and len(result) != expected:
        raise GDBRemoteError(
            f"Short GDB memory read: expected {expected} bytes, got {len(result)}"
        )
    return result


class GDBRemoteClient:
    """Tiny read-only GDB Remote Serial Protocol client for melonDS ARM9.

    Public operations expose memory reads only. The target is interrupted for
    a short read transaction and immediately resumed. No memory/register write
    packet is implemented by this class.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3333,
        *,
        timeout: float = 1.5,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.timeout = float(timeout)
        self.sock: socket.socket | None = None
        self.max_read = 512
        self._stopped = False
        self._pause_depth = 0

    @property
    def connected(self) -> bool:
        return self.sock is not None

    def connect(self) -> None:
        if self.sock is not None:
            return
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        with self.paused():
            supported = self._request("qSupported")
            for part in supported.split(";"):
                if part.startswith("PacketSize="):
                    try:
                        packet_size = int(part.split("=", 1)[1], 16)
                    except ValueError:
                        continue
                    self.max_read = max(32, min(512, (packet_size - 32) // 2))

    def close(self) -> None:
        if self.sock is None:
            return
        try:
            if self._stopped:
                self.resume()
        except (OSError, GDBRemoteError):
            pass
        try:
            self.sock.close()
        finally:
            self.sock = None
            self._stopped = False
            self._pause_depth = 0

    def __enter__(self) -> GDBRemoteClient:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _socket(self) -> socket.socket:
        if self.sock is None:
            raise GDBRemoteError("GDB client is not connected")
        return self.sock

    def _recv_exact(self, count: int) -> bytes:
        sock = self._socket()
        data = bytearray()
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise GDBRemoteError("GDB connection closed")
            data.extend(chunk)
        return bytes(data)

    def _read_packet(self) -> str:
        sock = self._socket()
        while True:
            marker = self._recv_exact(1)
            if marker in {b"+", b"-"}:
                continue
            if marker == b"$":
                break
        payload = bytearray()
        while True:
            ch = self._recv_exact(1)
            if ch == b"#":
                break
            payload.extend(ch)
        checksum_text = self._recv_exact(2)
        try:
            expected = int(checksum_text, 16)
        except ValueError as exc:
            sock.sendall(b"-")
            raise GDBRemoteError("Malformed GDB packet checksum") from exc
        actual = rsp_checksum(bytes(payload))
        if actual != expected:
            sock.sendall(b"-")
            raise GDBRemoteError(
                f"GDB packet checksum mismatch: expected {expected:02x}, got {actual:02x}"
            )
        sock.sendall(b"+")
        return payload.decode("ascii", errors="replace")

    def _send_packet(self, payload: str) -> None:
        sock = self._socket()
        packet = encode_packet(payload)
        for _attempt in range(3):
            sock.sendall(packet)
            ack = self._recv_exact(1)
            if ack == b"+":
                return
            if ack != b"-":
                raise GDBRemoteError(f"Unexpected GDB acknowledgement byte: {ack!r}")
        raise GDBRemoteError("GDB packet was rejected repeatedly")

    def _request(self, payload: str) -> str:
        self._send_packet(payload)
        return self._read_packet()

    def interrupt(self) -> str:
        if self._stopped:
            return "already-stopped"
        self._socket().sendall(b"\x03")
        response = self._read_packet()
        if not (response.startswith("S") or response.startswith("T")):
            raise GDBRemoteError(f"Unexpected stop response: {response!r}")
        self._stopped = True
        return response

    def resume(self) -> None:
        if not self._stopped:
            return
        self._send_packet("c")
        self._stopped = False

    @contextmanager
    def paused(self) -> Iterator[None]:
        outer = self._pause_depth == 0
        self._pause_depth += 1
        if outer:
            self.interrupt()
        try:
            yield
        finally:
            self._pause_depth -= 1
            if outer and self._pause_depth == 0:
                self.resume()

    def read_memory(self, address: int, length: int) -> bytes:
        if address < 0 or length < 0:
            raise ValueError("address and length must be non-negative")
        if length == 0:
            return b""
        result = bytearray()
        with self.paused():
            offset = 0
            while offset < length:
                size = min(self.max_read, length - offset)
                payload = self._request(f"m{address + offset:x},{size:x}")
                result.extend(decode_memory_payload(payload, size))
                offset += size
        return bytes(result)

    def read_u8(self, address: int) -> int:
        return self.read_memory(address, 1)[0]

    def read_u16(self, address: int) -> int:
        return struct.unpack("<H", self.read_memory(address, 2))[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read_memory(address, 4))[0]

    def read_i32(self, address: int) -> int:
        return struct.unpack("<i", self.read_memory(address, 4))[0]
