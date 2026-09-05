from renegade_ai.actions import DSButton
from renegade_ai.campaign.live_progression import LiveProgressionDirector
from renegade_ai.campaign.objectives import StoryObjective
from renegade_ai.campaign.outcome_memory import CampaignOutcomeMemory
from renegade_ai.campaign.structured_navigation import GridNode, StructuredGridNavigator
from renegade_ai.memory.platinum import StructuredLocation


class FakeWorld:
    def header_name(self, header_id: int) -> str:
        return f"MAP_{header_id}"

    def is_colliding(self, _header_id: int, _x: int, _z: int) -> bool:
        return False

    def portals_between(self, _source: int, _destination: int):
        return ()

    def map_neighbors(self, _source: int) -> set[int]:
        return set()


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


def director(tmp_path) -> LiveProgressionDirector:
    outcomes = CampaignOutcomeMemory(
        tmp_path / "outcomes.json",
        telemetry_path=tmp_path / "telemetry.jsonl",
    )
    return LiveProgressionDirector(world=FakeWorld(), outcome_memory=outcomes)


def test_live_progression_reuses_observed_cross_map_warp(tmp_path):
    navigator = StructuredGridNavigator(tmp_path / "map.json")
    navigator.nodes["3:5:5"] = GridNode(edges={"right": "4:2:8"})

    planner = director(tmp_path)
    objective = StoryObjective("next", "Reach next map", ("MAP_4",))
    decision = planner._decision_to_portal(
        loc(3, 5, 5),
        4,
        objective,
        navigator,
        (),
    )

    assert decision is not None
    assert decision.action == DSButton.RIGHT
    assert decision.portal is not None
    assert decision.portal["kind"] == "observed_renegade_warp"


def test_live_progression_astar_routes_to_observed_warp_source(tmp_path):
    navigator = StructuredGridNavigator(tmp_path / "map.json")
    navigator.nodes["3:5:5"] = GridNode(edges={"up": "4:9:9"})

    planner = director(tmp_path)
    objective = StoryObjective("next", "Reach next map", ("MAP_4",))
    decision = planner._decision_to_portal(
        loc(3, 3, 5),
        4,
        objective,
        navigator,
        (),
    )

    assert decision is not None
    assert decision.action == DSButton.RIGHT
    assert decision.path_length == 2


def test_combined_map_route_can_use_only_live_renegade_transitions(tmp_path):
    navigator = StructuredGridNavigator(tmp_path / "map.json")
    navigator.nodes["3:5:5"] = GridNode(edges={"right": "4:2:8"})
    navigator.nodes["4:2:8"] = GridNode(edges={"up": "5:9:9"})

    planner = director(tmp_path)
    assert planner._combined_map_route(3, {5}, navigator) == [3, 4, 5]
