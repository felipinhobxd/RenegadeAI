from __future__ import annotations

from collections import defaultdict

from renegade_ai.knowledge.models import MoveData, PokemonData, StrategyProfile

_SETUP_MOVES = {
    "belly-drum": 46.0,
    "calm-mind": 36.0,
    "coil": 38.0,
    "curse": 30.0,
    "dragon-dance": 46.0,
    "nasty-plot": 46.0,
    "quiver-dance": 50.0,
    "rock-polish": 34.0,
    "shell-smash": 54.0,
    "shift-gear": 48.0,
    "swords-dance": 46.0,
    "tail-glow": 50.0,
}
_RECOVERY_MOVES = {
    "heal-order",
    "milk-drink",
    "moonlight",
    "morning-sun",
    "recover",
    "rest",
    "roost",
    "slack-off",
    "soft-boiled",
    "synthesis",
    "wish",
}
_UTILITY_MOVES = {
    "encore",
    "leech-seed",
    "light-screen",
    "reflect",
    "spikes",
    "stealth-rock",
    "sticky-web",
    "taunt",
    "thunder-wave",
    "toxic",
    "toxic-spikes",
    "will-o-wisp",
}
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

_ABILITY_PRIORITY = {
    "adaptability": 100,
    "huge-power": 99,
    "pure-power": 99,
    "magic-guard": 97,
    "technician": 95,
    "speed-boost": 95,
    "poison-heal": 94,
    "regenerator": 94,
    "drizzle": 93,
    "drought": 93,
    "intimidate": 92,
    "guts": 91,
    "mold-breaker": 90,
    "levitate": 90,
    "no-guard": 89,
    "serene-grace": 89,
    "multiscale": 89,
    "iron-fist": 88,
    "tinted-lens": 88,
    "filter": 87,
    "solid-rock": 87,
    "sturdy": 86,
    "scrappy": 85,
    "natural-cure": 84,
    "blaze": 60,
    "torrent": 60,
    "overgrow": 60,
    "swarm": 60,
}


def _ability_slug(value: str) -> str:
    return value.lower().strip().replace(" ", "-")


def _learnable_moves(pokemon: PokemonData, moves: dict[str, MoveData]) -> list[MoveData]:
    return [moves[entry.move] for entry in pokemon.learnset if entry.move in moves]


def _ability_score(ability: str, pokemon: PokemonData, moves: dict[str, MoveData]) -> float:
    ability_slug = _ability_slug(ability)
    score = float(_ABILITY_PRIORITY.get(ability_slug, 50))
    learnable = _learnable_moves(pokemon, moves)
    damaging = [move for move in learnable if move.power and move.power > 0]

    # Move-dependent abilities should not outrank a universally useful ability
    # unless this species can actually exploit them in Renegade Platinum.
    if ability_slug == "iron-fist":
        punches = sum(move.slug in _PUNCHING_MOVES for move in damaging)
        score += min(24, punches * 6) if punches else -20
    elif ability_slug == "technician":
        eligible = sum((move.power or 0) <= 60 for move in damaging)
        score += min(18, eligible * 2) if eligible else -12
    elif ability_slug == "no-guard":
        inaccurate = sum(move.accuracy is not None and move.accuracy < 90 for move in damaging)
        score += min(20, inaccurate * 5) if inaccurate else -10
    elif ability_slug == "adaptability":
        stab_moves = sum(move.type.lower() in {value.lower() for value in pokemon.types} for move in damaging)
        score += min(12, stab_moves * 2)
    elif ability_slug in {"huge-power", "pure-power", "guts"}:
        score += 12 if pokemon.attack >= pokemon.special_attack else -8
    elif ability_slug == "serene-grace":
        # Secondary-effect chance is not yet stored in MoveData, so keep the
        # strong baseline but avoid inventing move-specific bonuses here.
        score += 0

    return score


def _preferred_ability(pokemon: PokemonData, moves: dict[str, MoveData]) -> str | None:
    if not pokemon.abilities:
        return None
    return max(pokemon.abilities, key=lambda ability: _ability_score(ability, pokemon, moves))


def _role(pokemon: PokemonData) -> tuple[str, str]:
    physical = pokemon.attack
    special = pokemon.special_attack
    best_offense = max(physical, special)
    bulk = pokemon.hp * 0.38 + pokemon.defense * 0.31 + pokemon.special_defense * 0.31

    if abs(physical - special) <= 12 and best_offense >= 85:
        offense = "mixed"
    elif physical > special:
        offense = "physical"
    else:
        offense = "special"

    if pokemon.speed >= 100 and best_offense >= 100:
        role = "fast sweeper"
    elif pokemon.speed >= 85 and best_offense >= 110:
        role = "offensive sweeper"
    elif bulk >= 105 and best_offense >= 95:
        role = "bulky attacker"
    elif bulk >= 112:
        role = "defensive wall"
    elif pokemon.speed >= 100:
        role = "fast utility"
    elif best_offense >= 100:
        role = "breaker"
    else:
        role = "balanced utility"
    return role, offense


