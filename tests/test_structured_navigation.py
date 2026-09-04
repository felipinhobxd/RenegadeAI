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


def test_structured_navigator_marks_blocked_and_explores_another_direction(tmp_path):
    nav = StructuredGridNavigator(tmp_path / "map.json")
    start = loc(10, 10)
    key, new_map = nav.observe(start)
    assert new_map is True

    first_action = nav.choose(key)
    moved = nav.record_transition(start, first_action, start)
    assert moved is False

    second_action = nav.choose(key)
    assert second_action != first_action
    assert second_action in {DSButton.UP, DSButton.RIGHT, DSButton.DOWN, DSButton.LEFT}
    assert first_action.value in nav.nodes[key].blocked


def test_structured_navigator_balances_directions_instead_of_repeating_up(tmp_path):
    nav = StructuredGridNavigator(tmp_path / "map.json")
    start = loc(10, 10)
    north = loc(10, 9)
    nav.observe(start)
    assert nav.record_transition(start, DSButton.UP, north) is True
    nav.observe(north)

    # UP has already been used on this map and DOWN is a known reverse edge.
    # A new tile should therefore explore a genuinely new side direction rather
    # than continuing the old global UP bias.
    assert nav.choose(north.key) in {DSButton.LEFT, DSButton.RIGHT}


def test_structured_navigator_records_safe_reverse_edge_for_backtracking(tmp_path):
    nav = StructuredGridNavigator(tmp_path / "map.json")
    start = loc(10, 10)
    right = loc(11, 10)

    assert nav.record_transition(start, DSButton.RIGHT, right) is True
    assert nav.nodes[start.key].edges["right"] == right.key
    assert nav.nodes[right.key].edges["left"] == start.key

    # Exhaust the destination's local frontier; it must know how to backtrack.
    nav.nodes[right.key].attempts.update({"up": 1, "right": 1, "down": 1})
    nav.nodes[right.key].blocked.extend(["up", "right", "down"])
    assert nav.choose_escape(right.key) == DSButton.LEFT


def test_transient_object_block_is_not_learned_as_a_wall(tmp_path):
    nav = StructuredGridNavigator(tmp_path / "map.json")
    start = loc(10, 10)
    assert nav.record_transition(
        start,
        DSButton.RIGHT,
        start,
        transient_block=True,
    ) is False
    assert "right" not in nav.nodes[start.key].blocked
