from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from renegade_ai.actions import DSButton
from renegade_ai.agent.runtime import BattleAutopilot
from renegade_ai.campaign.navigation import VisualTopoNavigator
from renegade_ai.campaign.structured_navigation import StructuredGridNavigator
from renegade_ai.learning.battle_memory import BattleAdaptiveMemory
from renegade_ai.learning.evolve import ASIEvolveEngine, RewardKind
from renegade_ai.memory.gdb import GDBRemoteError
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.ocr import OCRScanner
from renegade_ai.perception.scene import SceneObservation, SceneType, detect_scene
from renegade_ai.perception.scout import AutoCalibrationScout
from renegade_ai.perception.semantic import infer_semantic_label, normalize_ui_text

if TYPE_CHECKING:
    from renegade_ai.emulator.base import EmulatorAdapter
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.memory.platinum import PlatinumMemoryReader, StructuredLocation


_SCENE_CAPTURE_NAMES = {
    SceneType.OVERWORLD: "overworld",
    SceneType.BATTLE_COMMAND: "battle_command",
    SceneType.MOVE_MENU: "battle_move_menu",
    SceneType.BAG_MENU: "bag_categories",
    SceneType.PARTY_MENU: "battle_party",
    SceneType.SUMMARY_STATS: "summary_stats",
    SceneType.SUMMARY_MOVES: "summary_moves",
}

_MILESTONES = {
    "capture_success": RewardKind.CAPTURE_SUCCESS,
    "level_up": RewardKind.LEVEL_UP,
    "evolution": RewardKind.EVOLUTION,
    "badge_received": RewardKind.BADGE,
    "boss_victory": RewardKind.BOSS_WIN,
    "game_complete": RewardKind.GAME_COMPLETE,
}


@dataclass(slots=True)
class CampaignRunResult:
    completed: bool
    steps: int
    battles: int
    captures: int
    elapsed_seconds: float
    last_scene: SceneType
    last_label: str | None = None
    reason: str = ""


