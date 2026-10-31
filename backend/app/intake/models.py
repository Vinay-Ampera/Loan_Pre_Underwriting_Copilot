"""Pydantic shapes shared by the intake stages. No logic here."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DocType(StrEnum):
    PAN_CARD = "pan_card"
    AADHAAR = "aadhaar"
    PHOTO = "photo"
    PAYSLIP = "payslip"
    FORM16 = "form16"
    ITR = "itr"
    BANK_STATEMENT = "bank_statement"
    PNL_BALANCE_SHEET = "pnl_balance_sheet"
    GST_REGISTRATION = "gst_registration"
    GST_RETURNS = "gst_returns"
    UDYAM_CERTIFICATE = "udyam_certificate"
    BUSINESS_PROOF = "business_proof"
    SALE_AGREEMENT = "sale_agreement"
    TITLE_DEED = "title_deed"
    ENCUMBRANCE_CERTIFICATE = "encumbrance_certificate"
    APPROVED_PLAN = "approved_plan"
    ADMISSION_LETTER = "admission_letter"
    FEE_STRUCTURE = "fee_structure"
    MARKSHEET = "marksheet"
    DEALER_INVOICE = "dealer_invoice"
    DRIVING_LICENCE = "driving_licence"
    RC_BOOK = "rc_book"
    INSURANCE = "insurance"
    UNKNOWN = "unknown"


class PageKind(StrEnum):
    DIGITAL = "digital"  # has a usable text layer
    SCANNED = "scanned"  # image-only page inside a PDF
    PHOTO = "photo"  # a JPG or PNG upload


class PageInfo(BaseModel):
    index: int
    kind: PageKind
    chars: int = 0  # text-layer characters (0 for image pages)


class UploadCheck(BaseModel):
    """Outcome of the upload-time checks. `accepted=False` means: ask for a re-upload."""

    accepted: bool
    mime: str | None = None
    size_bytes: int = 0
    pages: list[PageInfo] = Field(default_factory=list)
    blur_score: float | None = None  # variance of the Laplacian at a fixed width; lower = blurrier
    page_aspect: float | None = None  # long/short side of the document found in a photo
    reject_code: str | None = None
    message: str = ""
    warnings: list[str] = Field(default_factory=list)


class ExtractedField(BaseModel):
    name: str
    value: str | float | int | None
    confidence: float = Field(ge=0.0, le=1.0)
    page: int = 0
    source: str = "rules"  # rules | llm | table
    low_confidence: bool = False


class Transaction(BaseModel):
    day: str  # ISO date
    desc: str
    ref: str = ""
    debit: float = 0.0
    credit: float = 0.0
    balance: float = 0.0


class ValidationIssue(BaseModel):
    code: str  # e.g. PAN_FORMAT, NET_PAY_MISMATCH, BALANCE_BREAK
    message: str
    field: str | None = None


class TamperHint(BaseModel):
    code: str  # e.g. EDITOR_PRODUCER, ROUND_SALARY, NET_PAY_MISMATCH
    message: str


class ExtractedDocument(BaseModel):
    """What the Extraction agent hands on (AGENTS.md section 2)."""

    doc_type: DocType
    fields: list[ExtractedField] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    tamper_hints: list[TamperHint] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    statement_style: str | None = None
    quality_score: float | None = None  # 0-100, measured here (feeds CM-DOC-11)
    avg_confidence: float | None = None
    upload: UploadCheck | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    def get(self, name: str) -> str | float | int | None:
        for f in self.fields:
            if f.name == name:
                return f.value
        return None
