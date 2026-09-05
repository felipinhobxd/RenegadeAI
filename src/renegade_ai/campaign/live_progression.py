from __future__ import annotations

from dataclasses import dataclass

from renegade_ai.actions import DSButton
from renegade_ai.campaign.objectives import StoryObjective
from renegade_ai.campaign.pathfinding import GridPoint, direction_between
from renegade_ai.campaign.progression import ProgressionDecision, ProgressionDirector
from renegade_ai.campaign.structured_navigation import StructuredGridNavigator
from renegade_ai.memory.platinum import StructuredFieldObject, StructuredLocation


@dataclass(frozen=True, slots=True)
class ObservedPortal:
    source_map_id: int
    destination_map_id: int
    source: GridPoint
    destination: GridPoint
    trigger_action: DSButton


class LiveProgressionDirector(ProgressionDirector):
    """Objective planner that overlays actual Renegade transitions on Platinum data.

    Static pret/pokeplatinum collision/warps are excellent prior knowledge, but
    a transition observed from the user's running Renegade Platinum save is the
    highest-authority evidence. Cross-map edges already learned by the exact RAM
    navigator are therefore reused as portals before static warp definitions.
    """

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
        best: tuple[int, ObservedPortal, list[GridPoint]] | None = None
        for portal in observed:
            path = self._path_to(location, portal.source, navigator, field_objects)
            if path is None:
                continue
            candidate = (len(path), portal, path)
            if best is None or candidate[0] < best[0]:
                best = candidate

        if best is not None:
            _length, portal, path = best
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
