from __future__ import annotations

import json
import struct
import urllib.error
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
    """Static Platinum topology/collision with live-save overrides layered above it.

    Static data comes from a pinned ``pret/pokeplatinum`` revision. Renegade
    Platinum is based on Platinum and largely reuses the field geometry, but the
    agent always treats successful/failed live movement as higher-authority
    evidence than this cache. This avoids turning a vanilla-data mismatch into a
    permanent autonomous-play deadlock.
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
        self._matrices: dict[int, dict[str, Any]] = {}
        self._header_cells: dict[int, list[MatrixCell]] = {}
        self._adjacency: dict[int, set[int]] = {}
        self._event_cache: dict[int, dict[str, Any]] = {}
        self._terrain_cache: dict[int, tuple[int, ...]] = {}
        self._load_index()

    @property
    def index_path(self) -> Path:
        return self.root / "matrix_index.json"

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
            "version": 1,
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

    def ensure_matrix_index(self) -> bool:
        """Build the map-header/matrix graph once and cache it locally."""
        if len(self._matrices) >= _MATRIX_COUNT:
            return True
        missing = [index for index in range(_MATRIX_COUNT) if index not in self._matrices]
        if not missing:
            return True
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(self._download_matrix, index) for index in missing]
            for future in as_completed(futures):
                try:
                    matrix_id, payload = future.result()
                except Exception:  # noqa: BLE001, S112 - public cache is best effort.
                    continue
                if payload is not None and "land_data_maps" in payload:
                    self._matrices[matrix_id] = payload
        if self._matrices:
            self._rebuild_indexes()
            self._save_index()
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

    def _rebuild_indexes(self) -> None:
        self._header_cells.clear()
        self._adjacency.clear()
        for matrix_id, matrix in self._matrices.items():
            headers = matrix.get("headers")
            land = matrix.get("land_data_maps")
            if not isinstance(headers, list) or not isinstance(land, list):
                continue
            for row, header_row in enumerate(headers):
                if not isinstance(header_row, list):
                    continue
                for col, raw_header in enumerate(header_row):
                    header_id = self._header_value(raw_header)
                    if header_id is None or header_id in _INVALID_HEADERS:
                        continue
                    try:
                        land_id = int(land[row][col])
                    except (IndexError, TypeError, ValueError):
                        continue
                    cell = MatrixCell(matrix_id, row, col, land_id)
                    self._header_cells.setdefault(header_id, []).append(cell)
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
        return self.root / "land" / f"map_{land_id:03d}.bin"

    def _terrain(self, land_id: int) -> tuple[int, ...] | None:
        if land_id in self._terrain_cache:
            return self._terrain_cache[land_id]
        path = self._land_path(land_id)
        if not path.exists():
            url = f"{_RAW_ROOT}/res/field/maps/data/map_{land_id:03d}.bin"
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

    def _event_path(self, map_name: str) -> Path:
        return self.root / "events" / f"events_{map_name.lower()}.json"

    def events(self, header_id: int) -> dict[str, Any]:
        if header_id in self._event_cache:
            return self._event_cache[header_id]
        map_name = self.header_name(header_id)
        path = self._event_path(map_name)
        payload: dict[str, Any] | None = None
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = raw if isinstance(raw, dict) else None
            except (OSError, ValueError):
                payload = None
        if payload is None:
            url = f"{_RAW_ROOT}/res/field/events/events_{map_name.lower()}.json"
            try:
                payload = self._fetch_json(url)
            except urllib.error.HTTPError:
                payload = None
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

    def stats(self) -> dict[str, int]:
        return {
            "matrices": len(self._matrices),
            "headers_indexed": len(self._header_cells),
            "map_edges": sum(len(value) for value in self._adjacency.values()),
            "events_cached": len(self._event_cache),
            "terrain_blocks_cached": len(self._terrain_cache),
        }

    @staticmethod
    def portal_dict(portal: WarpPortal | BoundaryPortal | None) -> dict[str, Any] | None:
        return None if portal is None else asdict(portal)
