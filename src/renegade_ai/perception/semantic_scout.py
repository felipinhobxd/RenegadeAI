from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from renegade_ai.learning.evolve import ASIEvolveEngine, RewardKind
from renegade_ai.perception.ocr import OCRScanner
from renegade_ai.perception.scout import AutoCalibrationScout
from renegade_ai.perception.semantic import infer_semantic_label, normalize_ui_text
from renegade_ai.perception.scene import SceneType


_SCENE_LABELS = {
    SceneType.OVERWORLD: "overworld",
    SceneType.BATTLE_COMMAND: "battle_command",
    SceneType.MOVE_MENU: "battle_move_menu",
    SceneType.BAG_MENU: "bag_categories",
    SceneType.PARTY_MENU: "battle_party",
    SceneType.SUMMARY_STATS: "summary_stats",
    SceneType.SUMMARY_MOVES: "summary_moves",
}

_MILESTONE_REWARDS = {
    "capture_success": RewardKind.CAPTURE_SUCCESS,
    "level_up": RewardKind.LEVEL_UP,
    "evolution": RewardKind.EVOLUTION,
    "badge_received": RewardKind.BADGE,
    "boss_victory": RewardKind.BOSS_WIN,
    "game_complete": RewardKind.GAME_COMPLETE,
}


def _text_token(label: str, lines: list[str]) -> str:
    normalized = " ".join(normalize_ui_text(line) for line in lines if line)
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=10).hexdigest()
    # Game completion is deliberately once-per-learning-profile. Other event
    # types use their visible text so a different badge/evolution/capture can be
    # rewarded while repeated frames of the same message are deduplicated.
    return label if label == "game_complete" else f"{label}:{digest}"


class SemanticAutoCalibrationScout(AutoCalibrationScout):
    """AutoCalibrationScout with OCR naming and milestone reward hooks."""

    def __init__(
        self,
        *args: Any,
        root: str | Path = Path("captures/auto-calibration"),
        reward_engine: ASIEvolveEngine | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, root=root, **kwargs)
        self._scanner: OCRScanner | None = None
        self.reward_engine = reward_engine or ASIEvolveEngine()

    def _semantic_lines(self, image: Any) -> list[str]:
        if self._scanner is None:
            self._scanner = OCRScanner(scale=3)
        try:
            return [line.text for line in self._scanner.scan(image) if line.confidence >= 0.42]
        except RuntimeError:
            # Active screenshot collection still works without vision extras.
            return []

    def _reward_semantic_event(self, label: str, lines: list[str]) -> float:
        kind = _MILESTONE_REWARDS.get(label)
        if kind is None:
            return 0.0
        token = _text_token(label, lines)
        return self.reward_engine.record(
            kind,
            token=token,
            metadata={
                "source": "semantic_scout",
                "screen_label": label,
                "ocr": lines[:24],
            },
        )

    def watch(self, seconds: float = 60.0, *, poll_seconds: float = 0.25):
        """Watch gameplay, semantically name unknown screens and reward milestones."""
        deadline = time.monotonic() + max(1.0, float(seconds))
        last_scene: SceneType | None = None
        last_signature: str | None = None
        unknown_index = 0

        while time.monotonic() < deadline:
            frame, screens, observation = self._snapshot()
            image = screens.viewport if screens.viewport is not None else frame
            # A compact visual signature avoids OCR on every unchanged frame.
            shape = getattr(image, "shape", ())
            raw = memoryview(image).tobytes() if hasattr(image, "tobytes") else bytes(str(shape), "utf-8")
            signature = hashlib.blake2b(raw[:: max(1, len(raw) // 4096)], digest_size=8).hexdigest()
            scene_changed = observation.scene != last_scene
            visually_changed = signature != last_signature

            if scene_changed or (observation.scene == SceneType.UNKNOWN and visually_changed):
                known_label = _SCENE_LABELS.get(observation.scene)
                lines: list[str] = []
                semantic_label: str | None = None
                if observation.scene == SceneType.UNKNOWN:
                    lines = self._semantic_lines(image)
                    semantic_label = infer_semantic_label(lines)

                if semantic_label is not None:
                    label = semantic_label
                    reward = self._reward_semantic_event(label, lines)
                    reward_note = "" if reward == 0 else f"; ASI-Evolve reward={reward:+.1f}"
                    note = f"Semantic OCR: {' | '.join(lines[:20])}{reward_note}"
                elif known_label is not None:
                    label = known_label
                    note = "Automatically captured while passive scout was watching."
                else:
                    unknown_index += 1
                    label = f"needed_unknown_{unknown_index:03d}"
                    note = (
                        "Unknown calibration inbox item. OCR could not assign a high-confidence "
                        "semantic label."
                    )

                self.save(
                    label,
                    frame=frame,
                    screens=screens,
                    observation=observation,
                    note=note,
                )

            last_scene = observation.scene
            last_signature = signature
            time.sleep(max(0.08, poll_seconds))

        self._write_manifest()
        return self.records
