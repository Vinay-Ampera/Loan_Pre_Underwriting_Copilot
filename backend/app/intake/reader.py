"""Turn an accepted upload into text cells: PyMuPDF + pdfplumber for digital PDFs (FR-4),
OpenCV + local OCR for photos and scanned pages (FR-5). Everything here is local.
"""

import io
import logging
from dataclasses import dataclass, field

import pdfplumber
import pymupdf

from app.intake import ocr, quality
from app.intake.models import PageKind, UploadCheck

log = logging.getLogger(__name__)

DIGITAL_CONFIDENCE = 0.99  # exact text from the PDF text layer
SCAN_DPI = 200


@dataclass
class PageText:
    index: int
    kind: PageKind
    cells: list[ocr.Cell]  # reading order; digital text gets x/y from the layout too

    @property
    def lines(self) -> list[str]:
        return [c.text for c in self.cells]


@dataclass
class ReadDocument:
    pages: list[PageText]
    tables: list[list[list[str]]] = field(
        default_factory=list
    )  # pdfplumber tables, digital PDFs only
    pdf_meta: dict[str, str] = field(default_factory=dict)
    ocr_engine: str | None = None

    @property
    def cells(self) -> list[ocr.Cell]:
        return [c for p in self.pages for c in p.cells]

    @property
    def lines(self) -> list[str]:
        return [c.text for c in self.cells]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def is_ocr(self) -> bool:
        return self.ocr_engine is not None

    @property
    def ocr_confidence(self) -> float | None:
        cells = [c for p in self.pages if p.kind is not PageKind.DIGITAL for c in p.cells]
        return sum(c.confidence for c in cells) / len(cells) if cells else None


def _digital_cells(page: pymupdf.Page) -> list[ocr.Cell]:
    cells = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                x0, y0, _, y1 = line["bbox"]
                cells.append(ocr.Cell(text, DIGITAL_CONFIDENCE, x0, (y0 + y1) / 2, y1 - y0))
    return ocr.reading_order(cells)


def _clean_table(raw: list[list[str | None]]) -> list[list[str]]:
    return [[(c or "").replace("\n", " ").strip() for c in row] for row in raw]


def _read_pdf(data: bytes, check: UploadCheck) -> ReadDocument:
    pages: list[PageText] = []
    tables: list[list[list[str]]] = []
    engine: str | None = None
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        meta = {k: str(v) for k, v in (doc.metadata or {}).items() if v}
        plumber = pdfplumber.open(io.BytesIO(data))
        try:
            for info in check.pages:
                page = doc[info.index]
                if info.kind is PageKind.DIGITAL:
                    pages.append(PageText(info.index, info.kind, _digital_cells(page)))
                    tables += [_clean_table(t) for t in plumber.pages[info.index].extract_tables()]
                else:
                    pix = page.get_pixmap(dpi=SCAN_DPI, alpha=False)
                    img = quality.decode(pix.tobytes("png"))
                    result = ocr.read_image(img) if img is not None else ocr.OcrResult([], "none")
                    engine = result.engine
                    pages.append(PageText(info.index, info.kind, result.cells))
        finally:
            plumber.close()
    return ReadDocument(pages, tables, meta, engine)


def _read_image(data: bytes) -> ReadDocument:
    img = quality.decode(data)
    result = ocr.read_image(img) if img is not None else ocr.OcrResult([], "none")
    return ReadDocument([PageText(0, PageKind.PHOTO, result.cells)], [], {}, result.engine)


def read_document(data: bytes, check: UploadCheck) -> ReadDocument:
    """`check` must be an accepted UploadCheck for the same bytes."""
    if not check.accepted:
        raise ValueError("cannot read a rejected upload")
    return _read_pdf(data, check) if check.mime == "application/pdf" else _read_image(data)
