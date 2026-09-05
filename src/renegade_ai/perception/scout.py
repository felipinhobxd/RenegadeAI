from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.agent.battle_controls import (
    BagCategory,
    BattleCommand,
    touch_bag_category,
    touch_battle_command,
    touch_party_slot,
    touch_summary_page_toggle,
)
from renegade_ai.emulator.base import EmulatorAdapter
from renegade_ai.perception.frame import DSScreens, split_ds_screens
from renegade_ai.perception.scene import SceneObservation, SceneType, detect_scene

# These are the screenshots that still unlock new autonomous actions. The scout
# can collect them without selecting an item, switching Pokemon or using RUN.
CALIBRATION_NEEDS = (
    "bag_restore_list",
    "bag_pokeballs_list",
    "bag_status_list",
    "bag_battle_items_list",
    "party_slot_action_menu",
)

_SCENE_LABELS = {
    SceneType.OVERWORLD: "overworld",
    SceneType.BATTLE_COMMAND: "battle_command",
    SceneType.MOVE_MENU: "battle_move_menu",
    SceneType.BAG_MENU: "bag_categories",
    SceneType.PARTY_MENU: "battle_party",
    SceneType.SUMMARY_STATS: "summary_stats",
    SceneType.SUMMARY_MOVES: "summary_moves",
    SceneType.UNKNOWN: "unknown",
}


@dataclass(frozen=True, slots=True)
class CaptureRecord:
    target: str
    scene: str
    confidence: float
    full: str
    viewport: str | None
    top: str
    bottom: str
    metadata: str
    created_at: str
    required: bool


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower())
    return value.strip("-") or "capture"


