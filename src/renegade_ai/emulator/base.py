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
    def press(self, button: DSButton) -> None:
        raise NotImplementedError
