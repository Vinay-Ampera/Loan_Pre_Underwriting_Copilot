"""Identity fields for the application form, read from the PAN card and the Aadhaar card
(Stage 10, Part B; partly reverses E-31, see E-47 and E-48).

Exactly five form fields may come from a document: name, date of birth, PAN, Aadhaar last four
and address. Every claim (amount, tenure, purpose, employment, income, mobile, email, residential
status, loan-type fields, the relationship) is never read from a document; this module has no
way to produce one.

A field is filled only when it is clear: the value was read with confidence, and when both cards
show the same field they agree (names by the same fuzzy bar as the KYC rule, dates exactly). If
they disagree the field is left empty with a note, and the officer types it; the identity rule
then compares what was typed with both cards as it always did. The PAN card is the only source
of the PAN and the Aadhaar card the only source of the address and the Aadhaar number.
"""

from typing import Any

from app.intake.models import ExtractedDocument
from app.scoring.matching import name_match, parse_date

IDENTITY_FIELDS = ("full_name", "dob", "pan", "aadhaar_last4", "address")
LABEL = {"full_name": "name", "dob": "date of birth", "pan": "PAN",
         "aadhaar_last4": "Aadhaar last four", "address": "address"}  # fmt: skip
NAME_MIN = 85


def _read(doc: ExtractedDocument | None, name: str) -> tuple[str | None, bool]:
    """(value, readable). A value flagged low-confidence is not used."""
    if doc is None:
        return None, True
    for f in doc.fields:
        if f.name == name and f.value not in (None, ""):
            return (None, False) if f.low_confidence else (str(f.value).strip(), True)
    return None, False


def _pick(
    field: str, pan_doc: ExtractedDocument | None, aad_doc: ExtractedDocument | None,
    notes: dict[str, str],
) -> str | None:  # fmt: skip
    if field == "pan":
        value, ok = _read(pan_doc, "pan")
        if value is None and pan_doc is not None:
            notes[field] = "The PAN could not be read reliably from the PAN card."
        return value.upper() if value else None
    if field == "address":
        value, ok = _read(aad_doc, "address")
        if value is None and aad_doc is not None:
            notes[field] = "The address could not be read reliably from the Aadhaar card."
        return value
    if field == "aadhaar_last4":
        value, ok = _read(aad_doc, "aadhaar")
        digits = "".join(c for c in (value or "") if c.isdigit())
        if len(digits) != 12:
            if aad_doc is not None:
                notes[field] = "The Aadhaar number could not be read reliably."
            return None
        return digits[-4:]
    # full_name and dob exist on both cards
    column = "name" if field == "full_name" else "dob"
    a, _ = _read(pan_doc, column)
    b, _ = _read(aad_doc, column)
    if a and b:
        agree = (
            (name_match(a, b) or 0) >= NAME_MIN
            if field == "full_name"
            else parse_date(a) is not None and parse_date(a) == parse_date(b)
        )
        if not agree:
            notes[field] = (f"The PAN card and the Aadhaar card show different "
                            f"{'names' if field == 'full_name' else 'dates of birth'}. Type it yourself.")  # fmt: skip
            return None
        value = a
    else:
        value = a or b
        if value is None and (pan_doc is not None or aad_doc is not None):
            notes[field] = f"The {LABEL[field]} could not be read reliably from the cards."
    if value and field == "dob":
        d = parse_date(value)
        return d.isoformat() if d else None
    return value


def prefill(cards: dict[str, dict[str, ExtractedDocument]]) -> dict[str, dict[str, Any]]:
    """`cards`: role -> {"pan_card": doc, "aadhaar": doc}. Returns, per role,
    {"values": {field: value}, "from_documents": [field...], "notes": {field: text}}."""
    out: dict[str, dict[str, Any]] = {}
    for role, docs in cards.items():
        pan_doc, aad_doc = docs.get("pan_card"), docs.get("aadhaar")
        notes: dict[str, str] = {}
        values: dict[str, str] = {}
        for f in IDENTITY_FIELDS:
            v = _pick(f, pan_doc, aad_doc, notes)
            if v:
                values[f] = v
        out[role] = {"values": values, "from_documents": sorted(values), "notes": notes}
    return out


def still_from_documents(offered: dict[str, str], typed: dict[str, Any]) -> list[str]:
    """Which of the offered values the officer kept exactly as filled. A value typed over, or
    changed, is the officer's own and is no longer marked as read from a document."""
    kept = []
    for f, v in offered.items():
        got = typed.get(f)
        if got is None:
            continue
        a, b = str(got).strip(), str(v).strip()
        same = a.upper() == b.upper() if f == "pan" else a == b
        if f == "dob":
            same = parse_date(a) == parse_date(b)
        if same:
            kept.append(f)
    return sorted(kept)
