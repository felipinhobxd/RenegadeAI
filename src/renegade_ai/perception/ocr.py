from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RecognizedText:
    text: str
    confidence: float
    box: tuple[float, float, float, float] | None = None

    @property
    def center(self) -> tuple[float, float] | None:
        if self.box is None:
            return None
        x0, y0, x1, y1 = self.box
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


def crop_normalized(image: Any, box: tuple[float, float, float, float]) -> Any:
    import numpy as np

    rgb = np.asarray(image)[..., :3]
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = box
    left = max(0, min(width - 1, round(x0 * width)))
    top = max(0, min(height - 1, round(y0 * height)))
    right = max(left + 1, min(width, round(x1 * width)))
    bottom = max(top + 1, min(height, round(y1 * height)))
    return rgb[top:bottom, left:right]


def upscale_for_ocr(image: Any, scale: int = 4) -> Any:
    import numpy as np
    from PIL import Image, ImageEnhance, ImageFilter

    rgb = np.asarray(image)[..., :3].astype("uint8")
    pil = Image.fromarray(rgb)
    scale = max(1, int(scale))
    pil = pil.resize((pil.width * scale, pil.height * scale), Image.Resampling.NEAREST)
    pil = ImageEnhance.Contrast(pil).enhance(1.30)
    pil = pil.filter(ImageFilter.SHARPEN)
    return np.asarray(pil)


def load_ocr_engine() -> Any:
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            'Battle OCR is not installed. Run: python -m pip install -e ".[dev,vision]"'
        ) from exc
    return RapidOCR()


def _normalized_box(raw_box: Any, width: int, height: int) -> tuple[float, float, float, float] | None:
    if raw_box is None:
        return None
    try:
        xs = [float(point[0]) for point in raw_box]
        ys = [float(point[1]) for point in raw_box]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or not ys:
        return None
    width = max(1, width)
    height = max(1, height)
    return (
        max(0.0, min(1.0, min(xs) / width)),
        max(0.0, min(1.0, min(ys) / height)),
        max(0.0, min(1.0, max(xs) / width)),
        max(0.0, min(1.0, max(ys) / height)),
    )


def parse_ocr_result(payload: Any, *, width: int = 1, height: int = 1) -> list[RecognizedText]:
    """Normalize RapidOCR 3.x and legacy result shapes.

    RapidOCR 3.x returns a RapidOCROutput object with ``txts``, ``scores`` and
    ``boxes`` attributes. Older rapidocr-onnxruntime versions returned a tuple
    whose first item was a list of ``[box, text, confidence]`` rows. Supporting
    both makes upgrades safe and keeps tests independent of the OCR package.
    """
    if payload is None:
        return []

    txts = getattr(payload, "txts", None)
    scores = getattr(payload, "scores", None)
    boxes = getattr(payload, "boxes", None)
    if txts is not None and scores is not None:
        box_values = list(boxes) if boxes is not None else [None] * len(txts)
        recognized: list[RecognizedText] = []
        for index, raw_text in enumerate(txts):
            text = str(raw_text).strip()
            if not text:
                continue
            try:
                confidence = float(scores[index])
            except (TypeError, ValueError, IndexError):
                confidence = 0.0
            raw_box = box_values[index] if index < len(box_values) else None
            recognized.append(
                RecognizedText(
                    text=text,
                    confidence=confidence,
                    box=_normalized_box(raw_box, width, height),
                )
            )
        return recognized

    # Legacy rapidocr-onnxruntime shape: (rows, elapsed)
    if isinstance(payload, tuple) and payload:
        payload = payload[0]
    if payload is None or not isinstance(payload, (list, tuple)):
        return []

    recognized = []
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
        recognized.append(
            RecognizedText(
                text=text,
                confidence=confidence,
                box=_normalized_box(item[0], width, height),
            )
        )
    return recognized


class OCRScanner:
    """One-pass OCR scanner for a DS screen.

    Running OCR once per screen is substantially faster than running a detector
    independently for every Pokemon name, HP area and move slot.
    """

    def __init__(self, engine: Any | None = None, *, scale: int = 4) -> None:
        self.engine = engine if engine is not None else load_ocr_engine()
        self.scale = max(1, int(scale))

    def scan(self, image: Any) -> list[RecognizedText]:
        prepared = upscale_for_ocr(image, self.scale)
        height, width = prepared.shape[:2]
        payload = self.engine(prepared)
        return parse_ocr_result(payload, width=width, height=height)


def lines_in_box(
    lines: list[RecognizedText] | tuple[RecognizedText, ...],
    box: tuple[float, float, float, float],
) -> list[RecognizedText]:
    x0, y0, x1, y1 = box
    selected: list[RecognizedText] = []
    for line in lines:
        center = line.center
        if center is None:
            # A legacy OCR result without coordinates cannot be spatially
            # filtered, so keep it rather than silently throwing text away.
            selected.append(line)
            continue
        x, y = center
        if x0 <= x <= x1 and y0 <= y <= y1:
            selected.append(line)
    return selected


def raw_text(lines: list[RecognizedText] | tuple[RecognizedText, ...]) -> tuple[str, ...]:
    return tuple(line.text for line in lines)
