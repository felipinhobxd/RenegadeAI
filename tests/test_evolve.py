from renegade_ai.learning.evolve import ASIEvolveEngine, RewardKind


def engine(tmp_path):
    return ASIEvolveEngine(
        state_path=tmp_path / "state.json",
        qtable_path=tmp_path / "qtable.json",
        ledger_path=tmp_path / "rewards.jsonl",
    )


def test_damage_reward_prefers_dealing_more_and_taking_less(tmp_path):
    evolve = engine(tmp_path)
    dealt = evolve.record(RewardKind.DAMAGE_DEALT, magnitude=0.50)
    taken = evolve.record(RewardKind.DAMAGE_TAKEN, magnitude=0.25)
    assert dealt == 60.0
    assert taken == -22.5
    assert evolve.state.lifetime_reward == 37.5


def test_one_time_milestone_is_deduplicated(tmp_path):
    evolve = engine(tmp_path)
    first = evolve.record(RewardKind.BADGE, token="coal-badge")
    second = evolve.record(RewardKind.BADGE, token="coal-badge")
    assert first == 600.0
    assert second == 0.0
    assert evolve.state.badges == 1


def test_action_correction_requires_repeated_evidence(tmp_path):
    evolve = engine(tmp_path)
    state = "battle:chimchar:nidoran-f:l0:ol0:PSN"
    action = "move:ember"
    assert evolve.correction(state, action) == 0.0
    for _ in range(6):
        evolve.record(
            RewardKind.OBJECTIVE_PROGRESS,
            magnitude=0.25,
            state_key=state,
            action_id=action,
        )
    assert 0.0 < evolve.correction(state, action) <= 22.0


def test_game_completion_has_large_long_horizon_reward(tmp_path):
    evolve = engine(tmp_path)
    reward = evolve.record(RewardKind.GAME_COMPLETE, token="hall-of-fame-first-clear")
    assert reward == 5000.0
    assert evolve.state.game_completions == 1
