from __future__ import annotations

import hashlib
import time
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.campaign.progression import ProgressionDecision, ProgressionDirector
from renegade_ai.campaign.runtime import CampaignAutopilot, _looks_like_text_interaction
from renegade_ai.learning.evolve import RewardKind
from renegade_ai.memory.gdb import GDBRemoteError
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.scene import SceneObservation, SceneType, detect_scene
from renegade_ai.perception.semantic import infer_semantic_label

_FIELD_LIKE = {SceneType.OVERWORLD, SceneType.UNKNOWN}


class SmartCampaignAutopilot(CampaignAutopilot):
    """Objective-driven campaign director with dialogue and stuck recovery.

    When validated ARM9 state is available this layer now prefers a real story
    objective, a static Platinum collision/warp world model and local A* over
    frontier exploration. Frontier exploration remains the fallback for local
    puzzles, scripted geometry that differs in Renegade, or unavailable public
    map data. Visual navigation is the final fallback if RAM itself is missing.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._no_progress_moves = 0
        self._last_stuck_capture_at = 0.0
        self._last_stuck_key: str | None = None
        self._last_dialogue_digest: str | None = None
        self._same_dialogue_presses = 0
        self.progression = ProgressionDirector()
        self._last_progression_poll = 0.0
        self._cached_progression_decision: ProgressionDecision | None = None
        self._last_objective_id: str | None = None

    @staticmethod
    def _text_digest(lines: list[str]) -> str:
        payload = "\n".join(line.strip() for line in lines if line.strip())
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=10).hexdigest()

    def _dialogue_lines(self, screens: DSScreens) -> list[str]:
        # Platinum normally renders conversations on the upper screen while
        # the lower Poketch screen can still look like ordinary overworld.
        lines = self._scan_text(screens.top)
        if _looks_like_text_interaction(lines):
            return lines
        if screens.viewport is not None:
            combined = self._scan_text(screens.viewport)
            if _looks_like_text_interaction(combined):
                return combined
        return []

    def _advance_dialogue(
        self,
        screens: DSScreens,
        *,
        force_once: bool = False,
    ) -> tuple[bool, list[str]]:
        lines = self._dialogue_lines(screens)
        if not lines and not force_once:
            return False, []

        if lines:
            digest = self._text_digest(lines)
            if digest == self._last_dialogue_digest:
                self._same_dialogue_presses += 1
            else:
                self._last_dialogue_digest = digest
                self._same_dialogue_presses = 0
            label = infer_semantic_label(lines)
            if label is not None:
                self._record_milestone(label, lines)
        else:
            self._same_dialogue_presses += 1

        # One A press, then re-observe. This advances normal dialogue without
        # blindly mashing through menus or repeated choices.
        self.emulator.press(DSButton.A)
        time.sleep(max(0.12, self.poll_seconds))
        self._movement_since_interaction = 0
        return True, lines

    def _progression_decision(self, location: Any) -> ProgressionDecision | None:
        if self.structured_reader is None:
            return None
        now = time.monotonic()
        # Replan immediately after movement/map changes, but avoid multiple
        # expensive world/flag reads inside the same short frame interval.
        if (
            self._cached_progression_decision is not None
            and now - self._last_progression_poll < 0.22
        ):
            return self._cached_progression_decision
        self._last_progression_poll = now
        try:
            progress = self.structured_reader.read_progress()
            story = self.structured_reader.read_story_state()
            decision = self.progression.decide(
                location=location,
                progress=progress,
                story=story,
                navigator=self.structured_navigator,
                field_objects=self._field_objects(),
            )
        except (OSError, GDBRemoteError, ValueError):
            return None

        objective_id = None if decision.objective is None else decision.objective.id
        if (
            self._last_objective_id is not None
            and objective_id is not None
            and objective_id != self._last_objective_id
        ):
            self.evolve.record(
                RewardKind.OBJECTIVE_PROGRESS,
                magnitude=0.12,
                token=f"objective-transition:{self._last_objective_id}->{objective_id}",
                metadata={
                    "source": "story_objective_planner",
                    "from": self._last_objective_id,
                    "to": objective_id,
                    "map": location.map_name,
                },
            )
        self._last_objective_id = objective_id
        self._cached_progression_decision = decision
        return decision

    def _save_stuck_capture(
        self,
        *,
        frame: Any,
        screens: DSScreens,
        observation: SceneObservation,
        key: str,
        action: DSButton,
        lines: list[str],
        note: str,
    ) -> None:
        now = time.monotonic()
        if key == self._last_stuck_key and now - self._last_stuck_capture_at < 8.0:
            return
        self._last_stuck_key = key
        self._last_stuck_capture_at = now
        location = self._last_structured_location
        if location is not None:
            target = f"stuck_{location.map_name}_{location.x}_{location.z}"
            nearby = [
                {
                    "id": obj.local_id,
                    "x": obj.x,
                    "z": obj.z,
                    "script": obj.script,
                    "trainer_type": obj.trainer_type,
                }
                for obj in self._field_objects()
                if abs(obj.x - location.x) + abs(obj.z - location.z) <= 2
            ]
            context = (
                f"RAM={location.map_name}#{location.map_header_id} "
                f"({location.x},{location.z}) facing={location.facing}; "
                f"attempt={action.value}; noProgress={self._no_progress_moves}; "
                f"nearbyObjects={nearby}; nav={self.structured_navigator.stats()}; "
                f"progression={self.progression.debug_state()}."
            )
        else:
            target = "stuck_visual_navigation"
            context = (
                f"visualState={key}; attempt={action.value}; "
                f"noProgress={self._no_progress_moves}; nav={self.navigator.stats()}."
            )
        if lines:
            context += f" OCR={' | '.join(lines[:24])}."
        context += f" {note}"
        self.scout.save(
            target,
            frame=frame,
            screens=screens,
            observation=observation,
            force=True,
            note=context,
        )

    def _structured_escape(
        self,
        before: Any,
        source_key: str,
        previous_action: DSButton,
    ) -> tuple[int, SceneType] | None:
        if self._no_progress_moves < 4:
            return None
        escape = self.structured_navigator.choose_escape(source_key)
        if escape == previous_action and self._no_progress_moves < 6:
            return None

        self.emulator.press(escape)
        time.sleep(max(0.12, self.poll_seconds))
        _frame, screens, observation = self._snapshot()
        after = self._structured_location()
        if after is not None:
            moved = self.structured_navigator.record_transition(before, escape, after)
            if moved:
                self._no_progress_moves = 0
                self._blocked_streak = 0
                self._cached_progression_decision = None
        if observation.scene not in _FIELD_LIKE:
            return 1, observation.scene

        advanced, _lines = self._advance_dialogue(screens)
        if advanced:
            return 2, detect_scene(
                split_ds_screens(self.emulator.capture(), self.screen_layout)
            ).scene
        return 1, observation.scene

    def _explore_structured_once(self, before: Any) -> tuple[int, SceneType]:
        self._record_map_discovery(before)
        source_key = self.structured_navigator.key(before)

        planned = self._progression_decision(before)
        if planned is not None and planned.action is not None:
            action = planned.action
        else:
            # Local puzzles / missing world graph data still use learned
            # frontier exploration instead of stalling the campaign.
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
        self._record_map_discovery(after)
        self._cached_progression_decision = None

        if moved:
            self._no_progress_moves = 0
            self._blocked_streak = 0
            # Do not periodically press A while following a precise A* route.
            # Only the frontier fallback retains the old conservative probe.
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

        # A failed planned move can be a scripted NPC/event rather than static
        # geometry. Dialogue gets first chance before the tile is treated as a
        # dead end by the next A* replan.
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

        if self._no_progress_moves >= 3:
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
                    "Automatic stuck capture with objective/A* context. "
                    f"{objective_note}"
                ),
            )

        escaped = self._structured_escape(before, source_key, action)
        if escaped is not None:
            return 1 + escaped[0], escaped[1]
        return 1, next_observation.scene

    def _explore_visual_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        state_key = self.navigator.observe(screens.top)
        action = self.navigator.choose(state_key)
        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        frame, next_screens, next_observation = self._snapshot()

        next_key = self.navigator.fingerprint(next_screens.top)
        if next_observation.scene not in _FIELD_LIKE:
            self._no_progress_moves = 0
            self.navigator.record_transition(state_key, action, next_key)
            return 1, next_observation.scene

        if next_key == state_key:
            self._no_progress_moves += 1
            advanced, lines = self._advance_dialogue(next_screens)
            if advanced:
                return 2, detect_scene(
                    split_ds_screens(self.emulator.capture(), self.screen_layout)
                ).scene
            self.navigator.record_transition(state_key, action, next_key)
            if self._no_progress_moves == 2:
                advanced, lines = self._advance_dialogue(next_screens, force_once=True)
                if advanced:
                    return 2, detect_scene(
                        split_ds_screens(self.emulator.capture(), self.screen_layout)
                    ).scene
            if self._no_progress_moves >= 3:
                self._save_stuck_capture(
                    frame=frame,
                    screens=next_screens,
                    observation=next_observation,
                    key=state_key,
                    action=action,
                    lines=lines,
                    note="Visual fallback could not make progress; context saved automatically.",
                )
        else:
            self._no_progress_moves = 0
            self.navigator.record_transition(state_key, action, next_key)

        actions = 1 + self._maybe_interact_after_movement()
        if actions > 1:
            scene = detect_scene(
                split_ds_screens(self.emulator.capture(), self.screen_layout)
            ).scene
            return actions, scene
        return actions, next_observation.scene
