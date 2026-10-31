"""Fuzzy matching of names, PAN, DOB and addresses across documents and the application form.

The same matcher the synthetic generator uses (rapidfuzz token_sort_ratio, 0-100), so a reference
score and a measured score agree. Thresholds are in `data/rules/rules.yaml`, not here.
"""

import re
from collections.abc import Iterable
from datetime import date, datetime

from rapidfuzz import fuzz

_HONORIFICS = re.compile(r"\b(mr|mrs|ms|miss|shri|smt|sri|dr)\b\.?", re.IGNORECASE)
_NOISE = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y")


def _norm(text: str, *, strip_titles: bool) -> str:
    if strip_titles:
        text = _HONORIFICS.sub(" ", text)
    return _SPACE.sub(" ", _NOISE.sub(" ", text.casefold())).strip()


def name_match(a: str | None, b: str | None) -> int | None:
    """0-100, order-insensitive ("Sinha Rekha" = "Rekha Sinha"). None when either is missing."""
    if not a or not b:
        return None
    return round(fuzz.token_sort_ratio(_norm(a, strip_titles=True), _norm(b, strip_titles=True)))


def address_match(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    # case and spacing only: punctuation carries meaning in an address ("12, Park Rd")
    return round(
        fuzz.token_sort_ratio(_SPACE.sub(" ", a.casefold()), _SPACE.sub(" ", b.casefold()))
    )


def pan_match(a: str | None, b: str | None) -> bool | None:
    """Exact match after trimming and upper-casing. A PAN is never fuzzy-matched."""
    if not a or not b:
        return None
    return a.strip().upper() == b.strip().upper()


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def dob_match(application: date, shown: Iterable[object]) -> bool | None:
    """True when every date shown on a document equals the application date. None = none shown."""
    parsed = [parse_date(v) for v in shown if v not in (None, "")]
    if not parsed:
        return None
    return all(d == application for d in parsed)


def min_score(scores: Iterable[int | None]) -> int | None:
    """Weakest of the scores that exist (a missing document does not lower the score)."""
    present = [s for s in scores if s is not None]
    return min(present) if present else None
