import numpy as np

from renegade_ai.actions import DSButton
from renegade_ai.campaign.navigation import VisualTopoNavigator


def image(value: int):
    return np.full((192, 256, 3), value, dtype=np.uint8)


def test_visual_navigator_records_and_reloads_transition(tmp_path):
    path = tmp_path / "map.json"
    navigator = VisualTopoNavigator(path)
    first = navigator.observe(image(0))
    second = navigator.observe(image(240))

    navigator.record_transition(first, DSButton.UP, second)
    assert navigator.nodes[first].edges["up"] == second
    assert navigator.stats()["steps"] == 1

    loaded = VisualTopoNavigator(path)
    assert loaded.nodes[first].edges["up"] == second
    assert loaded.total_steps == 1


def test_visual_navigator_marks_unchanged_direction_blocked(tmp_path):
    navigator = VisualTopoNavigator(tmp_path / "map.json")
    state = navigator.observe(image(32))
    navigator.record_transition(state, DSButton.UP, state)

    assert "up" in navigator.nodes[state].blocked
    assert navigator.choose(state) == DSButton.RIGHT


def test_visual_navigator_routes_to_nearest_frontier(tmp_path):
    navigator = VisualTopoNavigator(tmp_path / "map.json")
    first = navigator.observe(image(0))
    second = navigator.observe(image(96))

    # Exhaust the current node but leave the second node unexplored.
    navigator.nodes[first].attempts = {button.value: 1 for button in (
        DSButton.UP,
        DSButton.RIGHT,
        DSButton.DOWN,
        DSButton.LEFT,
    )}
    navigator.nodes[first].edges["right"] = second

    assert navigator.choose(first) == DSButton.RIGHT
