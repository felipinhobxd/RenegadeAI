from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from renegade_ai.actions import DSButton
from renegade_ai.campaign.objectives import StoryObjective
from renegade_ai.campaign.outcome_memory import CampaignOutcomeMemory
from renegade_ai.campaign.pathfinding import GridPoint, direction_between
from renegade_ai.campaign.progression import ProgressionDecision, ProgressionDirector
from renegade_ai.campaign.structured_navigation import StructuredGridNavigator
from renegade_ai.memory.platinum import (
    StructuredFieldObject,
    StructuredLocation,
    StructuredProgress,
    StructuredStoryState,
)


@dataclass(frozen=True, slots=True)
class ObservedPortal:
    source_map_id: int
    destination_map_id: int
    source: GridPoint
    destination: GridPoint
    trigger_action: DSButton


class LiveProgressionDirector(ProgressionDirector):
    """Objective planner that overlays actual Renegade state on Platinum data.

    Static pret/pokeplatinum collision/warps are prior knowledge. Successful
    cross-map movement observed in the user's running Renegade save has higher
    authority and is reused first. Persistent outcome memory adds a second live
    layer: places/actions that repeatedly do nothing become more expensive, so
    A* and target selection stop repeating short dead loops.
    """

    def __init__(
        self,
        *args,
        outcome_memory: CampaignOutcomeMemory | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.outcomes = outcome_memory or CampaignOutcomeMemory()
        self.last_story_digest: str | None = None
        self.last_badge_count: int | None = None
        self.last_loop_level: int = 0

    def _walkability(
        self,
        location: StructuredLocation,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
        *,
        allowed_goal: GridPoint | None = None,
    ):
        is_walkable, base_cost = super()._walkability(
            location,
            navigator,
            field_objects,
            allowed_goal=allowed_goal,
        )

        def step_cost(point: GridPoint) -> float:
            return base_cost(point) + self.outcomes.tile_penalty(location.map_header_id, point)

        return is_walkable, step_cost

    def _interaction_targets(self, header_id: int, objective: StoryObjective) -> list[GridPoint]:
        targets = super()._interaction_targets(header_id, objective)
        if not targets:
            return targets
        ranked = [
            (
                self.outcomes.target_suppressed(
                    objective.id,
                    header_id,
                    point,
                    "interaction",
                ),
                self.outcomes.target_penalty(
                    objective.id,
                    header_id,
                    point,
                    "interaction",
                ),
                index,
                point,
            )
            for index, point in enumerate(targets)
        ]
        usable = [row for row in ranked if not row[0]]
        selected = usable or ranked
        selected.sort(key=lambda row: (row[1], row[2]))
        return [row[3] for row in selected]

    @staticmethod
    def _observed_portals(
        navigator: StructuredGridNavigator,
        source_map_id: int,
        destination_map_id: int,
    ) -> tuple[ObservedPortal, ...]:
        portals: list[ObservedPortal] = []
        for source_key, node in navigator.nodes.items():
            source = navigator._parts(source_key)
            if source is None or source[0] != source_map_id:
                continue
            for raw_action, destination_key in node.edges.items():
                destination = navigator._parts(destination_key)
                if destination is None or destination[0] != destination_map_id:
                    continue
                if destination[0] == source[0]:
                    continue
                try:
                    action = DSButton.parse(raw_action)
                except ValueError:
                    continue
                portals.append(
                    ObservedPortal(
                        source_map_id=source[0],
                        destination_map_id=destination[0],
                        source=GridPoint(source[1], source[2]),
                        destination=GridPoint(destination[1], destination[2]),
                        trigger_action=action,
                    )
                )
        return tuple(portals)

    @staticmethod
    def observed_map_neighbors(
        navigator: StructuredGridNavigator,
        source_map_id: int,
    ) -> set[int]:
        result: set[int] = set()
        for source_key, node in navigator.nodes.items():
            source = navigator._parts(source_key)
            if source is None or source[0] != source_map_id:
                continue
            for destination_key in node.edges.values():
                destination = navigator._parts(destination_key)
                if destination is not None and destination[0] != source_map_id:
                    result.add(destination[0])
        return result

    def _combined_map_route(
        self,
        start_map_id: int,
        goal_map_ids: set[int],
        navigator: StructuredGridNavigator,
        *,
        max_maps: int = 260,
    ) -> list[int] | None:
        """BFS the map graph using both static and actually observed portals."""
        if start_map_id in goal_map_ids:
            return [start_map_id]
        queue: deque[int] = deque([start_map_id])
        parent: dict[int, int | None] = {start_map_id: None}
        while queue and len(parent) <= max_maps:
            current = queue.popleft()
            neighbors = self.world.map_neighbors(current)
            neighbors.update(self.observed_map_neighbors(navigator, current))
            for nxt in sorted(neighbors):
                if nxt in parent:
                    continue
                parent[nxt] = current
                if nxt in goal_map_ids:
                    path = [nxt]
                    while path[-1] != start_map_id:
                        previous = parent[path[-1]]
                        if previous is None:
                            break
                        path.append(previous)
                    path.reverse()
                    return path
                queue.append(nxt)
        return None

    def _decision_to_portal(
        self,
        location: StructuredLocation,
        next_map_id: int,
        objective: StoryObjective,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
    ) -> ProgressionDecision | None:
        observed = self._observed_portals(
            navigator,
            location.map_header_id,
            next_map_id,
        )
        best: tuple[float, ObservedPortal, list[GridPoint]] | None = None
        for portal in observed:
            path = self._path_to(location, portal.source, navigator, field_objects)
            if path is None:
                continue
            source_penalty = self.outcomes.action_penalty(
                objective.id,
                location,
                portal.trigger_action,
            ) if len(path) == 1 else 0.0
            candidate = (len(path) + source_penalty, portal, path)
            if best is None or candidate[0] < best[0]:
                best = candidate

        if best is not None:
            _score, portal, path = best
            if len(path) >= 2:
                return ProgressionDecision(
                    direction_between(path[0], path[1]),
                    objective,
                    "A* toward a warp previously observed in live Renegade RAM",
                    target_map_id=next_map_id,
                    target_map_name=self.world.header_name(next_map_id),
                    target=portal.source,
                    path_length=len(path) - 1,
                    portal={
                        "kind": "observed_renegade_warp",
                        "source_map_id": portal.source_map_id,
                        "destination_map_id": portal.destination_map_id,
                        "source": {"x": portal.source.x, "z": portal.source.z},
                        "destination": {
                            "x": portal.destination.x,
                            "z": portal.destination.z,
                        },
                        "trigger_action": portal.trigger_action.value,
                    },
                )
            return ProgressionDecision(
                portal.trigger_action,
                objective,
                "Trigger previously observed live Renegade warp",
                target_map_id=next_map_id,
                target_map_name=self.world.header_name(next_map_id),
                target=portal.source,
                path_length=0,
                portal={
                    "kind": "observed_renegade_warp",
                    "trigger_action": portal.trigger_action.value,
                },
            )

        return super()._decision_to_portal(
            location,
            next_map_id,
            objective,
            navigator,
            field_objects,
        )

    def _decision_to_coord_event(
        self,
        location: StructuredLocation,
        objective: StoryObjective,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
    ) -> ProgressionDecision | None:
        candidates: list[tuple[bool, float, int, GridPoint, list[GridPoint]]] = []
        for raw in self.world.coord_events(location.map_header_id):
            try:
                x = int(raw["x"])
                z = int(raw["z"])
                width = max(1, int(raw.get("width", 1)))
                length = max(1, int(raw.get("length", 1)))
            except (KeyError, TypeError, ValueError):
                continue

            # Try the center first, then the rectangle's origin. Coordinate
            # events activate by stepping into their area; no A press is needed.
            points = [
                GridPoint(x + (width - 1) // 2, z + (length - 1) // 2),
                GridPoint(x, z),
            ]
            for point in dict.fromkeys(points):
                path = self._path_to(location, point, navigator, field_objects)
                if path is None or len(path) < 2:
                    continue
                suppressed = self.outcomes.target_suppressed(
                    objective.id,
                    location.map_header_id,
                    point,
                    "coord_event",
                )
                penalty = self.outcomes.target_penalty(
                    objective.id,
                    location.map_header_id,
                    point,
                    "coord_event",
                )
                candidates.append((suppressed, len(path) + penalty, len(path), point, path))

        if not candidates:
            return None
        usable = [value for value in candidates if not value[0]]
        selected = usable or candidates
        _suppressed, _score, _length, target, path = min(selected, key=lambda value: value[1])
        return ProgressionDecision(
            direction_between(path[0], path[1]),
            objective,
            "A* toward a scripted coordinate event on the current story-objective map",
            target_map_id=location.map_header_id,
            target_map_name=location.map_name,
            target=target,
            path_length=len(path) - 1,
            should_interact=False,
        )

    def decide(
        self,
        *,
        location: StructuredLocation,
        progress: StructuredProgress,
        story: StructuredStoryState | None,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...] = (),
    ) -> ProgressionDecision:
        base = super().decide(
            location=location,
            progress=progress,
            story=story,
            navigator=navigator,
            field_objects=field_objects,
        )
        objective = base.objective
        self.last_story_digest = None if story is None else story.digest
        self.last_badge_count = progress.badge_count
        observed = self.outcomes.observe_state(
            location,
            objective_id=None if objective is None else objective.id,
            story_digest=self.last_story_digest,
        )
        self.last_loop_level = int(observed["loop_level"])

        if objective is None or base.action is not None:
            self.last_decision = base
            return base

        goal_ids = {
            header_id
            for map_name in objective.target_maps
            if (header_id := self.world.header_id(map_name)) is not None
        }

        # If the static map graph cannot reach the objective, retry with any
        # cross-map transitions learned from this actual Renegade playthrough.
        if goal_ids and location.map_header_id not in goal_ids:
            route = self._combined_map_route(
                location.map_header_id,
                goal_ids,
                navigator,
            )
            if route and len(route) >= 2:
                planned = self._decision_to_portal(
                    location,
                    route[1],
                    objective,
                    navigator,
                    field_objects,
                )
                if planned is not None:
                    self.last_decision = planned
                    return planned

        # Once on the intended map, static object events are handled by the
        # base planner. Coordinate-triggered story scenes are the next safest
        # structured target before falling back to local frontier exploration.
        if objective.interact and location.map_header_id in goal_ids:
            coord = self._decision_to_coord_event(
                location,
                objective,
                navigator,
                field_objects,
            )
            if coord is not None:
                self.last_decision = coord
                return coord

        self.last_decision = base
        return base
