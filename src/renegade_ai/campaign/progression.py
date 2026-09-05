from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.campaign.objectives import StoryObjective, StoryObjectivePlanner
from renegade_ai.campaign.pathfinding import GridPoint, astar_path, direction_between, neighbors
from renegade_ai.campaign.structured_navigation import StructuredGridNavigator
from renegade_ai.campaign.world_model import BoundaryPortal, PlatinumWorldModel, WarpPortal
from renegade_ai.memory.platinum import (
    StructuredFieldObject,
    StructuredLocation,
    StructuredProgress,
    StructuredStoryState,
)


@dataclass(frozen=True, slots=True)
class ProgressionDecision:
    action: DSButton | None
    objective: StoryObjective | None
    reason: str
    target_map_id: int | None = None
    target_map_name: str | None = None
    target: GridPoint | None = None
    path_length: int | None = None
    portal: dict[str, Any] | None = None
    should_interact: bool = False


class ProgressionDirector:
    """Turn story objectives into concrete collision-aware movement actions."""

    def __init__(
        self,
        *,
        world: PlatinumWorldModel | None = None,
        objectives: StoryObjectivePlanner | None = None,
    ) -> None:
        self.world = world or PlatinumWorldModel()
        self.objectives = objectives or StoryObjectivePlanner()
        self.last_decision: ProgressionDecision | None = None

    @staticmethod
    def _node_parts(key: str) -> tuple[int, int, int] | None:
        try:
            map_id, x, z = (int(value) for value in key.split(":", 2))
        except (TypeError, ValueError):
            return None
        return map_id, x, z

    def _live_blocked_tiles(
        self,
        location: StructuredLocation,
        navigator: StructuredGridNavigator,
    ) -> set[GridPoint]:
        blocked: set[GridPoint] = set()
        deltas = {
            "up": (0, -1),
            "right": (1, 0),
            "down": (0, 1),
            "left": (-1, 0),
        }
        for key, node in navigator.nodes.items():
            parsed = self._node_parts(key)
            if parsed is None or parsed[0] != location.map_header_id:
                continue
            _map_id, x, z = parsed
            for raw in node.blocked:
                delta = deltas.get(raw)
                if delta is not None:
                    blocked.add(GridPoint(x + delta[0], z + delta[1]))
        return blocked

    def _walkability(
        self,
        location: StructuredLocation,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
        *,
        allowed_goal: GridPoint | None = None,
    ):
        live_blocked = self._live_blocked_tiles(location, navigator)
        object_tiles = {GridPoint(obj.x, obj.z) for obj in field_objects}

        def is_walkable(point: GridPoint) -> bool:
            if point.x < 0 or point.z < 0:
                return False
            if allowed_goal is not None and point == allowed_goal:
                return True
            if point in object_tiles or point in live_blocked:
                return False
            collision = self.world.is_colliding(location.map_header_id, point.x, point.z)
            return collision is not True

        def step_cost(point: GridPoint) -> float:
            collision = self.world.is_colliding(location.map_header_id, point.x, point.z)
            # Known walkable terrain is preferred over an unknown static block.
            # Live successful movement will quickly override uncertainty anyway.
            return 1.0 if collision is False else 2.5

        return is_walkable, step_cost

    def _path_to(
        self,
        location: StructuredLocation,
        target: GridPoint,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
        *,
        allow_goal_occupied: bool = False,
    ) -> list[GridPoint] | None:
        start = GridPoint(location.x, location.z)
        walkable, cost = self._walkability(
            location,
            navigator,
            field_objects,
            allowed_goal=target if allow_goal_occupied else None,
        )
        return astar_path(start, target, is_walkable=walkable, step_cost=cost)

    def _interaction_targets(self, header_id: int, objective: StoryObjective) -> list[GridPoint]:
        events = self.world.events(header_id)
        raw_objects = events.get("object_events", ())
        scored: list[tuple[int, GridPoint]] = []
        hint = (objective.target_hint or "").upper()
        for raw in raw_objects:
            if not isinstance(raw, dict):
                continue
            try:
                point = GridPoint(int(raw["x"]), int(raw["z"]))
            except (KeyError, TypeError, ValueError):
                continue
            object_id = str(raw.get("id", "")).upper()
            trainer_type = str(raw.get("trainer_type", "")).upper()
            hidden_flag = str(raw.get("hidden_flag", "0")).upper()
            score = 0
            if hint and hint.replace(" ", "_") in object_id:
                score += 100
            if "LEADER" in object_id or "ROARK" in object_id or "CYRUS" in object_id:
                score += 80
            if trainer_type not in {"", "0", "TRAINER_TYPE_NONE"}:
                score += 45
            if "RIVAL" in object_id or "PROF" in object_id:
                score += 25
            if hidden_flag not in {"", "0"}:
                score += 3
            if score > 0:
                scored.append((score, point))
        scored.sort(key=lambda pair: -pair[0])
        return [point for _score, point in scored]

    def _approach_object(
        self,
        location: StructuredLocation,
        target: GridPoint,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
    ) -> tuple[list[GridPoint] | None, DSButton | None]:
        start = GridPoint(location.x, location.z)
        best_path: list[GridPoint] | None = None
        best_face: DSButton | None = None
        for face_action, adjacent in neighbors(target):
            # ``face_action`` points from the target to adjacent, so reverse it
            # when the player stands on adjacent and needs to face the target.
            reverse = {
                DSButton.UP: DSButton.DOWN,
                DSButton.DOWN: DSButton.UP,
                DSButton.LEFT: DSButton.RIGHT,
                DSButton.RIGHT: DSButton.LEFT,
            }[face_action]
            path = self._path_to(location, adjacent, navigator, field_objects)
            if path is None:
                continue
            if best_path is None or len(path) < len(best_path):
                best_path = path
                best_face = reverse
        if best_path is not None and len(best_path) == 1:
            return best_path, best_face
        if best_path and start == best_path[0]:
            return best_path, best_face
        return best_path, best_face

    def _decision_to_portal(
        self,
        location: StructuredLocation,
        next_map_id: int,
        objective: StoryObjective,
        navigator: StructuredGridNavigator,
        field_objects: tuple[StructuredFieldObject, ...],
    ) -> ProgressionDecision | None:
        current = GridPoint(location.x, location.z)
        portals = self.world.portals_between(location.map_header_id, next_map_id)
        best: tuple[int, WarpPortal | BoundaryPortal, list[GridPoint]] | None = None
        for portal in portals:
            path = self._path_to(location, portal.source, navigator, field_objects)
            if path is None:
                continue
            candidate = (len(path), portal, path)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None:
            return None

        _length, portal, path = best
        if len(path) >= 2:
            action = direction_between(path[0], path[1])
            return ProgressionDecision(
                action,
                objective,
                f"A* toward {portal.kind} leading to {self.world.header_name(next_map_id)}",
                target_map_id=next_map_id,
                target_map_name=self.world.header_name(next_map_id),
                target=portal.source,
                path_length=len(path) - 1,
                portal=self.world.portal_dict(portal),
            )

        # Standing on a warp usually triggers it by stepping onto the tile, so
        # a path of length one means re-evaluate surroundings. Matrix boundaries
        # need one step across into the destination cell.
        if isinstance(portal, BoundaryPortal):
            action = direction_between(current, portal.destination)
            return ProgressionDecision(
                action,
                objective,
                f"Cross matrix boundary into {self.world.header_name(next_map_id)}",
                target_map_id=next_map_id,
                target_map_name=self.world.header_name(next_map_id),
                target=portal.destination,
                path_length=1,
                portal=self.world.portal_dict(portal),
            )
        return ProgressionDecision(
            None,
            objective,
            "Standing on target warp; wait/re-observe before fallback exploration",
            target_map_id=next_map_id,
            target_map_name=self.world.header_name(next_map_id),
            target=portal.source,
            path_length=0,
            portal=self.world.portal_dict(portal),
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
        visited_maps = set(navigator.maps_seen.values())
        objective = self.objectives.choose(
            current_map=location.map_name,
            progress=progress,
            story=story,
            visited_maps=visited_maps,
        )
        if objective is None:
            decision = ProgressionDecision(None, None, "Main story is already complete")
            self.last_decision = decision
            return decision

        goal_ids = {
            header_id
            for map_name in objective.target_maps
            if (header_id := self.world.header_id(map_name)) is not None
        }
        if not goal_ids:
            decision = ProgressionDecision(
                None,
                objective,
                "Objective map names are not available in the current map-header catalog",
            )
            self.last_decision = decision
            return decision

        if location.map_header_id not in goal_ids:
            map_path = self.world.map_route(location.map_header_id, goal_ids)
            if map_path and len(map_path) >= 2:
                planned = self._decision_to_portal(
                    location,
                    map_path[1],
                    objective,
                    navigator,
                    field_objects,
                )
                if planned is not None:
                    self.last_decision = planned
                    return planned
                reason = (
                    f"World route exists ({len(map_path) - 1} map transitions) but no "
                    "currently reachable portal has a valid local A* path"
                )
            else:
                reason = "Static warp/matrix graph does not yet expose a route to this objective"
            decision = ProgressionDecision(
                None,
                objective,
                reason,
                target_map_id=next(iter(goal_ids)),
                target_map_name=self.world.header_name(next(iter(goal_ids))),
            )
            self.last_decision = decision
            return decision

        # We reached the objective map. For interaction objectives, use static
        # event objects to seek likely leaders/trainers/story NPCs rather than
        # walking the room at random.
        if objective.interact:
            candidates = self._interaction_targets(location.map_header_id, objective)
            for target in candidates:
                path, face = self._approach_object(location, target, navigator, field_objects)
                if path is None:
                    continue
                if len(path) >= 2:
                    action = direction_between(path[0], path[1])
                    decision = ProgressionDecision(
                        action,
                        objective,
                        "A* toward likely story/trainer interaction target",
                        target_map_id=location.map_header_id,
                        target_map_name=location.map_name,
                        target=target,
                        path_length=len(path) - 1,
                        should_interact=True,
                    )
                    self.last_decision = decision
                    return decision
                if face is not None:
                    decision = ProgressionDecision(
                        face,
                        objective,
                        "Adjacent to likely story target; face it so the runtime can interact",
                        target_map_id=location.map_header_id,
                        target_map_name=location.map_name,
                        target=target,
                        path_length=0,
                        should_interact=True,
                    )
                    self.last_decision = decision
                    return decision

        decision = ProgressionDecision(
            None,
            objective,
            "Objective map reached; use structured frontier exploration for the local puzzle/event",
            target_map_id=location.map_header_id,
            target_map_name=location.map_name,
        )
        self.last_decision = decision
        return decision

    def debug_state(self) -> dict[str, Any]:
        decision = self.last_decision
        return {
            "world": self.world.stats(),
            "objective": None if decision is None or decision.objective is None else asdict(decision.objective),
            "decision": None if decision is None else {
                "action": None if decision.action is None else decision.action.value,
                "reason": decision.reason,
                "target_map_id": decision.target_map_id,
                "target_map_name": decision.target_map_name,
                "target": None if decision.target is None else asdict(decision.target),
                "path_length": decision.path_length,
                "portal": decision.portal,
                "should_interact": decision.should_interact,
            },
        }
