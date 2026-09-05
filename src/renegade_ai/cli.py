from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

from renegade_ai import __version__
from renegade_ai.actions import DSButton
from renegade_ai.config import load_config
from renegade_ai.emulator.desktop import DesktopMelonDSAdapter
from renegade_ai.learning.store import ExperienceStore
from renegade_ai.perception.frame import split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene


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

    touch = sub.add_parser("touch", help="Touch normalized coordinates on the DS bottom screen")
    touch.add_argument("x", type=float, help="Horizontal coordinate from 0.0 to 1.0")
    touch.add_argument("y", type=float, help="Vertical coordinate from 0.0 to 1.0")

    sub.add_parser("observe", help="Capture once and print the recognized game scene")

    sync = sub.add_parser(
        "knowledge-sync",
        help="Download and build Renegade Platinum knowledge for National Dex 1-493",
    )
    sync.add_argument("--sprites", action="store_true", help="Also cache Platinum sprites locally")
    sync.add_argument("--workers", type=int, default=12)

    strategy = sub.add_parser("strategy", help="Show the generated Renegade build for a Pokemon")
    strategy.add_argument("pokemon", help="Pokemon name, e.g. chimchar, garchomp, rotom-heat")

    sub.add_parser(
        "identify",
        help="OCR the current battle: Pokemon, levels, exact HP, status, moves and PP",
    )
    sub.add_parser(
        "party-scan",
        help="Read the visible six-slot Pokemon party screen and remember it locally",
    )
    sub.add_parser(
        "summary-scan",
        help="Read and remember the visible Pokemon Dados or Movimentos summary page",
    )
    sub.add_parser("state-show", help="Show exact Pokemon data remembered from UI scans")
    sub.add_parser(
        "battle-plan",
        help="Rank the visible battle moves using OCR plus remembered exact Pokemon stats",
    )

    battle = sub.add_parser("battle-auto", help="Run the pixel-driven battle loop")
    battle.add_argument("--max-seconds", type=float, default=120.0)
    battle.add_argument("--poll-seconds", type=float, default=0.18)
    battle.add_argument(
        "--smart",
        action="store_true",
        help="Use OCR + Renegade dex + exact scanned state + matchup planning",
    )

    sub.add_parser("db-init", help="Initialize the experience database")
    return parser


def make_adapter(config_path: Path | None) -> tuple[object, DesktopMelonDSAdapter]:
    config = load_config(config_path)
    return config, DesktopMelonDSAdapter(config.melonds, config.capture)


def _format_metrics(metrics: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:.3f}" for name, value in sorted(metrics.items()))


def _load_battle_state(config_path: Path | None):
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.perception.battle_vision import BattleVision

    config, adapter = make_adapter(config_path)
    frame = adapter.capture()
    screens = split_ds_screens(frame, config.capture.screen_layout)
    dex = RenegadeDex()
    vision = BattleVision()
    return config, adapter, screens, dex, vision.observe(screens, dex)


def _fmt_hp(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.0%}"


def _fmt_exact_hp(current: int | None, maximum: int | None, fraction: float | None) -> str:
    if current is not None and maximum is not None:
        return f"{current}/{maximum} ({current / maximum:.0%})"
    return _fmt_hp(fraction)


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
    except Exception as exc:  # noqa: BLE001 - doctor reports dependency/OS failures
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


def cmd_touch(config_path: Path | None, x: float, y: float) -> int:
    _, adapter = make_adapter(config_path)
    try:
        adapter.touch_bottom(x, y)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Touched DS bottom screen at ({x:.3f}, {y:.3f})")
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


def cmd_knowledge_sync(sprites: bool, workers: int) -> int:
    from renegade_ai.knowledge.sync import sync_knowledge, sync_platinum_sprites

    print("Syncing Renegade Platinum Pokemon, moves and generated strategy profiles...")
    result = sync_knowledge(workers=max(1, workers))
    print(
        "Knowledge ready: "
        f"National Dex={result['national_dex_species']}/493, "
        f"records={result['pokemon_records']}, moves={result['moves']}, "
        f"strategies={result['strategies']}"
    )
    print(f"Pinned Renegade wiki revision: {result['wiki_commit']}")
    if sprites:
        print("Caching Platinum front/back sprites (optional visual fallback)...")
        sprite_result = sync_platinum_sprites(workers=max(1, workers * 2))
        print(
            f"Sprite cache: requested={sprite_result['requested']}, "
            f"downloaded={sprite_result['downloaded']}"
        )
    return 0


