from __future__ import annotations

from enum import StrEnum


class DSButton(StrEnum):
    A = "a"
    B = "b"
    X = "x"
    Y = "y"
    L = "l"
    R = "r"
    SELECT = "select"
    START = "start"
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

    @classmethod
    def parse(cls, value: str) -> DSButton:
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:
            choices = ", ".join(button.value for button in cls)
            raise ValueError(f"Unknown DS button {value!r}. Choose one of: {choices}") from exc
