from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from renegade_ai.knowledge.dex import RenegadeDex
from renegade_ai.knowledge.models import MoveData, PokemonData
from renegade_ai.perception.frame import DSScreens


@dataclass(frozen=True, slots=True)
class RecognizedText:
    text: str
    confidence: float


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
    moves: tuple[MoveData | None, ...]
    move_confidences: tuple[float, ...]
    raw_own_text: tuple[str, ...]
    raw_opponent_text: tuple[str, ...]
    raw_move_text: tuple[tuple[str, ...], ...]


_TOP_OPPONENT = (0.00, 0.08, 0.46, 0.23)
_TOP_OWN = (0.54, 0.48, 1.00, 0.64)
_TOP_OPPONENT_HP = (0.13, 0.19, 0.42, 0.27)
_TOP_OWN_HP = (0.70, 0.59, 1.00, 0.68)
_MOVE_SLOTS = (
    (0.03, 0.12, 0.48, 0.40),
    (0.52, 0.12, 0.98, 0.40),
    (0.03, 0.46, 0.48, 0.73),
    (0.52, 0.46, 0.98, 0.73),
)
_LEVEL_RE = re.compile(r"(?:LV|L)[^0-9]*(\d{1,3})", re.IGNORECASE)


def _crop_normalized(image: Any, box: tuple[float, float, float, float]) -> Any:
    import numpy as np

    rgb = np.asarray(image)[..., :3]
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = box
    left = max(0, min(width - 1, round(x0 * width)))
    top = max(0, min(height - 1, round(y0 * height)))
    right = max(left + 1, min(width, round(x1 * width)))
    bottom = max(top + 1, min(height, round(y1 * height)))
    return rgb[top:bottom, left:right]


def _upscale_for_ocr(image: Any) -> Any:
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter

    rgb = np.asarray(image)[..., :3].astype("uint8")
    pil = Image.fromarray(rgb)
    # Pixel-art text benefits from a crisp integer upscale before OCR.
    pil = pil.resize((pil.width * 4, pil.height * 4), Image.Resampling.NEAREST)
    pil = ImageEnhance.Contrast(pil).enhance(1.35)
    pil = pil.filter(ImageFilter.SHARPEN)
    return np.asarray(pil)


def _load_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            'Battle OCR is not installed. Run: python -m pip install -e ".[dev,vision]"'
        ) from exc
    return RapidOCR()


def _parse_ocr_result(payload: Any) -> list[RecognizedText]:
    if payload is None:
        return []
    # RapidOCR commonly returns (results, elapsed), while some versions expose
    # the result list directly. Support both shapes without pinning internals.
    if isinstance(payload, tuple) and len(payload) >= 1:
        payload = payload[0]
    if payload is None or not isinstance(payload, (list, tuple)):
        return []

    recognized: list[RecognizedText] = []
    for item in payload:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        text = str(item[1]).strip()
        if not text:
            continue
        try:
            confidence = float(item[2])
        except (TypeError, ValueError):
            confidence = 0.0
        recognized.append(RecognizedText(text=text, confidence=confidence))
    return recognized


def _ocr(engine: Any, image: Any) -> list[RecognizedText]:
    return _parse_ocr_result(engine(_upscale_for_ocr(image)))


def _best_pokemon_match(
    dex: RenegadeDex, lines: list[RecognizedText]
) -> tuple[PokemonData | None, float]:
    best: PokemonData | None = None
    best_score = 0.0
    for line in lines:
        candidates = [line.text, _LEVEL_RE.sub("", line.text)]
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
        # PP/type text often shares the same crop. Matching each OCR line avoids
        # polluting the move name with strings such as "PP 35/35".
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


def _longest_true_run(row: Any) -> int:
    import numpy as np

    values = np.asarray(row, dtype=bool)
    changes = np.diff(np.r_[False, values, False].astype("int8"))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return 0 if starts.size == 0 else int((ends - starts).max())


def _measure_hp(image: Any, box: tuple[float, float, float, float]) -> float | None:
    """Estimate the visible Gen-IV HP bar fill from its colored segment.

    The full bar in the calibrated Renegade Platinum HUD is about 18.8% of the
    upper-screen width. A later partial-HP screenshot can refine this constant,
    but this already gives a useful normalized signal for the decision engine.
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
    expected_full = max(1, round(full.shape[1] * 0.188))
    return max(0.0, min(1.0, longest / expected_full))


class BattleVision:
    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine if engine is not None else _load_ocr_engine()

    def observe(self, screens: DSScreens, dex: RenegadeDex) -> BattleVisualState:
        opponent_lines = _ocr(self.engine, _crop_normalized(screens.top, _TOP_OPPONENT))
        own_lines = _ocr(self.engine, _crop_normalized(screens.top, _TOP_OWN))

        own, own_confidence = _best_pokemon_match(dex, own_lines)
        opponent, opponent_confidence = _best_pokemon_match(dex, opponent_lines)

        move_records: list[MoveData | None] = []
        move_confidences: list[float] = []
        raw_moves: list[tuple[str, ...]] = []
        for slot in _MOVE_SLOTS:
            lines = _ocr(self.engine, _crop_normalized(screens.bottom, slot))
            move, confidence = _best_move_match(dex, lines)
            move_records.append(move)
            move_confidences.append(confidence)
            raw_moves.append(tuple(line.text for line in lines))

        return BattleVisualState(
            own=own,
            opponent=opponent,
            own_match_confidence=own_confidence,
            opponent_match_confidence=opponent_confidence,
            own_level=_extract_level(own_lines),
            opponent_level=_extract_level(opponent_lines),
            own_hp_fraction=_measure_hp(screens.top, _TOP_OWN_HP),
            opponent_hp_fraction=_measure_hp(screens.top, _TOP_OPPONENT_HP),
            moves=tuple(move_records),
            move_confidences=tuple(move_confidences),
            raw_own_text=tuple(line.text for line in own_lines),
            raw_opponent_text=tuple(line.text for line in opponent_lines),
            raw_move_text=tuple(raw_moves),
        )
