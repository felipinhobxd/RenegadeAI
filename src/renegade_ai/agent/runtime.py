from __future__ import annotations

import time
from dataclasses import dataclass

from renegade_ai.actions import DSButton
from renegade_ai.emulator.base import EmulatorAdapter
from renegade_ai.perception.frame import split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene


@dataclass(slots=True)
class BattleRunResult:
    ended: bool
    actions: int
    elapsed_seconds: float
    last_scene: SceneType


class BattleAutopilot:
    """Pixel-driven battle loop for the first playable milestone."""

    def __init__(self, emulator: EmulatorAdapter, screen_layout: str = "vertical") -> None:
        self.emulator = emulator
        self.screen_layout = screen_layout

    def run(self, *, max_seconds: float = 120.0, poll_seconds: float = 0.18) -> BattleRunResult:
        started = time.monotonic()
        actions = 0
        last_scene = SceneType.UNKNOWN
        acted_scene: SceneType | None = None
        saw_battle = False

        while time.monotonic() - started < max_seconds:
            frame = self.emulator.capture()
            screens = split_ds_screens(frame, self.screen_layout)
            observation = detect_scene(screens)
            scene = observation.scene
            last_scene = scene

            if acted_scene is not None and scene != acted_scene:
                acted_scene = None

            if scene in {SceneType.BATTLE_COMMAND, SceneType.MOVE_MENU}:
                saw_battle = True
                if acted_scene is None:
                    self.emulator.press(DSButton.A)
                    actions += 1
                    acted_scene = scene

            elif scene == SceneType.OVERWORLD and saw_battle:
                return BattleRunResult(
                    ended=True,
                    actions=actions,
                    elapsed_seconds=time.monotonic() - started,
                    last_scene=scene,
                )

            time.sleep(max(0.05, poll_seconds))

        return BattleRunResult(
            ended=False,
            actions=actions,
            elapsed_seconds=time.monotonic() - started,
            last_scene=last_scene,
        )
