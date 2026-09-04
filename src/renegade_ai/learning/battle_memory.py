from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from renegade_ai.learning.evolve import ASIEvolveEngine, RewardKind
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
    opponent_status: str | None = None


@dataclass(frozen=True, slots=True)
class BattleRewardBreakdown:
    damage_dealt: float = 0.0
    damage_taken: float = 0.0
    opponent_ko: bool = False
    own_faint: bool = False
    status_inflicted: bool = False
    status_received: bool = False


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


def reward_breakdown(
    previous: PendingBattleAction,
    current: BattleVisualState,
) -> BattleRewardBreakdown | None:
    if current.own is None or current.opponent is None:
        return None
    if current.own.slug != previous.own_slug:
        return None
    if previous.own_hp is None or previous.opponent_hp is None:
        return None
    if current.own_hp_fraction is None:
        return None

    damage_taken = max(0.0, previous.own_hp - current.own_hp_fraction)
    opponent_ko = current.opponent.slug != previous.opponent_slug
    if opponent_ko:
        damage_dealt = max(0.0, previous.opponent_hp)
    else:
        if current.opponent_hp_fraction is None:
            return None
        damage_dealt = max(0.0, previous.opponent_hp - current.opponent_hp_fraction)

    status_received = (
        previous.own_status is None
        and current.own_status in {"PSN", "BRN", "PAR", "SLP", "FRZ"}
    )
    status_inflicted = (
        not opponent_ko
        and previous.opponent_status is None
        and current.opponent_status in {"PSN", "BRN", "PAR", "SLP", "FRZ"}
    )
    own_faint = current.own_hp_fraction <= 0.0
    return BattleRewardBreakdown(
        damage_dealt=damage_dealt,
        damage_taken=damage_taken,
        opponent_ko=opponent_ko,
        own_faint=own_faint,
        status_inflicted=status_inflicted,
        status_received=status_received,
    )


def immediate_reward(previous: PendingBattleAction, current: BattleVisualState) -> float | None:
    """Return a bounded tactical reward from the next visible battle turn."""
    breakdown = reward_breakdown(previous, current)
    if breakdown is None:
        return None
    reward = breakdown.damage_dealt * 100.0 - breakdown.damage_taken * 65.0
    if breakdown.opponent_ko:
        reward += 22.0
    if breakdown.own_faint:
        reward -= 45.0
    if breakdown.status_inflicted:
        reward += 8.0
    if breakdown.status_received:
        reward -= 8.0
    return max(-100.0, min(100.0, reward))


class BattleAdaptiveMemory:
    """Mechanics-first learning with a richer ASI-Evolve reward ledger."""

    def __init__(
        self,
        path: str | Path = Path("data/battle_adaptive.json"),
        *,
        alpha: float = 0.20,
        evolve_engine: ASIEvolveEngine | None = None,
    ) -> None:
        self.path = Path(path)
        self.qtable = QTable.load(self.path, alpha=alpha, gamma=0.0, epsilon=0.0)
        self.qtable.gamma = 0.0
        self.qtable.epsilon = 0.0
        if evolve_engine is None:
            if self.path == Path("data/battle_adaptive.json"):
                evolve_engine = ASIEvolveEngine()
            else:
                stem = self.path.stem
                evolve_engine = ASIEvolveEngine(
                    state_path=self.path.with_name(f"{stem}_evolve_state.json"),
                    qtable_path=self.path.with_name(f"{stem}_evolve_qtable.json"),
                    ledger_path=self.path.with_name(f"{stem}_evolve_rewards.jsonl"),
                )
        self.evolve = evolve_engine
        self.pending: PendingBattleAction | None = None
        self.last_reward: float | None = None
        self.episode_reward: float = 0.0

    def correction(self, state_key: str, action_id: str) -> float:
        # Learned history may refine a close call, never overpower the simulator.
        legacy = self.qtable.q(state_key, action_id) * 0.25
        evolved = self.evolve.correction(state_key, action_id, limit=8.0)
        return max(-15.0, min(15.0, legacy + evolved))

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
            opponent_status=state.opponent_status,
        )

    def _record_breakdown(
        self,
        pending: PendingBattleAction,
        breakdown: BattleRewardBreakdown,
    ) -> None:
        common = {
            "state_key": pending.state_key,
            "action": pending.action_id,
            "own": pending.own_slug,
            "opponent": pending.opponent_slug,
        }
        if breakdown.damage_dealt > 0:
            self.evolve.record(
                RewardKind.DAMAGE_DEALT,
                magnitude=breakdown.damage_dealt,
                metadata=common,
            )
        if breakdown.damage_taken > 0:
            self.evolve.record(
                RewardKind.DAMAGE_TAKEN,
                magnitude=breakdown.damage_taken,
                metadata=common,
            )
        if breakdown.opponent_ko:
            self.evolve.record(RewardKind.OPPONENT_KO, metadata=common)
        if breakdown.own_faint:
            self.evolve.record(RewardKind.OWN_FAINT, metadata=common)
        if breakdown.status_inflicted:
            self.evolve.record(RewardKind.STATUS_INFLICTED, metadata=common)
        if breakdown.status_received:
            self.evolve.record(RewardKind.STATUS_RECEIVED, metadata=common)

    def observe_next_turn(self, current: BattleVisualState) -> float | None:
        if self.pending is None:
            return None
        pending = self.pending
        self.pending = None
        breakdown = reward_breakdown(pending, current)
        reward = immediate_reward(pending, current)
        if breakdown is None or reward is None:
            return None

        self._record_breakdown(pending, breakdown)
        self.qtable.update(pending.state_key, pending.action_id, reward, None)
        self.qtable.save(self.path)
        # Give the ASI-Evolve policy the same bounded net outcome so its
        # confidence-weighted correction can mature with repeated evidence.
        if reward >= 0:
            kind = RewardKind.OBJECTIVE_PROGRESS
            magnitude = min(1.0, reward / 100.0)
        else:
            kind = RewardKind.WASTED_ITEM
            magnitude = min(1.0, abs(reward) / 100.0)
        self.evolve.record(
            kind,
            magnitude=magnitude,
            state_key=pending.state_key,
            action_id=pending.action_id,
            metadata={"source": "net_battle_turn", "net_reward": reward},
        )
        self.last_reward = reward
        self.episode_reward += reward
        return reward

    def finish_battle(self, *, won: bool = True) -> float:
        """Reward or penalize the completed battle and close the episode."""
        kind = RewardKind.BATTLE_WIN if won else RewardKind.BATTLE_LOSS
        reward = self.evolve.record(kind, metadata={"source": "battle_end"})
        if self.pending is not None:
            pending = self.pending
            self.pending = None
            bounded = max(-100.0, min(100.0, reward))
            self.qtable.update(pending.state_key, pending.action_id, bounded, None)
            self.qtable.save(self.path)
        self.episode_reward += reward
        self.evolve.record_episode_reward(self.episode_reward)
        total = self.episode_reward
        self.episode_reward = 0.0
        self.last_reward = reward
        return total

    def record_milestone(
        self,
        kind: RewardKind,
        *,
        token: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> float:
        """Hook for future badge, boss, evolution and game-complete detectors."""
        return self.evolve.record(kind, token=token, metadata=dict(metadata or {}))
