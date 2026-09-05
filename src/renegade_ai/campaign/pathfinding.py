from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from renegade_ai.actions import DSButton


@dataclass(frozen=True, order=True, slots=True)
class GridPoint:
    x: int
    z: int

    def manhattan(self, other: GridPoint) -> int:
        return abs(self.x - other.x) + abs(self.z - other.z)


_DIRECTION_DELTAS: tuple[tuple[DSButton, int, int], ...] = (
    (DSButton.UP, 0, -1),
    (DSButton.RIGHT, 1, 0),
    (DSButton.DOWN, 0, 1),
    (DSButton.LEFT, -1, 0),
)


def neighbors(point: GridPoint) -> Iterable[tuple[DSButton, GridPoint]]:
    for action, dx, dz in _DIRECTION_DELTAS:
        yield action, GridPoint(point.x + dx, point.z + dz)


def direction_between(source: GridPoint, destination: GridPoint) -> DSButton:
    dx = destination.x - source.x
    dz = destination.z - source.z
    for action, action_dx, action_dz in _DIRECTION_DELTAS:
        if (dx, dz) == (action_dx, action_dz):
            return action
    raise ValueError(f"Points are not cardinally adjacent: {source} -> {destination}")


def astar_path(
    start: GridPoint,
    goal: GridPoint,
    *,
    is_walkable: Callable[[GridPoint], bool],
    step_cost: Callable[[GridPoint], float] | None = None,
    max_expansions: int = 20000,
) -> list[GridPoint] | None:
    """Find a shortest cardinal path, including ``start`` and ``goal``.

    The caller owns game-specific passability. This lets the campaign planner
    combine Platinum's static collision map with live dynamic blockers learned
    from the current save. Unknown tiles may be assigned a higher ``step_cost``
    rather than being treated as permanently impossible.
    """
    if start == goal:
        return [start]
    if not is_walkable(goal):
        return None

    cost = step_cost or (lambda _point: 1.0)
    frontier: list[tuple[float, int, GridPoint]] = []
    counter = 0
    heapq.heappush(frontier, (float(start.manhattan(goal)), counter, start))
    came_from: dict[GridPoint, GridPoint] = {}
    g_score: dict[GridPoint, float] = {start: 0.0}
    closed: set[GridPoint] = set()
    expansions = 0

    while frontier and expansions < max_expansions:
        _priority, _tie, current = heapq.heappop(frontier)
        if current in closed:
            continue
        if current == goal:
            path = [current]
            while current != start:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        closed.add(current)
        expansions += 1
        for _action, nxt in neighbors(current):
            if nxt in closed or not is_walkable(nxt):
                continue
            candidate = g_score[current] + max(0.001, float(cost(nxt)))
            if candidate >= g_score.get(nxt, float("inf")):
                continue
            came_from[nxt] = current
            g_score[nxt] = candidate
            counter += 1
            priority = candidate + nxt.manhattan(goal)
            heapq.heappush(frontier, (priority, counter, nxt))
    return None


def first_action(path: list[GridPoint] | None) -> DSButton | None:
    if not path or len(path) < 2:
        return None
    return direction_between(path[0], path[1])
