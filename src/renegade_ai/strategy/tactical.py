from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from renegade_ai.knowledge.dex import RenegadeDex
from renegade_ai.state.runtime import RuntimePokemon, RuntimeStateStore
from renegade_ai.strategy.mechanics import defender_immunity
from renegade_ai.strategy.type_chart import effectiveness

if TYPE_CHECKING:
    from renegade_ai.perception.battle_vision import BattleVisualState


@dataclass(frozen=True, slots=True)
class SwitchChoice:
    slot: int
    profile: RuntimePokemon
    score: float
    reason: str


def _incoming_risk(opponent_types: tuple[str, ...], candidate_types: tuple[str, ...], ability: str | None) -> float:
    risks: list[float] = []
    for attack_type in opponent_types:
        if defender_immunity(attack_type, ability):
            risks.append(0.0)
        else:
            risks.append(effectiveness(attack_type, candidate_types))
    return max(risks, default=1.0)


def _stab_pressure(candidate_types: tuple[str, ...], opponent_types: tuple[str, ...]) -> float:
    return max((effectiveness(move_type, opponent_types) for move_type in candidate_types), default=1.0)


def choose_emergency_switch(
    state: BattleVisualState,
    store: RuntimeStateStore,
    dex: RenegadeDex,
) -> SwitchChoice | None:
    """Pick a switch only when staying in is clearly dangerous.

    This deliberately does not switch just because another matchup is slightly
    better. Unnecessary switching costs a turn and is especially dangerous when
    the opponent can KO on entry. The policy becomes active after a party scan.
    """
    if state.own is None or state.opponent is None:
        return None
    own_hp = state.own_hp_fraction
    if own_hp is None:
        return None

    danger = own_hp <= 0.16 or (state.own_status in {"PSN", "BRN"} and own_hp <= 0.26)
    # When the opponent is nearly finished, prefer taking the KO unless our HP
    # is critical enough that almost any hit would end the run.
    if state.opponent_hp_fraction is not None and state.opponent_hp_fraction <= 0.20:
        danger = own_hp <= 0.08
    if not danger:
        return None

    own_slug = state.own.slug
    choices: list[SwitchChoice] = []
    for slot, slug in enumerate(store.party_slots):
        if slug is None or slug == own_slug:
            continue
        profile = store.profile_for(slug)
        candidate = dex.pokemon.get(slug)
        if profile is None or candidate is None:
            continue
        hp = profile.hp_fraction
        if hp is not None and hp <= 0.25:
            continue
        risk = _incoming_risk(state.opponent.types, candidate.types, profile.ability)
        pressure = _stab_pressure(candidate.types, state.opponent.types)
        health = 0.75 if hp is None else hp
        # Lower incoming risk is most important; health and offensive pressure
        # break ties. Higher final score is better.
        score = health * 2.2 + pressure * 0.8 - risk * 1.7
        choices.append(
            SwitchChoice(
                slot=slot,
                profile=profile,
                score=score,
                reason=(
                    f"emergency switch: current HP={own_hp:.0%}, candidate HP="
                    f"{('?' if hp is None else f'{hp:.0%}')}, incoming-risk={risk:g}x, "
                    f"STAB-pressure={pressure:g}x"
                ),
            )
        )
    return max(choices, key=lambda choice: choice.score) if choices else None
