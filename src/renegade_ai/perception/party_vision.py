from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from renegade_ai.knowledge.dex import RenegadeDex
from renegade_ai.knowledge.models import PokemonData
from renegade_ai.perception.frame import DSScreens
from renegade_ai.perception.ocr import OCRScanner, RecognizedText, lines_in_box, raw_text


@dataclass(frozen=True, slots=True)
class PartyMemberObservation:
    slot: int
    pokemon: PokemonData | None
    confidence: float
    hp_current: int | None
    hp_max: int | None
    status: str | None
    raw_text: tuple[str, ...]

    @property
    def hp_fraction(self) -> float | None:
        if self.hp_current is None or not self.hp_max:
            return None
        return self.hp_current / self.hp_max


@dataclass(frozen=True, slots=True)
class PartyVisualState:
    members: tuple[PartyMemberObservation, ...]

    @property
    def occupied(self) -> tuple[PartyMemberObservation, ...]:
        return tuple(member for member in self.members if member.pokemon is not None)


# Real party page: 2 columns x 3 rows. The bottom prompt/back button starts
# around 80% of screen height, so all six slots live above that boundary.
_PARTY_SLOTS = (
    (0.00, 0.00, 0.50, 0.25),
    (0.50, 0.00, 1.00, 0.25),
    (0.00, 0.24, 0.50, 0.49),
    (0.50, 0.24, 1.00, 0.49),
    (0.00, 0.48, 0.50, 0.74),
    (0.50, 0.48, 1.00, 0.74),
)
_FRACTION_RE = re.compile(r"([0-9]{1,3})\s*/\s*([0-9]{1,3})")
_STATUS = ("PSN", "BRN", "PAR", "SLP", "FRZ", "FNT")


def _match_pokemon(
    dex: RenegadeDex, lines: list[RecognizedText]
) -> tuple[PokemonData | None, float]:
    best: PokemonData | None = None
    best_score = 0.0
    for line in lines:
        record, fuzzy = dex.fuzzy_pokemon(line.text)
        score = fuzzy * max(0.45, line.confidence)
        if record is not None and score > best_score:
            best, best_score = record, score
    return best, min(1.0, best_score)


def _fraction(lines: list[RecognizedText]) -> tuple[int | None, int | None]:
    for line in lines:
        text = line.text.replace("O", "0").replace("o", "0")
        match = _FRACTION_RE.search(text)
        if match is None:
            continue
        current, maximum = int(match.group(1)), int(match.group(2))
        if 0 <= current <= maximum and 1 <= maximum <= 999:
            return current, maximum
    return None, None


def _status(lines: list[RecognizedText]) -> str | None:
    text = " ".join(line.text.upper() for line in lines)
    return next((status for status in _STATUS if status in text), None)


class PartyVision:
    def __init__(self, engine: Any | None = None) -> None:
        self.scanner = OCRScanner(engine)

    def observe(self, screens: DSScreens, dex: RenegadeDex) -> PartyVisualState:
        lines = self.scanner.scan(screens.bottom)
        members: list[PartyMemberObservation] = []
        for index, box in enumerate(_PARTY_SLOTS):
            slot_lines = lines_in_box(lines, box)
            pokemon, confidence = _match_pokemon(dex, slot_lines)
            hp_current, hp_max = _fraction(slot_lines)
            members.append(
                PartyMemberObservation(
                    slot=index,
                    pokemon=pokemon,
                    confidence=confidence,
                    hp_current=hp_current,
                    hp_max=hp_max,
                    status=_status(slot_lines),
                    raw_text=raw_text(slot_lines),
                )
            )
        return PartyVisualState(tuple(members))
