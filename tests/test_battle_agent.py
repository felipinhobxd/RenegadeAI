from renegade_ai.agent.battle import BattleAgent, BattleState, MoveOption
from renegade_ai.learning.qtable import QTable


def test_battle_agent_prefers_reliable_ko():
    agent = BattleAgent(QTable(epsilon=0.0))
    state = BattleState(
        own_name="Infernape",
        own_hp_fraction=0.8,
        opponent_name="Abomasnow",
        opponent_hp_fraction=0.5,
        moves=(
            MoveOption("Close Combat", damage_fraction=0.8, accuracy=1.0, effectiveness=2.0),
            MoveOption("Stone Edge", damage_fraction=0.9, accuracy=0.8, effectiveness=1.0),
        ),
    )
    decision = agent.choose(state)
    assert decision.action_id == "move:close combat"
    assert "learned_q" in decision.reason