def _nature_and_evs(pokemon: PokemonData, role: str, offense: str) -> tuple[str, str, str]:
    fast = pokemon.speed >= 90
    if offense == "physical":
        nature = "Jolly" if fast else "Adamant"
        evs = "252 Atk / 252 Spe / 4 HP" if fast else "252 Atk / 252 HP / 4 Spe"
        if "sweeper" in role:
            item = "Life Orb"
        elif role == "breaker":
            item = "Choice Band"
        else:
            item = "Leftovers"
    elif offense == "special":
        nature = "Timid" if fast else "Modest"
        evs = "252 SpA / 252 Spe / 4 HP" if fast else "252 SpA / 252 HP / 4 Spe"
        if "sweeper" in role:
            item = "Life Orb"
        elif role == "breaker":
            item = "Choice Specs"
        else:
            item = "Leftovers"
    else:
        nature = "Naive" if fast else "Quiet"
        evs = "252 Spe / 128 Atk / 128 SpA" if fast else "252 HP / 128 Atk / 128 SpA"
        item = "Life Orb"

    if role == "defensive wall":
        if pokemon.defense >= pokemon.special_defense:
            nature = "Impish" if pokemon.attack >= pokemon.special_attack else "Bold"
            evs = "252 HP / 252 Def / 4 SpD"
        else:
            nature = "Careful" if pokemon.attack >= pokemon.special_attack else "Calm"
            evs = "252 HP / 252 SpD / 4 Def"
        item = "Leftovers"
    elif role == "fast utility":
        item = "Focus Sash"
    return nature, evs, item


def _damage_score(pokemon: PokemonData, move: MoveData, offense: str) -> float:
    if move.power is None or move.power <= 0 or move.category.lower() == "status":
        return -1.0
    accuracy = 1.0 if move.accuracy is None else max(0.30, move.accuracy / 100.0)
    stab = 1.5 if move.type.lower() in {value.lower() for value in pokemon.types} else 1.0

    category = move.category.lower()
    if offense == "physical":
        alignment = 1.22 if category == "physical" else 0.72
    elif offense == "special":
        alignment = 1.22 if category == "special" else 0.72
    else:
        alignment = 1.08

    coverage = 1.04 if stab == 1.0 else 1.0
    return move.power * accuracy * stab * alignment * coverage


def _ideal_moves(
    pokemon: PokemonData,
    moves: dict[str, MoveData],
    role: str,
    offense: str,
) -> tuple[str, ...]:
    learnable = {entry.move for entry in pokemon.learnset}
    candidates = [moves[slug] for slug in learnable if slug in moves]
    damaging = sorted(candidates, key=lambda move: _damage_score(pokemon, move, offense), reverse=True)

    chosen: list[MoveData] = []
    used_types: set[str] = set()
    for move in damaging:
        if _damage_score(pokemon, move, offense) < 0:
            continue
        move_type = move.type.lower()
        if move_type in used_types and len(chosen) >= 2:
            continue
        chosen.append(move)
        used_types.add(move_type)
        if len(chosen) >= 4:
            break

    status_scores: dict[str, float] = defaultdict(float)
    for move_slug in learnable:
        if move_slug in _SETUP_MOVES:
            status_scores[move_slug] = _SETUP_MOVES[move_slug] + (
                8 if "sweeper" in role or role == "breaker" else 0
            )
        if move_slug in _RECOVERY_MOVES:
            status_scores[move_slug] = max(
                status_scores[move_slug], 46 if "wall" in role or "bulky" in role else 30
            )
        if move_slug in _UTILITY_MOVES:
            status_scores[move_slug] = max(
                status_scores[move_slug], 40 if "utility" in role or "wall" in role else 24
            )

    if status_scores:
        best_status = max(status_scores, key=status_scores.get)
        status_move = moves.get(best_status)
        if status_move is not None:
            replace = 1 if "sweeper" in role or role in {"defensive wall", "fast utility"} else 0
            if replace and len(chosen) >= 3:
                chosen[-1] = status_move
            elif len(chosen) < 4:
                chosen.append(status_move)

    return tuple(move.name for move in chosen[:4])


def build_strategy_profile(pokemon: PokemonData, moves: dict[str, MoveData]) -> StrategyProfile:
    role, offense = _role(pokemon)
    nature, evs, item = _nature_and_evs(pokemon, role, offense)
    ability = _preferred_ability(pokemon, moves)
    ideal_moves = _ideal_moves(pokemon, moves, role, offense)

    notes = [
        f"Renegade role generated from {pokemon.name}'s actual synced stats and typing.",
        "Ability choice is scored against this species' actual Renegade learnset.",
        "Battle-time decisions still override the ideal build when matchup, HP, PP or risk demands it.",
    ]
    return StrategyProfile(
        pokemon=pokemon.slug,
        role=role,
        offense=offense,
        nature=nature,
        evs=evs,
        item=item,
        ability=ability,
        ideal_moves=ideal_moves,
        notes=tuple(notes),
    )


def build_all_profiles(
    pokemon: dict[str, PokemonData], moves: dict[str, MoveData]
) -> dict[str, StrategyProfile]:
    return {slug: build_strategy_profile(record, moves) for slug, record in pokemon.items()}
