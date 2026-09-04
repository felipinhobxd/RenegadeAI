from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from renegade_ai.learning.qtable import QTable


@dataclass(frozen=True, slots=True)
class MoveOption:
    name: str
    damage_fraction: float
    accuracy: float = 1.0
    effectiveness: float = 1.0
    priority: int = 0
    pp_fraction: float = 1.0

    @property
    def action_id(self) -> str:
        return f"move:{self.name.lower()}"


@dataclass(frozen=True, slots=True)
class SwitchOption:
    name: str
    hp_fraction: float
    matchup_score: float

    @property
    def action_id(self) -> str:
        return f"switch:{self.name.lower()}"


@dataclass(frozen=True, slots=True)
class BattleState:
    own_name: str
    own_hp_fraction: float
    opponent_name: str
    opponent_hp_fraction: float
    moves: tuple[MoveOption, ...]
    switches: tuple[SwitchOption, ...] = ()

    def key(self) -> str:
        # Bucket HP so the learner generalizes across nearly-identical states.
        payload = {
            "own": self.own_name.lower(),
            "own_hp": round(max(0.0, min(1.0, self.own_hp_fraction)) * 10),
            "opponent": self.opponent_name.lower(),
            "opponent_hp": round(max(0.0, min(1.0, self.opponent_hp_fraction)) * 10),
            "moves": sorted(move.name.lower() for move in self.moves),
            "switches": sorted(switch.name.lower() for switch in self.switches),
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        return f"battle:{digest}"


@dataclass(frozen=True, slots=True)
class Decision:
    action_id: str
    score: float
    reason: str


class BattleAgent:
    def __init__(self, qtable: QTable):
        self.qtable = qtable

    @staticmethod
    def _move_score(move: MoveOption, opponent_hp: float) -> float:
        accuracy = max(0.0, min(1.0, move.accuracy))
        damage = max(0.0, move.damage_fraction) * max(0.0, move.effectiveness)
        expected = damage * accuracy
        ko_bonus = 1.2 if damage >= opponent_hp and opponent_hp > 0 else 0.0
        priority_bonus = 0.08 * max(0, move.priority)
        low_pp_penalty = 0.15 if move.pp_fraction <= 0.15 else 0.0
        return expected + ko_bonus + priority_bonus - low_pp_penalty

    @staticmethod
    def _switch_score(option: SwitchOption, own_hp: float) -> float:
        survival = max(0.0, min(1.0, option.hp_fraction)) * 0.25
        urgency = max(0.0, 0.35 - own_hp) * 0.4
        switch_cost = 0.20
        return option.matchup_score + survival + urgency - switch_cost

    def choose(self, state: BattleState) -> Decision:
        scores: dict[str, float] = {}
        reasons: dict[str, str] = {}

        for move in state.moves:
            score = self._move_score(move, state.opponent_hp_fraction)
            scores[move.action_id] = score
            reasons[move.action_id] = (
                f"expected damage={move.damage_fraction:.2f}, accuracy={move.accuracy:.2f}, "
                f"effectiveness={move.effectiveness:.2f}"
            )

        for switch in state.switches:
            score = self._switch_score(switch, state.own_hp_fraction)
            scores[switch.action_id] = score
            reasons[switch.action_id] = (
                f"matchup={switch.matchup_score:.2f}, hp={switch.hp_fraction:.2f}"
            )

        selected = self.qtable.select(state.key(), scores.keys(), scores)
        learned = self.qtable.q(state.key(), selected)
        return Decision(
            action_id=selected,
            score=scores[selected] + learned,
            reason=f"{reasons[selected]}; learned_q={learned:.3f}",
        )
