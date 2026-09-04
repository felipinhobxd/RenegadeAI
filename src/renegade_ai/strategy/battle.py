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
_FIXED_DAMAGE = {
    "dragon-rage": 40.0,
    "sonic-boom": 20.0,
}
_LEVEL_DAMAGE = {"night-shade", "seismic-toss"}


def _slug(value: str) -> str:
    return value.lower().strip().replace(" ", "-").replace("'", "").replace(".", "")


def _estimated_stat(base: int, level: int, *, hp: bool = False) -> float:
    """Approximate an in-game stat from base stat, level and a neutral average IV."""
    level = max(1, min(100, int(level)))
    core = ((2 * max(1, base) + 15) * level) / 100.0
    return core + level + 10 if hp else core + 5


def _damage_fraction(
    own: PokemonData,
    opponent: PokemonData,
    move: MoveData,
    *,
    own_level: int,
    opponent_level: int,
    stab: float,
    eff: float,
    opponent_hp: float,
) -> float | None:
    slug = _slug(move.name)
    opponent_max_hp = _estimated_stat(opponent.hp, opponent_level, hp=True)
    if slug in _FIXED_DAMAGE:
        return _FIXED_DAMAGE[slug] / opponent_max_hp
    if slug in _LEVEL_DAMAGE:
        return own_level / opponent_max_hp
    if slug == "super-fang":
        return max(0.0, opponent_hp) * 0.5
    if move.power is None or move.power <= 0:
        return None

    category = move.category.lower()
    if category == "physical":
        attack = _estimated_stat(own.attack, own_level)
        defense = _estimated_stat(opponent.defense, opponent_level)
    elif category == "special":
        attack = _estimated_stat(own.special_attack, own_level)
        defense = _estimated_stat(opponent.special_defense, opponent_level)
    else:
        return None

    level_factor = (2 * own_level / 5) + 2
    base_damage = ((level_factor * move.power * attack / max(1.0, defense)) / 50.0) + 2
    average_random_roll = 0.925
    damage = base_damage * stab * eff * average_random_roll
    return max(0.0, damage / max(1.0, opponent_max_hp))


def score_move(
    own: PokemonData,
    opponent: PokemonData,
    move: MoveData,
    *,
    own_hp: float = 1.0,
    opponent_hp: float = 1.0,
    pp_fraction: float = 1.0,
    own_level: int = 50,
    opponent_level: int = 50,
) -> tuple[float, float, float, str]:
    move_type = move.type.lower()
    eff = effectiveness(move_type, opponent.types)
    stab = 1.5 if move_type in {value.lower() for value in own.types} else 1.0
    slug = _slug(move.name)

    estimated_damage = _damage_fraction(
        own,
        opponent,
        move,
        own_level=own_level,
        opponent_level=opponent_level,
        stab=stab,
        eff=eff,
        opponent_hp=opponent_hp,
    )
    if estimated_damage is None:
        base = _STATUS_VALUE.get(slug, 12.0)
        if own_hp < 0.38 and slug in {
            "recover",
            "roost",
            "soft-boiled",
            "slack-off",
            "synthesis",
            "moonlight",
            "wish",
        }:
            base *= 1.65
        if opponent_hp < 0.30:
            base *= 0.46
        reason = f"status utility={base:.1f}"
        return base, eff, stab, reason

    accuracy = 1.0 if move.accuracy is None else max(0.01, move.accuracy / 100.0)
    reliability = accuracy**1.35
    score = estimated_damage * 100.0 * reliability

    if opponent_hp > 0 and estimated_damage >= opponent_hp:
        score += 54.0 * accuracy
    if accuracy < 0.80 and opponent_hp <= 0.35:
        score *= 0.83
    if pp_fraction <= 0.10:
        score *= 0.72
    elif pp_fraction <= 0.25:
        score *= 0.88
    if own_hp <= 0.20 and eff >= 2.0:
        score *= 1.10

    power_text = "fixed" if move.power is None else str(move.power)
    reason = (
        f"power={power_text}, STAB={stab:.1f}x, matchup={eff:.2g}x, "
        f"accuracy={accuracy:.0%}, estimated-damage={estimated_damage:.0%}"
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
    own_level: int = 50,
    opponent_level: int = 50,
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
            own_level=own_level,
            opponent_level=opponent_level,
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
