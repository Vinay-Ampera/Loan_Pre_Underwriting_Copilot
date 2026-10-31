"""Intake pipeline: upload bytes -> checked, read, classified, extracted, validated document.

Order (AGENTS.md section 2): upload checks -> per-page type -> text layer or OCR -> classify ->
local field extraction -> code validators -> tamper hints. The LLM pass (`enrich`) runs after,
on masked text, for the fields this local pass could not fill. Raw text never leaves `IntakeResult`
and is never logged.
"""

import math
import statistics
from dataclasses import dataclass, field
from datetime import date

from litellm.router import Router

from app.core.config import get_settings
from app.intake import (
    checks,
    classifier,
    duplicates,
    fields,
    injection,
    llm_extract,
    statement,
    tamper,
    upload,
)
from app.intake.fields import parse_money
from app.intake.masker import Masker
from app.intake.models import DocType, ExtractedDocument, ExtractedField, PageKind, UploadCheck
from app.intake.reader import ReadDocument, read_document
from app.services.llm import LLMResult

DIGITAL_QUALITY = 95.0  # design value for a clean text-layer PDF (docs/TESTING.md)
ID_PHOTO_QUALITY = (
    94.0  # an accepted passport-style photograph: no text to measure, so the "good photo" value
)
PHOTO_MAX_CELLS = 3  # an image with this little text and no title is a photograph


@dataclass
class IntakeResult:
    upload: UploadCheck
    document: ExtractedDocument | None = None  # None when the upload was rejected
    raw_text: str = field(default="", repr=False)  # local only: never log, never serialise
    missing: list[str] = field(default_factory=list)
    sha256: str = ""

    @property
    def accepted(self) -> bool:
        return self.upload.accepted


def measure_quality(
    check: UploadCheck, read: ReadDocument, issues: int, low_conf: int, total: int
) -> float:
    """0-100. Text-layer PDFs score the design value; photos and scans are scored from the measured
    blur and OCR confidence. Each validator issue and each low-confidence field costs points."""
    ocr_conf = read.ocr_confidence
    if ocr_conf is None:
        base = DIGITAL_QUALITY
    else:
        blur = check.blur_score or 0.0
        blur_part = min(1.0, max(0.0, math.log10(max(blur, 1.0) / 10) / math.log10(15)))
        conf_part = min(1.0, max(0.0, (ocr_conf - 0.85) / 0.14))
        base = 40 + 55 * (0.4 * blur_part + 0.6 * conf_part)
    penalty = min(20.0, 5.0 * issues) + (10.0 * low_conf / total if total else 0.0)
    return round(max(0.0, base - penalty), 1)


def _gst_months(read: ReadDocument) -> list[float]:
    sales = []
    for table in read.tables:
        for row in table:
            if len(row) >= 2 and row[0][:3].isalpha() and row[0][-4:].isdigit():
                v = parse_money(row[1])
                if v is not None:
                    sales.append(v)
    return sales