def _fingerprint(image: Any) -> str:
    import numpy as np

    rgb = np.asarray(image)[..., :3]
    if rgb.size == 0:
        return "empty"
    # A small deterministic thumbnail fingerprint is enough for duplicate
    # suppression while keeping this dependency-free.
    stride_y = max(1, rgb.shape[0] // 32)
    stride_x = max(1, rgb.shape[1] // 32)
    sample = rgb[::stride_y, ::stride_x][:32, :32]
    return hashlib.blake2b(sample.tobytes(), digest_size=10).hexdigest()


class AutoCalibrationScout:
    """Safely navigates reversible menus and names screenshots automatically."""

    def __init__(
        self,
        emulator: EmulatorAdapter,
        screen_layout: str = "vertical",
        *,
        root: str | Path = Path("captures/auto-calibration"),
        settle_seconds: float = 0.45,
    ) -> None:
        self.emulator = emulator
        self.screen_layout = screen_layout
        self.root = Path(root)
        self.settle_seconds = max(0.15, float(settle_seconds))
        self.root.mkdir(parents=True, exist_ok=True)
        self.records: list[CaptureRecord] = []
        self._fingerprints: set[str] = set()
        self._load_existing_manifest()

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def _load_existing_manifest(self) -> None:
        if not self.manifest_path.exists():
            return
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for item in raw.get("captures", ()):
            try:
                self.records.append(CaptureRecord(**item))
            except TypeError:
                continue

    def _snapshot(self) -> tuple[Any, DSScreens, SceneObservation]:
        frame = self.emulator.capture()
        screens = split_ds_screens(frame, self.screen_layout)
        return frame, screens, detect_scene(screens)

    def _write_manifest(self) -> None:
        captured = {record.target for record in self.records}
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat(),
            "needed_targets": list(CALIBRATION_NEEDS),
            "captured_needed": sorted(captured.intersection(CALIBRATION_NEEDS)),
            "missing_needed": sorted(set(CALIBRATION_NEEDS) - captured),
            "captures": [asdict(record) for record in self.records],
            "safety": {
                "uses_items": False,
                "switches_pokemon": False,
                "runs_from_battle": False,
                "selects_moves": False,
            },
        }
        self.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def save(
        self,
        target: str,
        *,
        frame: Any | None = None,
        screens: DSScreens | None = None,
        observation: SceneObservation | None = None,
        force: bool = False,
        note: str | None = None,
    ) -> CaptureRecord | None:
        from PIL import Image

        if frame is None or screens is None or observation is None:
            frame, screens, observation = self._snapshot()

        fingerprint = _fingerprint(screens.viewport if screens.viewport is not None else frame)
        duplicate_key = f"{target}:{fingerprint}"
        if duplicate_key in self._fingerprints and not force:
            return None
        self._fingerprints.add(duplicate_key)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target_slug = _slug(target)
        scene_slug = _slug(observation.scene.value)
        base = self.root / f"{target_slug}__seen-{scene_slug}__{timestamp}"
        full_path = base.with_suffix(".png")
        viewport_path = base.with_name(base.name + "__viewport").with_suffix(".png")
        top_path = base.with_name(base.name + "__top").with_suffix(".png")
        bottom_path = base.with_name(base.name + "__bottom").with_suffix(".png")
        metadata_path = base.with_suffix(".json")

        Image.fromarray(frame).save(full_path)
        viewport_value: str | None = None
        if screens.viewport is not None:
            Image.fromarray(screens.viewport).save(viewport_path)
            viewport_value = str(viewport_path)
        Image.fromarray(screens.top).save(top_path)
        Image.fromarray(screens.bottom).save(bottom_path)

        metadata = {
            "target": target,
            "required": target in CALIBRATION_NEEDS,
            "scene": observation.scene.value,
            "confidence": observation.confidence,
            "metrics": observation.metrics,
            "fingerprint": fingerprint,
            "note": note,
            "bounds": screens.bounds,
            "created_at": datetime.now(UTC).isoformat(),
        }
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        record = CaptureRecord(
            target=target,
            scene=observation.scene.value,
            confidence=observation.confidence,
            full=str(full_path),
            viewport=viewport_value,
            top=str(top_path),
            bottom=str(bottom_path),
            metadata=str(metadata_path),
            created_at=metadata["created_at"],
            required=target in CALIBRATION_NEEDS,
        )
        self.records.append(record)
        self._write_manifest()
        return record

    def _settle(self) -> tuple[Any, DSScreens, SceneObservation]:
        time.sleep(self.settle_seconds)
        return self._snapshot()

    def _press_back(self, times: int = 1) -> None:
        for _ in range(max(1, times)):
            self.emulator.press(DSButton.B)
            time.sleep(self.settle_seconds)

    def _return_to(self, target: SceneType, *, max_presses: int = 3) -> bool:
        for _ in range(max_presses + 1):
            _, _, observation = self._snapshot()
            if observation.scene == target:
                return True
            self._press_back()
        return False

    def _explore_bag(self) -> None:
        frame, screens, observation = self._snapshot()
        self.save("bag_categories", frame=frame, screens=screens, observation=observation)
        targets = (
            (BagCategory.RESTORE, "bag_restore_list"),
            (BagCategory.POKEBALLS, "bag_pokeballs_list"),
            (BagCategory.STATUS, "bag_status_list"),
            (BagCategory.BATTLE_ITEMS, "bag_battle_items_list"),
        )
        for category, target in targets:
            if (
                detect_scene(self._snapshot()[1]).scene != SceneType.BAG_MENU
                and not self._return_to(SceneType.BAG_MENU)
            ):
                return
            touch_bag_category(self.emulator, category)
            frame, screens, observation = self._settle()
            self.save(
                target,
                frame=frame,
                screens=screens,
                observation=observation,
                force=True,
                note="Opened category only; no item was selected.",
            )
            self._press_back()

    def _explore_party(self) -> None:
        frame, screens, observation = self._snapshot()
        self.save("battle_party", frame=frame, screens=screens, observation=observation)
        # Selecting the already-active first slot should expose the contextual
        # action menu without committing a switch. We immediately capture it and
        # press B. If the game/layout differs, the screenshot is still labeled
        # by intended target and the observed scene is preserved in metadata.
        touch_party_slot(self.emulator, 0)
        frame, screens, observation = self._settle()
        self.save(
            "party_slot_action_menu",
            frame=frame,
            screens=screens,
            observation=observation,
            force=True,
            note="Selected party slot 1 for calibration; no switch confirmation is pressed.",
        )
        self._press_back()

    def _explore_summary(self, initial: SceneType) -> None:
        frame, screens, observation = self._snapshot()
        self.save(_SCENE_LABELS[initial], frame=frame, screens=screens, observation=observation)
        touch_summary_page_toggle(self.emulator)
        frame, screens, observation = self._settle()
        label = _SCENE_LABELS.get(observation.scene, "summary_other_page")
        self.save(label, frame=frame, screens=screens, observation=observation, force=True)

    def run_active(self) -> list[CaptureRecord]:
        """Collect every currently reachable calibration target safely.

        Best starting point is the four-option battle command screen. The scout
        never touches RUN, never selects a move and never selects an item.
        """
        frame, screens, observation = self._snapshot()
        current = observation.scene
        self.save(_SCENE_LABELS[current], frame=frame, screens=screens, observation=observation)

        if current == SceneType.BATTLE_COMMAND:
            # Move menu geometry.
            touch_battle_command(self.emulator, BattleCommand.FIGHT)
            frame, screens, observation = self._settle()
            self.save(
                "battle_move_menu",
                frame=frame,
                screens=screens,
                observation=observation,
                force=True,
            )
            self._press_back()
            if not self._return_to(SceneType.BATTLE_COMMAND):
                return self.records

            # Bag and all four category lists.
            touch_battle_command(self.emulator, BattleCommand.BAG)
            self._settle()
            if detect_scene(self._snapshot()[1]).scene == SceneType.BAG_MENU:
                self._explore_bag()
            self._return_to(SceneType.BATTLE_COMMAND)

            # Party and the post-slot contextual menu.
            touch_battle_command(self.emulator, BattleCommand.POKEMON)
            self._settle()
            if detect_scene(self._snapshot()[1]).scene == SceneType.PARTY_MENU:
                self._explore_party()
            self._return_to(SceneType.BATTLE_COMMAND)

        elif current == SceneType.BAG_MENU:
            self._explore_bag()
        elif current == SceneType.PARTY_MENU:
            self._explore_party()
        elif current in {SceneType.SUMMARY_STATS, SceneType.SUMMARY_MOVES}:
            self._explore_summary(current)

        self._write_manifest()
        return self.records

    def watch(self, seconds: float = 60.0, *, poll_seconds: float = 0.25) -> list[CaptureRecord]:
        """Passively capture novel scene transitions and unknown screens.

        This is useful during normal play: when the project reaches a screen the
        classifier does not know yet, the scout stores it as an automatically
        named calibration inbox item instead of requiring a manual screenshot.
        """
        deadline = time.monotonic() + max(1.0, float(seconds))
        last_scene: SceneType | None = None
        last_fingerprint: str | None = None
        unknown_index = 0
        while time.monotonic() < deadline:
            frame, screens, observation = self._snapshot()
            image = screens.viewport if screens.viewport is not None else frame
            fingerprint = _fingerprint(image)
            scene_changed = observation.scene != last_scene
            visually_changed = fingerprint != last_fingerprint
            if scene_changed or (observation.scene == SceneType.UNKNOWN and visually_changed):
                if observation.scene == SceneType.UNKNOWN:
                    unknown_index += 1
                    label = f"needed_unknown_{unknown_index:03d}"
                else:
                    label = _SCENE_LABELS[observation.scene]
                self.save(
                    label,
                    frame=frame,
                    screens=screens,
                    observation=observation,
                    note="Automatically captured while passive scout was watching.",
                )
            last_scene = observation.scene
            last_fingerprint = fingerprint
            time.sleep(max(0.08, poll_seconds))
        self._write_manifest()
        return self.records

    def missing(self) -> tuple[str, ...]:
        captured = {record.target for record in self.records}
        return tuple(sorted(set(CALIBRATION_NEEDS) - captured))
