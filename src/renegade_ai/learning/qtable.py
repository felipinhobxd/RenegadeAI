from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class QTable:
    alpha: float = 0.20
    gamma: float = 0.95
    epsilon: float = 0.10
    values: dict[str, dict[str, float]] = field(default_factory=dict)

    def q(self, state: str, action: str) -> float:
        return self.values.get(state, {}).get(action, 0.0)

    def select(
        self,
        state: str,
        actions: Iterable[str],
        base_scores: Mapping[str, float] | None = None,
    ) -> str:
        candidates = list(actions)
        if not candidates:
            raise ValueError("At least one action is required")
        if random.random() < self.epsilon:
            return random.choice(candidates)

        base_scores = base_scores or {}
        return max(candidates, key=lambda action: base_scores.get(action, 0.0) + self.q(state, action))

    def update(
        self,
        state: str,
        action: str,
        reward: float,
        next_state: str | None,
        next_actions: Iterable[str] = (),
    ) -> float:
        current = self.q(state, action)
        future = 0.0
        if next_state is not None:
            next_values = [self.q(next_state, candidate) for candidate in next_actions]
            if next_values:
                future = max(next_values)
        target = reward + self.gamma * future
        updated = current + self.alpha * (target - current)
        self.values.setdefault(state, {})[action] = updated
        return updated

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "alpha": self.alpha,
            "gamma": self.gamma,
            "epsilon": self.epsilon,
            "values": self.values,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, **defaults: float) -> QTable:
        path = Path(path)
        if not path.exists():
            return cls(**defaults)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            alpha=float(payload.get("alpha", defaults.get("alpha", 0.20))),
            gamma=float(payload.get("gamma", defaults.get("gamma", 0.95))),
            epsilon=float(payload.get("epsilon", defaults.get("epsilon", 0.10))),
            values={
                str(state): {str(action): float(value) for action, value in action_values.items()}
                for state, action_values in payload.get("values", {}).items()
            },
        )
