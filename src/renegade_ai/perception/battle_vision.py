from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from renegade_ai.knowledge.dex import RenegadeDex
from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.perception.frame import DSScreens
from renegade_ai.perception.ocr import OCRScanner, RecognizedText, lines_in_box, raw_text


@dataclass(frozen=True, slots=True)
class BattleVisualState:
    own: PokemonData | None
    opponent: PokemonData | None
    own_match_confidence: float
    opponent_match_confidence: float
    own_level: int | None
    opponent_level: int | None
    own_hp_fraction: float | None
    opponent_hp_fraction: float | None
    own_hp_current: int | None
    own_hp_max: int | None
    own_status: str | None
    opponent_status: str | None
    moves: tuple[MoveData | None, ...]
    move_confidences: tuple[float, ...]
    pp_current: tuple[int | None, ...]
    pp_max: tuple[int | None, ...]
    raw_own_text: tuple[str, ...]
    raw_opponent_text: tuple[str, ...]
    raw_move_text: tuple[tuple[str, ...], ...]


# Normalized regions calibrated from the 820x492/493 split captures.
_TOP_OPPONENT = (0.00, 0.08, 0.47, 0.30)
_TOP_OWN = (0.50, 0.47, 1.00, 0.72)
_TOP_OPPONENT_HP = (0.13, 0.19, 0.42, 0.27)
_TOP_OWN_HP = (0.70, 0.57, 1.00, 0.67)
_MOVE_SLOTS = (
    (0.01, 0.10, 0.49, 0.42),
    (0.51, 0.10, 0.99, 0.42),
    (0.01, 0.44, 0.49, 0.75),
    (0.51, 0.44, 0.99, 0.75),
)
_LEVEL_RE = re.compile(r"(?:LV|L[VW]?)[. :_-]*([0-9]{1,3})", re.IGNORECASE)
_FRACTION_RE = re.compile(r"([0-9]{1,3})\s*/\s*([0-9]{1,3})")
_PP_RE = re.compile(r"PP[^0-9]*([0-9]{1,3})\s*/\s*([0-9]{1,3})", re.IGNORECASE)
_STATUS_ALIASES = {
    "PSN": "PSN",
    "POISON": "PSN",
    "TOX": "PSN",
    "BRN": "BRN",
    "BURN": "BRN",
    "PAR": "PAR",
    "SLP": "SLP",
    "SLEEP": "SLP",
    "FRZ": "FRZ",
    "FREEZE": "FRZ",
    "FNT": "FNT",
}


def _best_pokemon_match(
    dex: RenegadeDex, lines: list[RecognizedText]
) -> tuple[PokemonData | None, float]:
    best: PokemonData | None = None
    best_score = 0.0
    for line in lines:
        without_level = _LEVEL_RE.sub("", line.text)
        candidates = [line.text, without_level]
        for candidate in candidates:
            record, fuzzy = dex.fuzzy_pokemon(candidate)
            score = fuzzy * max(0.45, line.confidence)
            if record is not None and score > best_score:
                best = record
                best_score = score
    return best, min(1.0, best_score)


