from renegade_ai.knowledge.models import LearnMove, MoveData, PokemonData
from renegade_ai.strategy.profiles import build_strategy_profile


def test_special_sweeper_profile_uses_special_stab_and_speed_evs():
    pokemon = PokemonData(
        dex=999,
        slug="testmon",
        name="Testmon",
        types=("Fire", "Dragon"),
        abilities=("Blaze", "Levitate"),
        hp=78,
        attack=70,
        defense=75,
        special_attack=120,
        special_defense=85,
        speed=105,
        learnset=(
            LearnMove("flamethrower", "level-up", 30),
            LearnMove("dragon-pulse", "level-up", 40),
            LearnMove("scratch", "level-up", 1),
        ),
    )
    moves = {
        "flamethrower": MoveData("flamethrower", "Flamethrower", "Fire", "Special", 90, 100, 15),
        "dragon-pulse": MoveData("dragon-pulse", "Dragon Pulse", "Dragon", "Special", 85, 100, 10),
        "scratch": MoveData("scratch", "Scratch", "Normal", "Physical", 40, 100, 35),
    }

    profile = build_strategy_profile(pokemon, moves)

    assert profile.role == "fast sweeper"
    assert profile.offense == "special"
    assert profile.nature == "Timid"
    assert "252 SpA" in profile.evs
    assert "Flamethrower" in profile.ideal_moves
    assert "Dragon Pulse" in profile.ideal_moves
    assert profile.ability == "Levitate"
