from __future__ import annotations

import time
from typing import Any

from renegade_ai.actions import DSButton
from renegade_ai.config import CaptureConfig, MelonDSConfig
from renegade_ai.emulator.base import EmulatorAdapter, EmulatorWindow


class DesktopMelonDSAdapter(EmulatorAdapter):
    """Control stock melonDS through its desktop window.

    This deliberately avoids relying on experimental emulator scripting. It is
    the compatibility backend: keyboard input in, pixels out.
    """

    def __init__(self, melonds: MelonDSConfig, capture: CaptureConfig):
        self.config = melonds
        self.capture_config = capture
        self._window: Any | None = None

    def _find_native_window(self) -> Any:
        try:
            import pygetwindow as gw
        except Exception as exc:  # pragma: no cover - platform dependent
            raise RuntimeError(
                "Could not load PyGetWindow. Desktop window discovery is currently intended "
                "for Windows/macOS."
            ) from exc

        needle = self.config.window_title.lower()
        candidates = [w for w in gw.getAllWindows() if needle in (w.title or "").lower()]
        candidates = [w for w in candidates if w.width > 0 and w.height > 0]
        if not candidates:
            raise RuntimeError(
                f"No window containing {self.config.window_title!r} was found. "
                "Open melonDS and load the game first."
            )

        candidates.sort(key=lambda w: w.width * w.height, reverse=True)
        self._window = candidates[0]
        return self._window

    def locate(self) -> EmulatorWindow:
        window = self._find_native_window()
        return EmulatorWindow(
            title=window.title,
            left=int(window.left),
            top=int(window.top),
            width=int(window.width),
            height=int(window.height),
        )

    def focus(self) -> None:
        window = self._window or self._find_native_window()
        try:
            if getattr(window, "isMinimized", False):
                window.restore()
                time.sleep(0.15)
            window.activate()
            time.sleep(0.08)
        except Exception as exc:  # pragma: no cover - OS foreground rules vary
            raise RuntimeError(
                "Found melonDS but could not focus it. Click the emulator once and retry."
            ) from exc

    def _capture_box(self) -> dict[str, int]:
        window = self.locate()
        c = self.capture_config
        width = window.width - c.inset_left - c.inset_right
        height = window.height - c.inset_top - c.inset_bottom
        if width <= 0 or height <= 0:
            raise ValueError("Capture insets remove the entire melonDS window")
        return {
            "left": window.left + c.inset_left,
            "top": window.top + c.inset_top,
            "width": width,
            "height": height,
        }

    def capture(self) -> Any:
        import mss
        import numpy as np

        with mss.mss() as screen:
            shot = screen.grab(self._capture_box())
            bgra = np.asarray(shot)
        return bgra[:, :, :3][:, :, ::-1].copy()

    def press(self, button: DSButton) -> None:
        import pyautogui

        key = self.config.keys.get(button)
        if not key:
            raise KeyError(f"No keyboard mapping configured for DS button {button.value}")
        if self.config.focus_before_input:
            self.focus()
        pyautogui.keyDown(key)
        time.sleep(max(0.01, self.config.press_seconds))
        pyautogui.keyUp(key)
