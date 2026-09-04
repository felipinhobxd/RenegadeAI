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
from renegade_ai.perception.scene import detect_scene


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="renegade-ai")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check melonDS, capture, viewport and perception")

    capture = sub.add_parser("capture", help="Capture the melonDS window to a PNG")
    capture.add_argument("--output", type=Path, default=Path("captures/melonds.png"))
    capture.add_argument("--split", action="store_true", help="Also save cropped DS screens")

    press = sub.add_parser("press", help="Send one Nintendo DS button to melonDS")
    press.add_argument("button", help="a,b,x,y,l,r,select,start,up,down,left,right")
    press.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Override key hold duration, useful for testing the D-pad",
    )

    sub.add_parser("observe", help="Capture once and print the recognized game scene")

    battle = sub.add_parser(
        "battle-auto",
        help="Run the first safe pixel-driven battle loop",
    )
    battle.add_argument("--max-seconds", type=float, default=120.0)
    battle.add_argument("--poll-seconds", type=float, default=0.18)

    sub.add_parser("db-init", help="Initialize the experience database")
    return parser


def make_adapter(config_path: Path | None) -> tuple[object, DesktopMelonDSAdapter]:
    config = load_config(config_path)
    return config, DesktopMelonDSAdapter(config.melonds, config.capture)


def _format_metrics(metrics: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:.3f}" for name, value in sorted(metrics.items()))


def cmd_doctor(config_path: Path | None) -> int:
    print(f"RenegadeAI {__version__}")
    print(f"Python: {sys.version.split()[0]} ({platform.system()})")
    config, adapter = make_adapter(config_path)
    try:
        window = adapter.locate()
        print(f"melonDS: FOUND - {window.title!r}")
        print(f"Window: {window.width}x{window.height} at ({window.left}, {window.top})")
        print(f"Input backend: {adapter.input_backend_name}")
        frame = adapter.capture()
        print(f"Capture: OK - RGB {frame.shape[1]}x{frame.shape[0]}")
        screens = split_ds_screens(frame, config.capture.screen_layout)
        if screens.bounds is not None:
            x0, y0, x1, y1 = screens.bounds
            print(f"DS viewport: {x1 - x0}x{y1 - y0} at ({x0}, {y0})")
        observation = detect_scene(screens)
        print(f"Scene: {observation.scene.value} ({observation.confidence:.0%})")
        print(f"Scene metrics: {_format_metrics(observation.metrics)}")
    except Exception as exc:
        print(f"melonDS: ERROR - {exc}")
        return 1
    print("Foundation + perception checks passed.")
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
        viewport = output.with_name(f"{output.stem}-viewport{output.suffix}")
        Image.fromarray(screens.top).save(top)
        Image.fromarray(screens.bottom).save(bottom)
        if screens.viewport is not None:
            Image.fromarray(screens.viewport).save(viewport)
        print(f"Saved {top}")
        print(f"Saved {bottom}")
        if screens.viewport is not None:
            print(f"Saved {viewport}")
    return 0


def cmd_press(config_path: Path | None, raw_button: str, seconds: float | None) -> int:
    _, adapter = make_adapter(config_path)
    try:
        button = DSButton.parse(raw_button)
        adapter.press(button, seconds)
    except (ValueError, RuntimeError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    hold = f" for {seconds:.2f}s" if seconds is not None else ""
    print(f"Pressed DS {button.value.upper()}{hold} via {adapter.input_backend_name}")
    return 0


def cmd_observe(config_path: Path | None) -> int:
    config, adapter = make_adapter(config_path)
    frame = adapter.capture()
    screens = split_ds_screens(frame, config.capture.screen_layout)
    observation = detect_scene(screens)
    print(f"Scene: {observation.scene.value}")
    print(f"Confidence: {observation.confidence:.1%}")
    if screens.bounds is not None:
        x0, y0, x1, y1 = screens.bounds
        print(f"Viewport: {x1 - x0}x{y1 - y0} at ({x0}, {y0})")
    print(f"Metrics: {_format_metrics(observation.metrics)}")
    return 0


def cmd_battle_auto(
    config_path: Path | None,
    max_seconds: float,
    poll_seconds: float,
) -> int:
    from renegade_ai.agent.runtime import BattleAutopilot

    config, adapter = make_adapter(config_path)
    print("Battle autopilot started. Keep melonDS visible and do not use the keyboard.")
    print("Current policy: enter LUTAR and choose move slot 1.")
    result = BattleAutopilot(adapter, config.capture.screen_layout).run(
        max_seconds=max_seconds,
        poll_seconds=poll_seconds,
    )
    status = "ended" if result.ended else "timed out safely"
    print(
        f"Battle autopilot {status}: actions={result.actions}, "
        f"elapsed={result.elapsed_seconds:.1f}s, last_scene={result.last_scene.value}"
    )
    return 0 if result.ended else 2


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
        code = cmd_press(args.config, args.button, args.seconds)
    elif args.command == "observe":
        code = cmd_observe(args.config)
    elif args.command == "battle-auto":
        code = cmd_battle_auto(args.config, args.max_seconds, args.poll_seconds)
    elif args.command == "db-init":
        code = cmd_db_init(args.config)
    else:  # pragma: no cover
        parser.error("Unknown command")
        return
    raise SystemExit(code)


if __name__ == "__main__":
    main()
