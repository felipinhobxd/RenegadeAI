from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from renegade_ai.actions import DSButton
from renegade_ai.emulator.base import EmulatorAdapter
from renegade_ai.perception.frame import split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene

if TYPE_CHECKING:
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.perception.battle_vision import BattleVision


_MOVE_TOUCH_CENTERS = (
    (0.25, 0.27),
    (0.75, 0.27),
    (0.25, 0.59),
    (0.75, 0.59),
)


@dataclass(slots=True)
class BattleRunResult:
    ended: bool
    actions: int
    elapsed_seconds: float
    last_scene: SceneType
    last_decision: str | None = None


class BattleAutopilot:
    """Pixel-driven battle loop with optional Renegade-aware move planning."""

    def __init__(
        self,
        emulator: EmulatorAdapter,
        screen_layout: str = "vertical",
        *,
        dex: RenegadeDex | None = None,
        vision: BattleVision | None = None,
    ) -> None:
        self.emulator = emulator
        self.screen_layout = screen_layout
        self.dex = dex
        self.vision = vision

    @property
    def smart(self) -> bool:
        return self.dex is not None and self.vision is not None

    def _choose_move(self, screens) -> str:
        if not self.smart:
            self.emulator.press(DSButton.A)
            return "fallback move slot 1"

        from renegade_ai.strategy.battle import rank_moves

        assert self.dex is not None
        assert self.vision is not None
        state = self.vision.observe(screens, self.dex)
        if (
            state.own is None
            or state.opponent is None
            or state.own_match_confidence < 0.42
            or state.opponent_match_confidence < 0.42
        ):
            self.emulator.press(DSButton.A)
            return (
                "OCR uncertain; safe fallback slot 1 "
                f"(own={state.own_match_confidence:.0%}, "
                f"opponent={state.opponent_match_confidence:.0%})"
            )

        ranked = rank_moves(
            state.own,
            state.opponent,
            list(state.moves),
            own_hp=state.own_hp_fraction or 1.0,
            opponent_hp=state.opponent_hp_fraction or 1.0,
        )
        if not ranked:
            self.emulator.press(DSButton.A)
            return "No move was confidently recognized; safe fallback slot 1"

        best = ranked[0]
        x, y = _MOVE_TOUCH_CENTERS[best.slot]
        self.emulator.touch_bottom(x, y)
        return (
            f"{state.own.name} vs {state.opponent.name}: slot {best.slot + 1} "
            f"{best.move.name} score={best.score:.1f}; {best.reason}"
        )

    def _enter_fight(self) -> None:
        if self.smart:
            from renegade_ai.agent.battle_controls import BattleCommand, touch_battle_command

            touch_battle_command(self.emulator, BattleCommand.FIGHT)
        else:
            self.emulator.press(DSButton.A)

    def run(self, *, max_seconds: float = 120.0, poll_seconds: float = 0.18) -> BattleRunResult:
        started = time.monotonic()
        actions = 0
        last_scene = SceneType.UNKNOWN
        last_decision: str | None = None
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

            if scene == SceneType.BATTLE_COMMAND:
                saw_battle = True
                if acted_scene is None:
                    # Bag/party/run become deliberate planner actions after their
                    # contents are calibrated from real Renegade captures.
                    self._enter_fight()
                    actions += 1
                    acted_scene = scene
                    last_decision = "enter LUTAR/FIGHT"

            elif scene == SceneType.MOVE_MENU:
                saw_battle = True
                if acted_scene is None:
                    last_decision = self._choose_move(screens)
                    actions += 1
                    acted_scene = scene

            elif scene == SceneType.OVERWORLD and saw_battle:
                return BattleRunResult(
                    ended=True,
                    actions=actions,
                    elapsed_seconds=time.monotonic() - started,
                    last_scene=scene,
                    last_decision=last_decision,
                )

            time.sleep(max(0.05, poll_seconds))

        return BattleRunResult(
            ended=False,
            actions=actions,
            elapsed_seconds=time.monotonic() - started,
            last_scene=last_scene,
            last_decision=last_decision,
        )
