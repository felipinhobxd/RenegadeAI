from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib

from renegade_ai.actions import DSButton


DEFAULT_KEYS: dict[DSButton, str] = {
    DSButton.A: "x",
    DSButton.B: "z",
    DSButton.X: "s",
    DSButton.Y: "a",
    DSButton.L: "q",
    DSButton.R: "w",
    DSButton.SELECT: "backspace",
    DSButton.START: "enter",
    DSButton.UP: "up",
    DSButton.DOWN: "down",
    DSButton.LEFT: "left",
    DSButton.RIGHT: "right",
}


@dataclass(slots=True)
class CaptureConfig:
    inset_left: int = 0
    inset_top: int = 0
    inset_right: int = 0
    inset_bottom: int = 0
    screen_layout: str = "vertical"


@dataclass(slots=True)
class MelonDSConfig:
    window_title: str = "melonDS"
    focus_before_input: bool = True
    press_seconds: float = 0.06
    direction_press_seconds: float = 0.14
    input_backend: str = "auto"
    keys: dict[DSButton, str] = field(default_factory=lambda: dict(DEFAULT_KEYS))


@dataclass(slots=True)
class LearningConfig:
    database: Path = Path("data/experience.sqlite3")
    qtable: Path = Path("data/qtable.json")
    alpha: float = 0.20
    gamma: float = 0.95
    epsilon: float = 0.10


@dataclass(slots=True)
class AppConfig:
    melonds: MelonDSConfig = field(default_factory=MelonDSConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    learning: LearningConfig = field(default_factory=LearningConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    config = AppConfig()
    if path is None:
        default_path = Path("config.toml")
        if not default_path.exists():
            return config
        path = default_path

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    melon = raw.get("melonds", {})
    capture = raw.get("capture", {})
    learning = raw.get("learning", {})

    config.melonds.window_title = str(melon.get("window_title", config.melonds.window_title))
    config.melonds.focus_before_input = bool(
        melon.get("focus_before_input", config.melonds.focus_before_input)
    )
    config.melonds.press_seconds = float(melon.get("press_seconds", config.melonds.press_seconds))
    config.melonds.direction_press_seconds = float(
        melon.get("direction_press_seconds", config.melonds.direction_press_seconds)
    )
    config.melonds.input_backend = str(
        melon.get("input_backend", config.melonds.input_backend)
    ).strip().lower()
    if config.melonds.input_backend not in {"auto", "windows", "pyautogui"}:
        raise ValueError("melonds.input_backend must be auto, windows or pyautogui")

    key_data = melon.get("keys", {})
    for button in DSButton:
        if button.value in key_data:
            config.melonds.keys[button] = str(key_data[button.value])

    for name in ("inset_left", "inset_top", "inset_right", "inset_bottom"):
        if name in capture:
            setattr(config.capture, name, int(capture[name]))
    config.capture.screen_layout = str(capture.get("screen_layout", config.capture.screen_layout))

    config.learning.database = Path(learning.get("database", config.learning.database))
    config.learning.qtable = Path(learning.get("qtable", config.learning.qtable))
    config.learning.alpha = float(learning.get("alpha", config.learning.alpha))
    config.learning.gamma = float(learning.get("gamma", config.learning.gamma))
    config.learning.epsilon = float(learning.get("epsilon", config.learning.epsilon))
    return config
