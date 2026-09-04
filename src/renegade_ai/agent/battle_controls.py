from __future__ import annotations

from enum import StrEnum

from renegade_ai.emulator.base import EmulatorAdapter


class BattleCommand(StrEnum):
    FIGHT = "fight"
    BAG = "bag"
    RUN = "run"
    POKEMON = "pokemon"


class BagCategory(StrEnum):
    RESTORE = "restore"
    POKEBALLS = "pokeballs"
    STATUS = "status"
    BATTLE_ITEMS = "battle_items"


# Calibrated from the owner's Portuguese Renegade Platinum capture. The main
# FIGHT button occupies the large center panel; Bag/Run/Pokemon are the three
# lower buttons.
_COMMAND_TOUCH: dict[BattleCommand, tuple[float, float]] = {
    BattleCommand.FIGHT: (0.50, 0.42),
    BattleCommand.BAG: (0.15, 0.88),
    BattleCommand.RUN: (0.50, 0.91),
    BattleCommand.POKEMON: (0.85, 0.88),
}

_BAG_CATEGORY_TOUCH: dict[BagCategory, tuple[float, float]] = {
    BagCategory.RESTORE: (0.25, 0.24),
    BagCategory.POKEBALLS: (0.75, 0.24),
    BagCategory.STATUS: (0.25, 0.58),
    BagCategory.BATTLE_ITEMS: (0.75, 0.58),
}

_PARTY_X = (0.25, 0.75)
_PARTY_Y = (0.12, 0.37, 0.62)
_SUMMARY_PAGE_TOGGLE = (0.575, 0.90)
_BACK = (0.93, 0.90)


def touch_battle_command(emulator: EmulatorAdapter, command: BattleCommand) -> None:
    x, y = _COMMAND_TOUCH[command]
    emulator.touch_bottom(x, y)


def touch_bag_category(emulator: EmulatorAdapter, category: BagCategory) -> None:
    x, y = _BAG_CATEGORY_TOUCH[category]
    emulator.touch_bottom(x, y)


def touch_party_slot(emulator: EmulatorAdapter, slot: int) -> None:
    if not 0 <= slot < 6:
        raise ValueError("party slot must be between 0 and 5")
    row, column = divmod(slot, 2)
    emulator.touch_bottom(_PARTY_X[column], _PARTY_Y[row])


def touch_summary_page_toggle(emulator: EmulatorAdapter) -> None:
    emulator.touch_bottom(*_SUMMARY_PAGE_TOGGLE)


def touch_back(emulator: EmulatorAdapter) -> None:
    emulator.touch_bottom(*_BACK)
