from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from renegade_ai.memory.gdb import GDBRemoteClient, GDBRemoteError
from renegade_ai.memory.melonds_config import configure_melonds_debugger
from renegade_ai.memory.platinum import PlatinumMemoryReader


def _reader(host: str, port: int) -> tuple[GDBRemoteClient, PlatinumMemoryReader]:
    client = GDBRemoteClient(host, port)
    client.connect()
    reader = PlatinumMemoryReader(client)
    return client, reader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="renegade-ai memory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3333)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure", help="Patch melonDS TOML for ARM9 read-only GDB access")
    sub.add_parser("status", help="Probe melonDS and validate the Platinum SaveData anchor")
    sub.add_parser("location", help="Print exact map id/name and player X/Z from RAM")
    story = sub.add_parser("story", help="Read persistent Platinum story variables/flags")
    story.add_argument(
        "--all",
        action="store_true",
        help="Print every active flag instead of a compact meaningful sample",
    )
    sub.add_parser("objects", help="List persisted NPC/object hints on the current map")
    sub.add_parser("world", help="Print combined location/progress/story/NPC RAM snapshot")
    return parser


def _story_payload(reader: PlatinumMemoryReader, *, show_all: bool) -> dict[str, object]:
    story = reader.read_story_state()
    meaningful = [
        name
        for name in story.active_flags
        if name.startswith(
            (
                "FLAG_DEFEATED_",
                "FLAG_UNLOCKED_",
                "FLAG_TALKED_TO_",
                "FLAG_TEAM_GALACTIC_",
                "FLAG_GALACTIC_",
                "FLAG_RECEIVED_",
                "FLAG_HAS_",
                "FLAG_ROARK_",
            )
        )
    ]
    return {
        "digest": story.digest,
        "active_flag_count": len(story.active_flag_ids),
        "active_flags": list(story.active_flags) if show_all else meaningful[-80:],
        "nonzero_var_count": len(story.nonzero_vars),
        "nonzero_vars": story.nonzero_vars,
        "truncated_flags": not show_all and len(meaningful) > 80,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "configure":
        result = configure_melonds_debugger()
        print(f"Found configs: {len(result.paths)}")
        for path in result.paths:
            marker = "updated" if path in result.changed else "already configured"
            print(f"- {path} ({marker})")
        if not result.paths:
            print(
                "melonDS.toml was not found automatically. Start melonDS once so its "
                "configuration file exists, then rerun this diagnostic."
            )
        elif result.restart_required:
            print("melonDS configuration changed. Restart melonDS once.")
        return

    client: GDBRemoteClient | None = None
    try:
        client, reader = _reader(args.host, args.port)
        anchor = reader.probe()
        if args.command == "status":
            identity = reader.identity
            payload: object = {
                "connected": True,
                "read_only": True,
                "identity": asdict(identity) if identity else None,
                "anchor": asdict(anchor),
                "location": asdict(reader.read_location()),
                "progress": asdict(reader.read_progress()),
                "max_gdb_read": client.max_read,
            }
        elif args.command == "location":
            payload = asdict(reader.read_location())
        elif args.command == "story":
            payload = _story_payload(reader, show_all=args.all)
        elif args.command == "objects":
            objects = reader.read_field_objects(current_map_only=True)
            payload = {
                "location": asdict(reader.read_location()),
                "count": len(objects),
                "objects": [asdict(value) for value in objects],
            }
        else:
            world = reader.read_world_snapshot()
            payload = {
                "location": asdict(world.location),
                "progress": asdict(world.progress),
                "party_count": world.party_count,
                "story": {
                    "digest": world.story.digest,
                    "active_flag_count": len(world.story.active_flag_ids),
                    "nonzero_var_count": len(world.story.nonzero_vars),
                },
                "field_objects": [asdict(value) for value in world.field_objects],
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except (OSError, GDBRemoteError, ValueError) as exc:
        raise SystemExit(f"Structured memory unavailable: {exc}") from exc
    finally:
        if client is not None:
            client.close()
