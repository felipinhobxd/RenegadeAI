import struct

import pytest

from renegade_ai.memory.gdb import GDBRemoteError
from renegade_ai.memory.platinum import (
    FLAG_BYTES,
    GAME_CODE_ADDR,
    MAP_OBJECT_SAVE_COUNT,
    MAP_OBJECT_SAVE_SIZE,
    SAVE_BODY_OFFSET,
    SAVE_ENTRY_FIELD_OVERWORLD_STATE,
    SAVE_ENTRY_FIELD_PLAYER_STATE,
    SAVE_ENTRY_PARTY,
    SAVE_ENTRY_PLAYER,
    SAVE_ENTRY_VARS_FLAGS,
    SAVE_PAGE_INFO_OFFSET,
    SAVE_PAGE_INFO_SIZE,
    SAVE_POINTER_BY_LANGUAGE,
    VARS_START,
    MapHeaderCatalog,
    PlatinumMemoryReader,
    VarsFlagsCatalog,
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


def _put_page_info(
    memory: FakeMemory,
    save_base: int,
    entry: int,
    size: int,
    location: int,
) -> None:
    address = save_base + SAVE_PAGE_INFO_OFFSET + entry * SAVE_PAGE_INFO_SIZE
    memory.put(address, struct.pack("<IIIHH", entry, size, location, 0, 0))


def _valid_memory(*, party_capacity: int = 6) -> FakeMemory:
    memory = FakeMemory()
    save_base = 0x02210000
    game_code = (0x45 << 24) | 0x555043
    memory.put(GAME_CODE_ADDR, struct.pack("<I", game_code))
    pointer = SAVE_POINTER_BY_LANGUAGE[0x45][1]
    memory.put(pointer, struct.pack("<I", save_base))

    player_location = 0x1000
    _put_page_info(memory, save_base, SAVE_ENTRY_PLAYER, 0x2C, player_location)
    player_addr = save_base + SAVE_BODY_OFFSET + player_location
    trainer = bytearray(30)
    struct.pack_into("<I", trainer, 20, 12345)
    trainer[26] = 0b00000101
    trainer[29] = 0x01
    memory.put(player_addr + 4, bytes(trainer))

    party_location = 0xD078
    _put_page_info(memory, save_base, SAVE_ENTRY_PARTY, 0x600, party_location)
    party_addr = save_base + SAVE_BODY_OFFSET + party_location
    memory.put(party_addr, struct.pack("<ii", party_capacity, 2))

    field_location = 0xC000
    _put_page_info(memory, save_base, SAVE_ENTRY_FIELD_PLAYER_STATE, 0xA0, field_location)
    field_addr = save_base + SAVE_BODY_OFFSET + field_location
    memory.put(field_addr, struct.pack("<iiiii", 3, -1, 11, 22, 3))
    return memory


def _reader(tmp_path, memory: FakeMemory) -> PlatinumMemoryReader:
    catalog = MapHeaderCatalog(tmp_path / "maps.json")
    catalog.names = [
        "MAP_HEADER_EVERYWHERE",
        "MAP_HEADER_NOTHING",
        "MAP_HEADER_UNDERGROUND",
        "MAP_HEADER_JUBILIFE_CITY",
    ]
    story_catalog = VarsFlagsCatalog(tmp_path / "vars_flags.json")
    story_catalog.flag_names = {5: "FLAG_TEST_STORY"}
    story_catalog.var_names = {VARS_START + 1: "VAR_TEST_COUNTER"}
    return PlatinumMemoryReader(
        memory,
        catalog=catalog,
        story_catalog=story_catalog,
        profile_path=tmp_path / "profile.json",
    )


def test_reader_validates_savedata_and_reads_exact_location(tmp_path):
    memory = _valid_memory()
    reader = _reader(tmp_path, memory)
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
    reader = _reader(tmp_path, memory)
    with pytest.raises(GDBRemoteError, match="Party"):
        reader.probe()


def test_reader_exposes_named_story_flags_and_vars(tmp_path):
    memory = _valid_memory()
    save_base = 0x02210000
    vars_location = 0x5000
    variables = struct.pack("<4H", 0, 77, 0, 9)
    flags = bytearray(FLAG_BYTES)
    flags[5 >> 3] |= 1 << (5 & 7)
    payload = variables + bytes(flags)
    _put_page_info(memory, save_base, SAVE_ENTRY_VARS_FLAGS, len(payload), vars_location)
    memory.put(save_base + SAVE_BODY_OFFSET + vars_location, payload)

    reader = _reader(tmp_path, memory)
    story = reader.read_story_state()

    assert story.active_flag_ids == (5,)
    assert story.active_flags == ("FLAG_TEST_STORY",)
    assert story.nonzero_vars["VAR_TEST_COUNTER"] == 77
    assert story.nonzero_vars[f"VAR_0x{VARS_START + 3:04X}"] == 9
    assert len(story.digest) == 24


def test_reader_exposes_persisted_field_objects_for_current_map(tmp_path):
    memory = _valid_memory()
    save_base = 0x02210000
    object_location = 0x7000
    payload = bytearray(MAP_OBJECT_SAVE_SIZE * MAP_OBJECT_SAVE_COUNT)

    # Slot 0: active object on current Jubilife map at (12, 22).
    struct.pack_into("<I", payload, 0, 1)
    payload[8] = 7
    payload[9] = 2
    struct.pack_into("<b", payload, 13, 2)
    struct.pack_into("<H", payload, 16, 3)
    struct.pack_into("<H", payload, 18, 99)
    struct.pack_into("<H", payload, 20, 1)
    struct.pack_into("<H", payload, 22, 10)
    struct.pack_into("<H", payload, 24, 123)
    struct.pack_into("<h", payload, 38, 12)
    struct.pack_into("<h", payload, 42, 22)

    # Slot 1: active object from another map; filtered in current-map mode.
    offset = MAP_OBJECT_SAVE_SIZE
    struct.pack_into("<I", payload, offset, 1)
    payload[offset + 8] = 8
    struct.pack_into("<H", payload, offset + 16, 2)

    _put_page_info(
        memory,
        save_base,
        SAVE_ENTRY_FIELD_OVERWORLD_STATE,
        len(payload),
        object_location,
    )
    memory.put(save_base + SAVE_BODY_OFFSET + object_location, bytes(payload))

    reader = _reader(tmp_path, memory)
    objects = reader.read_field_objects(current_map_only=True)

    assert len(objects) == 1
    obj = objects[0]
    assert obj.local_id == 7
    assert obj.map_name == "JUBILIFE_CITY"
    assert (obj.x, obj.z) == (12, 22)
    assert obj.facing == "left"


def test_vars_flags_catalog_parses_aliases_and_sequential_values():
    text = """
FLAG_ZERO
FLAG_STORY
VARS_START = 16384
VAR_FIRST = VARS_START
VAR_SECOND
VAR_THIRD = VAR_FIRST + 2
"""
    flags, variables = VarsFlagsCatalog.parse(text)

    assert flags[0] == "FLAG_ZERO"
    assert flags[1] == "FLAG_STORY"
    assert variables[VARS_START] == "VAR_FIRST"
    assert variables[VARS_START + 1] == "VAR_SECOND"
    assert variables[VARS_START + 2] == "VAR_THIRD"
