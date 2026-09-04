from __future__ import annotations

from dataclasses import dataclass

from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.strategy.type_chart import effectiveness


@dataclass(frozen=True, slots=True)
class ScoredMove:
    slot: int
    move: MoveData
    score: float
    effectiveness: float
    stab: float
    reason: str


_STATUS_VALUE = {
    "belly-drum": 88.0,
    "calm-mind": 58.0,
    "dragon-dance": 76.0,
    "nasty-plot": 72.0,
    "quiver-dance": 82.0,
    "shell-smash": 92.0,
    "swords-dance": 72.0,
    "recover": 60.0,
    "roost": 60.0,
    "soft-boiled": 60.0,
    "slack-off": 60.0,
    "synthesis": 54.0,
    "moonlight": 54.0,
    "wish": 50.0,
    "stealth-rock": 38.0,
    "spikes": 32.0,
    "toxic-spikes": 30.0,
    "sticky-web": 44.0,
    "thunder-wave": 40.0,
    "will-o-wisp": 42.0,
    "toxic": 38.0,
    "leech-seed": 42.0,
    "taunt": 28.0,
    "encore": 30.0,
}


def _slug(value: str) -> str:
    return value.lower().strip().replace(" ", "-").replace("'", "").replace(".", "")


def _offense_alignment(own: PokemonData, move: MoveData) -> float:
    category = move.category.lower()
    if category == "physical":
        relevant = own.attack
        other = own.special_attack
    elif category == "special":
        relevant = own.special_attack
        other = own.attack
    else:
        return 1.0
    if relevant <= 0:
        return 1.0
    ratio = relevant / max(1, other)
    return max(0.72, min(1.30, 0.96 + (ratio - 1.0) * 0.22))


def score_move(
    own: PokemonData,
    opponent: PokemonData,
    move: MoveData,
    *,
    own_hp: float = 1.0,
    opponent_hp: float = 1.0,
    pp_fraction: float = 1.0,
) -> tuple[float, float, float, str]:
    move_type = move.type.lower()
    eff = effectiveness(move_type, opponent.types)
    stab = 1.5 if move_type in {value.lower() for value in own.types} else 1.0

    if move.category.lower() == "status" or not move.power:
        base = _STATUS_VALUE.get(_slug(move.name), 12.0)
        if own_hp < 0.38 and _slug(move.name) in {
            "recover", "roost", "soft-boiled", "slack-off", "synthesis", "moonlight", "wish"
        }:
            base *= 1.65
        if opponent_hp < 0.30:
            base *= 0.46
        reason = f"status utility={base:.1f}"
        return base, eff, stab, reason

    accuracy = 1.0 if move.accuracy is None else max(0.01, move.accuracy / 100.0)
    alignment = _offense_alignment(own, move)
    reliability = accuracy ** 1.35
    score = float(move.power) * stab * eff * alignment * reliability

    # Prefer a reliable finishing hit instead of a needlessly risky nuke.
    rough_damage = (move.power / 120.0) * stab * eff * alignment
    if opponent_hp > 0 and rough_damage >= opponent_hp:
        score += 54.0 * accuracy
    if accuracy < 0.80 and opponent_hp <= 0.35:
        score *= 0.83
    if pp_fraction <= 0.10:
        score *= 0.72
    elif pp_fraction <= 0.25:
        score *= 0.88
    if own_hp <= 0.20 and eff >= 2.0:
        score *= 1.10

    reason = (
        f"power={move.power}, STAB={stab:.1f}x, matchup={eff:.2g}x, "
        f"accuracy={accuracy:.0%}, offense-fit={alignment:.2f}"
    )
    return score, eff, stab, reason


def rank_moves(
    own: PokemonData,
    opponent: PokemonData,
    moves: list[MoveData | None] | tuple[MoveData | None, ...],
    *,
    own_hp: float = 1.0,
    opponent_hp: float = 1.0,
    pp_fractions: list[float] | tuple[float, ...] | None = None,
) -> list[ScoredMove]:
    ranked: list[ScoredMove] = []
    for index, move in enumerate(moves):
        if move is None:
            continue
        pp = 1.0 if pp_fractions is None or index >= len(pp_fractions) else pp_fractions[index]
        score, eff, stab, reason = score_move(
            own,
            opponent,
            move,
            own_hp=own_hp,
            opponent_hp=opponent_hp,
            pp_fraction=pp,
        )
        ranked.append(
            ScoredMove(
                slot=index,
                move=move,
                score=score,
                effectiveness=eff,
                stab=stab,
                reason=reason,
            )
        )
    ranked.sort(key=lambda option: option.score, reverse=True)
    return ranked
