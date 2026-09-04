from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from renegade_ai.learning.qtable import QTable

if TYPE_CHECKING:
    from renegade_ai.perception.battle_vision import BattleVisualState
    from renegade_ai.strategy.battle import ScoredMove


@dataclass(slots=True)
class PendingBattleAction:
    state_key: str
    action_id: str
    own_slug: str
    opponent_slug: str
    own_hp: float | None
    opponent_hp: float | None
    own_status: str | None


def matchup_state_key(state: BattleVisualState) -> str | None:
    if state.own is None or state.opponent is None:
        return None
    status = state.own_status or "healthy"
    level_band = (state.own_level or 0) // 10
    opponent_band = (state.opponent_level or 0) // 10
    return (
        f"battle:{state.own.slug}:{state.opponent.slug}:"
        f"l{level_band}:ol{opponent_band}:{status}"
    )


def immediate_reward(previous: PendingBattleAction, current: BattleVisualState) -> float | None:
    """Estimate whether the previous action helped using the next visible turn.

    The reward is deliberately simple and bounded. It complements the mechanics
    engine; it does not attempt to relearn Pokemon from scratch.
    """
    if current.own is None or current.opponent is None:
        return None
    if current.own.slug != previous.own_slug:
        return None
    if previous.own_hp is None or previous.opponent_hp is None:
        return None
    if current.own_hp_fraction is None:
        return None

    taken = max(0.0, previous.own_hp - current.own_hp_fraction)
    if current.opponent.slug == previous.opponent_slug:
        if current.opponent_hp_fraction is None:
            return None
        dealt = max(0.0, previous.opponent_hp - current.opponent_hp_fraction)
        ko_bonus = 0.0
    else:
        # A new opposing species at the next command screen strongly suggests
        # the previous opponent fainted. Credit its remaining pre-move HP plus a
        # small KO bonus rather than assuming a full-health KO.
        dealt = max(0.0, previous.opponent_hp)
        ko_bonus = 22.0

    reward = dealt * 100.0 - taken * 65.0 + ko_bonus
    if previous.own_status is None and current.own_status in {"PSN", "BRN", "PAR", "SLP", "FRZ"}:
        reward -= 8.0
    return max(-100.0, min(100.0, reward))


class BattleAdaptiveMemory:
    """Persistent, bounded learning on top of deterministic battle mechanics."""

    def __init__(
        self,
        path: str | Path = Path("data/qtable.json"),
        *,
        alpha: float = 0.20,
    ) -> None:
        self.path = Path(path)
        self.qtable = QTable.load(self.path, alpha=alpha, gamma=0.0, epsilon=0.0)
        # Immediate-turn learning behaves like a contextual bandit. Gamma and
        # epsilon are disabled so it never explores by making random live-run
        # choices and never amplifies long chains of noisy visual rewards.
        self.qtable.gamma = 0.0
        self.qtable.epsilon = 0.0
        self.pending: PendingBattleAction | None = None
        self.last_reward: float | None = None

    def correction(self, state_key: str, action_id: str) -> float:
        # Keep learned experience subordinate to the simulator. Even a large
        # history can only shift a move score by +/- 15 points.
        return max(-15.0, min(15.0, self.qtable.q(state_key, action_id) * 0.25))

    def choose(self, state: BattleVisualState, ranked: list[ScoredMove]) -> tuple[ScoredMove, float]:
        state_key = matchup_state_key(state)
        if state_key is None:
            return ranked[0], 0.0

        def total(option: ScoredMove) -> float:
            action = f"move:{option.move.slug}"
            return option.score + self.correction(state_key, action)

        best = max(ranked, key=total)
        return best, self.correction(state_key, f"move:{best.move.slug}")

    def remember(self, state: BattleVisualState, move_slug: str) -> None:
        state_key = matchup_state_key(state)
        if state_key is None or state.own is None or state.opponent is None:
            return
        self.pending = PendingBattleAction(
            state_key=state_key,
            action_id=f"move:{move_slug}",
            own_slug=state.own.slug,
            opponent_slug=state.opponent.slug,
            own_hp=state.own_hp_fraction,
            opponent_hp=state.opponent_hp_fraction,
            own_status=state.own_status,
        )

    def observe_next_turn(self, current: BattleVisualState) -> float | None:
        if self.pending is None:
            return None
        pending = self.pending
        self.pending = None
        reward = immediate_reward(pending, current)
        if reward is None:
            return None
        self.qtable.update(pending.state_key, pending.action_id, reward, None)
        self.qtable.save(self.path)
        self.last_reward = reward
        return reward
