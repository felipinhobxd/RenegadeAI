from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from renegade_ai.actions import DSButton


@dataclass(frozen=True, slots=True)
class EmulatorWindow:
    title: str
    left: int
    top: int
    width: int
    height: int


class EmulatorAdapter(ABC):
    """Boundary between the agent and an emulator implementation."""

    @abstractmethod
    def locate(self) -> EmulatorWindow:
        raise NotImplementedError

    @abstractmethod
    def focus(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def capture(self) -> Any:
        """Return an RGB numpy array."""
        raise NotImplementedError

    @abstractmethod
    def press(self, button: DSButton, duration: float | None = None) -> None:
        """Press a Nintendo DS button.

        ``duration`` overrides the configured hold time. Directional inputs often
        need a slightly longer hold than face buttons when driving stock melonDS
        from the desktop.
        """
        raise NotImplementedError

    def touch_bottom(self, x: float, y: float) -> None:
        """Touch normalized coordinates on the DS bottom screen.

        Coordinates use the inclusive logical range 0..1. Emulator backends that
        cannot provide touch input may keep the default implementation.
        """
        raise NotImplementedError("This emulator adapter does not implement touch input")
