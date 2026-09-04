from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from renegade_ai.actions import DSButton
from renegade_ai.memory.platinum import StructuredLocation

_DIRECTIONS = (DSButton.UP, DSButton.RIGHT, DSButton.DOWN, DSButton.LEFT)
_OPPOSITE = {
    DSButton.UP: DSButton.DOWN,
    DSButton.DOWN: DSButton.UP,
    DSButton.LEFT: DSButton.RIGHT,
    DSButton.RIGHT: DSButton.LEFT,
}
_DELTAS = {
    DSButton.UP: (0, -1),
    DSButton.DOWN: (0, 1),
    DSButton.LEFT: (-1, 0),
    DSButton.RIGHT: (1, 0),
}


@dataclass(slots=True)
class GridNode:
    visits: int = 0
    attempts: dict[str, int] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)


class StructuredGridNavigator:
    """Exact-coordinate frontier explorer backed by read-only game state.

    The original implementation always tried UP, RIGHT, DOWN, LEFT on every
    unseen tile. That produced a strong global directional bias. This version
    balances directions across each map, records safe reverse edges for normal
    one-tile movement, and routes through the known graph to the nearest real
    unexplored frontier before retrying walls.
    """

    def __init__(self, path: str | Path = Path("data/structured_map.json")) -> None:
        self.path = Path(path)
        self.nodes: dict[str, GridNode] = {}
        self.maps_seen: dict[str, str] = {}
        self.transitions = 0
        self._load()

    @staticmethod
    def key(location: StructuredLocation) -> str:
        return location.key

    @staticmethod
    def _parts(key: str) -> tuple[int, int, int] | None:
        try:
            map_id, x, z = (int(value) for value in key.split(":", 2))
        except (TypeError, ValueError):
            return None
        return map_id, x, z

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.maps_seen = {
            str(key): str(value) for key, value in dict(payload.get("maps_seen", {})).items()
        }
        self.transitions = int(payload.get("transitions", 0))
        raw_nodes = payload.get("nodes", {})
        if not isinstance(raw_nodes, dict):
            return
        for key, value in raw_nodes.items():
            if not isinstance(value, dict):
                continue
            allowed = GridNode.__dataclass_fields__
            data = {name: item for name, item in value.items() if name in allowed}
            try:
                self.nodes[str(key)] = GridNode(**data)
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "maps_seen": self.maps_seen,
            "transitions": self.transitions,
            "nodes": {key: asdict(node) for key, node in self.nodes.items()},
        }
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def observe(self, location: StructuredLocation) -> tuple[str, bool]:
        key = self.key(location)
        node = self.nodes.setdefault(key, GridNode())
        node.visits += 1
        map_key = str(location.map_header_id)
        is_new_map = map_key not in self.maps_seen
        self.maps_seen[map_key] = location.map_name
        return key, is_new_map

    def _map_direction_totals(self, key: str) -> dict[str, int]:
        parts = self._parts(key)
        map_id = parts[0] if parts is not None else None
        totals = {action.value: 0 for action in _DIRECTIONS}
        for node_key, node in self.nodes.items():
            node_parts = self._parts(node_key)
            if map_id is not None and (node_parts is None or node_parts[0] != map_id):
                continue
            for action in _DIRECTIONS:
                totals[action.value] += node.attempts.get(action.value, 0)
        return totals

    def _rotation_rank(self, key: str, action: DSButton) -> int:
        parts = self._parts(key)
        if parts is None:
            return _DIRECTIONS.index(action)
        map_id, x, z = parts
        rotation = (map_id * 3 + x * 5 + z * 7) % len(_DIRECTIONS)
        index = _DIRECTIONS.index(action)
        return (index - rotation) % len(_DIRECTIONS)

    def _target_key(self, key: str, action: DSButton) -> str | None:
        parts = self._parts(key)
        if parts is None:
            return None
        map_id, x, z = parts
        dx, dz = _DELTAS[action]
        return f"{map_id}:{x + dx}:{z + dz}"

    def _candidate_score(self, key: str, action: DSButton) -> tuple[int, int, int, int]:
        node = self.nodes.setdefault(key, GridNode())
        totals = self._map_direction_totals(key)
        target_key = self._target_key(key, action)
        target = self.nodes.get(target_key) if target_key is not None else None
        # Unknown target tiles come first, then low-visit known tiles. Global
        # direction usage removes the old UP/RIGHT bias on long open stretches.
        known_penalty = 0 if target is None else 1
        target_visits = 0 if target is None else target.visits
        return (
            known_penalty,
            totals.get(action.value, 0),
            target_visits + node.attempts.get(action.value, 0),
            self._rotation_rank(key, action),
        )

    def _untried(self, key: str) -> list[DSButton]:
        node = self.nodes.setdefault(key, GridNode())
        blocked = set(node.blocked)
        return [
            action
            for action in _DIRECTIONS
            if action.value not in node.attempts
            and action.value not in node.edges
            and action.value not in blocked
        ]

    def _known_edges(self, key: str) -> list[tuple[DSButton, str]]:
        node = self.nodes.get(key)
        if node is None:
            return []
        result: list[tuple[DSButton, str]] = []
        for raw_action, destination in node.edges.items():
            if raw_action in node.blocked:
                continue
            try:
                action = DSButton.parse(raw_action)
            except ValueError:
                continue
            if action in _DIRECTIONS:
                result.append((action, destination))
        return result

    def choose(self, key: str) -> DSButton:
        """Choose a balanced local frontier or route to the nearest one."""
        direct = self._untried(key)
        if direct:
            return min(direct, key=lambda action: self._candidate_score(key, action))

        # Route over already verified edges toward the nearest node that still
        # has unexplored directions. Sorting neighbors by visit count makes the
        # route prefer less-travelled branches when several frontiers tie.
        queue: deque[tuple[str, DSButton | None]] = deque([(key, None)])
        seen = {key}
        while queue:
            current, first = queue.popleft()
            if current != key and self._untried(current) and first is not None:
                return first
            edges = self._known_edges(current)
            edges.sort(key=lambda item: self.nodes.get(item[1], GridNode()).visits)
            for action, destination in edges:
                if destination in seen:
                    continue
                seen.add(destination)
                queue.append((destination, first or action))

        # The known component has no frontier. Prefer a verified edge to a
        # low-visit tile so the agent backtracks instead of hammering a wall.
        known = self._known_edges(key)
        if known:
            action, _destination = min(
                known,
                key=lambda item: (
                    self.nodes.get(item[1], GridNode()).visits,
                    self.nodes[key].attempts.get(item[0].value, 0),
                    self._rotation_rank(key, item[0]),
                ),
            )
            return action

        node = self.nodes.setdefault(key, GridNode())
        candidates = [action for action in _DIRECTIONS if action.value not in set(node.blocked)]
        if not candidates:
            candidates = list(_DIRECTIONS)
        return min(candidates, key=lambda action: self._candidate_score(key, action))

    def choose_escape(self, key: str) -> DSButton:
        """Prefer a verified way out of a repeatedly stuck coordinate."""
        known = self._known_edges(key)
        if known:
            action, _destination = min(
                known,
                key=lambda item: (
                    self.nodes.get(item[1], GridNode()).visits,
                    self.nodes[key].attempts.get(item[0].value, 0),
                ),
            )
            return action
        return self.choose(key)

    def record_transition(
        self,
        before: StructuredLocation,
        action: DSButton,
        after: StructuredLocation,
        *,
        transient_block: bool = False,
    ) -> bool:
        source = self.key(before)
        destination = self.key(after)
        node = self.nodes.setdefault(source, GridNode())
        node.attempts[action.value] = node.attempts.get(action.value, 0) + 1
        moved = destination != source
        if moved:
            node.edges[action.value] = destination
            if action.value in node.blocked:
                node.blocked.remove(action.value)
            destination_node = self.nodes.setdefault(destination, GridNode())

            # A normal one-tile movement on the same map gives us a reliable
            # reverse edge for backtracking. Map transitions and jumps are not
            # assumed reversible.
            if (
                before.map_header_id == after.map_header_id
                and abs(before.x - after.x) + abs(before.z - after.z) == 1
            ):
                reverse = _OPPOSITE[action]
                destination_node.edges.setdefault(reverse.value, source)
        else:
            node.edges.pop(action.value, None)
            if transient_block:
                if action.value in node.blocked:
                    node.blocked.remove(action.value)
            elif action.value not in node.blocked:
                node.blocked.append(action.value)

        self.maps_seen[str(after.map_header_id)] = after.map_name
        self.transitions += 1
        self.save()
        return moved

    def stats(self) -> dict[str, int]:
        return {
            "maps": len(self.maps_seen),
            "tiles": len(self.nodes),
            "edges": sum(len(node.edges) for node in self.nodes.values()),
            "blocked": sum(len(node.blocked) for node in self.nodes.values()),
            "transitions": self.transitions,
        }
