import pytest

from renegade_ai.memory.gdb import (
    GDBRemoteClient,
    GDBRemoteError,
    decode_memory_payload,
    encode_packet,
    rsp_checksum,
)


def test_rsp_checksum_and_packet():
    payload = b"m2000000,4"
    packet = encode_packet(payload)
    assert packet == b"$m2000000,4#" + f"{rsp_checksum(payload):02x}".encode("ascii")


def test_decode_memory_payload():
    assert decode_memory_payload("0102ff00", 4) == b"\x01\x02\xff\x00"
    with pytest.raises(GDBRemoteError):
        decode_memory_payload("E01")
    with pytest.raises(GDBRemoteError):
        decode_memory_payload("00", 2)


class FakeSocket:
    def __init__(self, incoming: bytes) -> None:
        self.incoming = bytearray(incoming)
        self.sent = bytearray()
        self.timeout = None
        self.closed = False

    def settimeout(self, value):
        self.timeout = value

    def sendall(self, data: bytes):
        self.sent.extend(data)

    def recv(self, count: int) -> bytes:
        if not self.incoming:
            return b""
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def close(self):
        self.closed = True


def packet(payload: str) -> bytes:
    return encode_packet(payload)


def test_connect_immediately_continues_and_reads_without_ctrl_c(monkeypatch):
    # Server sequence: connection handshake ack, ack for Continue, ack +
    # qSupported response, ack + memory response.
    incoming = (
        b"+"
        + b"+"
        + b"+"
        + packet("PacketSize=400")
        + b"+"
        + packet("01020304")
    )
    fake = FakeSocket(incoming)
    monkeypatch.setattr(
        "renegade_ai.memory.gdb.socket.create_connection",
        lambda *_args, **_kwargs: fake,
    )

    client = GDBRemoteClient(timeout=0.1)
    client.connect()
    data = client.read_memory(0x02000000, 4)

    assert data == b"\x01\x02\x03\x04"
    assert fake.sent.startswith(b"+" + encode_packet("c"))
    assert b"\x03" not in fake.sent
    assert client.interrupt_count == 0
    assert client.read_requests == 1
    assert client.bytes_read == 4


def test_fail_open_sends_continue_before_closing(monkeypatch):
    fake = FakeSocket(b"")
    monkeypatch.setattr(
        "renegade_ai.memory.gdb.socket.create_connection",
        lambda *_args, **_kwargs: fake,
    )
    client = GDBRemoteClient(timeout=0.1)

    with pytest.raises(GDBRemoteError):
        client.connect()

    assert encode_packet("c") in fake.sent
    assert fake.closed is True
    assert client.connected is False
