from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DSScreens:
    top: Any
    bottom: Any


def split_ds_screens(frame: Any, layout: str = "vertical") -> DSScreens:
    """Split a captured melonDS client into approximate top/bottom DS screens.

    This is intentionally only geometry. Later perception stages will calibrate
    exact screen bounds and remove borders/menu chrome.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        raise ValueError("Expected an HxWxC image")

    height, width = frame.shape[:2]
    if layout == "vertical":
        midpoint = height // 2
        return DSScreens(top=frame[:midpoint], bottom=frame[midpoint:])
    if layout == "horizontal":
        midpoint = width // 2
        return DSScreens(top=frame[:, :midpoint], bottom=frame[:, midpoint:])
    raise ValueError("screen_layout must be 'vertical' or 'horizontal'")
