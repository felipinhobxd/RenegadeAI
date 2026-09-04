from __future__ import annotations

import json
import struct
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from renegade_ai.memory.gdb import GDBRemoteClient, GDBRemoteError

GAME_CODE_ADDR = 0x02FFFE0C
PLATINUM_VERSION_CODE = 0x555043  # "CPU" in little-endian low 24 bits.

# Verified public Platinum addresses used by the Pokemon-Lua tooling. The
# pointed object is validated as SaveData before RenegadeAI trusts it.
SAVE_POINTER_BY_LANGUAGE = {
    0x44: ("GER", 0x02101ECC),
    0x45: ("EUR/USA", 0x02101D2C),
    0x46: ("FRE", 0x02101F0C),
    0x49: ("ITA", 0x02101E8C),
    0x4A: ("JPN", 0x0210112C),
    0x4B: ("KOR", 0x02102C2C),
    0x53: ("SPA", 0x02101F2C),
}

MAIN_RAM_START = 0x02000000
MAIN_RAM_END = 0x02400000

SAVE_BODY_OFFSET = 0x14
SAVE_PAGE_INFO_OFFSET = 0x20024
SAVE_PAGE_INFO_SIZE = 16
SAVE_ENTRY_PLAYER = 1
SAVE_ENTRY_PARTY = 2
SAVE_ENTRY_FIELD_PLAYER_STATE = 6

POKEPLATINUM_COMMIT = "bca37652996330898fdd2408281ea419b8c995c7"
MAP_HEADERS_URL = (
    "https://raw.githubusercontent.com/pret/pokeplatinum/"
    f"{POKEPLATINUM_COMMIT}/generated/map_headers.txt"
)
DEFAULT_MAP_HEADERS_PATH = Path("data/knowledge/renegade_platinum/map_headers.json")
DEFAULT_PROFILE_PATH = Path("data/memory_profile.json")

_FACING_NAMES = {-1: "none", 0: "up", 1: "down", 2: "left", 3: "right"}


@dataclass(frozen=True, slots=True)
class GameIdentity:
    game_code: int
    version_code: int
    language_code: int
    language: str
    save_pointer_address: int


@dataclass(frozen=True, slots=True)
class StructuredLocation:
    map_header_id: int
    map_name: str
    warp_id: int
    x: int
    z: int
    face_direction: int
    facing: str
    source: str = "melonDS-gdb"
    confidence: float = 1.0

    @property
    def key(self) -> str:
        return f"{self.map_header_id}:{self.x}:{self.z}"


@dataclass(frozen=True, slots=True)
class StructuredProgress:
    badge_mask: int
    badge_count: int
    money: int
    main_story_cleared: bool
    has_national_dex: bool


@dataclass(frozen=True, slots=True)
class SaveAnchor:
    save_base: int
    player_location: int
    party_location: int
    field_state_location: int
    party_capacity: int
    party_count: int


