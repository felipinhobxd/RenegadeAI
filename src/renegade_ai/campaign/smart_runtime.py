from __future__ import annotations

import hashlib
import time
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.campaign.runtime import CampaignAutopilot, _looks_like_text_interaction
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.scene import SceneObservation, SceneType, detect_scene
from renegade_ai.perception.semantic import infer_semantic_label

_FIELD_LIKE = {SceneType.OVERWORLD, SceneType.UNKNOWN}


class SmartCampaignAutopilot(CampaignAutopilot):
    """Campaign director with balanced exploration, dialogue recovery and stuck captures."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._no_progress_moves = 0
        self._last_stuck_capture_at = 0.0
        self._last_stuck_key: str | None = None
        self._last_dialogue_digest: str | None = None
        self._same_dialogue_presses = 0

    @staticmethod
    def _text_digest(lines: list[str]) -> str:
        payload = "\n".join(line.strip() for line in lines if line.strip())
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=10).hexdigest()

    def _dialogue_lines(self, screens: DSScreens) -> list[str]:
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

        self.emulator.press(DSButton.A)
        time.sleep(max(0.12, self.poll_seconds))
        self._movement_since_interaction = 0
        return True, lines

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
                f"nearbyObjects={nearby}; nav={self.structured_navigator.stats()}."
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
        action = self.structured_navigator.choose(source_key)
        target_has_object = self._object_on_target_tile(before, action)

        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        frame, next_screens, next_observation = self._snapshot()

        if next_observation.scene not in _FIELD_LIKE:
            self._no_progress_moves = 0
            self._blocked_streak = 0
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

        if moved:
            self._no_progress_moves = 0
            self._blocked_streak = 0
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

        if target_has_object:
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
            self._save_stuck_capture(
                frame=frame,
                screens=next_screens,
                observation=next_observation,
                key=source_key,
                action=action,
                lines=lines,
                note=(
                    "Automatic stuck capture: inspect this screen if the local "
                    "RAM/OCR recovery cannot identify the next interaction."
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
