from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.campaign.live_progression import LiveProgressionDirector
from renegade_ai.campaign.pathfinding import GridPoint
from renegade_ai.campaign.progression import ProgressionDecision
from renegade_ai.campaign.smart_runtime import _FIELD_LIKE, SmartCampaignAutopilot
from renegade_ai.learning.evolve import RewardKind
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene


def _looks_like_dialogue_box(image: Any) -> bool:
    """Cheap pre-OCR cue for Platinum's upper-screen dialogue box.

    Dialogue can begin automatically while the lower Poketch still resembles
    the normal overworld. A light, low-saturation rectangle with dark glyphs in
    the lower part of the upper DS screen is only a cue: OCR still has to
    confirm readable dialogue before any A press is issued.
    """
    import numpy as np

    rgb = np.asarray(image)[..., :3].astype(np.int16)
    if rgb.size == 0:
        return False
    height, width = rgb.shape[:2]
    region = rgb[int(height * 0.58) : int(height * 0.97), int(width * 0.02) : int(width * 0.98)]
    if region.size == 0:
        return False
    maximum = region.max(axis=2)
    minimum = region.min(axis=2)
    mean = region.mean(axis=2)
    neutral_light = (maximum - minimum < 55) & (mean > 125)
    dark_ink = maximum < 95
    return float(neutral_light.mean()) >= 0.32 and float(dark_ink.mean()) >= 0.012


@dataclass(slots=True)
class PendingTarget:
    objective_id: str
    map_id: int
    target: GridPoint
    kind: str
    story_digest: str | None
    badge_count: int | None

    @property
    def key(self) -> str:
        return f"{self.objective_id}|{self.map_id}:{self.target.x}:{self.target.z}|{self.kind}"


