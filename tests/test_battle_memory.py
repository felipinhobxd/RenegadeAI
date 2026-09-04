from renegade_ai.knowledge.models import PokemonData
from renegade_ai.learning.battle_memory import (
    BattleAdaptiveMemory,
    PendingBattleAction,
    immediate_reward,
)
from renegade_ai.perception.battle_vision import BattleVisualState


def pokemon(slug: str) -> PokemonData:
    return PokemonData(
        dex=1,
        slug=slug,
        name=slug.title(),
        types=("Normal",),
        abilities=(),
        hp=60,
        attack=60,
        defense=60,
        special_attack=60,
        special_defense=60,
        speed=60,
    )


def state(*, own_hp: float, opponent_hp: float, opponent_slug: str = "foe") -> BattleVisualState:
    return BattleVisualState(
        own=pokemon("hero"),
        opponent=pokemon(opponent_slug),
        own_match_confidence=1.0,
        opponent_match_confidence=1.0,
        own_level=10,
        opponent_level=10,
        own_hp_fraction=own_hp,
        opponent_hp_fraction=opponent_hp,
        own_hp_current=None,
        own_hp_max=None,
        own_status=None,
        opponent_status=None,
        moves=(),
        move_confidences=(),
        pp_current=(),
        pp_max=(),
        raw_own_text=(),
        raw_opponent_text=(),
        raw_move_text=(),
    )


def test_immediate_reward_prefers_dealing_damage_over_taking_damage():
    previous = PendingBattleAction(
        state_key="battle:hero:foe:l1:ol1:healthy",
        action_id="move:tackle",
        own_slug="hero",
        opponent_slug="foe",
        own_hp=1.0,
        opponent_hp=1.0,
        own_status=None,
    )
    reward = immediate_reward(previous, state(own_hp=0.9, opponent_hp=0.5))
    assert reward is not None
    assert reward > 0


def test_adaptive_memory_persists_learned_value(tmp_path):
    path = tmp_path / "qtable.json"
    memory = BattleAdaptiveMemory(path)
    before = state(own_hp=1.0, opponent_hp=1.0)
    memory.remember(before, "tackle")
    reward = memory.observe_next_turn(state(own_hp=0.95, opponent_hp=0.6))
    assert reward is not None
    assert path.exists()

    loaded = BattleAdaptiveMemory(path)
    key = "battle:hero:foe:l1:ol1:healthy"
    assert loaded.qtable.q(key, "move:tackle") > 0
    assert 0 < loaded.correction(key, "move:tackle") <= 15
