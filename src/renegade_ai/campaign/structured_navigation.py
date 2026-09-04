from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from renegade_ai.actions import DSButton
from renegade_ai.memory.platinum import StructuredLocation

_DIRECTIONS = (DSButton.UP, DSButton.RIGHT, DSButton.DOWN, DSButton.LEFT)


@dataclass(slots=True)
class GridNode:
    visits: int = 0
    attempts: dict[str, int] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)


class StructuredGridNavigator:
    """Exact-coordinate exploration graph backed by read-only game state."""

    def __init__(self, path: str | Path = Path("data/structured_map.json")) -> None:
        self.path = Path(path)
        self.nodes: dict[str, GridNode] = {}
        self.maps_seen: dict[str, str] = {}
        self.transitions = 0
        self._load()

    @staticmethod
    def key(location: StructuredLocation) -> str:
        return location.key

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
            "version": 1,
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

    def _untried(self, key: str) -> list[DSButton]:
        node = self.nodes.setdefault(key, GridNode())
        blocked = set(node.blocked)
        return [
            action
            for action in _DIRECTIONS
            if action.value not in node.attempts and action.value not in blocked
        ]

    def choose(self, key: str) -> DSButton:
        direct = self._untried(key)
        if direct:
            return direct[0]

        queue: deque[tuple[str, DSButton | None]] = deque([(key, None)])
        seen = {key}
        while queue:
            current, first = queue.popleft()
            if current != key and self._untried(current) and first is not None:
                return first
            node = self.nodes.get(current)
            if node is None:
                continue
            for raw_action, destination in node.edges.items():
                if destination in seen:
                    continue
                try:
                    action = DSButton.parse(raw_action)
                except ValueError:
                    continue
                if action not in _DIRECTIONS:
                    continue
                seen.add(destination)
                queue.append((destination, first or action))

        node = self.nodes.setdefault(key, GridNode())
        candidates = [action for action in _DIRECTIONS if action.value not in set(node.blocked)]
        if not candidates:
            candidates = list(_DIRECTIONS)
        return min(
            candidates,
            key=lambda action: (node.attempts.get(action.value, 0), _DIRECTIONS.index(action)),
        )

    def record_transition(
        self,
        before: StructuredLocation,
        action: DSButton,
        after: StructuredLocation,
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
            self.nodes.setdefault(destination, GridNode())
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
