import struct

import pytest

from renegade_ai.memory.gdb import GDBRemoteError
from renegade_ai.memory.platinum import (
    GAME_CODE_ADDR,
    SAVE_BODY_OFFSET,
    SAVE_ENTRY_FIELD_PLAYER_STATE,
    SAVE_ENTRY_PARTY,
    SAVE_ENTRY_PLAYER,
    SAVE_PAGE_INFO_OFFSET,
    SAVE_PAGE_INFO_SIZE,
    SAVE_POINTER_BY_LANGUAGE,
    MapHeaderCatalog,
    PlatinumMemoryReader,
)


class FakeMemory:
    def __init__(self):
        self.bytes = {}

    def put(self, address: int, payload: bytes) -> None:
        for offset, value in enumerate(payload):
            self.bytes[address + offset] = value

    def read_memory(self, address: int, length: int) -> bytes:
        try:
            return bytes(self.bytes[address + offset] for offset in range(length))
        except KeyError as exc:
            raise AssertionError(f"unmapped fake read at 0x{address:08X}") from exc

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read_memory(address, 4))[0]


def _valid_memory(*, party_capacity: int = 6) -> FakeMemory:
    memory = FakeMemory()
    save_base = 0x02210000
    game_code = (0x45 << 24) | 0x555043
    memory.put(GAME_CODE_ADDR, struct.pack("<I", game_code))
    pointer = SAVE_POINTER_BY_LANGUAGE[0x45][1]
    memory.put(pointer, struct.pack("<I", save_base))

    player_location = 0x1000
    player_info = save_base + SAVE_PAGE_INFO_OFFSET + SAVE_ENTRY_PLAYER * SAVE_PAGE_INFO_SIZE
    memory.put(
        player_info,
        struct.pack("<IIIHH", SAVE_ENTRY_PLAYER, 0x2C, player_location, 0, 0),
    )
    player_addr = save_base + SAVE_BODY_OFFSET + player_location
    trainer = bytearray(30)
    struct.pack_into("<I", trainer, 20, 12345)
    trainer[26] = 0b00000101
    trainer[29] = 0x01
    memory.put(player_addr + 4, bytes(trainer))

    party_location = 0xD078
    party_info = save_base + SAVE_PAGE_INFO_OFFSET + SAVE_ENTRY_PARTY * SAVE_PAGE_INFO_SIZE
    memory.put(
        party_info,
        struct.pack("<IIIHH", SAVE_ENTRY_PARTY, 0x600, party_location, 0, 0),
    )
    party_addr = save_base + SAVE_BODY_OFFSET + party_location
    memory.put(party_addr, struct.pack("<ii", party_capacity, 2))

    field_location = 0xC000
    field_info = (
        save_base
        + SAVE_PAGE_INFO_OFFSET
        + SAVE_ENTRY_FIELD_PLAYER_STATE * SAVE_PAGE_INFO_SIZE
    )
    memory.put(
        field_info,
        struct.pack(
            "<IIIHH",
            SAVE_ENTRY_FIELD_PLAYER_STATE,
            0xA0,
            field_location,
            0,
            0,
        ),
    )
    field_addr = save_base + SAVE_BODY_OFFSET + field_location
    memory.put(field_addr, struct.pack("<iiiii", 3, -1, 11, 22, 3))
    return memory


def test_reader_validates_savedata_and_reads_exact_location(tmp_path):
    memory = _valid_memory()
    catalog = MapHeaderCatalog(tmp_path / "maps.json")
    catalog.names = [
        "MAP_HEADER_EVERYWHERE",
        "MAP_HEADER_NOTHING",
        "MAP_HEADER_UNDERGROUND",
        "MAP_HEADER_JUBILIFE_CITY",
    ]
    reader = PlatinumMemoryReader(
        memory,
        catalog=catalog,
        profile_path=tmp_path / "profile.json",
    )
    anchor = reader.probe()
    location = reader.read_location()

    assert anchor.party_count == 2
    assert location.map_header_id == 3
    assert location.map_name == "JUBILIFE_CITY"
    assert (location.x, location.z) == (11, 22)
    assert location.facing == "right"
    progress = reader.read_progress()
    assert progress.badge_count == 2
    assert progress.money == 12345
    assert progress.main_story_cleared is True
    assert (tmp_path / "profile.json").exists()


def test_reader_rejects_wrong_savedata_anchor(tmp_path):
    memory = _valid_memory(party_capacity=99)
    catalog = MapHeaderCatalog(tmp_path / "maps.json")
    catalog.names = ["MAP_HEADER_EVERYWHERE"]
    reader = PlatinumMemoryReader(
        memory,
        catalog=catalog,
        profile_path=tmp_path / "profile.json",
    )
    with pytest.raises(GDBRemoteError, match="Party"):
        reader.probe()
