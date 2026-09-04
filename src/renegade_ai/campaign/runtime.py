from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from renegade_ai.actions import DSButton
from renegade_ai.agent.runtime import BattleAutopilot
from renegade_ai.campaign.navigation import VisualTopoNavigator
from renegade_ai.learning.battle_memory import BattleAdaptiveMemory
from renegade_ai.learning.evolve import ASIEvolveEngine, RewardKind
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.ocr import OCRScanner
from renegade_ai.perception.scene import SceneObservation, SceneType, detect_scene
from renegade_ai.perception.scout import AutoCalibrationScout
from renegade_ai.perception.semantic import infer_semantic_label, normalize_ui_text

if TYPE_CHECKING:
    from renegade_ai.emulator.base import EmulatorAdapter
    from renegade_ai.knowledge.dex import RenegadeDex


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
    """Conservatively decide when A is likely to advance text/menu state."""
    normalized = " ".join(normalize_ui_text(line) for line in lines if line).strip()
    if not normalized:
        return False
    words = normalized.split()
    if len(words) >= 4:
        return True
    keywords = (
        "continue",
        "continuar",
        "sim",
        "yes",
        "nao",
        "no",
        "pokemon",
        "recebeu",
        "obteve",
        "parabens",
        "congratulations",
        "level",
        "nivel",
        "evoluiu",
        "evolved",
    )
    return any(keyword in normalized for keyword in keywords)


class CampaignAutopilot:
    """Unattended director that combines battle AI, scouting and exploration.

    This layer is intentionally emulator-facing rather than a scripted route.
    It continuously observes the real save, lets the battle planner take over
    battles, automatically collects missing calibration screens, advances text,
    and builds a persistent visual graph while exploring the overworld.

    The visual navigator is a baseline for long-horizon autonomy. Future direct
    RAM/map readers can replace it without changing this director.
    """

    def __init__(
        self,
        emulator: EmulatorAdapter,
        screen_layout: str,
        *,
        dex: RenegadeDex,
        navigator: VisualTopoNavigator | None = None,
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

        memory = BattleAdaptiveMemory(evolve_engine=self.evolve)
        self.battle = BattleAutopilot(
            emulator,
            screen_layout,
            dex=dex,
            vision=BattleVision(),
            state_store=RuntimeStateStore(),
            adaptive_memory=memory,
        )

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

    def _explore_once(self, screens: DSScreens) -> tuple[int, SceneType]:
        state_key = self.navigator.observe(screens.top)
        action = self.navigator.choose(state_key)
        self.emulator.press(action)
        time.sleep(max(0.12, self.poll_seconds))
        _frame, next_screens, next_observation = self._snapshot()

        next_is_field_like = next_observation.scene in {SceneType.OVERWORLD, SceneType.UNKNOWN}
        if next_is_field_like:
            next_key = self.navigator.observe(next_screens.top)
            self.navigator.record_transition(state_key, action, next_key)
            if next_key == state_key:
                self._blocked_streak += 1
            else:
                self._blocked_streak = 0
        else:
            # A battle/menu transition is useful progress, not a blocked edge.
            next_key = self.navigator.fingerprint(next_screens.top)
            self.navigator.record_transition(state_key, action, next_key)
            self._blocked_streak = 0

        self._movement_since_interaction += 1
        if self._blocked_streak >= 2 or self._movement_since_interaction >= 8:
            # Interacting after reaching an obstacle/frontier is far safer than
            # spamming A continuously and is enough to trigger NPCs, signs,
            # doors/events and many story conversations encountered in travel.
            self.emulator.press(DSButton.A)
            self._movement_since_interaction = 0
            self._blocked_streak = 0
            time.sleep(max(0.10, self.poll_seconds))
            return 2, detect_scene(split_ds_screens(self.emulator.capture(), self.screen_layout)).scene
        return 1, next_observation.scene

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
                # A closed/minimized emulator should end this session cleanly;
                # the outer autoplay daemon will wait for melonDS to return.
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
                # The first real battle doubles as automatic calibration. No
                # separate scout command is needed.
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
                # If a menu was opened accidentally while exploring, retreat one
                # level instead of selecting an unknown item/switch operation.
                self.emulator.press(DSButton.B)
                steps += 1
                time.sleep(self.poll_seconds)
                continue

            if scene == SceneType.UNKNOWN and _looks_like_text_interaction(lines):
                # One press per newly observed frame prevents the classic
                # repeated-A/NPC dialogue loop seen in other Pokemon agents.
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
