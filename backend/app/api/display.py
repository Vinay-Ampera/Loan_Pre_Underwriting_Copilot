"""What the UI may show: identifiers are always masked (DESIGN_SYSTEM section 5, SECURITY section 1).

PAN keeps its first five and last characters, Aadhaar its last four digits; phone, GSTIN, e-mail
and long account numbers are masked the same way. Names, amounts and dates are shown as they are
to the officer who owns the case.
"""

import re

_PAN = re.compile(r"\b([A-Z]{5})\d{4}([A-Z])\b")
_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?(\d{4})(?!\d)")
_GSTIN = re.compile(r"\b(\d{2}[A-Z]{5})\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_PHONE = re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{5}(\d{4})(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_ACCOUNT = re.compile(r"(?<![\d,.])\d{5,14}(\d{4})(?![\d,]|\.\d)")


def mask_pan(pan: str | None) -> str | None:
    return None if not pan else f"{pan[:5]}****{pan[-1]}"


def mask_aadhaar_last4(last4: str | None) -> str | None:
    return None if not last4 else f"XXXX XXXX {last4}"


def mask_phone(phone: str | None) -> str | None:
    return None if not phone else f"******{phone[-4:]}"


def display_text(value: str) -> str:
    """Mask every identifier pattern in a value shown on screen."""
    value = _GSTIN.sub(lambda m: f"{m.group(1)}****", value)
    value = _PAN.sub(lambda m: f"{m.group(1)}****{m.group(2)}", value)
    value = _AADHAAR.sub(lambda m: f"XXXX XXXX {m.group(1)}", value)
    value = _EMAIL.sub(lambda m: f"****@{m.group(1)}", value)
    value = _PHONE.sub(lambda m: f"******{m.group(1)}", value)
    return _ACCOUNT.sub(lambda m: f"****{m.group(1)}", value)


# ---- the auditor sees names, addresses and birth dates masked as well (SECURITY.md D3)
def mask_name(name: str | None) -> str | None:
    """'Asha Rao' -> 'A*** R**': first letter of each part and a star per remaining letter (max 3)."""
    if not name:
        return None
    return " ".join(p[0] + "*" * min(len(p) - 1, 3) for p in name.split())


def mask_dob(dob: object) -> str | None:
    """Birth year only."""
    return None if not dob else f"{str(dob)[:4]}-**-**"


def scrub_for_auditor(value: object, names: list[str]) -> object:
    """Mask identifiers and every part of the given names (3+ letters) in any nested value."""
    parts = sorted({p for n in names for p in n.split() if len(p) >= 3}, key=len, reverse=True)
    pats = [(re.compile(re.escape(p), re.IGNORECASE), mask_name(p) or "") for p in parts]

    def walk(v: object) -> object:
        if isinstance(v, str):
            v = display_text(v)
            for pat, repl in pats:
                v = pat.sub(repl, v)
            return v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    return walk(value)
