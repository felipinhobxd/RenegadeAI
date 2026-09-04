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
    return parser


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
            payload = {
                "connected": True,
                "read_only": True,
                "identity": asdict(identity) if identity else None,
                "anchor": asdict(anchor),
                "progress": asdict(reader.read_progress()),
                "max_gdb_read": client.max_read,
            }
        else:
            payload = asdict(reader.read_location())
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    except (OSError, GDBRemoteError) as exc:
        raise SystemExit(f"Structured memory unavailable: {exc}") from exc
    finally:
        if client is not None:
            client.close()
