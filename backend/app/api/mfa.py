"""2-step verification pieces (SECURITY.md 4h): time-based 6-digit codes, the sealed setup key,
the QR code and recovery codes. No database and no HTTP here; `auth.py` and `users.py` use them.

The codes follow RFC 6238 with the settings every authenticator app reads by default (SHA-1, six
digits, 30 seconds), so Microsoft Authenticator, Google Authenticator and others all work. A code
from the 30 seconds before or after is accepted for a phone clock that is a little off, and only
a step newer than the last one accepted counts, so each code works once.
"""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from typing import Any
from urllib.parse import quote, urlencode

import segno
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings

ISSUER = "Pramaan"
STEP_SECONDS = 30
DIGITS = 6
RECOVERY_COUNT = 8
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: easy to read off paper
_RECOVERY_LENGTH = 10  # about 49 bits each


# --------------------------------------------------------------------------- codes
def new_secret() -> str:
    """160 random bits in base32 (32 characters), the size RFC 4226 recommends."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    number = (struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{number:0{DIGITS}d}"


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def matching_step(
    secret: str, code: str, last_step: int | None, now: float | None = None
) -> int | None:
    """The step `code` belongs to (the previous, current or next 30 seconds), or None. A step at or
    before `last_step` never matches: that code was already used."""
    if not re.fullmatch(rf"\d{{{DIGITS}}}", code):
        return None
    here = current_step(now)
    found = None
    for step in (here - 1, here, here + 1):  # all three compared: no early exit to time
        if hmac.compare_digest(code_at(secret, step), code) and (
            last_step is None or step > last_step
        ):
            found = step
    return found


def clean_code(raw: str) -> str:
    """What the person typed, without spaces or dashes, in lower case."""
    return re.sub(r"[\s-]", "", raw).lower()


# --------------------------------------------------------------------------- the stored key
def _fernet(settings: Settings) -> Fernet:
    """Derived from the server secret like the upload-link seal, under its own label."""
    raw = hashlib.sha256(b"mfa-secret:" + settings.jwt_secret.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(raw.digest()))


def seal(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode()).decode()


def unseal(settings: Settings, sealed: str | None) -> str | None:
    """The key, or None when there is none or JWT_SECRET changed since it was sealed."""
    if not sealed:
        return None
    try:
        return _fernet(settings).decrypt(sealed.encode()).decode()
    except InvalidToken:
        return None


# --------------------------------------------------------------------------- setting up
def setup_payload(secret: str, email: str) -> dict[str, Any]:
    """What the setup screen shows: the QR code for the app to scan and the same key as text, in
    groups of four, for typing in by hand."""
    label = quote(f"{ISSUER}:{email}")
    query = urlencode({"secret": secret, "issuer": ISSUER, "algorithm": "SHA1",
                       "digits": DIGITS, "period": STEP_SECONDS})  # fmt: skip
    uri = f"otpauth://totp/{label}?{query}"
    qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2, dark="#000", light="#fff")
    return {
        "qr": qr,
        "key": " ".join(secret[i : i + 4] for i in range(0, len(secret), 4)),
        "issuer": ISSUER,
        "account": email,
        "digits": DIGITS,
        "period": STEP_SECONDS,
    }


# --------------------------------------------------------------------------- recovery codes
def new_recovery_codes() -> list[str]:
    """Shown once, as xxxxx-xxxxx. Only their hashes are stored."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_LENGTH))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def looks_like_recovery(cleaned: str) -> bool:
    return len(cleaned) == _RECOVERY_LENGTH and all(c in _RECOVERY_ALPHABET for c in cleaned)


def hash_recovery(code: str) -> str:
    return hashlib.sha256(clean_code(code).encode()).hexdigest()
