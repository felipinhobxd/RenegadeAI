from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from renegade_ai.perception.frame import DSScreens


class SceneType(StrEnum):
    OVERWORLD = "overworld"
    BATTLE_COMMAND = "battle_command"
    MOVE_MENU = "move_menu"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SceneObservation:
    scene: SceneType
    confidence: float
    metrics: dict[str, float]


def _ratio(mask: Any) -> float:
    return float(mask.mean())


def screen_metrics(screen: Any) -> dict[str, float]:
    """Extract cheap color features from a DS screen.

    These intentionally avoid OCR and fixed pixel coordinates. The current
    thresholds are calibrated from the user's real Renegade Platinum captures:
    overworld, the red LUTAR battle command, and the four-slot move menu.
    """
    import numpy as np

    rgb = np.asarray(screen)[..., :3].astype(np.int16)
    if rgb.size == 0:
        return {name: 0.0 for name in ("red", "blue", "tan", "yellow", "purple", "dark")}

    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]
    maximum = np.max(rgb, axis=2)

    return {
        "red": _ratio((r > 180) & (g < 120) & (b < 120)),
        "blue": _ratio((b > 120) & (b > r * 1.15) & (b > g * 1.05)),
        "tan": _ratio((r > 130) & (r < 220) & (g > 110) & (g < 200) & (b < 150)),
        "yellow": _ratio((r > 180) & (g > 160) & (b < 130)),
        "purple": _ratio((r > 70) & (r < 170) & (b > 80) & (b > g * 1.10)),
        "dark": _ratio(maximum < 50),
    }


def detect_scene(screens: DSScreens) -> SceneObservation:
    metrics = screen_metrics(screens.bottom)
    red = metrics["red"]
    blue = metrics["blue"]
    tan = metrics["tan"]
    move_colors = metrics["red"] + metrics["yellow"] + metrics["purple"]

    # User capture: LUTAR screen has ~28% strong red and almost no blue.
    if red >= 0.18 and blue < 0.05:
        confidence = min(1.0, 0.70 + (red - 0.18) * 2.5)
        return SceneObservation(SceneType.BATTLE_COMMAND, confidence, metrics)

    # User capture: attack selection has a large blue VOLTAR bar and colored
    # move slots, while the command/overworld screens have effectively no blue.
    if blue >= 0.08 and move_colors >= 0.05:
        confidence = min(1.0, 0.72 + (blue - 0.08) * 1.8)
        return SceneObservation(SceneType.MOVE_MENU, confidence, metrics)

    # The lower overworld screen in this early-game state is almost entirely the
    # tan Poketch placeholder background (~99% by this metric).
    if tan >= 0.60 and red < 0.05 and blue < 0.05:
        confidence = min(1.0, 0.75 + (tan - 0.60) * 0.6)
        return SceneObservation(SceneType.OVERWORLD, confidence, metrics)

    return SceneObservation(SceneType.UNKNOWN, 0.25, metrics)
