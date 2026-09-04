from renegade_ai.actions import DSButton
from renegade_ai.campaign.structured_navigation import StructuredGridNavigator
from renegade_ai.memory.platinum import StructuredLocation


def loc(x: int, z: int, map_id: int = 3) -> StructuredLocation:
    return StructuredLocation(
        map_header_id=map_id,
        map_name="JUBILIFE_CITY",
        warp_id=-1,
        x=x,
        z=z,
        face_direction=0,
        facing="up",
    )


def test_structured_navigator_marks_blocked_and_explores_next_direction(tmp_path):
    nav = StructuredGridNavigator(tmp_path / "map.json")
    start = loc(10, 10)
    key, new_map = nav.observe(start)
    assert new_map is True
    assert nav.choose(key) == DSButton.UP

    moved = nav.record_transition(start, DSButton.UP, start)
    assert moved is False
    assert nav.choose(key) == DSButton.RIGHT

    right = loc(11, 10)
    assert nav.record_transition(start, DSButton.RIGHT, right) is True
    stats = nav.stats()
    assert stats["maps"] == 1
    assert stats["tiles"] == 2
    assert stats["blocked"] == 1
