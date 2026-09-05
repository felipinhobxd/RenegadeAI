from __future__ import annotations

import numpy as np

from renegade_ai.perception.frame import DSScreens, crop_game_viewport, split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene


def test_crop_game_viewport_removes_black_bars_and_chrome() -> None:
    frame = np.zeros((400, 600, 3), dtype=np.uint8)
    # centered, fully visible vertical DS viewport
    frame[40:380, 180:420] = (180, 170, 120)

    cropped, bounds = crop_game_viewport(frame, "vertical")

    assert bounds == (180, 40, 420, 380)
    assert cropped.shape == (340, 240, 3)


def test_split_uses_cropped_viewport() -> None:
    frame = np.zeros((400, 600, 3), dtype=np.uint8)
    frame[40:380, 180:420] = (180, 170, 120)

    screens = split_ds_screens(frame, "vertical")

    assert screens.bounds == (180, 40, 420, 380)
    assert screens.top.shape == (170, 240, 3)
    assert screens.bottom.shape == (170, 240, 3)


def test_detect_overworld_from_tan_lower_screen() -> None:
    top = np.full((192, 256, 3), (100, 180, 100), dtype=np.uint8)
    bottom = np.full((192, 256, 3), (180, 160, 100), dtype=np.uint8)

    observation = detect_scene(DSScreens(top=top, bottom=bottom))

    assert observation.scene == SceneType.OVERWORLD


def test_detect_battle_command_from_large_red_area() -> None:
    top = np.full((192, 256, 3), (100, 180, 100), dtype=np.uint8)
    bottom = np.full((192, 256, 3), (220, 235, 210), dtype=np.uint8)
    bottom[45:155, 25:230] = (235, 55, 55)

    observation = detect_scene(DSScreens(top=top, bottom=bottom))

    assert observation.scene == SceneType.BATTLE_COMMAND


def test_detect_move_menu_from_blue_bar_and_colored_slots() -> None:
    top = np.full((192, 256, 3), (100, 180, 100), dtype=np.uint8)
    bottom = np.full((192, 256, 3), (220, 235, 210), dtype=np.uint8)
    bottom[145:192, 20:236] = (45, 145, 205)
    bottom[15:75, 15:120] = (230, 210, 95)
    bottom[80:140, 15:120] = (230, 65, 55)
    bottom[15:75, 135:240] = (120, 90, 145)

    observation = detect_scene(DSScreens(top=top, bottom=bottom))

    assert observation.scene == SceneType.MOVE_MENU