class ObjectiveCampaignAutopilot(SmartCampaignAutopilot):
    """Full campaign loop with goal routing, outcome learning and dialogue checks."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Preserve the world/objective caches created by the base class while
        # upgrading portal selection to prefer transitions actually observed in
        # the user's running Renegade Platinum save.
        self.progression = LiveProgressionDirector(
            world=self.progression.world,
            objectives=self.progression.objectives,
        )
        self._pending_target: PendingTarget | None = None

    def _evaluate_pending_target(
        self,
        location: Any,
        decision: ProgressionDecision | None,
    ) -> None:
        pending = self._pending_target
        if pending is None:
            return

        current_objective = None
        if decision is not None and decision.objective is not None:
            current_objective = decision.objective.id
        current_story = self.progression.last_story_digest
        current_badges = self.progression.last_badge_count
        success = (
            location.map_header_id != pending.map_id
            or (current_objective is not None and current_objective != pending.objective_id)
            or (
                pending.story_digest is not None
                and current_story is not None
                and current_story != pending.story_digest
            )
            or (
                pending.badge_count is not None
                and current_badges is not None
                and current_badges > pending.badge_count
            )
        )

        self.progression.outcomes.record_target_result(
            objective_id=pending.objective_id,
            map_id=pending.map_id,
            point=pending.target,
            kind=pending.kind,
            success=success,
        )
        state_key = f"story-target:{pending.key}"
        self.evolve.record(
            RewardKind.GOOD_TURN if success else RewardKind.BAD_TURN,
            magnitude=0.06 if success else 0.08,
            state_key=state_key,
            action_id=pending.kind,
            metadata={
                "source": "campaign_outcome_memory",
                "objective": pending.objective_id,
                "target": {"x": pending.target.x, "z": pending.target.z},
                "kind": pending.kind,
                "success": success,
            },
        )
        self._pending_target = None

    def _arm_pending_target(self, decision: ProgressionDecision | None) -> None:
        if decision is None or decision.objective is None or decision.target is None:
            return
        kind: str | None = None
        if decision.should_interact and decision.path_length == 0:
            kind = "interaction"
        elif (
            decision.path_length == 1
            and "coordinate event" in decision.reason.lower()
        ):
            kind = "coord_event"
        if kind is None:
            return

        pending = PendingTarget(
            objective_id=decision.objective.id,
            map_id=decision.target_map_id
            if decision.target_map_id is not None
            else -1,
            target=decision.target,
            kind=kind,
            story_digest=self.progression.last_story_digest,
            badge_count=self.progression.last_badge_count,
        )
        if self._pending_target is None or self._pending_target.key != pending.key:
            self._pending_target = pending

    def _progression_decision(self, location: Any) -> ProgressionDecision | None:
        decision = super()._progression_decision(location)
        if decision is None:
            return None
        # This method is reached only after the proactive dialogue handler has
        # had first chance to advance visible text. Therefore a pending target
        # surviving until this point can be evaluated using fresh story RAM.
        self._evaluate_pending_target(location, decision)
        self._arm_pending_target(decision)
        return decision

    def _record_navigation_outcome(
        self,
        before: Any,
        action: DSButton,
        after: Any,
        planned: ProgressionDecision | None,
    ) -> None:
        objective_id = None
        if planned is not None and planned.objective is not None:
            objective_id = planned.objective.id
        stat = self.progression.outcomes.record_transition(
            before,
            action,
            after,
            objective_id=objective_id,
        )
        if before.key == after.key:
            # Keep the learning signal intentionally small. Collision/A* remains
            # authoritative; this only teaches the bounded correction layer that
            # repeating this exact action from this exact state was unproductive.
            self.evolve.record(
                RewardKind.BAD_TURN,
                magnitude=min(0.12, 0.025 + stat.no_effect * 0.012),
                state_key=f"nav:{before.key}:{objective_id or '*'}",
                action_id=action.value,
                metadata={
                    "source": "campaign_outcome_memory",
                    "reason": "same_location_after_action",
                    "attempts": stat.attempts,
                    "blocked": stat.blocked,
                },
            )

    def _explore_structured_once(self, before: Any) -> tuple[int, SceneType]:
        """Goal-directed step with an explicit before/after learning signal."""
        self._record_map_discovery(before)
        source_key = self.structured_navigator.key(before)

        planned = self._progression_decision(before)
        if planned is not None and planned.action is not None:
            action = planned.action
        else:
            action = self.structured_navigator.choose(source_key)
        target_has_object = self._object_on_target_tile(before, action)

        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        frame, next_screens, next_observation = self._snapshot()

        if next_observation.scene not in _FIELD_LIKE:
            self._no_progress_moves = 0
            self._blocked_streak = 0
            self._cached_progression_decision = None
            return 1, next_observation.scene

        after = self._structured_location()
        if after is None:
            self._no_progress_moves = 0
            return 1, next_observation.scene

        moved = self.structured_navigator.record_transition(
            before,
            action,
            after,
            transient_block=target_has_object,
        )
        self._record_navigation_outcome(before, action, after, planned)
        self._record_map_discovery(after)
        self._cached_progression_decision = None

        if moved:
            self._no_progress_moves = 0
            self._blocked_streak = 0
            if planned is not None and planned.action is not None:
                return 1, next_observation.scene
            actions = 1 + self._maybe_interact_after_movement()
            if actions > 1:
                scene = detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
                return actions, scene
            return actions, next_observation.scene

        self._no_progress_moves += 1
        self._blocked_streak += 1

        advanced, lines = self._advance_dialogue(next_screens)
        if advanced:
            scene = detect_scene(
                split_ds_screens(self.emulator.capture(), self.screen_layout)
            ).scene
            return 2, scene

        planned_interaction = planned is not None and planned.should_interact
        if target_has_object or planned_interaction:
            advanced, lines = self._advance_dialogue(next_screens, force_once=True)
            if advanced:
                scene = detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
                return 2, scene

        if self._no_progress_moves == 2:
            advanced, lines = self._advance_dialogue(next_screens, force_once=True)
            if advanced:
                scene = detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
                return 2, scene

        loop_level = self.progression.last_loop_level
        if self._no_progress_moves >= 3 or loop_level >= 2:
            objective_note = (
                "No objective route was available."
                if planned is None
                else f"Planner: {planned.reason}"
            )
            self._save_stuck_capture(
                frame=frame,
                screens=next_screens,
                observation=next_observation,
                key=source_key,
                action=action,
                lines=lines,
                note=(
                    "Automatic stuck capture with learned outcome/A* context. "
                    f"loopLevel={loop_level}; outcomes={self.progression.outcomes.stats()}; "
                    f"{objective_note}"
                ),
            )

        escaped = self._structured_escape(before, source_key, action)
        if escaped is not None:
            return 1 + escaped[0], escaped[1]
        return 1, next_observation.scene

    def _explore_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        # Detect dialogue BEFORE issuing a movement command. The older recovery
        # path already checked dialogue after a failed move; this removes that
        # wasted direction press for automatic NPC/story conversations.
        if _looks_like_dialogue_box(screens.top):
            advanced, _lines = self._advance_dialogue(screens)
            if advanced:
                scene = detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
                return 1, scene
        return super()._explore_once(screens)