def _visual_signature(image: Any) -> str:
    import numpy as np

    rgb = np.asarray(image)[..., :3]
    if rgb.size == 0:
        return "empty"
    height, width = rgb.shape[:2]
    stride_y = max(1, height // 32)
    stride_x = max(1, width // 32)
    sample = (rgb[::stride_y, ::stride_x][:32, :32] // 16).astype("uint8")
    return hashlib.blake2b(sample.tobytes(), digest_size=10).hexdigest()


def _looks_like_text_interaction(lines: list[str]) -> bool:
    normalized = " ".join(normalize_ui_text(line) for line in lines if line).strip()
    if not normalized:
        return False
    words = normalized.split()
    if len(words) >= 4:
        return True
    keywords = (
        "continue", "continuar", "sim", "yes", "nao", "no", "pokemon",
        "recebeu", "obteve", "parabens", "congratulations", "level",
        "nivel", "evoluiu", "evolved",
    )
    return any(keyword in normalized for keyword in keywords)


class CampaignAutopilot:
    """Hybrid full-campaign director using structured RAM plus vision fallback."""

    def __init__(
        self,
        emulator: EmulatorAdapter,
        screen_layout: str,
        *,
        dex: RenegadeDex,
        navigator: VisualTopoNavigator | None = None,
        structured_reader: PlatinumMemoryReader | None = None,
        structured_navigator: StructuredGridNavigator | None = None,
        evolve_engine: ASIEvolveEngine | None = None,
        capture_root: str | Path = Path("captures/auto-calibration"),
        poll_seconds: float = 0.18,
    ) -> None:
        from renegade_ai.perception.battle_vision import BattleVision
        from renegade_ai.state.runtime import RuntimeStateStore

        self.emulator = emulator
        self.screen_layout = screen_layout
        self.poll_seconds = max(0.08, float(poll_seconds))
        self.navigator = navigator or VisualTopoNavigator()
        self.structured_reader = structured_reader
        self.structured_navigator = structured_navigator or StructuredGridNavigator()
        self.evolve = evolve_engine or ASIEvolveEngine()
        self.scout = AutoCalibrationScout(
            emulator,
            screen_layout,
            root=capture_root,
            settle_seconds=max(0.20, self.poll_seconds * 1.8),
        )
        self._scanner: OCRScanner | None = None
        self._last_capture_signature: str | None = None
        self._last_capture_scene: SceneType | None = None
        self._unknown_index = 0
        self._milestone_tokens: set[str] = set()
        self._movement_since_interaction = 0
        self._blocked_streak = 0
        self._structured_failures = 0
        self._last_structured_location: StructuredLocation | None = None
        self._last_badge_mask: int | None = None
        self._last_story_cleared: bool | None = None
        self._last_progress_poll = 0.0

        memory = BattleAdaptiveMemory(evolve_engine=self.evolve)
        self.battle = BattleAutopilot(
            emulator,
            screen_layout,
            dex=dex,
            vision=BattleVision(),
            state_store=RuntimeStateStore(),
            adaptive_memory=memory,
        )

    @property
    def structured_navigation_active(self) -> bool:
        return self.structured_reader is not None and self._structured_failures < 4

    def _snapshot(self) -> tuple[Any, DSScreens, SceneObservation]:
        frame = self.emulator.capture()
        screens = split_ds_screens(frame, self.screen_layout)
        return frame, screens, detect_scene(screens)

    def _scan_text(self, image: Any) -> list[str]:
        if self._scanner is None:
            self._scanner = OCRScanner(scale=3)
        try:
            return [line.text for line in self._scanner.scan(image) if line.confidence >= 0.42]
        except RuntimeError:
            return []

    def _structured_location(self) -> StructuredLocation | None:
        if not self.structured_navigation_active or self.structured_reader is None:
            return None
        try:
            location = self.structured_reader.read_location()
        except (OSError, GDBRemoteError, ValueError):
            self._structured_failures += 1
            return None
        self._structured_failures = 0
        self._last_structured_location = location
        return location

    def _record_map_discovery(self, location: StructuredLocation) -> None:
        _key, is_new_map = self.structured_navigator.observe(location)
        if not is_new_map:
            return
        self.evolve.record(
            RewardKind.OBJECTIVE_PROGRESS,
            magnitude=0.15,
            token=f"structured-map:{location.map_header_id}",
            metadata={
                "source": "structured_ram",
                "map_header_id": location.map_header_id,
                "map_name": location.map_name,
                "x": location.x,
                "z": location.z,
            },
        )

    def _poll_structured_progress(self) -> bool:
        if not self.structured_navigation_active or self.structured_reader is None:
            return False
        now = time.monotonic()
        if now - self._last_progress_poll < 2.0:
            return bool(self._last_story_cleared)
        self._last_progress_poll = now
        try:
            progress = self.structured_reader.read_progress()
        except (OSError, GDBRemoteError, ValueError):
            self._structured_failures += 1
            return False

        previous_badges = self._last_badge_mask
        previous_cleared = self._last_story_cleared
        self._last_badge_mask = progress.badge_mask
        self._last_story_cleared = progress.main_story_cleared

        if previous_badges is not None:
            gained = progress.badge_mask & ~previous_badges
            for badge_index in range(8):
                if gained & (1 << badge_index):
                    self.evolve.record(
                        RewardKind.BADGE,
                        token=f"ram-badge:{badge_index}",
                        metadata={
                            "source": "structured_ram",
                            "badge_index": badge_index,
                            "badge_count": progress.badge_count,
                        },
                    )

        if previous_cleared is False and progress.main_story_cleared:
            self.evolve.record(
                RewardKind.GAME_COMPLETE,
                token="ram-main-story-cleared",
                metadata={"source": "structured_ram"},
            )
        return progress.main_story_cleared

    def _record_milestone(self, label: str, lines: list[str]) -> float:
        kind = _MILESTONES.get(label)
        if kind is None:
            return 0.0
        normalized = " ".join(normalize_ui_text(line) for line in lines if line)
        digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=10).hexdigest()
        token = label if label == "game_complete" else f"{label}:{digest}"
        if token in self._milestone_tokens:
            return 0.0
        self._milestone_tokens.add(token)
        return self.evolve.record(
            kind,
            token=token,
            metadata={"source": "campaign_autopilot", "ocr": lines[:24]},
        )

    def _capture_if_novel(
        self,
        frame: Any,
        screens: DSScreens,
        observation: SceneObservation,
        *,
        semantic_label: str | None,
        lines: list[str],
    ) -> int:
        image = screens.viewport if screens.viewport is not None else frame
        signature = _visual_signature(image)
        changed = (
            signature != self._last_capture_signature
            or observation.scene != self._last_capture_scene
        )
        if not changed:
            return 0

        self._last_capture_signature = signature
        self._last_capture_scene = observation.scene
        structured = self._last_structured_location
        if semantic_label is not None:
            target = semantic_label
        elif observation.scene in _SCENE_CAPTURE_NAMES:
            target = _SCENE_CAPTURE_NAMES[observation.scene]
        elif observation.scene == SceneType.UNKNOWN:
            self._unknown_index += 1
            target = f"needed_unknown_{self._unknown_index:03d}"
        else:
            target = observation.scene.value

        note = "Autonomous campaign capture."
        if structured is not None:
            note += (
                f" RAM: {structured.map_name}#{structured.map_header_id} "
                f"({structured.x},{structured.z}) facing={structured.facing}."
            )
        if lines:
            note += f" OCR: {' | '.join(lines[:20])}"
        record = self.scout.save(
            target,
            frame=frame,
            screens=screens,
            observation=observation,
            note=note,
        )
        return int(record is not None)

    def _maybe_interact_after_movement(self) -> int:
        self._movement_since_interaction += 1
        if self._blocked_streak < 2 and self._movement_since_interaction < 8:
            return 0
        self.emulator.press(DSButton.A)
        self._movement_since_interaction = 0
        self._blocked_streak = 0
        time.sleep(max(0.10, self.poll_seconds))
        return 1

    def _explore_structured_once(
        self,
        before: StructuredLocation,
    ) -> tuple[int, SceneType]:
        self._record_map_discovery(before)
        source_key = self.structured_navigator.key(before)
        action = self.structured_navigator.choose(source_key)
        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        _frame, _next_screens, next_observation = self._snapshot()

        if next_observation.scene not in {SceneType.OVERWORLD, SceneType.UNKNOWN}:
            self._blocked_streak = 0
            return 1, next_observation.scene

        after = self._structured_location()
        if after is None:
            self._blocked_streak = 0
            return 1, next_observation.scene

        moved = self.structured_navigator.record_transition(before, action, after)
        self._record_map_discovery(after)
        self._blocked_streak = 0 if moved else self._blocked_streak + 1
        actions = 1 + self._maybe_interact_after_movement()
        if actions > 1:
            scene = detect_scene(
                split_ds_screens(self.emulator.capture(), self.screen_layout)
            ).scene
            return actions, scene
        return actions, next_observation.scene

    def _explore_visual_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        state_key = self.navigator.observe(screens.top)
        action = self.navigator.choose(state_key)
        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        _frame, next_screens, next_observation = self._snapshot()

        next_is_field_like = next_observation.scene in {SceneType.OVERWORLD, SceneType.UNKNOWN}
        if next_is_field_like:
            next_key = self.navigator.observe(next_screens.top)
            self.navigator.record_transition(state_key, action, next_key)
            self._blocked_streak = self._blocked_streak + 1 if next_key == state_key else 0
        else:
            next_key = self.navigator.fingerprint(next_screens.top)
            self.navigator.record_transition(state_key, action, next_key)
            self._blocked_streak = 0

        actions = 1 + self._maybe_interact_after_movement()
        if actions > 1:
            scene = detect_scene(
                split_ds_screens(self.emulator.capture(), self.screen_layout)
            ).scene
            return actions, scene
        return actions, next_observation.scene

    def _explore_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        structured = self._structured_location()
        if structured is not None:
            return self._explore_structured_once(structured)
        return self._explore_visual_once(screens)

    def _run_safe_calibration_if_needed(self) -> int:
        missing_before = set(self.scout.missing())
        if not missing_before:
            return 0
        before = len(self.scout.records)
        self.scout.run_active()
        return max(0, len(self.scout.records) - before)

    def run(self, *, max_seconds: float | None = None) -> CampaignRunResult:
        started = time.monotonic()
        steps = 0
        battles = 0
        captures = 0
        last_scene = SceneType.UNKNOWN
        last_label: str | None = None

        while max_seconds is None or time.monotonic() - started < max_seconds:
            try:
                frame, screens, observation = self._snapshot()
            except RuntimeError as exc:
                return CampaignRunResult(
                    completed=False,
                    steps=steps,
                    battles=battles,
                    captures=captures,
                    elapsed_seconds=time.monotonic() - started,
                    last_scene=last_scene,
                    last_label=last_label,
                    reason=str(exc),
                )

            scene = observation.scene
            last_scene = scene
            image = screens.viewport if screens.viewport is not None else frame

            if self._poll_structured_progress():
                return CampaignRunResult(
                    completed=True,
                    steps=steps,
                    battles=battles,
                    captures=captures,
                    elapsed_seconds=time.monotonic() - started,
                    last_scene=scene,
                    last_label="game_complete_ram",
                    reason="Main-story-cleared flag detected from read-only RAM",
                )

            if scene in {SceneType.OVERWORLD, SceneType.UNKNOWN}:
                structured = self._structured_location()
                if structured is not None:
                    self._record_map_discovery(structured)

            lines: list[str] = []
            semantic_label: str | None = None
            if scene == SceneType.UNKNOWN:
                lines = self._scan_text(image)
                semantic_label = infer_semantic_label(lines)
                last_label = semantic_label
            captures += self._capture_if_novel(
                frame,
                screens,
                observation,
                semantic_label=semantic_label,
                lines=lines,
            )

            if semantic_label is not None:
                self._record_milestone(semantic_label, lines)
                if semantic_label == "game_complete":
                    return CampaignRunResult(
                        completed=True,
                        steps=steps,
                        battles=battles,
                        captures=captures,
                        elapsed_seconds=time.monotonic() - started,
                        last_scene=scene,
                        last_label=semantic_label,
                        reason="Hall of Fame / game completion detected",
                    )

            if scene in {SceneType.BATTLE_COMMAND, SceneType.MOVE_MENU}:
                if scene == SceneType.BATTLE_COMMAND:
                    captures += self._run_safe_calibration_if_needed()
                result = self.battle.run(max_seconds=600.0, poll_seconds=self.poll_seconds)
                steps += result.actions
                battles += int(result.ended)
                time.sleep(self.poll_seconds)
                continue

            if scene in {
                SceneType.BAG_MENU,
                SceneType.PARTY_MENU,
                SceneType.SUMMARY_STATS,
                SceneType.SUMMARY_MOVES,
            }:
                self.emulator.press(DSButton.B)
                steps += 1
                time.sleep(self.poll_seconds)
                continue

            if scene == SceneType.UNKNOWN and _looks_like_text_interaction(lines):
                self.emulator.press(DSButton.A)
                steps += 1
                time.sleep(max(0.12, self.poll_seconds))
                continue

            moved, _next_scene = self._explore_once(screens)
            steps += moved
            time.sleep(self.poll_seconds)

        return CampaignRunResult(
            completed=False,
            steps=steps,
            battles=battles,
            captures=captures,
            elapsed_seconds=time.monotonic() - started,
            last_scene=last_scene,
            last_label=last_label,
            reason="time limit reached",
        )
