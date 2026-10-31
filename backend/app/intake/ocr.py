"""Local OCR (FR-5). No image ever leaves the machine.

Engines, tried in order:
  1. RapidOCR: the PaddleOCR PP-OCR models run through onnxruntime (see docs/IMPLEMENTATION_PLAN.md
     Stage 2 notes: the paddlepaddle wheels pin PyYAML and OpenCV versions that clash with LiteLLM).
  2. PaddleOCR, when it is installed in the environment.
  3. Tesseract, when the binary and pytesseract are present.
Output is a list of text cells in reading order, each with a confidence.
"""

import logging
import shutil
import statistics
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import numpy as np

from app.intake.quality import Image, deskew

log = logging.getLogger(__name__)


class OcrUnavailableError(RuntimeError):
    """No OCR engine could be loaded."""


@dataclass(frozen=True)
class Cell:
    text: str
    confidence: float
    x: float
    y: float
    h: float


@dataclass(frozen=True)
class OcrResult:
    cells: list[Cell]
    engine: str

    @property
    def lines(self) -> list[str]:
        return [c.text for c in self.cells]

    @property
    def mean_confidence(self) -> float:
        return statistics.fmean(c.confidence for c in self.cells) if self.cells else 0.0


class _Engine(Protocol):
    name: str

    def read(self, img: Image) -> list[Cell]: ...


class _RapidOcr:
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr import RapidOCR

        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        # a larger detection side recovers small text on degraded photos (calibrated on the dev set)
        self._ocr = RapidOCR(
            params={
                "Global.log_level": "error",
                "Det.limit_side_len": 1500,
                "Det.limit_type": "max",
            }
        )

    def read(self, img: Image) -> list[Cell]:
        res: Any = self._ocr(img)
        if res.boxes is None or res.txts is None or res.scores is None:
            return []
        cells = []
        for box, txt, score in zip(res.boxes, res.txts, res.scores, strict=True):
            xs, ys = box[:, 0], box[:, 1]
            cells.append(Cell(str(txt), float(score), float(xs.min()), float((ys.min() + ys.max()) / 2),
                              float(ys.max() - ys.min())))  # fmt: skip
        return cells


class _PaddleOcr:
    name = "paddleocr"

    def __init__(self) -> None:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found,unused-ignore]

        self._ocr = PaddleOCR(lang="en", use_doc_orientation_classify=False,
                              use_doc_unwarping=False, use_textline_orientation=False)  # fmt: skip

    def read(self, img: Image) -> list[Cell]:
        out = self._ocr.predict(img)[0]
        cells = []
        for box, txt, score in zip(
            out["rec_polys"], out["rec_texts"], out["rec_scores"], strict=True
        ):
            box = np.asarray(box)
            xs, ys = box[:, 0], box[:, 1]
            cells.append(Cell(str(txt), float(score), float(xs.min()), float((ys.min() + ys.max()) / 2),
                              float(ys.max() - ys.min())))  # fmt: skip
        return cells


class _Tesseract:
    name = "tesseract"

    def __init__(self) -> None:
        import pytesseract  # type: ignore[import-not-found,unused-ignore]

        if shutil.which("tesseract") is None:
            raise OcrUnavailableError("tesseract binary not found")
        self._t = pytesseract

    def read(self, img: Image) -> list[Cell]:
        data = self._t.image_to_data(img, output_type=self._t.Output.DICT)
        cells = []
        for txt, conf, x, y, h in zip(data["text"], data["conf"], data["left"], data["top"],
                                      data["height"], strict=True):  # fmt: skip
            if txt.strip() and float(conf) >= 0:
                cells.append(
                    Cell(txt.strip(), float(conf) / 100, float(x), float(y + h / 2), float(h))
                )
        return cells


@lru_cache(maxsize=1)
def get_engine() -> _Engine:
    errors = []
    for factory in (_RapidOcr, _PaddleOcr, _Tesseract):
        try:
            return factory()
        except (ImportError, OcrUnavailableError, RuntimeError) as exc:
            errors.append(f"{factory.__name__}: {type(exc).__name__}")
    raise OcrUnavailableError("no OCR engine available: " + "; ".join(errors))


def reading_order(cells: list[Cell]) -> list[Cell]:
    """Top-to-bottom rows, left-to-right inside a row, so a label comes before its value."""
    if not cells:
        return []
    row_h = statistics.median(c.h for c in cells) or 10.0
    rows: list[list[Cell]] = []
    for c in sorted(cells, key=lambda c: c.y):
        if rows and abs(c.y - statistics.fmean(r.y for r in rows[-1])) < 0.6 * row_h:
            rows[-1].append(c)
        else:
            rows.append([c])
    return [c for row in rows for c in sorted(row, key=lambda c: c.x)]


def read_image(img: Image, *, straighten: bool = True) -> OcrResult:
    """OCR one image (BGR or gray). Deskews first by default."""
    engine = get_engine()
    if straighten:
        img = deskew(img)
    return OcrResult(reading_order(engine.read(img)), engine.name)
