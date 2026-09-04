import pytest

from renegade_ai.memory.gdb import (
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