def process_file(data: bytes, filename: str, *, as_of: date | None = None,
                 max_bytes: int | None = None) -> IntakeResult:  # fmt: skip
    """All local stages. Never raises on a bad upload; a rejection is a result."""
    as_of = as_of or date.today()
    limit = max_bytes if max_bytes is not None else get_settings().max_upload_mb * 1024 * 1024
    check = upload.check_upload(data, filename, limit)
    if not check.accepted:
        return IntakeResult(upload=check, sha256=duplicates.sha256_hex(data))

    read = read_document(data, check)
    cells = read.cells
    photo_like = check.pages[0].kind is PageKind.PHOTO and len(cells) <= PHOTO_MAX_CELLS
    doc_type, cls_conf = classifier.classify(read.lines, has_photo_only=photo_like)

    flds: list[ExtractedField] = fields.extract_fields(doc_type, cells)
    issues = []
    earnings: dict[str, float] = {}
    deductions: dict[str, float] = {}
    txns = []
    style = None
    if doc_type is DocType.PAYSLIP:
        earnings, deductions = fields.payslip_components(cells)
    if doc_type is DocType.BANK_STATEMENT:
        parsed = statement.parse_statement(read)
        flds, txns, style = parsed.fields, parsed.transactions, parsed.style
        issues += checks.check_balances(txns, parsed.opening_balance)

    issues += checks.check_ids(doc_type, flds)
    issues += checks.check_dates(flds, as_of)
    issues += checks.check_totals(doc_type, flds, earnings, deductions,
                                  _gst_months(read) if doc_type is DocType.GST_RETURNS else None)  # fmt: skip
    flds = checks.apply_confidence_rules(flds, issues)

    flags: list[str] = list(check.warnings)
    if read.is_ocr:
        flags.append("read_by_ocr")
    if doc_type is DocType.UNKNOWN:
        flags.append("unrecognised_document")
    required = fields.REQUIRED.get(doc_type, frozenset())
    if required - {f.name for f in flds}:
        flags.append("missing_required_fields")
    if injection.scan(read.text):
        flags.append("possible_prompt_injection")
    units = len(_gst_months(read)) if doc_type is DocType.GST_RETURNS else None
    low = [f.name for f in flds if f.low_confidence]
    if low:
        flags.append("low_confidence_fields")
    hints = tamper.document_hints(doc_type, read.pdf_meta, flds, earnings, deductions)

    found = {f.name for f in flds}
    missing = sorted(required - found)
    avg = (
        statistics.fmean(f.confidence for f in flds if f.name in required)
        if required & found
        else None
    )
    doc = ExtractedDocument(
        doc_type=doc_type, fields=flds, quality_flags=flags, tamper_hints=hints, issues=issues,
        transactions=txns, statement_style=style,
        quality_score=ID_PHOTO_QUALITY
        if doc_type is DocType.PHOTO
        else measure_quality(check, read, len(issues), len(low), len(flds)),
        avg_confidence=None if avg is None else round(avg, 3), upload=check,
        meta={"classifier_confidence": cls_conf, "pages": len(read.pages), "ocr_engine": read.ocr_engine,
              "ocr_confidence": None if read.ocr_confidence is None else round(read.ocr_confidence, 3),
              "missing_fields": missing, "units": units},
    )  # fmt: skip
    return IntakeResult(
        upload=check,
        document=doc,
        raw_text=read.text,
        missing=missing,
        sha256=duplicates.sha256_hex(data),
    )


def register_known(masker: Masker, doc: ExtractedDocument) -> None:
    """Teach the masker the names and addresses found locally, so they are tokenised wherever
    they appear in this or any later document of the case."""
    for f in doc.fields:
        if isinstance(f.value, str):
            if f.name in fields.NAME_FIELDS:
                masker.add_known("NAME", f.value)
            elif f.name in fields.ADDRESS_FIELDS:
                masker.add_known("ADDR", f.value)


async def enrich(result: IntakeResult, router: Router, masker: Masker,
                 calls: "list[LLMResult[llm_extract.LLMFields]] | None" = None) -> IntakeResult:  # fmt: skip
    """LLM pass on masked text for missing fields (or all generic fields of an unknown document).
    Local values always win: the model only fills gaps."""
    doc = result.document
    if doc is None:
        return result
    have = {f.name for f in doc.fields}
    wanted = (
        llm_extract.wanted_fields(doc.doc_type, have)
        if (result.missing or doc.doc_type is DocType.UNKNOWN)
        else []
    )
    if doc.doc_type is not DocType.UNKNOWN:
        wanted = [w for w in wanted if w in result.missing]
    if not wanted:
        return result
    register_known(masker, doc)
    extra = await llm_extract.llm_extract(
        router, doc.doc_type, result.raw_text, masker, wanted, calls
    )
    merged = checks.apply_confidence_rules(
        [*doc.fields, *extra], checks.check_ids(doc.doc_type, [*doc.fields, *extra])
    )
    doc.fields = merged
    still = sorted(fields.REQUIRED.get(doc.doc_type, frozenset()) - {f.name for f in merged})
    doc.meta["missing_fields"] = still
    if extra:
        doc.quality_flags.append("llm_filled_fields")
    return IntakeResult(
        upload=result.upload,
        document=doc,
        raw_text=result.raw_text,
        missing=still,
        sha256=result.sha256,
    )
