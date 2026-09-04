from __future__ import annotations

from renegade_ai.knowledge.models import MoveData


_PUNCHING_MOVES = {
    "bullet-punch",
    "comet-punch",
    "dizzy-punch",
    "drain-punch",
    "dynamic-punch",
    "fire-punch",
    "focus-punch",
    "hammer-arm",
    "ice-punch",
    "mach-punch",
    "mega-punch",
    "meteor-mash",
    "shadow-punch",
    "sky-uppercut",
    "thunder-punch",
}
_RECOIL_MOVES = {
    "brave-bird",
    "double-edge",
    "flare-blitz",
    "head-smash",
    "submission",
    "take-down",
    "volt-tackle",
    "wood-hammer",
}


def slug(value: str | None) -> str:
    if value is None:
        return ""
    return (
        value.lower()
        .strip()
        .replace(" ", "-")
        .replace("'", "")
        .replace(".", "")
    )


def stab_multiplier(ability: str | None, is_stab: bool) -> float:
    if not is_stab:
        return 1.0
    return 2.0 if slug(ability) == "adaptability" else 1.5


def move_power_multiplier(
    ability: str | None,
    move: MoveData,
    *,
    hp_fraction: float = 1.0,
) -> float:
    """Return offensive move-power multipliers that can be inferred safely."""
    ability_slug = slug(ability)
    move_slug = slug(move.name)
    multiplier = 1.0

    if ability_slug == "iron-fist" and move_slug in _PUNCHING_MOVES:
        multiplier *= 1.2
    if ability_slug == "technician" and move.power is not None and move.power <= 60:
        multiplier *= 1.5
    if ability_slug == "reckless" and move_slug in _RECOIL_MOVES:
        multiplier *= 1.2

    low_hp_boost = {
        "blaze": "fire",
        "torrent": "water",
        "overgrow": "grass",
        "swarm": "bug",
    }.get(ability_slug)
    if hp_fraction <= 1 / 3 and low_hp_boost == move.type.lower():
        multiplier *= 1.5

    return multiplier


def attack_stat_multiplier(
    ability: str | None,
    *,
    category: str,
    status: str | None = None,
) -> float:
    ability_slug = slug(ability)
    category = category.lower()
    status = (status or "").upper()
    multiplier = 1.0

    if category == "physical" and ability_slug in {"huge-power", "pure-power"}:
        multiplier *= 2.0
    if category == "physical" and ability_slug == "hustle":
        multiplier *= 1.5
    if category == "physical" and ability_slug == "guts" and status:
        multiplier *= 1.5

    # Burn halves physical damage unless Guts is active.
    if category == "physical" and status == "BRN" and ability_slug != "guts":
        multiplier *= 0.5
    return multiplier


def accuracy_multiplier(ability: str | None, *, category: str) -> float:
    if slug(ability) == "hustle" and category.lower() == "physical":
        return 0.8
    return 1.0


def defender_immunity(
    move_type: str,
    defender_ability: str | None,
    *,
    attacker_ability: str | None = None,
) -> bool:
    if slug(attacker_ability) == "mold-breaker":
        return False
    ability = slug(defender_ability)
    move_type = move_type.lower()
    return (
        (move_type == "ground" and ability == "levitate")
        or (move_type == "fire" and ability == "flash-fire")
        or (move_type == "water" and ability in {"water-absorb", "dry-skin"})
        or (move_type == "electric" and ability in {"volt-absorb", "motor-drive"})
    )


def defender_damage_multiplier(
    move_type: str,
    effectiveness: float,
    defender_ability: str | None,
    *,
    attacker_ability: str | None = None,
) -> float:
    if slug(attacker_ability) == "mold-breaker":
        return 1.0
    ability = slug(defender_ability)
    move_type = move_type.lower()
    multiplier = 1.0
    if ability == "thick-fat" and move_type in {"fire", "ice"}:
        multiplier *= 0.5
    if ability == "heatproof" and move_type == "fire":
        multiplier *= 0.5
    if ability in {"filter", "solid-rock"} and effectiveness > 1.0:
        multiplier *= 0.75
    return multiplier