def _best_move_match(
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
            best = record
            best_score = score
    return best, min(1.0, best_score)


def _extract_level(lines: list[RecognizedText]) -> int | None:
    for line in lines:
        normalized = line.text.replace("I", "1").replace("l", "1")
        match = _LEVEL_RE.search(normalized)
        if match is not None:
            level = int(match.group(1))
            if 1 <= level <= 100:
                return level
    return None


def _extract_fraction(lines: list[RecognizedText]) -> tuple[int | None, int | None]:
    for line in lines:
        normalized = line.text.replace("O", "0").replace("o", "0")
        match = _FRACTION_RE.search(normalized)
        if match is None:
            continue
        current, maximum = int(match.group(1)), int(match.group(2))
        if 0 <= current <= maximum and 1 <= maximum <= 999:
            return current, maximum
    return None, None


def _extract_pp(lines: list[RecognizedText]) -> tuple[int | None, int | None]:
    for line in lines:
        normalized = line.text.replace("O", "0").replace("o", "0")
        match = _PP_RE.search(normalized)
        if match is None:
            # Some OCR runs split the letters PP away from the fraction.
            fraction = _FRACTION_RE.search(normalized)
            if fraction is None:
                continue
            current, maximum = int(fraction.group(1)), int(fraction.group(2))
        else:
            current, maximum = int(match.group(1)), int(match.group(2))
        if 0 <= current <= maximum and 1 <= maximum <= 99:
            return current, maximum
    return None, None


def _extract_status(lines: list[RecognizedText]) -> str | None:
    joined = " ".join(line.text.upper() for line in lines)
    for raw, normalized in _STATUS_ALIASES.items():
        if raw in joined:
            return normalized
    return None


def _longest_true_run(row: Any) -> int:
    import numpy as np

    values = np.asarray(row, dtype=bool)
    changes = np.diff(np.r_[False, values, False].astype("int8"))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return 0 if starts.size == 0 else int((ends - starts).max())


def _crop_normalized(image: Any, box: tuple[float, float, float, float]) -> Any:
    import numpy as np

    rgb = np.asarray(image)[..., :3]
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = box
    return rgb[
        max(0, round(y0 * height)) : min(height, round(y1 * height)),
        max(0, round(x0 * width)) : min(width, round(x1 * width)),
    ]


def _measure_hp(image: Any, box: tuple[float, float, float, float]) -> float | None:
    """Estimate the visible HP-bar fill from green/yellow/red pixels.

    The new 14/20 capture provides a real calibration point: a 70% Chimchar HP
    bar spans about 105 pixels on an 820px screen, so a full bar is ~150px
    (18.3% of screen width). Numeric own HP, when OCR can read it, overrides
    this estimate exactly.
    """
    import numpy as np

    full = np.asarray(image)[..., :3].astype("int16")
    crop = _crop_normalized(full, box)
    if crop.size == 0:
        return None
    r = crop[:, :, 0]
    g = crop[:, :, 1]
    b = crop[:, :, 2]
    green = (g > 105) & (g > r * 1.14) & (g > b * 1.10)
    yellow = (r > 155) & (g > 120) & (b < 125) & (abs(r - g) < 110)
    red = (r > 155) & (g < 130) & (b < 125)
    colored = green | yellow | red
    longest = max((_longest_true_run(row) for row in colored), default=0)
    if longest < max(3, round(full.shape[1] * 0.015)):
        return None
    expected_full = max(1, round(full.shape[1] * 0.183))
    return max(0.0, min(1.0, longest / expected_full))


class BattleVision:
    def __init__(self, engine: Any | None = None) -> None:
        self.scanner = OCRScanner(engine)

    def observe(self, screens: DSScreens, dex: RenegadeDex) -> BattleVisualState:
        # One OCR inference per DS screen instead of one inference per crop.
        top_lines = self.scanner.scan(screens.top)
        bottom_lines = self.scanner.scan(screens.bottom)
        opponent_lines = lines_in_box(top_lines, _TOP_OPPONENT)
        own_lines = lines_in_box(top_lines, _TOP_OWN)

        own, own_confidence = _best_pokemon_match(dex, own_lines)
        opponent, opponent_confidence = _best_pokemon_match(dex, opponent_lines)
        own_current, own_max = _extract_fraction(own_lines)

        own_hp = _measure_hp(screens.top, _TOP_OWN_HP)
        if own_current is not None and own_max:
            own_hp = own_current / own_max

        move_records: list[MoveData | None] = []
        move_confidences: list[float] = []
        pp_current: list[int | None] = []
        pp_max: list[int | None] = []
        raw_moves: list[tuple[str, ...]] = []
        for slot in _MOVE_SLOTS:
            lines = lines_in_box(bottom_lines, slot)
            move, confidence = _best_move_match(dex, lines)
            current_pp, maximum_pp = _extract_pp(lines)
            move_records.append(move)
            move_confidences.append(confidence)
            pp_current.append(current_pp)
            pp_max.append(maximum_pp)
            raw_moves.append(raw_text(lines))

        return BattleVisualState(
            own=own,
            opponent=opponent,
            own_match_confidence=own_confidence,
            opponent_match_confidence=opponent_confidence,
            own_level=_extract_level(own_lines),
            opponent_level=_extract_level(opponent_lines),
            own_hp_fraction=own_hp,
            opponent_hp_fraction=_measure_hp(screens.top, _TOP_OPPONENT_HP),
            own_hp_current=own_current,
            own_hp_max=own_max,
            own_status=_extract_status(own_lines),
            opponent_status=_extract_status(opponent_lines),
            moves=tuple(move_records),
            move_confidences=tuple(move_confidences),
            pp_current=tuple(pp_current),
            pp_max=tuple(pp_max),
            raw_own_text=raw_text(own_lines),
            raw_opponent_text=raw_text(opponent_lines),
            raw_move_text=tuple(raw_moves),
        )
