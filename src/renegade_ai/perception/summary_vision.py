from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from renegade_ai.knowledge.dex import RenegadeDex, normalize_name
from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.perception.frame import DSScreens
from renegade_ai.perception.ocr import OCRScanner, RecognizedText, lines_in_box, raw_text


@dataclass(frozen=True, slots=True)
class SummaryStatsObservation:
    pokemon: PokemonData | None
    confidence: float
    level: int | None
    hp_current: int | None
    hp_max: int | None
    status: str | None
    ability: str | None
    item: str | None
    attack: int | None
    defense: int | None
    special_attack: int | None
    special_defense: int | None
    speed: int | None
    raw_text: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SummaryMovesObservation:
    pokemon: PokemonData | None
    confidence: float
    status: str | None
    moves: tuple[MoveData | None, ...]
    move_confidences: tuple[float, ...]
    pp_current: tuple[int | None, ...]
    pp_max: tuple[int | None, ...]
    raw_move_text: tuple[tuple[str, ...], ...]


_HEADER = (0.00, 0.00, 1.00, 0.18)
_LEVEL = (0.00, 0.14, 0.38, 0.32)
_HP = (0.61, 0.14, 1.00, 0.31)
_STATS = (0.62, 0.29, 1.00, 0.73)
_ABILITY = (0.00, 0.30, 0.62, 0.63)
_ITEM = (0.00, 0.62, 0.60, 0.79)
_SUMMARY_MOVE_SLOTS = (
    (0.00, 0.19, 0.50, 0.49),
    (0.50, 0.19, 1.00, 0.49),
    (0.00, 0.48, 0.50, 0.76),
    (0.50, 0.48, 1.00, 0.76),
)
_LEVEL_RE = re.compile(r"(?:NV|LV)[. :_-]*([0-9]{1,3})", re.IGNORECASE)
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


def _status(lines: list[RecognizedText]) -> str | None:
    joined = " ".join(line.text.upper() for line in lines)
    return next((status for status in _STATUS if status in joined), None)


def _level(lines: list[RecognizedText]) -> int | None:
    for line in lines:
        text = line.text.replace("I", "1").replace("l", "1")
        match = _LEVEL_RE.search(text)
        if match is not None:
            value = int(match.group(1))
            if 1 <= value <= 100:
                return value
    return None


def _fraction(lines: list[RecognizedText], *, maximum_limit: int = 999) -> tuple[int | None, int | None]:
    for line in lines:
        text = line.text.replace("O", "0").replace("o", "0")
        match = _FRACTION_RE.search(text)
        if match is None:
            continue
        current, maximum = int(match.group(1)), int(match.group(2))
        if 0 <= current <= maximum and 1 <= maximum <= maximum_limit:
            return current, maximum
    return None, None


def _ability(lines: list[RecognizedText], pokemon: PokemonData | None) -> str | None:
    if pokemon is None or not pokemon.abilities:
        return None
    best: str | None = None
    best_score = 0.0
    for ability in pokemon.abilities:
        target = normalize_name(ability)
        for line in lines:
            candidate = normalize_name(line.text)
            if not candidate:
                continue
            score = SequenceMatcher(None, candidate, target).ratio()
            if target in candidate or candidate in target:
                score = max(score, 0.92)
            if score > best_score:
                best, best_score = ability, score
    return best if best_score >= 0.58 else None


def _item(lines: list[RecognizedText]) -> str | None:
    values = [line.text.strip() for line in lines if line.text.strip()]
    joined = " ".join(values).lower()
    if any(marker in joined for marker in ("sem itens", "sem item", "no item", "none")):
        return None
    ignored = {"item", "itens", "held item"}
    candidates = [value for value in values if value.lower() not in ignored]
    return max(candidates, key=len) if candidates else None


def _five_stats(lines: list[RecognizedText]) -> tuple[int | None, int | None, int | None, int | None, int | None]:
    # The five right-column stat values are vertically ordered Attack, Defense,
    # Sp.Atk, Sp.Def, Speed. Sorting numeric OCR boxes by Y avoids depending on
    # Portuguese labels and also works if the user changes the language patch.
    candidates: list[tuple[float, int]] = []
    for line in lines:
        match = re.fullmatch(r"[^0-9]*([0-9]{1,3})[^0-9]*", line.text.strip())
        if match is None:
            continue
        value = int(match.group(1))
        if not 1 <= value <= 999:
            continue
        center = line.center
        y = 0.0 if center is None else center[1]
        candidates.append((y, value))
    candidates.sort(key=lambda item: item[0])
    values = [value for _, value in candidates[:5]]
    values.extend([None] * (5 - len(values)))
    return tuple(values[:5])  # type: ignore[return-value]


def _match_move(
    dex: RenegadeDex, lines: list[RecognizedText]
) -> tuple[MoveData | None, float]:
    best: MoveData | None = None
    best_score = 0.0
    for line in lines:
        if "PP" in line.text.upper() or _FRACTION_RE.search(line.text):
            continue
        record, fuzzy = dex.fuzzy_move(line.text)
        score = fuzzy * max(0.45, line.confidence)
        if record is not None and score > best_score:
            best, best_score = record, score
    return best, min(1.0, best_score)


class SummaryVision:
    def __init__(self, engine: Any | None = None) -> None:
        self.scanner = OCRScanner(engine)

    def observe_stats(self, screens: DSScreens, dex: RenegadeDex) -> SummaryStatsObservation:
        lines = self.scanner.scan(screens.bottom)
        header = lines_in_box(lines, _HEADER)
        pokemon, confidence = _match_pokemon(dex, header)
        hp_current, hp_max = _fraction(lines_in_box(lines, _HP))
        attack, defense, special_attack, special_defense, speed = _five_stats(
            lines_in_box(lines, _STATS)
        )
        return SummaryStatsObservation(
            pokemon=pokemon,
            confidence=confidence,
            level=_level(lines_in_box(lines, _LEVEL)),
            hp_current=hp_current,
            hp_max=hp_max,
            status=_status(header),
            ability=_ability(lines_in_box(lines, _ABILITY), pokemon),
            item=_item(lines_in_box(lines, _ITEM)),
            attack=attack,
            defense=defense,
            special_attack=special_attack,
            special_defense=special_defense,
            speed=speed,
            raw_text=raw_text(lines),
        )

    def observe_moves(self, screens: DSScreens, dex: RenegadeDex) -> SummaryMovesObservation:
        lines = self.scanner.scan(screens.bottom)
        header = lines_in_box(lines, _HEADER)
        pokemon, confidence = _match_pokemon(dex, header)
        moves: list[MoveData | None] = []
        move_confidences: list[float] = []
        pp_current: list[int | None] = []
        pp_max: list[int | None] = []
        raw_moves: list[tuple[str, ...]] = []
        for box in _SUMMARY_MOVE_SLOTS:
            slot_lines = lines_in_box(lines, box)
            move, move_confidence = _match_move(dex, slot_lines)
            current, maximum = _fraction(slot_lines, maximum_limit=99)
            moves.append(move)
            move_confidences.append(move_confidence)
            pp_current.append(current)
            pp_max.append(maximum)
            raw_moves.append(raw_text(slot_lines))
        return SummaryMovesObservation(
            pokemon=pokemon,
            confidence=confidence,
            status=_status(header),
            moves=tuple(moves),
            move_confidences=tuple(move_confidences),
            pp_current=tuple(pp_current),
            pp_max=tuple(pp_max),
            raw_move_text=tuple(raw_moves),
        )
