from __future__ import annotations

from dataclasses import dataclass

from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.state.runtime import RuntimePokemon
from renegade_ai.strategy.mechanics import (
    accuracy_multiplier,
    attack_stat_multiplier,
    defender_damage_multiplier,
    defender_immunity,
    move_power_multiplier,
    slug,
    stab_multiplier,
)
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
    "leer": 10.0,
    "growl": 8.0,
}
_FIXED_DAMAGE = {
    "dragon-rage": 40.0,
    "sonic-boom": 20.0,
}
_LEVEL_DAMAGE = {"night-shade", "seismic-toss"}


def _estimated_stat(base: int, level: int, *, hp: bool = False) -> float:
    """Estimate a neutral 15-IV, zero-EV stat when exact UI data is unavailable."""
    level = max(1, min(100, int(level)))
    core = ((2 * max(1, base) + 15) * level) / 100.0
    return core + level + 10 if hp else core + 5


def _runtime_stat(
    runtime: RuntimePokemon | None,
    field: str,
    base: int,
    level: int,
    *,
    hp: bool = False,
) -> float:
    if runtime is not None:
        value = getattr(runtime, field, None)
        if value is not None and value > 0:
            return float(value)
    return _estimated_stat(base, level, hp=hp)


def _effective_type_multiplier(
    own: PokemonData,
    opponent: PokemonData,
    move: MoveData,
    *,
    own_ability: str | None,
    opponent_ability: str | None,
) -> float:
    move_type = move.type.lower()
    eff = effectiveness(move_type, opponent.types)

    # Scrappy removes Ghost immunities for Normal/Fighting attacks.
    if eff == 0.0 and slug(own_ability) == "scrappy" and move_type in {"normal", "fighting"}:
        non_ghost = tuple(value for value in opponent.types if value.lower() != "ghost")
        eff = effectiveness(move_type, non_ghost) if non_ghost else 1.0

    if defender_immunity(move_type, opponent_ability, attacker_ability=own_ability):
        return 0.0
    if slug(opponent_ability) == "wonder-guard" and eff <= 1.0:
        return 0.0
    if slug(own_ability) == "tinted-lens" and 0.0 < eff < 1.0:
        eff *= 2.0
    return eff


