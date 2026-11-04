"""Request dependencies: a database connection, the signed-in user, and role checks.

Roles are enforced here on the server for every endpoint; the UI hiding a button is a courtesy.
The role is read from the database on each request, never trusted from the token alone, so a
deactivated user or a changed role takes effect at once.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, Engine, text

from app.api.security import decode_token
from app.core.config import Settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class User:
    id: UUID
    name: str
    email: str
    role: str
    sid: UUID | None = None  # the sign-in session this request belongs to


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_conn(engine: Engine = Depends(get_engine)) -> Iterator[Connection]:
    """One transaction per request: committed when the endpoint returns, rolled back on error."""
    with engine.begin() as conn:
        yield conn


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings_dep),
    engine: Engine = Depends(get_engine),
) -> User:
    if creds is None:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(settings, creds.credentials)
        user_id, sid = UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Your session has expired. Sign in again.") from None
    with engine.connect() as conn:
        row = conn.execute(
            text("""SELECT u.id, u.name, u.email, u.role, u.active,
                           s.started_at, s.last_active, s.revoked_at
                    FROM users u LEFT JOIN user_sessions s ON s.id = :s AND s.user_id = u.id
                    WHERE u.id = :i"""),
            {"i": user_id, "s": sid},
        ).first()
    if row is None or not row.active:
        raise HTTPException(401, "This account is not active.")
    if row.started_at is None or row.revoked_at is not None or session_over(settings, row):
        raise HTTPException(401, "Your session has ended. Sign in again.")
    return User(id=row.id, name=row.name, email=row.email, role=row.role, sid=sid)


def session_over(settings: Settings, row: Any, now: datetime | None = None) -> str | None:
    """'max' or 'idle' when the session has run past a limit, else None. Both limits are
    enforced here on the server; the browser's timers are only a courtesy warning."""
    now = now or datetime.now(UTC)
    if now - row.started_at > timedelta(hours=settings.session_max_hours):
        return "max"
    if now - row.last_active > timedelta(minutes=settings.idle_timeout_minutes):
        return "idle"
    return None


def require_role(*roles: str) -> Callable[[User], User]:
    def check(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This action is for {' or '.join(roles)} accounts only.")
        return user

    return check


officer_only = require_role("officer")
admin_only = require_role("admin")
auditor_only = require_role("auditor")
# Case data: an officer (own cases) or an admin (every case). Never the auditor, who sees
# aggregate tables only.
case_reader = require_role("officer", "admin")
# Read-only data every signed-in role may see. Writes must never use this.
any_reader = require_role("officer", "admin", "auditor")


def write_audit(
    conn: Connection, actor_id: UUID | None, action: str, entity: str, entity_id: UUID | str | None,
    *, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None,
) -> None:  # fmt: skip
    """Append to the audit log. Never put raw identifiers or document text in `before`/`after`."""
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, before, after)
                VALUES (:u, :a, :e, :i, CAST(:b AS jsonb), CAST(:f AS jsonb))"""),
        {"u": actor_id, "a": action, "e": entity, "i": None if entity_id is None else str(entity_id),
         "b": None if before is None else json.dumps(before, default=str),
         "f": None if after is None else json.dumps(after, default=str)},
    )  # fmt: skip
