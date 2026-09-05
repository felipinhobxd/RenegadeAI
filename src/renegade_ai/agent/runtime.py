from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from renegade_ai.actions import DSButton
from renegade_ai.emulator.base import EmulatorAdapter
from renegade_ai.perception.frame import split_ds_screens
from renegade_ai.perception.scene import SceneType, detect_scene

if TYPE_CHECKING:
    from renegade_ai.knowledge.dex import RenegadeDex
    from renegade_ai.learning.battle_memory import BattleAdaptiveMemory
    from renegade_ai.perception.battle_vision import BattleVision, BattleVisualState
    from renegade_ai.state.runtime import RuntimePokemon, RuntimeStateStore

_MOVE_TOUCH_CENTERS = (
    (0.25, 0.27),
    (0.75, 0.27),
    (0.25, 0.59),
    (0.75, 0.59),
)


def _screen_fingerprint(screen: Any) -> str:
    import numpy as np

    rgb = np.asarray(screen)[..., :3]
    if rgb.size == 0:
        return "empty"
    height, width = rgb.shape[:2]
    sy = max(1, height // 24)
    sx = max(1, width // 32)
    sample = (rgb[::sy, ::sx][:24, :32] // 16).astype("uint8")
    return hashlib.blake2b(sample.tobytes(), digest_size=8).hexdigest()


@dataclass(slots=True)
class BattleRunResult:
    ended: bool
    actions: int
    elapsed_seconds: float
    last_scene: SceneType
    last_decision: str | None = None


class BattleAutopilot:
    """Pixel-driven battle loop with Renegade mechanics and bounded learning."""

    def __init__(
        self,
        emulator: EmulatorAdapter,
        screen_layout: str = "vertical",
        *,
        dex: RenegadeDex | None = None,
        vision: BattleVision | None = None,
        state_store: RuntimeStateStore | None = None,
        adaptive_memory: BattleAdaptiveMemory | None = None,
    ) -> None:
        self.emulator = emulator
        self.screen_layout = screen_layout
        self.dex = dex
        self.vision = vision
        if state_store is None and dex is not None and vision is not None:
            from renegade_ai.state.runtime import RuntimeStateStore

            state_store = RuntimeStateStore()
        if adaptive_memory is None and dex is not None and vision is not None:
            from renegade_ai.learning.battle_memory import BattleAdaptiveMemory

            adaptive_memory = BattleAdaptiveMemory()
        self.state_store = state_store
        self.adaptive_memory = adaptive_memory

    @property
    def smart(self) -> bool:
        return self.dex is not None and self.vision is not None

    def _update_runtime_profile(self, state: BattleVisualState) -> RuntimePokemon | None:
        if self.state_store is None or state.own is None:
            return None
        profile = self.state_store.upsert(
            state.own.slug,
            state.own.name,
            level=state.own_level,
            hp_current=state.own_hp_current,
            hp_max=state.own_hp_max,
            status=state.own_status,
        )
        self.state_store.save()
        return profile

    def _moves_and_pp(self, state: BattleVisualState, profile: RuntimePokemon | None):
        assert self.dex is not None
        moves = list(state.moves)
        current = list(state.pp_current)
        maximum = list(state.pp_max)

        if profile is not None:
            # Summary scans save known moves in screen order. Empty fourth slots
            # are naturally absent and therefore do not shift the common 1/2/3
            # pattern. Explicit slot metadata remains available for future sparse
            # menu recovery.
            for index, cached in enumerate(profile.moves[:4]):
                while len(moves) <= index:
                    moves.append(None)
                    current.append(None)
                    maximum.append(None)
                if moves[index] is None:
                    moves[index] = self.dex.moves.get(cached.slug)
                if current[index] is None:
                    current[index] = cached.pp_current
                if maximum[index] is None:
                    maximum[index] = cached.pp_max

        pp_fractions: list[float] = []
        for now, full in zip(current, maximum, strict=False):
            if now is None or not full:
                pp_fractions.append(1.0)
            else:
                pp_fractions.append(max(0.0, min(1.0, now / full)))
        while len(pp_fractions) < len(moves):
            pp_fractions.append(1.0)
        return moves, pp_fractions

    def _choose_move(self, screens) -> str:
        if not self.smart:
            self.emulator.press(DSButton.A)
            return "fallback move slot 1"

        from renegade_ai.strategy.battle import rank_moves

        assert self.dex is not None
        assert self.vision is not None
        state = self.vision.observe(screens, self.dex)
        profile = self._update_runtime_profile(state)
        if (
            state.own is None
            or state.opponent is None
            or state.own_match_confidence < 0.42
            or state.opponent_match_confidence < 0.42
        ):
            self.emulator.press(DSButton.A)
            return (
                "OCR uncertain; safe fallback slot 1 "
                f"(own={state.own_match_confidence:.0%}, "
                f"opponent={state.opponent_match_confidence:.0%})"
            )

        moves, pp_fractions = self._moves_and_pp(state, profile)
        ranked = rank_moves(
            state.own,
            state.opponent,
            moves,
            own_hp=state.own_hp_fraction or 1.0,
            opponent_hp=state.opponent_hp_fraction or 1.0,
            pp_fractions=pp_fractions,
            own_level=state.own_level or (profile.level if profile else None) or 50,
            opponent_level=state.opponent_level or 50,
            own_runtime=profile,
        )
        if not ranked:
            self.emulator.press(DSButton.A)
            return "No move was confidently recognized or cached; safe fallback slot 1"

        best = ranked[0]
        learned_correction = 0.0
        if self.adaptive_memory is not None:
            best, learned_correction = self.adaptive_memory.choose(state, ranked)

        if best.score < -100:
            return "All recognized damaging move PP appears exhausted; no automatic input sent"

        x, y = _MOVE_TOUCH_CENTERS[best.slot]
        self.emulator.touch_bottom(x, y)
        if self.adaptive_memory is not None:
            self.adaptive_memory.remember(state, best.move.slug)

        status_text = "" if not state.own_status else f", status={state.own_status}"
        learning_text = (
            ""
            if abs(learned_correction) < 0.05
            else f", learned={learned_correction:+.1f}"
        )
        return (
            f"{state.own.name} vs {state.opponent.name}: slot {best.slot + 1} "
            f"{best.move.name} score={best.score:.1f}{learning_text}{status_text}; {best.reason}"
        )

    def _observe_learning_transition(self, screens) -> float | None:
        if not self.smart or self.adaptive_memory is None:
            return None
        assert self.dex is not None
        assert self.vision is not None
        state = self.vision.observe(screens, self.dex)
        self._update_runtime_profile(state)
        return self.adaptive_memory.observe_next_turn(state)

    def _enter_fight(self) -> None:
        if self.smart:
            from renegade_ai.agent.battle_controls import BattleCommand, touch_battle_command

            touch_battle_command(self.emulator, BattleCommand.FIGHT)
        else:
            self.emulator.press(DSButton.A)

    def run(self, *, max_seconds: float = 120.0, poll_seconds: float = 0.18) -> BattleRunResult:
        started = time.monotonic()
        actions = 0
        last_scene = SceneType.UNKNOWN
        last_decision: str | None = None
        acted_scene: SceneType | None = None
        saw_battle = False
        unknown_key: str | None = None
        unknown_since = started
        unknown_pressed = False
        last_known_battle_scene = started
        unknown_advances = 0

        while time.monotonic() - started < max_seconds:
            frame = self.emulator.capture()
            screens = split_ds_screens(frame, self.screen_layout)
            observation = detect_scene(screens)
            scene = observation.scene
            last_scene = scene
            now = time.monotonic()

            if scene != SceneType.UNKNOWN:
                unknown_key = None
                unknown_pressed = False
                unknown_advances = 0

            if acted_scene is not None and scene != acted_scene:
                acted_scene = None

            if scene == SceneType.BATTLE_COMMAND:
                saw_battle = True
                last_known_battle_scene = now
                if acted_scene is None:
                    reward = self._observe_learning_transition(screens)
                    # Bag and switching have calibrated entry buttons/screens,
                    # but item rows and switch confirmation still require the
                    # autonomous scout captures before they are allowed live.
                    self._enter_fight()
                    actions += 1
                    acted_scene = scene
                    last_decision = "enter LUTAR/FIGHT"
                    if reward is not None:
                        last_decision += f"; learned reward={reward:+.1f}"

            elif scene == SceneType.MOVE_MENU:
                saw_battle = True
                last_known_battle_scene = now
                if acted_scene is None:
                    last_decision = self._choose_move(screens)
                    if "no automatic input" not in last_decision:
                        actions += 1
                    acted_scene = scene

            elif scene == SceneType.OVERWORLD and saw_battle:
                # Smart mode never intentionally uses RUN, so a normal
                # battle->overworld transition is treated as successful battle
                # completion. Future capture/flee detectors can pass a more
                # specific outcome when those actions are enabled.
                if self.adaptive_memory is not None:
                    total_reward = self.adaptive_memory.finish_battle(won=True)
                    suffix = f"ASI-Evolve battle reward={total_reward:+.1f}"
                    last_decision = f"{last_decision}; {suffix}" if last_decision else suffix
                return BattleRunResult(
                    ended=True,
                    actions=actions,
                    elapsed_seconds=now - started,
                    last_scene=scene,
                    last_decision=last_decision,
                )

            elif scene in {
                SceneType.BAG_MENU,
                SceneType.PARTY_MENU,
                SceneType.SUMMARY_STATS,
                SceneType.SUMMARY_MOVES,
            }:
                # Never mash A on a non-battle menu. This also protects against
                # the old bug where summary moves looked like the battle menu.
                last_decision = f"paused safely on {scene.value}; no automatic input"

            elif scene == SceneType.UNKNOWN and saw_battle:
                # Battle animations and text boxes are frequently UNKNOWN to the
                # cheap color classifier. Wait until a frame is visually stable
                # before pressing A once. If the text changes, it becomes a new
                # stable frame and may receive one more A. This advances battle
                # narration without the classic repeated-A menu spam loop.
                key = _screen_fingerprint(screens.bottom)
                if key != unknown_key:
                    unknown_key = key
                    unknown_since = now
                    unknown_pressed = False
                elif not unknown_pressed and now - unknown_since >= max(0.55, poll_seconds * 3):
                    self.emulator.press(DSButton.A)
                    actions += 1
                    unknown_pressed = True
                    unknown_advances += 1
                    last_decision = "advance stable battle text"

                # Some later overworld palettes are not yet classified as
                # OVERWORLD. Do not hold the campaign hostage for ten minutes:
                # after a prolonged unknown period, release control to the
                # campaign director. If this was still a battle, the next known
                # battle screen simply hands control back here.
                if now - last_known_battle_scene >= 12.0 and unknown_advances >= 2:
                    return BattleRunResult(
                        ended=False,
                        actions=actions,
                        elapsed_seconds=now - started,
                        last_scene=scene,
                        last_decision="prolonged unknown; returned control to campaign director",
                    )

            time.sleep(max(0.05, poll_seconds))

        return BattleRunResult(
            ended=False,
            actions=actions,
            elapsed_seconds=time.monotonic() - started,
            last_scene=last_scene,
            last_decision=last_decision,
        )