class MapHeaderCatalog:
    def __init__(self, path: str | Path = DEFAULT_MAP_HEADERS_PATH) -> None:
        self.path = Path(path)
        self.names: list[str] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        names = payload.get("names") if isinstance(payload, dict) else None
        if isinstance(names, list):
            self.names = [str(value) for value in names]

    def ensure(self, *, timeout: float = 8.0) -> None:
        if self.names:
            return
        request = urllib.request.Request(
            MAP_HEADERS_URL,
            headers={"User-Agent": "RenegadeAI/0.6 structured-memory"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8")
        except OSError:
            return
        names = [line.strip() for line in text.splitlines() if line.strip()]
        if not names:
            return
        self.names = names
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pokeplatinum_commit": POKEPLATINUM_COMMIT,
            "source": MAP_HEADERS_URL,
            "names": names,
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def name(self, map_header_id: int) -> str:
        if 0 <= map_header_id < len(self.names):
            raw = self.names[map_header_id]
            prefix = "MAP_HEADER_"
            return raw[len(prefix) :] if raw.startswith(prefix) else raw
        return f"MAP_{map_header_id}"


class PlatinumMemoryReader:
    """Validated, read-only structured state reader for Platinum/Renegade.

    The static pointer table is never trusted by itself. We first parse the
    in-memory SaveData page table and verify the Party entry (capacity/count).
    Only then is the FieldOverworldState player Location exposed.
    """

    def __init__(
        self,
        client: GDBRemoteClient,
        *,
        catalog: MapHeaderCatalog | None = None,
        profile_path: str | Path = DEFAULT_PROFILE_PATH,
        reporter: Callable[[str], None] | None = None,
    ) -> None:
        self.client = client
        self.catalog = catalog or MapHeaderCatalog()
        self.profile_path = Path(profile_path)
        self.reporter = reporter
        self.identity: GameIdentity | None = None
        self.anchor: SaveAnchor | None = None

    @staticmethod
    def _is_main_ram_pointer(value: int) -> bool:
        return MAIN_RAM_START <= value < MAIN_RAM_END and value % 4 == 0

    def _report(self, message: str) -> None:
        if self.reporter is not None:
            self.reporter(message)

    def _page_info(self, save_base: int, entry: int) -> tuple[int, int, int, int, int]:
        address = save_base + SAVE_PAGE_INFO_OFFSET + entry * SAVE_PAGE_INFO_SIZE
        raw = self.client.read_memory(address, SAVE_PAGE_INFO_SIZE)
        return struct.unpack("<IIIHH", raw)

    def detect_identity(self) -> GameIdentity:
        game_code = self.client.read_u32(GAME_CODE_ADDR)
        version_code = game_code & 0xFFFFFF
        language_code = (game_code >> 24) & 0xFF
        if version_code != PLATINUM_VERSION_CODE:
            ascii_code = struct.pack("<I", game_code).decode("ascii", errors="replace")
            raise GDBRemoteError(
                f"Expected Pokemon Platinum-compatible game code, got {ascii_code!r} "
                f"(0x{game_code:08X})"
            )
        language_info = SAVE_POINTER_BY_LANGUAGE.get(language_code)
        if language_info is None:
            raise GDBRemoteError(
                f"Unsupported Platinum language code 0x{language_code:02X}"
            )
        language, pointer_address = language_info
        identity = GameIdentity(
            game_code=game_code,
            version_code=version_code,
            language_code=language_code,
            language=language,
            save_pointer_address=pointer_address,
        )
        self.identity = identity
        return identity

    def probe(self) -> SaveAnchor:
        identity = self.identity or self.detect_identity()
        save_base = self.client.read_u32(identity.save_pointer_address)
        if not self._is_main_ram_pointer(save_base):
            raise GDBRemoteError(
                f"Platinum SaveData pointer is not in ARM9 main RAM: 0x{save_base:08X}"
            )

        player_page_id, player_size, player_location, _checksum, _block = self._page_info(
            save_base, SAVE_ENTRY_PLAYER
        )
        if player_page_id != SAVE_ENTRY_PLAYER:
            raise GDBRemoteError(
                f"SaveData validation failed: player page id={player_page_id}"
            )
        if not (0x20 <= player_size <= 0x1000 and 0 <= player_location < 0x20000):
            raise GDBRemoteError("SaveData validation failed: implausible player page")

        party_page_id, party_size, party_location, _checksum, _block = self._page_info(
            save_base, SAVE_ENTRY_PARTY
        )
        if party_page_id != SAVE_ENTRY_PARTY:
            raise GDBRemoteError(
                f"SaveData validation failed: party page id={party_page_id}"
            )
        if not (8 <= party_size <= 0x4000 and 0 <= party_location < 0x20000):
            raise GDBRemoteError("SaveData validation failed: implausible party page")
        party_addr = save_base + SAVE_BODY_OFFSET + party_location
        party_capacity, party_count = struct.unpack(
            "<ii", self.client.read_memory(party_addr, 8)
        )
        if party_capacity != 6 or not (0 <= party_count <= 6):
            raise GDBRemoteError(
                "SaveData validation failed: "
                f"Party(capacity={party_capacity}, count={party_count})"
            )

        field_page_id, field_size, field_location, _checksum, _block = self._page_info(
            save_base, SAVE_ENTRY_FIELD_PLAYER_STATE
        )
        if field_page_id != SAVE_ENTRY_FIELD_PLAYER_STATE:
            raise GDBRemoteError(
                f"SaveData validation failed: field page id={field_page_id}"
            )
        if not (0x40 <= field_size <= 0x1000 and 0 <= field_location < 0x20000):
            raise GDBRemoteError("SaveData validation failed: implausible field-state page")

        anchor = SaveAnchor(
            save_base=save_base,
            player_location=player_location,
            party_location=party_location,
            field_state_location=field_location,
            party_capacity=party_capacity,
            party_count=party_count,
        )
        self.anchor = anchor
        self.catalog.ensure()
        self._save_profile(anchor)
        self._report(
            "Structured RAM validated: "
            f"SaveData=0x{save_base:08X}, party={party_count}/6, "
            f"fieldOffset=0x{field_location:X}."
        )
        return anchor

    def _save_profile(self, anchor: SaveAnchor) -> None:
        identity = self.identity
        if identity is None:
            return
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "mode": "read-only",
            "game": asdict(identity),
            "anchor": asdict(anchor),
            "pokeplatinum_commit": POKEPLATINUM_COMMIT,
        }
        temp = self.profile_path.with_suffix(self.profile_path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(self.profile_path)

    @staticmethod
    def _validate_location(values: tuple[int, int, int, int, int]) -> None:
        map_header_id, warp_id, x, z, face_direction = values
        if not (0 <= map_header_id < 2048):
            raise GDBRemoteError(f"Invalid map header id from RAM: {map_header_id}")
        if not (-1 <= warp_id < 4096):
            raise GDBRemoteError(f"Invalid warp id from RAM: {warp_id}")
        if not (-128 <= x <= 8192 and -128 <= z <= 8192):
            raise GDBRemoteError(f"Invalid player coordinates from RAM: ({x}, {z})")
        if face_direction not in _FACING_NAMES:
            raise GDBRemoteError(f"Invalid facing direction from RAM: {face_direction}")

    def read_location(self) -> StructuredLocation:
        anchor = self.anchor or self.probe()
        address = anchor.save_base + SAVE_BODY_OFFSET + anchor.field_state_location
        values = struct.unpack("<iiiii", self.client.read_memory(address, 20))
        self._validate_location(values)
        map_header_id, warp_id, x, z, face_direction = values
        return StructuredLocation(
            map_header_id=map_header_id,
            map_name=self.catalog.name(map_header_id),
            warp_id=warp_id,
            x=x,
            z=z,
            face_direction=face_direction,
            facing=_FACING_NAMES[face_direction],
        )

    def read_progress(self) -> StructuredProgress:
        anchor = self.anchor or self.probe()
        player_addr = anchor.save_base + SAVE_BODY_OFFSET + anchor.player_location
        # PlayerSave.info starts at +4. TrainerInfo has an 8-char UTF-16 name
        # (16 bytes), then id/money and five one-byte fields followed by flags.
        raw = self.client.read_memory(player_addr + 4, 30)
        money = struct.unpack_from("<I", raw, 20)[0]
        badge_mask = raw[26]
        flags = raw[29]
        return StructuredProgress(
            badge_mask=badge_mask,
            badge_count=int(badge_mask).bit_count(),
            money=money,
            main_story_cleared=bool(flags & 0x01),
            has_national_dex=bool(flags & 0x02),
        )

    def party_count(self) -> int:
        anchor = self.anchor or self.probe()
        party_addr = anchor.save_base + SAVE_BODY_OFFSET + anchor.party_location
        return struct.unpack("<i", self.client.read_memory(party_addr + 4, 4))[0]
