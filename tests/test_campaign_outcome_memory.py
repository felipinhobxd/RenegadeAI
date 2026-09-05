from renegade_ai.actions import DSButton
from renegade_ai.campaign.outcome_memory import CampaignOutcomeMemory
from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.memory.platinum import StructuredLocation


def loc(map_id: int, x: int, z: int) -> StructuredLocation:
    return StructuredLocation(
        map_header_id=map_id,
        map_name=f"MAP_{map_id}",
        warp_id=-1,
        x=x,
        z=z,
        face_direction=0,
        facing="up",
    )


def memory(tmp_path) -> CampaignOutcomeMemory:
    return CampaignOutcomeMemory(
        tmp_path / "outcomes.json",
        telemetry_path=tmp_path / "telemetry.jsonl",
    )


def test_same_location_builds_action_penalty_and_persists(tmp_path):
    outcomes = memory(tmp_path)
    before = loc(3, 5, 5)
    for _ in range(3):
        outcomes.record_transition(
            before,
            DSButton.UP,
            before,
            objective_id="reach_lab",
        )

    assert outcomes.action_penalty("reach_lab", before, DSButton.UP) > 10.0
    reloaded = memory(tmp_path)
    assert reloaded.action_penalty("reach_lab", before, DSButton.UP) > 10.0


def test_recent_loop_tiles_cost_more_than_unvisited_tiles(tmp_path):
    outcomes = memory(tmp_path)
    here = loc(3, 5, 5)
    other = loc(3, 6, 5)
    for _ in range(6):
        outcomes.observe_state(here, objective_id="goal", story_digest="same")
        outcomes.observe_state(other, objective_id="goal", story_digest="same")

    assert outcomes.tile_penalty(3, GridPoint(5, 5)) > outcomes.tile_penalty(
        3, GridPoint(20, 20)
    )
    state = outcomes.observe_state(here, objective_id="goal", story_digest="same")
    assert state["loop_level"] >= 1


def test_story_progress_resets_short_term_loop(tmp_path):
    outcomes = memory(tmp_path)
    here = loc(3, 5, 5)
    for _ in range(8):
        outcomes.observe_state(here, objective_id="goal", story_digest="before")
    assert outcomes.observe_state(
        here, objective_id="goal", story_digest="before"
    )["loop_level"] >= 1

    progressed = outcomes.observe_state(
        here,
        objective_id="next_goal",
        story_digest="after",
    )
    assert progressed["story_changed"] is True
    assert progressed["objective_changed"] is True
    assert progressed["loop_level"] == 0


def test_useless_target_is_suppressed_but_success_forgives_it(tmp_path):
    outcomes = memory(tmp_path)
    target = GridPoint(8, 9)
    for _ in range(2):
        outcomes.record_target_result(
            objective_id="story",
            map_id=3,
            point=target,
            kind="interaction",
            success=False,
        )

    assert outcomes.target_suppressed("story", 3, target, "interaction") is True
    outcomes.record_target_result(
        objective_id="story",
        map_id=3,
        point=target,
        kind="interaction",
        success=True,
    )
    assert outcomes.target_suppressed("story", 3, target, "interaction") is False
