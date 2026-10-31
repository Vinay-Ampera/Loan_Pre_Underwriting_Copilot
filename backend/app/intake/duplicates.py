"""Duplicate uploads within one case (docs/EDGE_CASES.md E-01).

Two checks, in order:
  1. SHA-256 of the file: the identical file again. Never a false match.
  2. A content key built from the extracted fields: document type + person + period, so a rescan
     or re-export of the same document matches while payslips for different months, or a
     co-applicant's documents, do not. A document whose key cannot be built (OCR missed a part)
     is never called a duplicate.
File names are not used: they are not reliable in either direction.
Pure functions and an in-memory registry; storing `sha256` is the case layer's job (Stage 5/6).
"""

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum

from app.intake.models import DocType, ExtractedDocument, TamperHint

# What identifies "the same document" per type. Every part must be present to build a key.
_KEYS: dict[DocType, tuple[str, ...]] = {
    DocType.PAYSLIP: ("pan", "month"),
    DocType.FORM16: ("pan", "ay"),
    DocType.ITR: ("pan", "ay"),
    DocType.PAN_CARD: ("pan",),
    DocType.AADHAAR: ("aadhaar",),
    DocType.GST_REGISTRATION: ("gstin",),
    DocType.GST_RETURNS: ("gstin",),
    DocType.UDYAM_CERTIFICATE: ("udyam",),
    DocType.DRIVING_LICENCE: ("licence_no",),
    DocType.RC_BOOK: ("registration",),
}
# Money fields compared when two documents share a key: same key, different amounts = conflict.
_AMOUNTS = ("gross", "net", "total_deductions", "gross_total_income", "total_taxable_income",
            "credits_total", "debits_total", "closing_balance", "total", "net_profit")  # fmt: skip


class Verdict(StrEnum):
    NEW = "new"
    EXACT_DUPLICATE = "exact_duplicate"  # same bytes: ignore
    SAME_DOCUMENT = "same_document"  # same content under another file: ignore
    CONFLICTING = (
        "conflicting_duplicate"  # same document, different amounts: keep both, tamper hint
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_key(doc: ExtractedDocument) -> str | None:
    """Stable identity of a document, or None when it cannot be told apart safely."""
    if doc.doc_type is DocType.BANK_STATEMENT:
        acct = doc.get("account_no")
        if not acct or not doc.transactions:
            return None
        days = sorted(t.day for t in doc.transactions)
        return f"bank_statement|{acct}|{days[0]}|{days[-1]}"
    parts = _KEYS.get(doc.doc_type)
    if not parts:
        return None
    values = [doc.get(p) for p in parts]
    if any(v in (None, "") for v in values):
        return None
    return "|".join([doc.doc_type.value, *(str(v) for v in values)])


def amounts(doc: ExtractedDocument) -> dict[str, float]:
    return {f.name: float(f.value) for f in doc.fields
            if f.name in _AMOUNTS and isinstance(f.value, int | float)}  # fmt: skip


@dataclass(frozen=True)
class Seen:
    label: str  # for messages only (original file name); never used to decide
    sha256: str
    key: str | None
    amounts: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    matched: str | None = None  # label of the earlier file
    message: str = ""

    @property
    def keep(self) -> bool:
        """False when the new upload should be ignored."""
        return self.verdict in (Verdict.NEW, Verdict.CONFLICTING)


class CaseDocuments:
    """Accepted documents of one case. Rejected uploads are never recorded."""

    def __init__(self) -> None:
        self._seen: list[Seen] = []

    def check(self, label: str, sha256: str, doc: ExtractedDocument | None) -> Decision:
        for s in self._seen:
            if s.sha256 == sha256:
                return Decision(
                    Verdict.EXACT_DUPLICATE, s.label, f"Same file already uploaded ({s.label})"
                )
        key = document_key(doc) if doc else None
        if key is None or doc is None:
            return Decision(Verdict.NEW)
        mine = amounts(doc)
        for s in self._seen:
            if s.key != key:
                continue
            differs = [
                k for k in mine.keys() & s.amounts.keys() if abs(mine[k] - s.amounts[k]) > 1.0
            ]
            if differs:
                return Decision(Verdict.CONFLICTING, s.label,
                                f"Same document as {s.label} but {', '.join(sorted(differs))} differ")  # fmt: skip
            return Decision(
                Verdict.SAME_DOCUMENT, s.label, f"Same document already uploaded ({s.label})"
            )
        return Decision(Verdict.NEW)

    def add(self, label: str, sha256: str, doc: ExtractedDocument | None) -> Decision:
        """Check, then record the upload unless it is an ignorable duplicate. A conflicting
        duplicate is kept and carries a tamper hint on the document."""
        decision = self.check(label, sha256, doc)
        if decision.keep:
            self._seen.append(
                Seen(label, sha256, document_key(doc) if doc else None, amounts(doc) if doc else {})
            )
        if decision.verdict is Verdict.CONFLICTING and doc is not None:
            doc.tamper_hints.append(TamperHint(code="DUPLICATE_CONFLICT", message=decision.message))
        if not decision.keep and doc is not None:
            doc.quality_flags.append("duplicate_ignored")
        return decision

    def unique_count(self, doc_type: DocType | None = None) -> int:
        """Documents that count towards completeness: duplicates never fill a missing slot."""
        return len({s.key or s.sha256 for s in self._seen
                    if doc_type is None or (s.key or "").startswith(doc_type.value)})  # fmt: skip
