from __future__ import annotations

import json
import re
import struct
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.memory.platinum import POKEPLATINUM_COMMIT, MapHeaderCatalog

_RAW_ROOT = (
    "https://raw.githubusercontent.com/pret/pokeplatinum/"
    f"{POKEPLATINUM_COMMIT}"
)
_MATRIX_COUNT = 289
_TILES_PER_BLOCK = 32
_TERRAIN_OFFSET = 0x10
_TERRAIN_SIZE = 0x800
_COLLISION_MASK = 0x8000
_INVALID_HEADERS = {0, 1, 2}


@dataclass(frozen=True, slots=True)
class MatrixCell:
    matrix_id: int
    row: int
    col: int
    land_data_id: int


@dataclass(frozen=True, slots=True)
class MapHeaderMetadata:
    matrix_id: int
    events_name: str | None = None


@dataclass(frozen=True, slots=True)
class WarpPortal:
    source_header_id: int
    destination_header_id: int
    source: GridPoint
    destination_warp_id: int
    kind: str = "warp"


@dataclass(frozen=True, slots=True)
class BoundaryPortal:
    source_header_id: int
    destination_header_id: int
    source: GridPoint
    destination: GridPoint
    kind: str = "matrix_boundary"


class PlatinumWorldModel:
    """Static Platinum topology/collision with live-save overrides above it.

    Static geometry is read from a pinned ``pret/pokeplatinum`` revision. The
    real game uses map headers -> map matrices -> land-data blocks. Each land
    block contains a 32x32 u16 terrain-attribute grid beginning at 0x10; bit
    0x8000 is the collision bit. Static warp events come from the matching map
    event archive.

    Renegade Platinum is based on Platinum and normally reuses field geometry,
    but successful/failed movement observed from the user's running game remains
    higher-authority evidence than this vanilla cache.
    """

    def __init__(
        self,
        root: str | Path = Path("data/world"),
        *,
        catalog: MapHeaderCatalog | None = None,
        timeout: float = 6.0,
    ) -> None:
        self.root = Path(root)
        self.timeout = max(1.0, float(timeout))
        self.catalog = catalog or MapHeaderCatalog()
        self.catalog.ensure(timeout=self.timeout)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "events").mkdir(exist_ok=True)
        (self.root / "land").mkdir(exist_ok=True)

        self._name_to_id = {
            name.removeprefix("MAP_HEADER_"): index
            for index, name in enumerate(self.catalog.names)
        }
        self._symbol_to_id = {
            name: index for index, name in enumerate(self.catalog.names)
        }
        self._header_metadata: dict[int, MapHeaderMetadata] = {}
        self._matrices: dict[int, dict[str, Any]] = {}
        self._header_cells: dict[int, list[MatrixCell]] = {}
        self._adjacency: dict[int, set[int]] = {}
        self._event_cache: dict[int, dict[str, Any]] = {}
        self._terrain_cache: dict[int, tuple[int, ...]] = {}

        self._load_header_metadata()
        self._load_index()

    @property
    def index_path(self) -> Path:
        return self.root / "matrix_index.json"

    @property
    def header_metadata_path(self) -> Path:
        return self.root / "map_header_metadata.json"

    def header_id(self, name: str) -> int | None:
        normalized = name.strip().upper().removeprefix("MAP_HEADER_")
        return self._name_to_id.get(normalized)

    def header_name(self, header_id: int) -> str:
        return self.catalog.name(header_id)

    def _fetch(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "RenegadeAI/0.7 progression-planner"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def _fetch_json(self, url: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._fetch(url).decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def _load_header_metadata(self) -> None:
        if not self.header_metadata_path.exists():
            return
        try:
            payload = json.loads(self.header_metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if payload.get("pokeplatinum_commit") != POKEPLATINUM_COMMIT:
            return
        entries = payload.get("headers", {})
        if not isinstance(entries, dict):
            return
        for raw_id, raw in entries.items():
            if not isinstance(raw, dict):
                continue
            try:
                header_id = int(raw_id)
                matrix_id = int(raw["matrix_id"])
            except (KeyError, TypeError, ValueError):
                continue
            events_name = raw.get("events_name")
            self._header_metadata[header_id] = MapHeaderMetadata(
                matrix_id=matrix_id,
                events_name=str(events_name) if events_name else None,
            )

    def _save_header_metadata(self) -> None:
        payload = {
            "version": 1,
            "pokeplatinum_commit": POKEPLATINUM_COMMIT,
            "headers": {
                str(header_id): asdict(metadata)
                for header_id, metadata in sorted(self._header_metadata.items())
            },
        }
        temporary = self.header_metadata_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.header_metadata_path)

    def ensure_header_metadata(self) -> bool:
        """Parse the decomp's authoritative map-header -> matrix/event table."""
        if self._header_metadata:
            return True
        url = f"{_RAW_ROOT}/include/data/map_headers.h"
        try:
            text = self._fetch(url).decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return False

        entry_re = re.compile(
            r"\[(MAP_HEADER_[A-Z0-9_]+)\]\s*=\s*\{(.*?)\n\s*\},",
            re.DOTALL,
        )
        matrix_re = re.compile(r"\.mapMatrixID\s*=\s*map_matrix_(\d+)")
        events_re = re.compile(r"\.eventsArchiveID\s*=\s*(events_[A-Za-z0-9_]+)")

        for symbol, body in entry_re.findall(text):
            header_id = self._symbol_to_id.get(symbol)
            matrix_match = matrix_re.search(body)
            if header_id is None or matrix_match is None:
                continue
            events_match = events_re.search(body)
            self._header_metadata[header_id] = MapHeaderMetadata(
                matrix_id=int(matrix_match.group(1)),
                events_name=events_match.group(1) if events_match else None,
            )

        if not self._header_metadata:
            return False
        try:
            self._save_header_metadata()
        except OSError:
            pass
        return True

    def _load_index(self) -> None:
        if not self.index_path.exists():
            return
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if payload.get("pokeplatinum_commit") != POKEPLATINUM_COMMIT:
            return
        matrices = payload.get("matrices", {})
        if isinstance(matrices, dict):
            self._matrices = {
                int(key): value
                for key, value in matrices.items()
                if isinstance(value, dict)
            }
        self._rebuild_indexes()

    def _save_index(self) -> None:
        payload = {
            "version": 2,
            "pokeplatinum_commit": POKEPLATINUM_COMMIT,
            "matrices": {str(key): value for key, value in sorted(self._matrices.items())},
        }
        temporary = self.index_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.index_path)

    def _matrix_url(self, matrix_id: int) -> str:
        return f"{_RAW_ROOT}/res/field/matrices/map_matrix_{matrix_id:03d}.json"

    def _download_matrix(self, matrix_id: int) -> tuple[int, dict[str, Any] | None]:
        return matrix_id, self._fetch_json(self._matrix_url(matrix_id))

    @staticmethod
    def _matrix_maps(matrix: dict[str, Any]) -> list[Any] | None:
        # The current pret JSON schema calls the land-data grid ``maps``.
        # ``land_data_maps`` is accepted only for old/generated caches.
        value = matrix.get("maps")
        if not isinstance(value, list):
            value = matrix.get("land_data_maps")
        return value if isinstance(value, list) else None

    def ensure_matrix_index(self) -> bool:
        """Build and cache the real map-header/matrix graph."""
        self.ensure_header_metadata()
        missing = [index for index in range(_MATRIX_COUNT) if index not in self._matrices]
        if missing:
            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = [pool.submit(self._download_matrix, index) for index in missing]
                for future in as_completed(futures):
                    try:
                        matrix_id, payload = future.result()
                    except Exception:  # noqa: BLE001 - public cache is best effort.
                        continue
                    if payload is not None and self._matrix_maps(payload) is not None:
                        self._matrices[matrix_id] = payload

        if self._matrices:
            self._rebuild_indexes()
            try:
                self._save_index()
            except OSError:
                pass
        return len(self._matrices) >= _MATRIX_COUNT

    def _header_value(self, raw: Any) -> int | None:
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            if raw in self._symbol_to_id:
                return self._symbol_to_id[raw]
            try:
                return int(raw, 0)
            except ValueError:
                return None
        return None

    @staticmethod
    def _land_value(raw: Any) -> int | None:
        if isinstance(raw, int):
            return raw
        if not isinstance(raw, str):
            return None
        match = re.fullmatch(r"(?:MAP|map_data)_(\d+)(?:\.bin)?", raw)
        if match is not None:
            return int(match.group(1))
        try:
            return int(raw, 0)
        except ValueError:
            return None

    def _append_cell(self, header_id: int, cell: MatrixCell) -> None:
        if header_id in _INVALID_HEADERS:
            return
        values = self._header_cells.setdefault(header_id, [])
        if cell not in values:
            values.append(cell)

    def _rebuild_indexes(self) -> None:
        self._header_cells.clear()
        self._adjacency.clear()

        headers_by_matrix: dict[int, list[int]] = {}
        for header_id, metadata in self._header_metadata.items():
            if header_id not in _INVALID_HEADERS:
                headers_by_matrix.setdefault(metadata.matrix_id, []).append(header_id)

        for matrix_id, matrix in self._matrices.items():
            land = self._matrix_maps(matrix)
            if not isinstance(land, list):
                continue
            headers = matrix.get("headers")
            has_headers = isinstance(headers, list) and bool(headers)

            # Matrices with a header section (notably the Sinnoh main matrix)
            # identify the active map header per 32x32 block directly.
            if has_headers:
                for row, header_row in enumerate(headers):
                    if not isinstance(header_row, list):
                        continue
                    for col, raw_header in enumerate(header_row):
                        header_id = self._header_value(raw_header)
                        if header_id is None or header_id in _INVALID_HEADERS:
                            continue
                        try:
                            raw_land = land[row][col]
                        except (IndexError, TypeError):
                            continue
                        land_id = self._land_value(raw_land)
                        if land_id is None:
                            continue
                        self._append_cell(header_id, MatrixCell(matrix_id, row, col, land_id))

                        for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                            rr, cc = row + dr, col + dc
                            if rr < 0 or cc < 0 or rr >= len(headers):
                                continue
                            neighbor_row = headers[rr]
                            if not isinstance(neighbor_row, list) or cc >= len(neighbor_row):
                                continue
                            neighbor = self._header_value(neighbor_row[cc])
                            if (
                                neighbor is None
                                or neighbor in _INVALID_HEADERS
                                or neighbor == header_id
                            ):
                                continue
                            self._adjacency.setdefault(header_id, set()).add(neighbor)
                continue

            # Interior/cave matrices often omit a header-ID section. The game
            # substitutes the current map header for those matrix cells. The
            # authoritative map-header table tells us which headers use this
            # matrix, so assign the same geometry to each such header.
            users = headers_by_matrix.get(matrix_id, ())
            for row, land_row in enumerate(land):
                if not isinstance(land_row, list):
                    continue
                for col, raw_land in enumerate(land_row):
                    land_id = self._land_value(raw_land)
                    if land_id is None:
                        continue
                    cell = MatrixCell(matrix_id, row, col, land_id)
                    for header_id in users:
                        self._append_cell(header_id, cell)

    def matrix_cell_for(self, header_id: int, x: int, z: int) -> MatrixCell | None:
        if header_id not in self._header_cells:
            self.ensure_matrix_index()
        candidates = self._header_cells.get(header_id, ())
        row, col = z // _TILES_PER_BLOCK, x // _TILES_PER_BLOCK
        for cell in candidates:
            if cell.row == row and cell.col == col:
                return cell
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _land_path(self, land_id: int) -> Path:
        return self.root / "land" / f"map_data_{land_id:03d}.bin"

    def _terrain(self, land_id: int) -> tuple[int, ...] | None:
        if land_id in self._terrain_cache:
            return self._terrain_cache[land_id]
        path = self._land_path(land_id)
        if not path.exists():
            url = f"{_RAW_ROOT}/res/field/maps/data/map_data_{land_id:03d}.bin"
            try:
                data = self._fetch(url)
            except OSError:
                return None
            try:
                path.write_bytes(data)
            except OSError:
                pass
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if len(data) < _TERRAIN_OFFSET + _TERRAIN_SIZE:
            return None
        terrain_size = struct.unpack_from("<I", data, 0)[0]
        if terrain_size != _TERRAIN_SIZE:
            return None
        values = struct.unpack_from("<1024H", data, _TERRAIN_OFFSET)
        self._terrain_cache[land_id] = values
        return values

    def tile_attributes(self, header_id: int, x: int, z: int) -> int | None:
        cell = self.matrix_cell_for(header_id, x, z)
        if cell is None:
            return None
        terrain = self._terrain(cell.land_data_id)
        if terrain is None:
            return None
        local_x, local_z = x % _TILES_PER_BLOCK, z % _TILES_PER_BLOCK
        return terrain[local_z * _TILES_PER_BLOCK + local_x]

    def is_colliding(self, header_id: int, x: int, z: int) -> bool | None:
        attributes = self.tile_attributes(header_id, x, z)
        return None if attributes is None else bool(attributes & _COLLISION_MASK)

    def tile_behavior(self, header_id: int, x: int, z: int) -> int | None:
        attributes = self.tile_attributes(header_id, x, z)
        return None if attributes is None else attributes & 0xFF

    def _event_name(self, header_id: int) -> str:
        if not self._header_metadata:
            self.ensure_header_metadata()
        metadata = self._header_metadata.get(header_id)
        if metadata is not None and metadata.events_name:
            return metadata.events_name
        return f"events_{self.header_name(header_id).lower()}"

    def _event_path(self, event_name: str) -> Path:
        return self.root / "events" / f"{event_name}.json"

    def events(self, header_id: int) -> dict[str, Any]:
        if header_id in self._event_cache:
            return self._event_cache[header_id]
        event_name = self._event_name(header_id)
        path = self._event_path(event_name)
        payload: dict[str, Any] | None = None
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = raw if isinstance(raw, dict) else None
            except (OSError, ValueError):
                payload = None
        if payload is None:
            url = f"{_RAW_ROOT}/res/field/events/{event_name}.json"
            payload = self._fetch_json(url)
            if payload is not None:
                try:
                    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                except OSError:
                    pass
        result = payload or {}
        self._event_cache[header_id] = result
        return result

    def warps(self, header_id: int) -> tuple[WarpPortal, ...]:
        result: list[WarpPortal] = []
        for raw in self.events(header_id).get("warp_events", ()):
            if not isinstance(raw, dict):
                continue
            destination = self._header_value(raw.get("dest_header_id"))
            if destination is None:
                continue
            try:
                result.append(
                    WarpPortal(
                        source_header_id=header_id,
                        destination_header_id=destination,
                        source=GridPoint(int(raw["x"]), int(raw["z"])),
                        destination_warp_id=int(raw.get("dest_warp_id", -1)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(result)

    def coord_events(self, header_id: int) -> tuple[dict[str, Any], ...]:
        return tuple(
            value
            for value in self.events(header_id).get("coord_events", ())
            if isinstance(value, dict)
        )

    def map_neighbors(self, header_id: int) -> set[int]:
        if header_id not in self._adjacency and not self._matrices:
            self.ensure_matrix_index()
        neighbors = set(self._adjacency.get(header_id, set()))
        neighbors.update(warp.destination_header_id for warp in self.warps(header_id))
        return neighbors

    def map_route(
        self,
        start_header_id: int,
        goal_header_ids: set[int],
        *,
        max_maps: int = 220,
    ) -> list[int] | None:
        if start_header_id in goal_header_ids:
            return [start_header_id]
        if not self._matrices:
            self.ensure_matrix_index()
        queue: deque[int] = deque([start_header_id])
        parent: dict[int, int | None] = {start_header_id: None}
        while queue and len(parent) <= max_maps:
            current = queue.popleft()
            for nxt in sorted(self.map_neighbors(current)):
                if nxt in parent or nxt in _INVALID_HEADERS:
                    continue
                parent[nxt] = current
                if nxt in goal_header_ids:
                    path = [nxt]
                    while path[-1] != start_header_id:
                        previous = parent[path[-1]]
                        if previous is None:
                            break
                        path.append(previous)
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def _boundary_portals(self, source_id: int, destination_id: int) -> list[BoundaryPortal]:
        portals: list[BoundaryPortal] = []
        source_cells = self._header_cells.get(source_id, ())
        destination_cells = {
            (cell.matrix_id, cell.row, cell.col): cell
            for cell in self._header_cells.get(destination_id, ())
        }
        for source_cell in source_cells:
            for dr, dc in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                destination_cell = destination_cells.get(
                    (source_cell.matrix_id, source_cell.row + dr, source_cell.col + dc)
                )
                if destination_cell is None:
                    continue
                for offset in range(_TILES_PER_BLOCK):
                    if dr == -1:
                        src = GridPoint(source_cell.col * 32 + offset, source_cell.row * 32)
                        dst = GridPoint(src.x, src.z - 1)
                    elif dr == 1:
                        src = GridPoint(source_cell.col * 32 + offset, source_cell.row * 32 + 31)
                        dst = GridPoint(src.x, src.z + 1)
                    elif dc == -1:
                        src = GridPoint(source_cell.col * 32, source_cell.row * 32 + offset)
                        dst = GridPoint(src.x - 1, src.z)
                    else:
                        src = GridPoint(source_cell.col * 32 + 31, source_cell.row * 32 + offset)
                        dst = GridPoint(src.x + 1, src.z)
                    source_collision = self.is_colliding(source_id, src.x, src.z)
                    dest_collision = self.is_colliding(destination_id, dst.x, dst.z)
                    if source_collision is False and dest_collision is False:
                        portals.append(BoundaryPortal(source_id, destination_id, src, dst))
        return portals

    def portals_between(
        self,
        source_header_id: int,
        destination_header_id: int,
    ) -> tuple[WarpPortal | BoundaryPortal, ...]:
        event_portals = [
            warp
            for warp in self.warps(source_header_id)
            if warp.destination_header_id == destination_header_id
        ]
        if event_portals:
            return tuple(event_portals)
        if not self._matrices:
            self.ensure_matrix_index()
        return tuple(self._boundary_portals(source_header_id, destination_header_id))

    def nearest_portal(
        self,
        source_header_id: int,
        destination_header_id: int,
        current: GridPoint,
    ) -> WarpPortal | BoundaryPortal | None:
        portals = self.portals_between(source_header_id, destination_header_id)
        if not portals:
            return None
        return min(portals, key=lambda portal: current.manhattan(portal.source))

    def warm_current_map(self, header_id: int, x: int, z: int) -> None:
        """Best-effort prefetch of current collision block and event archive."""
        self.ensure_matrix_index()
        cell = self.matrix_cell_for(header_id, x, z)
        if cell is not None:
            self._terrain(cell.land_data_id)
        self.events(header_id)

    def stats(self) -> dict[str, int]:
        return {
            "header_metadata": len(self._header_metadata),
            "matrices": len(self._matrices),
            "headers_indexed": len(self._header_cells),
            "map_edges": sum(len(value) for value in self._adjacency.values()),
            "events_cached": len(self._event_cache),
            "terrain_blocks_cached": len(self._terrain_cache),
        }

    @staticmethod
    def portal_dict(portal: WarpPortal | BoundaryPortal | None) -> dict[str, Any] | None:
        return None if portal is None else asdict(portal)
