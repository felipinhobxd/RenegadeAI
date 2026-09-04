from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from renegade_ai.learning.qtable import QTable


class RewardKind(StrEnum):
    DAMAGE_DEALT = "damage_dealt"
    DAMAGE_TAKEN = "damage_taken"
    OPPONENT_KO = "opponent_ko"
    OWN_FAINT = "own_faint"
    STATUS_INFLICTED = "status_inflicted"
    STATUS_RECEIVED = "status_received"
    GOOD_TURN = "good_turn"
    BAD_TURN = "bad_turn"
    BATTLE_WIN = "battle_win"
    BATTLE_LOSS = "battle_loss"
    CAPTURE_SUCCESS = "capture_success"
    LEVEL_UP = "level_up"
    EVOLUTION = "evolution"
    NEW_SPECIES = "new_species"
    GOOD_SWITCH = "good_switch"
    EFFICIENT_HEAL = "efficient_heal"
    WASTED_ITEM = "wasted_item"
    OBJECTIVE_PROGRESS = "objective_progress"
    TRAINER_WIN = "trainer_win"
    BOSS_WIN = "boss_win"
    BADGE = "badge"
    GAME_COMPLETE = "game_complete"


@dataclass(frozen=True, slots=True)
class RewardWeights:
    damage_dealt: float = 120.0
    damage_taken: float = -90.0
    opponent_ko: float = 35.0
    own_faint: float = -70.0
    status_inflicted: float = 12.0
    status_received: float = -15.0
    good_turn: float = 35.0
    bad_turn: float = -35.0
    battle_win: float = 100.0
    battle_loss: float = -120.0
    capture_success: float = 45.0
    level_up: float = 20.0
    evolution: float = 70.0
    new_species: float = 35.0
    good_switch: float = 18.0
    efficient_heal: float = 15.0
    wasted_item: float = -25.0
    objective_progress: float = 80.0
    trainer_win: float = 140.0
    boss_win: float = 400.0
    badge: float = 600.0
    game_complete: float = 5000.0

    def value_for(self, kind: RewardKind) -> float:
        return float(getattr(self, kind.value))


@dataclass(frozen=True, slots=True)
class RewardEvent:
    kind: RewardKind
    reward: float
    magnitude: float
    state_key: str | None = None
    action_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass(slots=True)
class EvolveState:
    version: int = 1
    generation: int = 1
    lifetime_reward: float = 0.0
    reward_events: int = 0
    positive_events: int = 0
    negative_events: int = 0
    battle_wins: int = 0
    battle_losses: int = 0
    trainer_wins: int = 0
    boss_wins: int = 0
    captures: int = 0
    badges: int = 0
    game_completions: int = 0
    best_episode_reward: float = 0.0
    action_visits: dict[str, int] = field(default_factory=dict)
    seen_tokens: list[str] = field(default_factory=list)

    @property
    def fitness(self) -> float:
        if self.reward_events <= 0:
            return 0.0
        average = self.lifetime_reward / self.reward_events
        win_bonus = self.battle_wins * 0.5 + self.boss_wins * 8.0 + self.badges * 15.0
        return average + win_bonus


_DEFAULT_STATE_PATH = Path("data/evolve_state.json")
_DEFAULT_QTABLE_PATH = Path("data/evolve_qtable.json")
_DEFAULT_LEDGER_PATH = Path("data/evolve_rewards.jsonl")