def cmd_strategy(raw_pokemon: str) -> int:
    from renegade_ai.knowledge.dex import RenegadeDex

    dex = RenegadeDex()
    pokemon = dex.pokemon_by_name(raw_pokemon)
    confidence = 1.0
    if pokemon is None:
        pokemon, confidence = dex.fuzzy_pokemon(raw_pokemon)
    if pokemon is None:
        print(f"Pokemon not found: {raw_pokemon!r}")
        return 1
    profile = dex.strategies.get(pokemon.slug)
    if profile is None:
        print(f"No strategy generated for {pokemon.name}")
        return 1

    print(f"{pokemon.name} #{pokemon.dex} ({' / '.join(pokemon.types)})")
    if confidence < 1.0:
        print(f"Matched input with confidence {confidence:.0%}")
    print(f"Role: {profile.role}")
    print(f"Offense: {profile.offense}")
    print(f"Ability: {profile.ability or 'any'}")
    print(f"Nature: {profile.nature}")
    print(f"EVs: {profile.evs}")
    print(f"Held item: {profile.item}")
    print("Ideal moves:")
    for move in profile.ideal_moves:
        print(f"  - {move}")
    print("Live battle decisions override the generic build when the matchup requires it.")
    return 0


def cmd_identify(config_path: Path | None) -> int:
    _config, _adapter, screens, _dex, state = _load_battle_state(config_path)
    scene = detect_scene(screens)
    print(f"Scene: {scene.scene.value} ({scene.confidence:.0%})")
    own = "unknown" if state.own is None else state.own.name
    opponent = "unknown" if state.opponent is None else state.opponent.name
    print(
        f"Own: {own} level={state.own_level or '?'} "
        f"hp={_fmt_exact_hp(state.own_hp_current, state.own_hp_max, state.own_hp_fraction)} "
        f"status={state.own_status or '-'} match={state.own_match_confidence:.0%}"
    )
    print(
        f"Opponent: {opponent} level={state.opponent_level or '?'} "
        f"hp={_fmt_hp(state.opponent_hp_fraction)} status={state.opponent_status or '-'} "
        f"match={state.opponent_match_confidence:.0%}"
    )
    for index, move in enumerate(state.moves, start=1):
        name = "unknown/empty" if move is None else move.name
        confidence = state.move_confidences[index - 1]
        current = state.pp_current[index - 1]
        maximum = state.pp_max[index - 1]
        pp = "?" if current is None or maximum is None else f"{current}/{maximum}"
        print(f"Move {index}: {name} PP={pp} ({confidence:.0%})")
    if state.own is None or state.opponent is None:
        print(f"Raw own OCR: {state.raw_own_text}")
        print(f"Raw opponent OCR: {state.raw_opponent_text}")
    return 0


def cmd_party_scan(config_path: Path | None) -> int:
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.perception.party_vision import PartyVision
    from renegade_ai.state.runtime import RuntimeStateStore

    config, adapter = make_adapter(config_path)
    screens = split_ds_screens(adapter.capture(), config.capture.screen_layout)
    scene = detect_scene(screens)
    if scene.scene != SceneType.PARTY_MENU:
        print(f"Current scene is {scene.scene.value}. Open POKEMON so the party list is visible.")
        return 2

    dex = RenegadeDex()
    state = PartyVision().observe(screens, dex)
    store = RuntimeStateStore()
    for member in state.members:
        if member.pokemon is None:
            store.set_party_slot(member.slot, None)
            print(f"Slot {member.slot + 1}: empty")
            continue
        pokemon = member.pokemon
        store.set_party_slot(member.slot, pokemon.slug)
        store.upsert(
            pokemon.slug,
            pokemon.name,
            hp_current=member.hp_current,
            hp_max=member.hp_max,
            status=member.status,
        )
        print(
            f"Slot {member.slot + 1}: {pokemon.name} "
            f"HP={_fmt_exact_hp(member.hp_current, member.hp_max, member.hp_fraction)} "
            f"status={member.status or '-'} match={member.confidence:.0%}"
        )
    store.save()
    print("Party state saved to data/runtime_state.json")
    return 0


