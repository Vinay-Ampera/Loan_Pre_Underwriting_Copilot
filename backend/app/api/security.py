"""Password hashing (argon2) and short-lived JWTs. The secret comes from `Settings` only."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

_hasher = PasswordHasher()
_ALGORITHM = "HS256"
DEFAULT_SECRET = "change-me-to-a-long-random-string"  # noqa: S105 - the .env.example placeholder
# verified against when the e-mail is unknown, so a missing user takes as long as a wrong password
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_token(settings: Settings, user_id: str, role: str) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user_id, "role": role, "iat": now,
              "exp": now + timedelta(minutes=settings.access_token_minutes)}  # fmt: skip
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=_ALGORITHM)


def decode_token(settings: Settings, token: str) -> dict[str, Any]:
    """The token's claims, or `jwt.PyJWTError` when it is invalid or expired."""
    return jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=[_ALGORITHM])
