"""Offline ID validators. Pure functions, no lookups, no logging of identifiers."""

import re

# --- Aadhaar: 12 digits, first digit 2-9, Verhoeff checksum -------------------------------
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)  # fmt: skip
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)  # fmt: skip
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_check_digit(payload: str) -> str:
    """Check digit to append to a numeric payload."""
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def aadhaar_valid(aadhaar: str) -> bool:
    return bool(re.fullmatch(r"[2-9][0-9]{11}", aadhaar)) and verhoeff_valid(aadhaar)


# --- PAN: AAAAA9999A; 4th letter holder type; 5th letter surname initial (individuals) ----
PAN_RE = re.compile(r"[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]")


def pan_valid(pan: str, surname: str | None = None) -> bool:
    """Format check; if `surname` is given and the holder is an individual, check the 5th letter."""
    if not PAN_RE.fullmatch(pan):
        return False
    if surname is not None and pan[3] == "P":
        return pan[4] == surname.strip()[:1].upper()
    return True


# --- GSTIN: 2-digit state, PAN, entity digit, 'Z', check character ---------------------------
_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        prod = _GST_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += prod // 36 + prod % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def gstin_valid(gstin: str, pan: str | None = None) -> bool:
    """Format and checksum; with `pan`, also that the embedded PAN matches."""
    if not GSTIN_RE.fullmatch(gstin) or gstin[14] != gstin_check_char(gstin[:14]):
        return False
    return pan is None or gstin[2:12] == pan


# --- Udyam: UDYAM-XX-00-0000000 ------------------------------------------------------------
UDYAM_RE = re.compile(r"UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}")


def udyam_valid(udyam_no: str) -> bool:
    return bool(UDYAM_RE.fullmatch(udyam_no))