def cmd_summary_scan(config_path: Path | None) -> int:
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.perception.summary_vision import SummaryVision
    from renegade_ai.state.runtime import RuntimeMove, RuntimeStateStore

    config, adapter = make_adapter(config_path)
    screens = split_ds_screens(adapter.capture(), config.capture.screen_layout)
    scene = detect_scene(screens)
    dex = RenegadeDex()
    vision = SummaryVision()
    store = RuntimeStateStore()

    if scene.scene == SceneType.SUMMARY_STATS:
        state = vision.observe_stats(screens, dex)
        if state.pokemon is None:
            print(f"Could not identify Pokemon. Raw OCR: {state.raw_text}")
            return 2
        pokemon = state.pokemon
        store.upsert(
            pokemon.slug,
            pokemon.name,
            level=state.level,
            hp_current=state.hp_current,
            hp_max=state.hp_max,
            status=state.status,
            ability=state.ability,
            item=state.item,
            attack=state.attack,
            defense=state.defense,
            special_attack=state.special_attack,
            special_defense=state.special_defense,
            speed=state.speed,
        )
        store.save()
        print(f"Saved exact stats for {pokemon.name} (match={state.confidence:.0%})")
        print(
            f"Lv={state.level or '?'} HP={state.hp_current or '?'}/{state.hp_max or '?'} "
            f"status={state.status or '-'} ability={state.ability or '?'} "
            f"item={state.item or 'none'}"
        )
        print(
            f"Atk={state.attack or '?'} Def={state.defense or '?'} "
            f"SpA={state.special_attack or '?'} SpD={state.special_defense or '?'} "
            f"Spe={state.speed or '?'}"
        )
        return 0

    if scene.scene == SceneType.SUMMARY_MOVES:
        state = vision.observe_moves(screens, dex)
        if state.pokemon is None:
            print("Could not identify Pokemon on the Movimentos page.")
            return 2
        pokemon = state.pokemon
        profile = store.upsert(pokemon.slug, pokemon.name, status=state.status)
        profile.moves = []
        for index, move in enumerate(state.moves):
            if move is None:
                continue
            profile.moves.append(
                RuntimeMove(
                    slug=move.slug,
                    name=move.name,
                    pp_current=state.pp_current[index],
                    pp_max=state.pp_max[index],
                )
            )
            pp = (
                "?"
                if state.pp_current[index] is None or state.pp_max[index] is None
                else f"{state.pp_current[index]}/{state.pp_max[index]}"
            )
            print(f"Move {index + 1}: {move.name} PP={pp}")
        store.save()
        print(f"Saved moves for {pokemon.name} (match={state.confidence:.0%})")
        return 0

    print(
        f"Current scene is {scene.scene.value}. Open Dados or Movimentos in the Pokemon summary."
    )
    return 2


def cmd_state_show() -> int:
    from renegade_ai.state.runtime import RuntimeStateStore

    store = RuntimeStateStore()
    party = store.party()
    if not party:
        print("No scanned party state yet. Run party-scan and summary-scan.")
        return 0
    for slot, slug in enumerate(store.party_slots, start=1):
        if slug is None:
            print(f"Slot {slot}: empty")
            continue
        profile = store.profile_for(slug)
        if profile is None:
            print(f"Slot {slot}: {slug} (no details)")
            continue
        print(
            f"Slot {slot}: {profile.name} Lv={profile.level or '?'} "
            f"HP={profile.hp_current or '?'}/{profile.hp_max or '?'} "
            f"status={profile.status or '-'} ability={profile.ability or '?'} "
            f"item={profile.item or 'none'}"
        )
        if profile.attack is not None:
            print(
                f"  Atk={profile.attack} Def={profile.defense} SpA={profile.special_attack} "
                f"SpD={profile.special_defense} Spe={profile.speed}"
            )
        if profile.moves:
            print(
                "  Moves: "
                + ", ".join(
                    f"{move.name} {move.pp_current or '?'}/{move.pp_max or '?'}"
                    for move in profile.moves
                )
            )
    return 0


