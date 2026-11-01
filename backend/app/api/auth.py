"""Sign-in. Passwords are hashed with argon2; repeated failures lock the account for a while
(SECURITY.md section 4). Every login, failure and lockout is written to the audit log."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text

from app.api.deps import User, current_user, get_conn, get_settings_dep, write_audit
from app.api.schemas import CO_APPLICANT, LOAN_FIELDS, LoginIn
from app.api.security import create_token, verify_password
from app.core.config import Settings

router = APIRouter(tags=["auth"])
BAD_LOGIN = "Email or password is incorrect."


def _user_json(u: User) -> dict[str, Any]:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


@router.post("/auth/login")
def login(
    body: LoginIn, conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep)
) -> Any:  # fmt: skip
    # failures are returned, not raised, so the failure count and audit row are committed
    row = conn.execute(
        text("""SELECT id, name, email, role, active, password_hash, failed_logins, locked_until
                FROM users WHERE lower(email) = lower(:e) FOR UPDATE"""),
        {"e": body.email.strip()},
    ).first()
    now = datetime.now(UTC)
    if row is not None and row.locked_until and row.locked_until > now:
        write_audit(conn, row.id, "login_blocked", "user", row.id, after={"reason": "locked"})
        return JSONResponse(
            {"detail": "Too many failed attempts. Try again in a few minutes."}, 423
        )
    ok = verify_password(body.password, row.password_hash if row else None)
    if row is None or not ok or not row.active:
        if row is not None:
            failures = row.failed_logins + 1
            lock = now + timedelta(minutes=settings.login_lock_minutes) \
                if failures >= settings.login_max_failures else None  # fmt: skip
            conn.execute(
                text("UPDATE users SET failed_logins = :f, locked_until = :l WHERE id = :i"),
                {"f": 0 if lock else failures, "l": lock, "i": row.id},
            )
            write_audit(conn, row.id, "login_locked" if lock else "login_failed", "user", row.id)
        else:
            write_audit(conn, None, "login_failed", "user", None, after={"unknown_email": True})
        return JSONResponse({"detail": BAD_LOGIN}, 401)
    conn.execute(text("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = :i"),
                 {"i": row.id})  # fmt: skip
    write_audit(conn, row.id, "login", "user", row.id)
    user = User(id=row.id, name=row.name, email=row.email, role=row.role)
    return {"access_token": create_token(settings, str(row.id), row.role), "token_type": "bearer",
            "user": _user_json(user)}  # fmt: skip


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return _user_json(user)


@router.get("/meta/loan-types")
def loan_types(_: User = Depends(current_user)) -> dict[str, Any]:
    """The loan-specific form sections and the co-applicant rule per loan type."""
    return {"fields": LOAN_FIELDS, "co_applicant": CO_APPLICANT}
