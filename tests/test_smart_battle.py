from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.strategy.battle import rank_moves


def pokemon(name: str, types: tuple[str, ...], attack: int, special_attack: int) -> PokemonData:
    return PokemonData(
        dex=1,
        slug=name.lower(),
        name=name,
        types=types,
        abilities=(),
        hp=60,
        attack=attack,
        defense=60,
        special_attack=special_attack,
        special_defense=60,
        speed=60,
    )


def move(name: str, move_type: str, category: str, power: int) -> MoveData:
    return MoveData(
        slug=name.lower().replace(" ", "-"),
        name=name,
        type=move_type,
        category=category,
        power=power,
        accuracy=100,
        pp=25,
    )


def test_chimchar_prefers_scratch_over_resisted_ember_against_water():
    chimchar = pokemon("Chimchar", ("Fire",), 58, 58)
    piplup = pokemon("Piplup", ("Water",), 51, 61)
    ranked = rank_moves(
        chimchar,
        piplup,
        [
            move("Scratch", "Normal", "Physical", 40),
            move("Leer", "Normal", "Status", 0),
            move("Ember", "Fire", "Special", 40),
        ],
    )
    assert ranked[0].move.name == "Scratch"


def test_chimchar_prefers_stab_ember_against_grass():
    chimchar = pokemon("Chimchar", ("Fire",), 58, 58)
    turtwig = pokemon("Turtwig", ("Grass",), 68, 45)
    ranked = rank_moves(
        chimchar,
        turtwig,
        [
            move("Scratch", "Normal", "Physical", 40),
            move("Ember", "Fire", "Special", 40),
        ],
    )
    assert ranked[0].move.name == "Ember"
    assert ranked[0].effectiveness == 2.0
