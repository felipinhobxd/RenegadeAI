from __future__ import annotations

import argparse
import json
from pathlib import Path

from renegade_ai.cli import make_adapter
from renegade_ai.learning.battle_memory import BattleAdaptiveMemory
from renegade_ai.learning.evolve import ASIEvolveEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renegade-ai evolve",
        description=(
            "ASI-Evolve mode: mechanics-first autonomous play with hierarchical rewards "
            "and persistent outcome learning."
        ),
    )
    parser.add_argument("--config", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    battle = sub.add_parser("battle", help="Run one smart battle with ASI-Evolve rewards")
    battle.add_argument("--max-seconds", type=float, default=180.0)
    battle.add_argument("--poll-seconds", type=float, default=0.18)

    sub.add_parser("status", help="Show generation, reward, fitness and progress counters")
    sub.add_parser("reset-preview", help="Show which local learning files would be reset")
    return parser


def cmd_status() -> int:
    engine = ASIEvolveEngine()
    status = engine.status()
    print("ASI-Evolve status")
    print(f"Generation: {status['generation']}")
    print(f"Lifetime reward: {status['lifetime_reward']:.1f}")
    print(f"Fitness: {status['fitness']:.2f}")
    print(f"Reward events: {status['reward_events']}")
    print(
        "Battles: "
        f"wins={status['battle_wins']} losses={status['battle_losses']} "
        f"trainer={status['trainer_wins']} boss={status['boss_wins']}"
    )
    print(
        f"Captures={status['captures']} badges={status['badges']} "
        f"game-completions={status['game_completions']}"
    )
    print(f"Learned state groups: {status['q_states']}")
    return 0


def cmd_battle(config_path: Path | None, max_seconds: float, poll_seconds: float) -> int:
    from renegade_ai.agent.runtime import BattleAutopilot
    from renegade_ai.knowledge.bootstrap import ensure_renegade_dex
    from renegade_ai.perception.battle_vision import BattleVision
    from renegade_ai.state.runtime import RuntimeStateStore

    config, adapter = make_adapter(config_path)
    evolve = ASIEvolveEngine(
        qtable_path=config.learning.qtable.with_name("evolve_qtable.json"),
    )
    memory = BattleAdaptiveMemory(
        config.learning.qtable.with_name("battle_adaptive.json"),
        alpha=config.learning.alpha,
        evolve_engine=evolve,
    )
    # First-run bootstrap is automatic. This is intentionally done before the
    # battle loop so a user can simply start autonomous mode on a clean clone.
    dex = ensure_renegade_dex()
    autopilot = BattleAutopilot(
        adapter,
        config.capture.screen_layout,
        dex=dex,
        vision=BattleVision(),
        state_store=RuntimeStateStore(),
        adaptive_memory=memory,
    )
    print("ASI-Evolve battle started.")
    print(
        "Reward signals: damage dealt +, damage taken -, KO +, status outcomes, "
        "battle win/loss and future campaign milestones."
    )
    print("No random exploration is used during the live save. Ctrl+C stops immediately.")
    try:
        result = autopilot.run(max_seconds=max_seconds, poll_seconds=poll_seconds)
    except KeyboardInterrupt:
        print("ASI-Evolve stopped by user.")
        return 130

    print(
        f"Battle ended={result.ended} actions={result.actions} "
        f"elapsed={result.elapsed_seconds:.1f}s scene={result.last_scene.value}"
    )
    if result.last_decision:
        print(f"Last decision: {result.last_decision}")
    status = evolve.status()
    print(
        f"Generation={status['generation']} lifetime-reward={status['lifetime_reward']:.1f} "
        f"fitness={status['fitness']:.2f}"
    )
    return 0 if result.ended else 2


def cmd_reset_preview() -> int:
    files = [
        "data/evolve_state.json",
        "data/evolve_qtable.json",
        "data/evolve_rewards.jsonl",
        "data/battle_adaptive.json",
    ]
    print(json.dumps({"would_reset": files, "performed": False}, indent=2))
    print("This command never deletes learning data; remove files manually only if desired.")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "battle":
        code = cmd_battle(args.config, args.max_seconds, args.poll_seconds)
    elif args.command == "status":
        code = cmd_status()
    elif args.command == "reset-preview":
        code = cmd_reset_preview()
    else:  # pragma: no cover
        raise AssertionError(args.command)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
