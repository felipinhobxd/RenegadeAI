from __future__ import annotations

import argparse
from pathlib import Path

from renegade_ai.cli import make_adapter
from renegade_ai.perception.semantic_scout import SemanticAutoCalibrationScout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renegade-ai scout",
        description="Automatically collect and name screenshots needed for calibration.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("captures/auto-calibration"),
        help="Directory for full/viewport/top/bottom PNGs and manifest.json",
    )
    parser.add_argument(
        "--watch-seconds",
        type=float,
        default=0.0,
        help="After active scouting, passively capture novel/unknown screens for N seconds",
    )
    parser.add_argument(
        "--passive-only",
        action="store_true",
        help="Do not navigate menus; only watch and capture scene transitions",
    )
    parser.add_argument("--settle-seconds", type=float, default=0.45)
    parser.add_argument("--config", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config, adapter = make_adapter(args.config)
    scout = SemanticAutoCalibrationScout(
        adapter,
        config.capture.screen_layout,
        root=args.output,
        settle_seconds=args.settle_seconds,
    )

    try:
        before = len(scout.records)
        if not args.passive_only:
            scout.run_active()
        if args.watch_seconds > 0:
            scout.watch(args.watch_seconds)
    except KeyboardInterrupt:
        print("Scout stopped by user; captures already written are preserved.")
    except Exception as exc:
        print(f"Scout stopped safely: {exc}")
        raise SystemExit(2) from exc

    new_records = scout.records[before:]
    print(f"Auto-calibration directory: {scout.root}")
    print(f"New captures: {len(new_records)}")
    for record in new_records:
        needed = " [NEEDED]" if record.required else ""
        print(
            f"  {record.target}{needed}: scene={record.scene} "
            f"confidence={record.confidence:.0%} -> {record.full}"
        )

    missing = scout.missing()
    if missing:
        print("Still missing:")
        for target in missing:
            print(f"  - {target}")
        print("The bot did not force unsafe actions to obtain these screens.")
    else:
        print("All currently requested calibration screenshots were collected automatically.")
    print(f"Manifest: {scout.manifest_path}")


if __name__ == "__main__":
    main()
