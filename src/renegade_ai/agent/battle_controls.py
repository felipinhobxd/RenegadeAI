from __future__ import annotations

from enum import StrEnum

from renegade_ai.emulator.base import EmulatorAdapter


class BattleCommand(StrEnum):
    FIGHT = "fight"
    BAG = "bag"
    RUN = "run"
    POKEMON = "pokemon"


# Normalized lower-screen centers from the standard Diamond/Pearl/Platinum
# battle-command layout. Real Renegade captures will be used to refine these
# before Bag/switch actions become automatic planner choices.
_COMMAND_TOUCH: dict[BattleCommand, tuple[float, float]] = {
    BattleCommand.FIGHT: (0.50, 0.48),
    BattleCommand.BAG: (0.15, 0.88),
    BattleCommand.RUN: (0.50, 0.90),
    BattleCommand.POKEMON: (0.85, 0.88),
}


def touch_battle_command(emulator: EmulatorAdapter, command: BattleCommand) -> None:
    x, y = _COMMAND_TOUCH[command]
    emulator.touch_bottom(x, y)
