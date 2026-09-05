from renegade_ai.actions import DSButton
from renegade_ai.campaign.pathfinding import GridPoint, astar_path, first_action


def test_astar_routes_around_collision_wall():
    blocked = {GridPoint(1, 0), GridPoint(1, 1)}
    path = astar_path(
        GridPoint(0, 0),
        GridPoint(2, 0),
        is_walkable=lambda point: (
            -1 <= point.x <= 3 and -1 <= point.z <= 2 and point not in blocked
        ),
    )

    assert path is not None
    assert path[0] == GridPoint(0, 0)
    assert path[-1] == GridPoint(2, 0)
    assert all(point not in blocked for point in path)
    assert first_action(path) in {DSButton.UP, DSButton.DOWN, DSButton.LEFT}


def test_astar_returns_none_when_goal_is_colliding():
    goal = GridPoint(1, 0)
    path = astar_path(
        GridPoint(0, 0),
        goal,
        is_walkable=lambda point: point != goal,
    )
    assert path is None
