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
