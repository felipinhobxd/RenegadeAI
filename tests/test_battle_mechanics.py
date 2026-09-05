from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.state.runtime import RuntimePokemon
from renegade_ai.strategy.battle import rank_moves, score_move
from renegade_ai.strategy.mechanics import move_power_multiplier


def pokemon(name: str, types: tuple[str, ...], **stats: int) -> PokemonData:
    defaults = {
        "hp": 60,
        "attack": 60,
        "defense": 60,
        "special_attack": 60,
        "special_defense": 60,
        "speed": 60,
    }
    defaults.update(stats)
    return PokemonData(
        dex=1,
        slug=name.lower(),
        name=name,
        types=types,
        abilities=(),
        **defaults,
    )


def move(name: str, move_type: str, category: str, power: int) -> MoveData:
    return MoveData(
        slug=name.lower().replace(" ", "-"),
        name=name,
        type=move_type,
        category=category,
        power=power,
        accuracy=100,
        pp=20,
    )


def test_iron_fist_boosts_punches_but_not_scratch():
    mach_punch = move("Mach Punch", "Fighting", "Physical", 40)
    scratch = move("Scratch", "Normal", "Physical", 40)
    assert move_power_multiplier("Iron Fist", mach_punch) == 1.2
    assert move_power_multiplier("Iron Fist", scratch) == 1.0


def test_zero_pp_move_is_never_selected_over_usable_move():
    own = pokemon("Chimchar", ("Fire",), attack=58, special_attack=58)
    foe = pokemon("Nidoran Female", ("Poison",), defense=52, special_defense=40)
    runtime = RuntimePokemon(
        slug="chimchar",
        name="Chimchar",
        level=5,
        attack=11,
        special_attack=11,
        ability="Iron Fist",
        status="PSN",
    )
    ranked = rank_moves(
        own,
        foe,
        [move("Scratch", "Normal", "Physical", 40), move("Ember", "Fire", "Special", 40)],
        pp_fractions=[0.0, 1.0],
        own_level=5,
        opponent_level=5,
        own_runtime=runtime,
    )
    assert ranked[0].move.name == "Ember"


def test_levitate_makes_ground_move_score_zero():
    own = pokemon("Garchomp", ("Dragon", "Ground"), attack=130)
    foe = pokemon("Rotom", ("Electric", "Ghost"), defense=77)
    earthquake = move("Earthquake", "Ground", "Physical", 100)
    foe_runtime = RuntimePokemon(slug="rotom", name="Rotom", ability="Levitate")
    score, effectiveness_value, _stab, reason = score_move(
        own,
        foe,
        earthquake,
        opponent_runtime=foe_runtime,
    )
    assert score == 0.0
    assert effectiveness_value == 0.0
    assert "immune" in reason
