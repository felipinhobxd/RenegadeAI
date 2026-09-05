from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from renegade_ai.cli import make_adapter
from renegade_ai.config import AppConfig, load_config
from renegade_ai.knowledge.bootstrap import ensure_renegade_dex
from renegade_ai.learning.evolve import ASIEvolveEngine
from renegade_ai.memory.gdb import GDBRemoteClient, GDBRemoteError
from renegade_ai.memory.melonds_config import configure_melonds_debugger
from renegade_ai.memory.platinum import PlatinumMemoryReader


def _log(message: str, *, path: Path = Path("runs/autoplay.log")) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renegade-ai-autoplay",
        description=(
            "Background RenegadeAI director. Waits for melonDS and starts the autonomous "
            "campaign automatically when the game window appears."
        ),
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--wait-seconds", type=float, default=2.0)
    parser.add_argument("--poll-seconds", type=float, default=0.18)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one melonDS session and exit instead of waiting for the emulator again.",
    )
    return parser


def _try_auto_configure_debugger(config: AppConfig) -> None:
    if not config.memory.enabled or not config.memory.auto_configure_melonds:
        return
    result = configure_melonds_debugger()
    if result.changed:
        joined = ", ".join(str(path) for path in result.changed)
        _log(
            "Updated melonDS for structured read-only ARM9 state "
            f"(GDB enabled, JIT disabled): {joined}. A melonDS restart is required."
        )


def _wait_for_melonds(config_path: Path | None, wait_seconds: float):
    config, adapter = make_adapter(config_path)
    announced = False
    while True:
        try:
            window = adapter.locate()
            _log(f"melonDS detected: {window.title!r} ({window.width}x{window.height})")
            return config, adapter
        except RuntimeError:
            if not announced:
                _log("Waiting for melonDS. Open the emulator and load Renegade Platinum.")
                announced = True
            time.sleep(max(0.5, wait_seconds))


def _connect_structured_memory(
    config: AppConfig,
) -> tuple[GDBRemoteClient | None, PlatinumMemoryReader | None]:
    if not config.memory.enabled:
        return None, None
    client = GDBRemoteClient(
        config.memory.host,
        config.memory.arm9_port,
        timeout=config.memory.timeout,
    )
    try:
        client.connect()
        reader = PlatinumMemoryReader(client, reporter=_log)
        reader.probe()
        location = reader.read_location()
        progress = reader.read_progress()
        party_count = reader.party_count()
        try:
            story = reader.read_story_state()
            objects = reader.read_field_objects(current_map_only=True)
            enrichment = (
                f", storyFlags={len(story.active_flag_ids)}, "
                f"storyVars={len(story.nonzero_vars)}, mapObjects={len(objects)}"
            )
        except (OSError, GDBRemoteError, ValueError):
            enrichment = ", story/object enrichment=pending"
    except (OSError, GDBRemoteError, ValueError) as exc:
        client.close()
        _log(
            "Structured ARM9 state is not available in this melonDS session; "
            f"vision/OCR fallback remains active. Reason: {exc}"
        )
        return None, None

    _log(
        "Structured ARM9 read-only mode active: "
        f"{location.map_name}#{location.map_header_id} "
        f"({location.x},{location.z}), facing={location.facing}, "
        f"party={party_count}/6, badges={progress.badge_count}, money={progress.money}"
        f"{enrichment}."
    )
    return client, reader


def run_daemon(
    *,
    config_path: Path | None = None,
    wait_seconds: float = 2.0,
    poll_seconds: float = 0.18,
    once: bool = False,
) -> int:
    initial_config = load_config(config_path)
    _try_auto_configure_debugger(initial_config)

    while True:
        config, adapter = _wait_for_melonds(config_path, wait_seconds)
        _try_auto_configure_debugger(config)
        memory_client: GDBRemoteClient | None = None
        try:
            dex = ensure_renegade_dex(reporter=_log)
            from renegade_ai.campaign.objective_runtime import ObjectiveCampaignAutopilot

            memory_client, structured_reader = _connect_structured_memory(config)
            evolve = ASIEvolveEngine(
                qtable_path=config.learning.qtable.with_name("evolve_qtable.json"),
            )
            campaign = ObjectiveCampaignAutopilot(
                adapter,
                config.capture.screen_layout,
                dex=dex,
                structured_reader=structured_reader,
                evolve_engine=evolve,
                poll_seconds=poll_seconds,
            )

            if structured_reader is not None:
                _log(
                    "Preparing objective navigation world cache: real Platinum map-header "
                    "metadata, matrices, collision blocks and warp graph. This is cached."
                )
                complete_world = campaign.progression.world.ensure_matrix_index()
                try:
                    location = structured_reader.read_location()
                    campaign.progression.world.warm_current_map(
                        location.map_header_id,
                        location.x,
                        location.z,
                    )
                    decision = campaign._progression_decision(location)
                    if decision is not None and decision.objective is not None:
                        _log(
                            "Current story objective: "
                            f"{decision.objective.id} - {decision.objective.description}; "
                            f"planner={decision.reason}."
                        )
                except (OSError, GDBRemoteError, ValueError):
                    pass
                world_stats = campaign.progression.world.stats()
                _log(
                    "World planner ready: "
                    f"completeMatrixIndex={complete_world}, stats={world_stats}. "
                    "Static Platinum data is overlaid with movement/warps observed from "
                    "the live Renegade save."
                )

            mode = (
                "structured RAM + story objectives + real collision/warps + A*"
                if structured_reader is not None
                else "balanced vision/OCR fallback"
            )
            _log(
                "Autonomous campaign started: "
                f"navigation={mode}; proactive dialogue detection, stuck screenshots, "
                "battle takeover and ASI-Evolve are active."
            )
            result = campaign.run()
            _log(
                "Campaign session stopped: "
                f"completed={result.completed} steps={result.steps} battles={result.battles} "
                f"captures={result.captures} reason={result.reason}"
            )
            if result.completed:
                _log("Game completion detected. Autoplay will stop for this playthrough.")
                return 0
        except KeyboardInterrupt:
            _log("Autoplay stopped by user.")
            return 130
        except Exception as exc:  # noqa: BLE001 - daemon must survive session failures.
            _log(f"Autoplay session error: {type(exc).__name__}: {exc}")
            time.sleep(max(2.0, wait_seconds))
        finally:
            if memory_client is not None:
                memory_client.close()

        if once:
            return 0
        _try_auto_configure_debugger(load_config(config_path))
        _log("melonDS session ended or failed; waiting for the game to appear again.")
        time.sleep(max(0.5, wait_seconds))


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    code = run_daemon(
        config_path=args.config,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
        once=args.once,
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main(sys.argv[1:])
