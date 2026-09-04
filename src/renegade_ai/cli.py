from __future__ import annotations

import argparse
from pathlib import Path
import platform
import sys

from renegade_ai import __version__
from renegade_ai.actions import DSButton
from renegade_ai.config import load_config
from renegade_ai.emulator.desktop import DesktopMelonDSAdapter
from renegade_ai.learning.store import ExperienceStore
from renegade_ai.perception.frame import split_ds_screens


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="renegade-ai")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check whether melonDS can be found and captured")

    capture = sub.add_parser("capture", help="Capture the melonDS window to a PNG")
    capture.add_argument("--output", type=Path, default=Path("captures/melonds.png"))
    capture.add_argument("--split", action="store_true", help="Also save approximate DS screens")

    press = sub.add_parser("press", help="Send one Nintendo DS button to melonDS")
    press.add_argument("button", help="a,b,x,y,l,r,select,start,up,down,left,right")

    sub.add_parser("db-init", help="Initialize the experience database")
    return parser


def make_adapter(config_path: Path | None) -> tuple[object, DesktopMelonDSAdapter]:
    config = load_config(config_path)
    return config, DesktopMelonDSAdapter(config.melonds, config.capture)


def cmd_doctor(config_path: Path | None) -> int:
    print(f"RenegadeAI {__version__}")
    print(f"Python: {sys.version.split()[0]} ({platform.system()})")
    config, adapter = make_adapter(config_path)
    try:
        window = adapter.locate()
        print(f"melonDS: FOUND - {window.title!r}")
        print(f"Window: {window.width}x{window.height} at ({window.left}, {window.top})")
        frame = adapter.capture()
        print(f"Capture: OK - RGB {frame.shape[1]}x{frame.shape[0]}")
        print(f"Layout: {config.capture.screen_layout}")
    except Exception as exc:
        print(f"melonDS: ERROR - {exc}")
        return 1
    print("Foundation checks passed.")
    return 0


def cmd_capture(config_path: Path | None, output: Path, split: bool) -> int:
    from PIL import Image

    config, adapter = make_adapter(config_path)
    frame = adapter.capture()
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(output)
    print(f"Saved {output}")
    if split:
        screens = split_ds_screens(frame, config.capture.screen_layout)
        top = output.with_name(f"{output.stem}-top{output.suffix}")
        bottom = output.with_name(f"{output.stem}-bottom{output.suffix}")
        Image.fromarray(screens.top).save(top)
        Image.fromarray(screens.bottom).save(bottom)
        print(f"Saved {top}")
        print(f"Saved {bottom}")
    return 0


def cmd_press(config_path: Path | None, raw_button: str) -> int:
    _, adapter = make_adapter(config_path)
    try:
        button = DSButton.parse(raw_button)
        adapter.press(button)
    except (ValueError, RuntimeError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Pressed DS {button.value.upper()}")
    return 0


def cmd_db_init(config_path: Path | None) -> int:
    config = load_config(config_path)
    ExperienceStore(config.learning.database)
    print(f"Experience database ready: {config.learning.database}")
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        code = cmd_doctor(args.config)
    elif args.command == "capture":
        code = cmd_capture(args.config, args.output, args.split)
    elif args.command == "press":
        code = cmd_press(args.config, args.button)
    elif args.command == "db-init":
        code = cmd_db_init(args.config)
    else:  # pragma: no cover
        parser.error("Unknown command")
        return
    raise SystemExit(code)


if __name__ == "__main__":
    main()