def cmd_battle_plan(config_path: Path | None) -> int:
    from renegade_ai.state.runtime import RuntimeStateStore
    from renegade_ai.strategy.battle import rank_moves

    _config, _adapter, screens, _dex, state = _load_battle_state(config_path)
    scene = detect_scene(screens)
    if scene.scene != SceneType.MOVE_MENU:
        print(f"Current scene is {scene.scene.value}. Open LUTAR so battle moves are visible.")
        return 2
    if state.own is None or state.opponent is None:
        print("Could not identify both Pokemon. Run renegade-ai identify for OCR details.")
        return 2

    store = RuntimeStateStore()
    runtime = store.profile_for(state.own.slug)
    moves = list(state.moves)
    pp_current = list(state.pp_current)
    pp_max = list(state.pp_max)
    if runtime is not None:
        for index, cached in enumerate(runtime.moves[:4]):
            if index < len(moves) and moves[index] is None:
                moves[index] = _dex.moves.get(cached.slug)
            if index < len(pp_current) and pp_current[index] is None:
                pp_current[index] = cached.pp_current
            if index < len(pp_max) and pp_max[index] is None:
                pp_max[index] = cached.pp_max

    pp_fractions = [
        1.0 if now is None or not full else max(0.0, min(1.0, now / full))
        for now, full in zip(pp_current, pp_max, strict=False)
    ]
    ranked = rank_moves(
        state.own,
        state.opponent,
        moves,
        own_hp=state.own_hp_fraction or 1.0,
        opponent_hp=state.opponent_hp_fraction or 1.0,
        pp_fractions=pp_fractions,
        own_level=state.own_level or (runtime.level if runtime else None) or 50,
        opponent_level=state.opponent_level or 50,
        own_runtime=runtime,
    )
    if not ranked:
        print("No move was recognized. Run identify and send the output/capture.")
        return 2

    print(f"Battle plan: {state.own.name} vs {state.opponent.name}")
    if runtime is not None and runtime.ability:
        print(f"Using scanned ability/stats: {runtime.ability}")
    for rank, option in enumerate(ranked, start=1):
        print(
            f"{rank}. slot {option.slot + 1}: {option.move.name} score={option.score:.1f} "
            f"effectiveness={option.effectiveness:g}x - {option.reason}"
        )
    print(f"BEST: slot {ranked[0].slot + 1} -> {ranked[0].move.name}")
    return 0


def cmd_battle_auto(
    config_path: Path | None,
    max_seconds: float,
    poll_seconds: float,
    smart: bool,
) -> int:
    from renegade_ai.agent.runtime import BattleAutopilot

    config, adapter = make_adapter(config_path)
    kwargs = {}
    if smart:
        from renegade_ai.knowledge.dex import RenegadeDex
        from renegade_ai.perception.battle_vision import BattleVision

        kwargs = {"dex": RenegadeDex(), "vision": BattleVision()}

    print("Battle autopilot started. Keep melonDS visible and do not use keyboard/mouse.")
    if smart:
        print(
            "Smart policy: OCR + exact scanned stats/ability/PP + Renegade mechanics + touch."
        )
    else:
        print("Basic policy: enter LUTAR and choose slot 1. Add --smart for matchup planning.")
    result = BattleAutopilot(adapter, config.capture.screen_layout, **kwargs).run(
        max_seconds=max_seconds,
        poll_seconds=poll_seconds,
    )
    status = "ended" if result.ended else "timed out safely"
    print(
        f"Battle autopilot {status}: actions={result.actions}, "
        f"elapsed={result.elapsed_seconds:.1f}s, last_scene={result.last_scene.value}"
    )
    if result.last_decision:
        print(f"Last decision: {result.last_decision}")
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
    elif args.command == "touch":
        code = cmd_touch(args.config, args.x, args.y)
    elif args.command == "observe":
        code = cmd_observe(args.config)
    elif args.command == "knowledge-sync":
        code = cmd_knowledge_sync(args.sprites, args.workers)
    elif args.command == "strategy":
        code = cmd_strategy(args.pokemon)
    elif args.command == "identify":
        code = cmd_identify(args.config)
    elif args.command == "party-scan":
        code = cmd_party_scan(args.config)
    elif args.command == "summary-scan":
        code = cmd_summary_scan(args.config)
    elif args.command == "state-show":
        code = cmd_state_show()
    elif args.command == "battle-plan":
        code = cmd_battle_plan(args.config)
    elif args.command == "battle-auto":
        code = cmd_battle_auto(args.config, args.max_seconds, args.poll_seconds, args.smart)
    elif args.command == "db-init":
        code = cmd_db_init(args.config)
    else:  # pragma: no cover
        parser.error("Unknown command")
        return
    raise SystemExit(code)


if __name__ == "__main__":
    main()
