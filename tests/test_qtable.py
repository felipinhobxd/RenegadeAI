from renegade_ai.learning.qtable import QTable


def test_q_update_moves_toward_reward():
    q = QTable(alpha=0.5, gamma=0.9, epsilon=0.0)
    updated = q.update("s1", "move:a", reward=1.0, next_state=None)
    assert updated == 0.5
    assert q.q("s1", "move:a") == 0.5


def test_select_combines_heuristic_and_learning():
    q = QTable(epsilon=0.0)
    q.values = {"state": {"move:safe": 0.8}}
    selected = q.select(
        "state",
        ["move:strong", "move:safe"],
        {"move:strong": 1.0, "move:safe": 0.4},
    )
    assert selected == "move:safe"