def _held_item_multiplier(
    item: str | None,
    move: MoveData,
    *,
    effectiveness_value: float,
) -> float:
    item_slug = slug(item)
    category = move.category.lower()
    if item_slug == "life-orb":
        return 1.3
    if item_slug == "choice-band" and category == "physical":
        return 1.5
    if item_slug == "choice-specs" and category == "special":
        return 1.5
    if item_slug == "expert-belt" and effectiveness_value > 1.0:
        return 1.2
    if item_slug == "muscle-band" and category == "physical":
        return 1.1
    if item_slug == "wise-glasses" and category == "special":
        return 1.1
    return 1.0


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
    own_hp: float,
    own_runtime: RuntimePokemon | None,
    opponent_runtime: RuntimePokemon | None,
) -> tuple[float, float, float] | None:
    move_slug = slug(move.name)
    opponent_max_hp = _runtime_stat(
        opponent_runtime,
        "hp_max",
        opponent.hp,
        opponent_level,
        hp=True,
    )
    if move_slug in _FIXED_DAMAGE:
        fraction = _FIXED_DAMAGE[move_slug] / opponent_max_hp
        return fraction, fraction, fraction
    if move_slug in _LEVEL_DAMAGE:
        fraction = own_level / opponent_max_hp
        return fraction, fraction, fraction
    if move_slug == "super-fang":
        fraction = max(0.0, opponent_hp) * 0.5
        return fraction, fraction, fraction
    if move.power is None or move.power <= 0 or eff <= 0.0:
        return None

    category = move.category.lower()
    if category == "physical":
        attack = _runtime_stat(own_runtime, "attack", own.attack, own_level)
        defense = _runtime_stat(opponent_runtime, "defense", opponent.defense, opponent_level)
    elif category == "special":
        attack = _runtime_stat(own_runtime, "special_attack", own.special_attack, own_level)
        defense = _runtime_stat(
            opponent_runtime,
            "special_defense",
            opponent.special_defense,
            opponent_level,
        )
    else:
        return None

    own_ability = None if own_runtime is None else own_runtime.ability
    opponent_ability = None if opponent_runtime is None else opponent_runtime.ability
    own_status = None if own_runtime is None else own_runtime.status
    attack *= attack_stat_multiplier(own_ability, category=category, status=own_status)

    effective_power = float(move.power) * move_power_multiplier(
        own_ability,
        move,
        hp_fraction=own_hp,
    )
    level_factor = (2 * own_level / 5) + 2
    base_damage = ((level_factor * effective_power * attack / max(1.0, defense)) / 50.0) + 2
    modifier = stab * eff
    modifier *= defender_damage_multiplier(
        move.type,
        eff,
        opponent_ability,
        attacker_ability=own_ability,
    )
    modifier *= _held_item_multiplier(
        None if own_runtime is None else own_runtime.item,
        move,
        effectiveness_value=eff,
    )

    minimum = base_damage * modifier * 0.85 / max(1.0, opponent_max_hp)
    maximum = base_damage * modifier / max(1.0, opponent_max_hp)
    mean = (minimum + maximum) / 2.0
    return max(0.0, minimum), max(0.0, mean), max(0.0, maximum)


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
    own_runtime: RuntimePokemon | None = None,
    opponent_runtime: RuntimePokemon | None = None,
) -> tuple[float, float, float, str]:
    own_ability = None if own_runtime is None else own_runtime.ability
    opponent_ability = None if opponent_runtime is None else opponent_runtime.ability
    move_type = move.type.lower()
    eff = _effective_type_multiplier(
        own,
        opponent,
        move,
        own_ability=own_ability,
        opponent_ability=opponent_ability,
    )
    is_stab = move_type in {value.lower() for value in own.types}
    stab = stab_multiplier(own_ability, is_stab)
    move_slug = slug(move.name)

    damage_range = _damage_fraction(
        own,
        opponent,
        move,
        own_level=own_level,
        opponent_level=opponent_level,
        stab=stab,
        eff=eff,
        opponent_hp=opponent_hp,
        own_hp=own_hp,
        own_runtime=own_runtime,
        opponent_runtime=opponent_runtime,
    )
    if damage_range is None:
        if eff == 0.0 and move.power:
            return 0.0, eff, stab, "immune: move cannot affect this opponent"
        base = _STATUS_VALUE.get(move_slug, 12.0)
        if own_hp < 0.38 and move_slug in {
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

    minimum_damage, estimated_damage, maximum_damage = damage_range
    accuracy = 1.0 if move.accuracy is None else max(0.01, move.accuracy / 100.0)
    accuracy *= accuracy_multiplier(own_ability, category=move.category)
    if slug(own_ability) == "no-guard" or slug(opponent_ability) == "no-guard":
        accuracy = 1.0
    accuracy = min(1.0, accuracy)

    reliability = accuracy**1.35
    score = estimated_damage * 100.0 * reliability

    # Reliable KO decisions get a large bonus; guaranteed minimum-roll KOs get
    # an additional bonus over moves that only KO on a high roll.
    if opponent_hp > 0 and maximum_damage >= opponent_hp:
        score += 30.0 * accuracy
    if opponent_hp > 0 and minimum_damage >= opponent_hp:
        score += 34.0 * accuracy
    if accuracy < 0.80 and opponent_hp <= 0.35:
        score *= 0.83
    if pp_fraction <= 0.0:
        score = -1_000.0
    elif pp_fraction <= 0.10:
        score *= 0.72
    elif pp_fraction <= 0.25:
        score *= 0.88
    if own_hp <= 0.20 and eff >= 2.0:
        score *= 1.10

    power_text = "fixed" if move.power is None else str(move.power)
    ability_text = "" if not own_ability else f", ability={own_ability}"
    reason = (
        f"power={power_text}, STAB={stab:.1f}x, matchup={eff:.2g}x, "
        f"accuracy={accuracy:.0%}, damage={minimum_damage:.0%}-{maximum_damage:.0%}"
        f"{ability_text}"
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
    own_runtime: RuntimePokemon | None = None,
    opponent_runtime: RuntimePokemon | None = None,
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
            own_runtime=own_runtime,
            opponent_runtime=opponent_runtime,
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
