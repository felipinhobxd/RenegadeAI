from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DSScreens:
    top: Any
    bottom: Any
    viewport: Any | None = None
    bounds: tuple[int, int, int, int] | None = None


def _largest_true_run(mask: Any) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for index, enabled in enumerate(mask):
        if bool(enabled) and start is None:
            start = index
        if start is not None and (not bool(enabled) or index == len(mask) - 1):
            end = index if not bool(enabled) else index + 1
            if best is None or end - start > best[1] - best[0]:
                best = (start, end)
            start = None
    return best


def crop_game_viewport(frame: Any, layout: str = "vertical") -> tuple[Any, tuple[int, int, int, int]]:
    """Automatically remove melonDS chrome and black side bars.

    The detector is intentionally geometry/color based instead of using fixed
    coordinates. This lets it keep working when the user resizes the melonDS
    window. It was calibrated against the 1936x1048 melonDS 1.1 captures used by
    this project, where it isolates the centered DS viewport reliably.
    """
    import numpy as np

    if frame is None or getattr(frame, "ndim", 0) != 3:
        raise ValueError("Expected an HxWxC image")
    if layout not in {"vertical", "horizontal"}:
        raise ValueError("screen_layout must be 'vertical' or 'horizontal'")

    rgb = np.asarray(frame)[..., :3]
    bright = np.max(rgb, axis=2) > 40

    if layout == "vertical":
        occupancy = bright.mean(axis=0)
        run = _largest_true_run(occupancy >= 0.35)
        x0, x1 = run if run is not None else (0, rgb.shape[1])
        row_occupancy = bright[:, x0:x1].mean(axis=1)
        active_rows = np.flatnonzero(row_occupancy >= 0.75)
        if active_rows.size:
            y0, y1 = int(active_rows[0]), int(active_rows[-1]) + 1
        else:
            y0, y1 = 0, rgb.shape[0]
    else:
        occupancy = bright.mean(axis=1)
        run = _largest_true_run(occupancy >= 0.35)
        y0, y1 = run if run is not None else (0, rgb.shape[0])
        col_occupancy = bright[y0:y1, :].mean(axis=0)
        active_cols = np.flatnonzero(col_occupancy >= 0.75)
        if active_cols.size:
            x0, x1 = int(active_cols[0]), int(active_cols[-1]) + 1
        else:
            x0, x1 = 0, rgb.shape[1]

    # Avoid absurd detections caused by an almost-black transitional frame.
    if x1 - x0 < 64 or y1 - y0 < 64:
        return rgb, (0, 0, rgb.shape[1], rgb.shape[0])
    return rgb[y0:y1, x0:x1], (x0, y0, x1, y1)


def split_ds_screens(frame: Any, layout: str = "vertical") -> DSScreens:
    """Crop the visible DS viewport and split it into top/bottom screens."""
    viewport, bounds = crop_game_viewport(frame, layout)
    height, width = viewport.shape[:2]
    if layout == "vertical":
        midpoint = height // 2
        return DSScreens(
            top=viewport[:midpoint],
            bottom=viewport[midpoint:],
            viewport=viewport,
            bounds=bounds,
        )
    midpoint = width // 2
    return DSScreens(
        top=viewport[:, :midpoint],
        bottom=viewport[:, midpoint:],
        viewport=viewport,
        bounds=bounds,
    )
