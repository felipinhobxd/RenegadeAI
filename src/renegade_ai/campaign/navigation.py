from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from renegade_ai.actions import DSButton

_DIRECTION_ORDER = (
    DSButton.UP,
    DSButton.RIGHT,
    DSButton.DOWN,
    DSButton.LEFT,
)


@dataclass(slots=True)
class VisualNode:
    visits: int = 0
    attempts: dict[str, int] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    semantic_labels: list[str] = field(default_factory=list)


class VisualTopoNavigator:
    """Persistent pixel-only exploration graph for the overworld.

    This remains the fallback when structured RAM is unavailable. Direction
    choice is balanced globally so entering a new visual state no longer means
    blindly trying UP and then RIGHT every time.
    """

    def __init__(self, path: str | Path = Path("data/campaign_map.json")) -> None:
        self.path = Path(path)
        self.nodes: dict[str, VisualNode] = {}
        self.total_steps = 0
        self._load()

    @staticmethod
    def fingerprint(image: Any) -> str:
        import numpy as np

        rgb = np.asarray(image)[..., :3]
        if rgb.size == 0:
            return "empty"
        height, width = rgb.shape[:2]
        step_y = max(1, height // 24)
        step_x = max(1, width // 32)
        sample = rgb[::step_y, ::step_x][:24, :32]
        quantized = (sample // 24).astype("uint8")
        return hashlib.blake2b(quantized.tobytes(), digest_size=10).hexdigest()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.total_steps = int(payload.get("total_steps", 0))
        raw_nodes = payload.get("nodes", {})
        if not isinstance(raw_nodes, dict):
            return
        for key, value in raw_nodes.items():
            if not isinstance(value, dict):
                continue
            allowed = {name for name in VisualNode.__dataclass_fields__}
            data = {name: item for name, item in value.items() if name in allowed}
            try:
                self.nodes[str(key)] = VisualNode(**data)
            except TypeError:
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "total_steps": self.total_steps,
            "nodes": {key: asdict(node) for key, node in self.nodes.items()},
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def observe(self, image: Any, *, semantic_label: str | None = None) -> str:
        key = self.fingerprint(image)
        node = self.nodes.setdefault(key, VisualNode())
        node.visits += 1
        if semantic_label and semantic_label not in node.semantic_labels:
            node.semantic_labels.append(semantic_label)
            node.semantic_labels = node.semantic_labels[-12:]
        return key

    @staticmethod
    def _action_name(action: DSButton | str) -> str:
        return action.value if isinstance(action, DSButton) else str(action)

    def record_transition(
        self,
        state_key: str,
        action: DSButton | str,
        next_key: str,
    ) -> None:
        node = self.nodes.setdefault(state_key, VisualNode())
        action_name = self._action_name(action)
        node.attempts[action_name] = node.attempts.get(action_name, 0) + 1
        self.total_steps += 1

        if next_key == state_key:
            node.edges.pop(action_name, None)
            if action_name not in node.blocked:
                node.blocked.append(action_name)
        else:
            node.edges[action_name] = next_key
            if action_name in node.blocked:
                node.blocked.remove(action_name)
            self.nodes.setdefault(next_key, VisualNode())
        self.save()

    def _direction_totals(self) -> dict[str, int]:
        totals = {action.value: 0 for action in _DIRECTION_ORDER}
        for node in self.nodes.values():
            for action in _DIRECTION_ORDER:
                totals[action.value] += node.attempts.get(action.value, 0)
        return totals

    @staticmethod
    def _rotation_rank(key: str, action: DSButton) -> int:
        try:
            rotation = int(key[:8], 16) % len(_DIRECTION_ORDER)
        except ValueError:
            rotation = 0
        index = _DIRECTION_ORDER.index(action)
        return (index - rotation) % len(_DIRECTION_ORDER)

    def _untried(self, key: str) -> list[DSButton]:
        node = self.nodes.setdefault(key, VisualNode())
        blocked = set(node.blocked)
        return [
            action
            for action in _DIRECTION_ORDER
            if action.value not in node.attempts
            and action.value not in node.edges
            and action.value not in blocked
        ]

    def _least_tried(self, key: str) -> DSButton:
        node = self.nodes.setdefault(key, VisualNode())
        candidates = [action for action in _DIRECTION_ORDER if action.value not in node.blocked]
        if not candidates:
            candidates = list(_DIRECTION_ORDER)
        totals = self._direction_totals()
        return min(
            candidates,
            key=lambda action: (
                totals[action.value],
                node.attempts.get(action.value, 0),
                self._rotation_rank(key, action),
            ),
        )

    def choose(self, state_key: str) -> DSButton:
        """Choose the next movement toward the nearest unexplored frontier."""
        direct = self._untried(state_key)
        if direct:
            totals = self._direction_totals()
            return min(
                direct,
                key=lambda action: (
                    totals[action.value],
                    self._rotation_rank(state_key, action),
                ),
            )

        queue: deque[tuple[str, DSButton | None]] = deque([(state_key, None)])
        seen = {state_key}
        while queue:
            key, first_action = queue.popleft()
            if key != state_key and self._untried(key) and first_action is not None:
                return first_action
            node = self.nodes.get(key)
            if node is None:
                continue
            edges: list[tuple[DSButton, str]] = []
            for raw_action, next_key in node.edges.items():
                if raw_action in node.blocked or next_key in seen:
                    continue
                try:
                    action = DSButton.parse(raw_action)
                except ValueError:
                    continue
                if action in _DIRECTION_ORDER:
                    edges.append((action, next_key))
            edges.sort(key=lambda item: self.nodes.get(item[1], VisualNode()).visits)
            for action, next_key in edges:
                seen.add(next_key)
                queue.append((next_key, first_action or action))

        return self._least_tried(state_key)

    def stats(self) -> dict[str, int]:
        blocked = sum(len(node.blocked) for node in self.nodes.values())
        edges = sum(len(node.edges) for node in self.nodes.values())
        return {
            "visual_states": len(self.nodes),
            "edges": edges,
            "blocked_edges": blocked,
            "steps": self.total_steps,
        }