class ASIEvolveEngine:
    """Hierarchical reward engine for the project's self-improving policy.

    "ASI-Evolve" is the project mode name. The implementation is deliberately
    bounded reinforcement learning rather than unrestricted self-modification:
    deterministic Pokemon mechanics remain the primary decision signal while
    learned outcomes provide a confidence-weighted correction.
    """

    def __init__(
        self,
        *,
        state_path: str | Path = _DEFAULT_STATE_PATH,
        qtable_path: str | Path = _DEFAULT_QTABLE_PATH,
        ledger_path: str | Path = _DEFAULT_LEDGER_PATH,
        weights: RewardWeights | None = None,
        alpha: float = 0.18,
    ) -> None:
        self.state_path = Path(state_path)
        self.qtable_path = Path(qtable_path)
        self.ledger_path = Path(ledger_path)
        self.weights = weights or RewardWeights()
        self.state = self._load_state()
        self.qtable = QTable.load(self.qtable_path, alpha=alpha, gamma=0.0, epsilon=0.0)
        self.qtable.gamma = 0.0
        self.qtable.epsilon = 0.0

    def _load_state(self) -> EvolveState:
        if not self.state_path.exists():
            return EvolveState()
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        valid = {name for name in EvolveState.__dataclass_fields__}
        return EvolveState(**{key: value for key, value in raw.items() if key in valid})

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.state)
        payload["fitness"] = self.state.fitness
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
        self.qtable.save(self.qtable_path)

    def _append_ledger(self, event: RewardEvent) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(event)
        payload["kind"] = event.kind.value
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _visit_key(state_key: str, action_id: str) -> str:
        return f"{state_key}|{action_id}"

    def record(
        self,
        kind: RewardKind,
        *,
        magnitude: float = 1.0,
        state_key: str | None = None,
        action_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> float:
        """Record one reward event and evolve the learned policy.

        ``magnitude`` is normally 0..1 for continuous outcomes such as HP
        fractions. Milestones use 1.0. ``token`` deduplicates one-time rewards
        such as a particular badge or Hall of Fame completion.
        """
        if token is not None and token in self.state.seen_tokens:
            return 0.0

        magnitude = max(0.0, float(magnitude))
        reward = self.weights.value_for(kind) * magnitude
        event = RewardEvent(
            kind=kind,
            reward=reward,
            magnitude=magnitude,
            state_key=state_key,
            action_id=action_id,
            metadata=dict(metadata or {}),
            created_at=datetime.now(UTC).isoformat(),
        )

        self.state.lifetime_reward += reward
        self.state.reward_events += 1
        if reward >= 0:
            self.state.positive_events += 1
        else:
            self.state.negative_events += 1

        counters = {
            RewardKind.BATTLE_WIN: "battle_wins",
            RewardKind.BATTLE_LOSS: "battle_losses",
            RewardKind.TRAINER_WIN: "trainer_wins",
            RewardKind.BOSS_WIN: "boss_wins",
            RewardKind.CAPTURE_SUCCESS: "captures",
            RewardKind.BADGE: "badges",
            RewardKind.GAME_COMPLETE: "game_completions",
        }
        counter = counters.get(kind)
        if counter is not None:
            setattr(self.state, counter, getattr(self.state, counter) + 1)

        if token is not None:
            self.state.seen_tokens.append(token)
            self.state.seen_tokens = self.state.seen_tokens[-512:]

        if state_key is not None and action_id is not None:
            # Action learning is clipped so a huge campaign milestone cannot
            # make one arbitrary move permanently dominate battle mechanics.
            learning_reward = max(-100.0, min(100.0, reward))
            self.qtable.update(state_key, action_id, learning_reward, None)
            visit_key = self._visit_key(state_key, action_id)
            self.state.action_visits[visit_key] = self.state.action_visits.get(visit_key, 0) + 1

        # One generation means roughly one hundred observed outcomes. The name
        # is useful for tracking progress; no opaque code/model mutation occurs.
        self.state.generation = 1 + self.state.reward_events // 100
        self._append_ledger(event)
        self._save()
        return reward

    def correction(self, state_key: str, action_id: str, *, limit: float = 22.0) -> float:
        """Return a confidence-weighted learned correction to a base score."""
        raw = self.qtable.q(state_key, action_id)
        visits = self.state.action_visits.get(self._visit_key(state_key, action_id), 0)
        confidence = 1.0 - math.exp(-visits / 6.0)
        correction = raw * 0.22 * confidence
        return max(-limit, min(limit, correction))

    def record_episode_reward(self, total_reward: float) -> None:
        if total_reward > self.state.best_episode_reward:
            self.state.best_episode_reward = float(total_reward)
            self._save()

    def status(self) -> dict[str, Any]:
        return {
            **asdict(self.state),
            "fitness": self.state.fitness,
            "q_states": len(self.qtable.values),
        }
