"""Document classifier (FR-6): title phrases matched with a typo-tolerant fuzzy match, so it
works on OCR text too. Order matters: the most specific phrases come first.
"""

from rapidfuzz import fuzz

from app.intake.models import DocType

# (phrase, type). A phrase must appear in the top of the document (titles are near the top).
_PHRASES: tuple[tuple[str, DocType], ...] = (
    ("permanent account number card", DocType.PAN_CARD),
    ("aadhaar number", DocType.AADHAAR),
    ("unique identification authority", DocType.AADHAAR),
    ("payslip for", DocType.PAYSLIP),
    ("form 16 certificate under section 203", DocType.FORM16),
    ("income tax return acknowledgement", DocType.ITR),
    ("gstr-3b summary", DocType.GST_RETURNS),
    ("gst registration certificate", DocType.GST_REGISTRATION),
    ("udyam registration certificate", DocType.UDYAM_CERTIFICATE),
    ("shop and establishment certificate", DocType.BUSINESS_PROOF),
    ("certificate of constitution", DocType.BUSINESS_PROOF),
    ("financial statements for the year ended", DocType.PNL_BALANCE_SHEET),
    ("agreement for sale", DocType.SALE_AGREEMENT),
    ("title deed", DocType.TITLE_DEED),
    ("encumbrance certificate", DocType.ENCUMBRANCE_CERTIFICATE),
    ("approved building plan", DocType.APPROVED_PLAN),
    ("letter of admission", DocType.ADMISSION_LETTER),
    ("fee structure", DocType.FEE_STRUCTURE),
    ("statement of marks", DocType.MARKSHEET),
    ("proforma invoice", DocType.DEALER_INVOICE),
    ("driving licence", DocType.DRIVING_LICENCE),
    ("motor insurance policy", DocType.INSURANCE),
    ("registration certificate", DocType.RC_BOOK),  # after the GST and Udyam certificates
    ("statement of account", DocType.BANK_STATEMENT),
    ("account statement", DocType.BANK_STATEMENT),
    ("passbook statement", DocType.BANK_STATEMENT),
    ("opening balance", DocType.BANK_STATEMENT),
)
HEAD_LINES = 14  # a title is in the first lines; looking further invites false matches
MIN_SCORE = 90.0


def _norm(text: str) -> str:
    return " ".join(text.lower().replace(":", " ").replace(",", " ").split())


def _match(phrase: str, line: str) -> float:
    """Phrase inside a longer line scores by containment; a shorter line must match as a whole."""
    return (
        fuzz.partial_ratio(phrase, line) if len(line) >= len(phrase) else fuzz.ratio(phrase, line)
    )


def classify(lines: list[str], has_photo_only: bool = False) -> tuple[DocType, float]:
    """Returns (type, confidence 0-1). UNKNOWN when nothing matches well enough."""
    if not lines:
        return (DocType.PHOTO, 0.8) if has_photo_only else (DocType.UNKNOWN, 0.0)
    head = [_norm(line) for line in lines[:HEAD_LINES]]
    best_type, best = DocType.UNKNOWN, 0.0
    for phrase, doc_type in _PHRASES:
        score = max(
            (_match(phrase, h) for h in head if 0.85 * len(phrase) <= len(h) <= 3.5 * len(phrase)),
            default=0,
        )
        if score > best:
            best_type, best = doc_type, score
    if best >= MIN_SCORE:
        return best_type, round(best / 100, 2)
    if has_photo_only:  # an image with next to no text and no title is a photograph
        return DocType.PHOTO, 0.8
    return DocType.UNKNOWN, 0.0
