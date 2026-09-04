from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from renegade_ai.perception.frame import DSScreens


class SceneType(StrEnum):
    OVERWORLD = "overworld"
    BATTLE_COMMAND = "battle_command"
    MOVE_MENU = "move_menu"
    BAG_MENU = "bag_menu"
    PARTY_MENU = "party_menu"
    SUMMARY_STATS = "summary_stats"
    SUMMARY_MOVES = "summary_moves"
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

    Thresholds are calibrated from real melonDS 1.1 Renegade Platinum captures
    supplied by the project owner. This classifier intentionally runs before OCR
    so the expensive recognizer is only used on screens that need text.
    """
    import numpy as np

    rgb = np.asarray(screen)[..., :3].astype(np.int16)
    if rgb.size == 0:
        return {
            name: 0.0
            for name in ("red", "blue", "tan", "yellow", "purple", "dark", "green")
        }

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
        "green": _ratio((g > 115) & (g > r * 1.10) & (g > b * 1.05)),
    }


def classify_metrics(metrics: dict[str, float]) -> tuple[SceneType, float]:
    """Classify one lower-screen metric vector.

    Ordering matters: several menus share the same blue back button. The new
    summary-moves screen, for example, previously looked enough like the battle
    move menu to make the old detector unsafe.
    """
    red = metrics.get("red", 0.0)
    blue = metrics.get("blue", 0.0)
    tan = metrics.get("tan", 0.0)
    yellow = metrics.get("yellow", 0.0)
    purple = metrics.get("purple", 0.0)
    dark = metrics.get("dark", 0.0)

    # Real command capture: red=0.289, blue=0.038.
    if red >= 0.18 and blue < 0.08 and purple < 0.05:
        return SceneType.BATTLE_COMMAND, min(1.0, 0.80 + (red - 0.18) * 1.5)

    # Bag category selector: tan=0.500, purple=0.116, almost no red.
    if tan >= 0.34 and purple >= 0.07 and red < 0.05:
        return SceneType.BAG_MENU, min(1.0, 0.82 + (tan - 0.34) * 0.45)

    # Pokemon summary stats page: blue=0.500, purple=0.095, tan~0.
    if blue >= 0.40 and 0.04 <= purple <= 0.18 and tan < 0.08:
        return SceneType.SUMMARY_STATS, min(1.0, 0.84 + (blue - 0.40) * 0.35)

    # Party page: blue=0.250, purple=0.278, tan=0.032.
    if blue >= 0.16 and purple >= 0.20 and tan < 0.10:
        return SceneType.PARTY_MENU, min(1.0, 0.82 + (purple - 0.20) * 0.7)

    # Summary move page: blue=0.217, tan=0.223, purple=0.167, dark~0.
    # This MUST run before battle move-menu detection.
    if blue >= 0.12 and tan >= 0.14 and purple >= 0.10 and dark < 0.04:
        return SceneType.SUMMARY_MOVES, min(1.0, 0.84 + (tan - 0.14) * 0.7)

    # Battle attack selector from the earlier calibrated capture has a blue back
    # bar, colored move slots, little tan, and a significant dark fraction.
    move_colors = red + yellow + purple
    if blue >= 0.08 and move_colors >= 0.05 and tan < 0.12:
        confidence = 0.76 + min(0.18, (blue - 0.08) * 0.9) + min(0.06, dark * 0.4)
        return SceneType.MOVE_MENU, min(1.0, confidence)

    # Early Poketch overworld placeholder: overwhelmingly tan.
    if tan >= 0.60 and red < 0.05 and blue < 0.05:
        return SceneType.OVERWORLD, min(1.0, 0.75 + (tan - 0.60) * 0.6)

    return SceneType.UNKNOWN, 0.25


def detect_scene(screens: DSScreens) -> SceneObservation:
    metrics = screen_metrics(screens.bottom)
    scene, confidence = classify_metrics(metrics)
    return SceneObservation(scene, confidence, metrics)
