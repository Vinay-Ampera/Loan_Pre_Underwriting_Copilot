"""Sign-in and sessions. Passwords are hashed with argon2; repeated failures lock the account for
a while (SECURITY.md section 4). Every login, failure, lockout and session end is written to the
audit log.

A sign-in is a `user_sessions` row. The 15-minute access token names it; the refresh token sits in
an HttpOnly cookie and is rotated on every use. The server ends a session after the idle timeout
or the hard maximum, whatever the browser does (SECURITY.md section 4a).

2-step verification (SECURITY.md 4h): for the roles in MFA_ROLES (admin and auditor), and for any
account that has it set up, a correct password gives no session, only a 5-minute token for the code
step. The first time, the answer also carries a QR code to scan; the first good code turns 2-step on
and returns eight recovery codes, shown once. Wrong codes count toward the same lockout as wrong
passwords."""

import hmac
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text

from app.api import mfa
from app.api.deps import (
    User,
    current_user,
    get_conn,
    get_settings_dep,
    session_over,
    write_audit,
)  # fmt: skip
from app.api.schemas import CO_APPLICANT, LOAN_FIELDS, LoginIn, MfaIn
from app.api.security import (
    create_mfa_token,
    create_token,
    decode_mfa_token,
    hash_refresh,
    new_refresh_secret,
    password_mark,
    verify_password,
)  # fmt: skip
from app.core.config import Settings

router = APIRouter(tags=["auth"])
BAD_LOGIN = "Email or password is incorrect."
LOCKED = "Too many failed attempts. Try again in a few minutes."
BAD_CODE = "That code is not right. Use the newest code in the app, or a recovery code."
RESTART = "This sign-in took too long or was reset. Enter your email and password again."
COOKIE = "lc_refresh"
COOKIE_PATH = "/api/v1/auth"
ENDED = {  # what the browser is told when the server ends a session
    "idle": "You were signed out after a period of no activity.",
    "max": "Your working session reached its time limit. Sign in again.",
    "reuse": "This session was closed for your safety. Sign in again.",
    "inactive": "This account is not active.",
}


def _set_cookie(response: Response, settings: Settings, sid: UUID, secret: str) -> None:
    # No max-age: a session cookie, gone when the browser closes. Only sent to /auth routes.
    response.set_cookie(COOKIE, f"{sid}.{secret}", httponly=True, samesite="strict",
                        secure=settings.app_env != "dev", path=COOKIE_PATH)  # fmt: skip


def _ended(settings: Settings, reason: str) -> JSONResponse:
    res = JSONResponse({"detail": ENDED.get(reason, ENDED["reuse"]), "reason": reason}, 401)
    res.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict",
                      secure=settings.app_env != "dev")  # fmt: skip
    return res


def _session_json(settings: Settings, started_at: datetime) -> dict[str, Any]:
    """The limits the browser needs for its timers and warnings. The server enforces them."""
    return {
        "access_token_seconds": settings.access_token_minutes * 60,
        "idle_timeout_seconds": settings.idle_timeout_minutes * 60,
        "idle_warning_seconds": settings.idle_warning_minutes * 60,
        "max_ends_at": (started_at + timedelta(hours=settings.session_max_hours)).isoformat(),
    }


def _user_json(u: User) -> dict[str, Any]:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


def _failed(conn: Connection, settings: Settings, row: Any, action: str) -> bool:
    """One more failure for a wrong password or a wrong code; True when it locks the account."""
    failures = row.failed_logins + 1
    lock = datetime.now(UTC) + timedelta(minutes=settings.login_lock_minutes) \
        if failures >= settings.login_max_failures else None  # fmt: skip
    conn.execute(
        text("UPDATE users SET failed_logins = :f, locked_until = :l WHERE id = :i"),
        {"f": 0 if lock else failures, "l": lock, "i": row.id},
    )
    write_audit(conn, row.id, "login_locked" if lock else action, "user", row.id)
    return lock is not None


def _start_session(
    conn: Connection, response: Response, settings: Settings, row: Any, mfa_used: str | None
) -> dict[str, Any]:  # fmt: skip
    """The sign-in itself: a session row, the refresh cookie and a 15-minute access token."""
    conn.execute(text("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = :i"),
                 {"i": row.id})  # fmt: skip
    write_audit(conn, row.id, "login", "user", row.id,
                after=None if mfa_used is None else {"two_step": mfa_used})  # fmt: skip
    user = User(id=row.id, name=row.name, email=row.email, role=row.role)
    sid, secret = uuid4(), new_refresh_secret()
    conn.execute(text("DELETE FROM user_sessions WHERE started_at < now() - interval '2 days'"))
    started_at = conn.execute(
        text("""INSERT INTO user_sessions (id, user_id, refresh_hash)
                VALUES (:s, :u, :h) RETURNING started_at"""),
        {"s": sid, "u": row.id, "h": hash_refresh(secret)},
    ).scalar_one()
    _set_cookie(response, settings, sid, secret)
    return {"access_token": create_token(settings, str(row.id), row.role, str(sid)),
            "token_type": "bearer", "user": _user_json(user),
            "session": _session_json(settings, started_at)}  # fmt: skip


def needs_two_step(settings: Settings, row: Any) -> bool:
    return row.role in settings.mfa_role_set() or row.mfa_enabled_at is not None


_LOGIN_ROW = """SELECT id, name, email, role, active, password_hash, failed_logins, locked_until,
                       mfa_secret, mfa_pending_secret, mfa_enabled_at, mfa_last_step
                FROM users WHERE {where} FOR UPDATE"""


@router.post("/auth/login")
def login(
    body: LoginIn, response: Response, conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep)
) -> Any:  # fmt: skip
    # failures are returned, not raised, so the failure count and audit row are committed
    row = conn.execute(
        text(_LOGIN_ROW.format(where="lower(email) = lower(:e)")), {"e": body.email.strip()}
    ).first()
    now = datetime.now(UTC)
    if row is not None and row.locked_until and row.locked_until > now:
        write_audit(conn, row.id, "login_blocked", "user", row.id, after={"reason": "locked"})
        return JSONResponse({"detail": LOCKED}, 423)
    ok = verify_password(body.password, row.password_hash if row else None)
    if row is None or not ok or not row.active:
        if row is not None:
            _failed(conn, settings, row, "login_failed")
        else:
            write_audit(conn, None, "login_failed", "user", None, after={"unknown_email": True})
        return JSONResponse({"detail": BAD_LOGIN}, 401)
    if not needs_two_step(settings, row):
        return _start_session(conn, response, settings, row, None)
    # the password was right: the code comes next. The failure count is kept until then.
    write_audit(conn, row.id, "two_step_asked", "user", row.id)
    token = create_mfa_token(settings, str(row.id), row.password_hash)
    if row.mfa_enabled_at is not None:
        return {"mfa": "code", "mfa_token": token}
    secret = mfa.new_secret()  # first sign-in, or after a reset: set it up now
    conn.execute(text("UPDATE users SET mfa_pending_secret = :p WHERE id = :i"),
                 {"p": mfa.seal(settings, secret), "i": row.id})  # fmt: skip
    return {"mfa": "setup", "mfa_token": token, "setup": mfa.setup_payload(secret, row.email)}


@router.post("/auth/mfa/verify")
def verify_two_step(
    body: MfaIn, response: Response, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> Any:  # fmt: skip
    """The code step. Setting up: the first code from the app confirms the new key, turns 2-step on
    and returns the recovery codes. Signing in: a code from the app, or one unused recovery code."""
    restart = JSONResponse({"detail": RESTART, "reason": "restart"}, 401)
    try:
        claims = decode_mfa_token(settings, body.mfa_token)
        user_id = UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return restart
    row = conn.execute(text(_LOGIN_ROW.format(where="id = :i")), {"i": user_id}).first()
    if row is None or not row.active or claims.get("pwd") != password_mark(row.password_hash):
        return restart
    if row.locked_until and row.locked_until > datetime.now(UTC):
        write_audit(conn, row.id, "login_blocked", "user", row.id, after={"reason": "locked"})
        return JSONResponse({"detail": LOCKED}, 423)
    code = mfa.clean_code(body.code)

    def wrong() -> JSONResponse:
        locked = _failed(conn, settings, row, "two_step_failed")
        return (
            JSONResponse({"detail": LOCKED}, 423)
            if locked
            else JSONResponse({"detail": BAD_CODE}, 401)
        )

    if row.mfa_enabled_at is None:  # setting up
        pending = mfa.unseal(settings, row.mfa_pending_secret)
        if pending is None:
            return restart
        step = mfa.matching_step(pending, code, None)
        if step is None:
            return wrong()
        codes = mfa.new_recovery_codes()
        conn.execute(
            text("""UPDATE users SET mfa_secret = mfa_pending_secret, mfa_pending_secret = NULL,
                        mfa_enabled_at = now(), mfa_last_step = :s, updated_at = now()
                    WHERE id = :i"""),
            {"s": step, "i": row.id},
        )
        conn.execute(text("DELETE FROM user_recovery_codes WHERE user_id = :i"), {"i": row.id})
        for c in codes:
            conn.execute(text("INSERT INTO user_recovery_codes (user_id, code_hash) VALUES (:u, :h)"),
                         {"u": row.id, "h": mfa.hash_recovery(c)})  # fmt: skip
        write_audit(conn, row.id, "two_step_enabled", "user", row.id)
        return {**_start_session(conn, response, settings, row, "setup"), "recovery_codes": codes}
    secret = mfa.unseal(settings, row.mfa_secret)
    step = None if secret is None else mfa.matching_step(secret, code, row.mfa_last_step)
    if step is not None:
        conn.execute(text("UPDATE users SET mfa_last_step = :s WHERE id = :i"),
                     {"s": step, "i": row.id})  # fmt: skip
        return _start_session(conn, response, settings, row, "app")
    spent = mfa.looks_like_recovery(code) and conn.execute(
        text("""UPDATE user_recovery_codes SET used_at = now()
                WHERE user_id = :u AND code_hash = :h AND used_at IS NULL RETURNING id"""),
        {"u": row.id, "h": mfa.hash_recovery(code)},
    ).first()  # fmt: skip
    if not spent:
        return wrong()
    left = conn.execute(
        text("SELECT count(*) FROM user_recovery_codes WHERE user_id = :u AND used_at IS NULL"),
        {"u": row.id},
    ).scalar_one()
    write_audit(conn, row.id, "two_step_recovery_used", "user", row.id, after={"left": left})
    return {
        **_start_session(conn, response, settings, row, "recovery"),
        "recovery_codes_left": left,
    }


def _end(conn: Connection, session_id: UUID, user_id: UUID, reason: str) -> None:
    conn.execute(
        text("""UPDATE user_sessions SET revoked_at = now(), revoked_reason = :r
                WHERE id = :s AND revoked_at IS NULL"""),
        {"s": session_id, "r": reason},
    )
    action = {"logout": "logout", "idle": "session_idle_end", "max": "session_max_end",
              "reuse": "token_reuse", "inactive": "session_inactive_end"}[reason]  # fmt: skip
    write_audit(conn, user_id, action, "user", user_id)


@router.post("/auth/refresh")
def refresh(
    request: Request, response: Response, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> Any:  # fmt: skip
    """A new 15-minute access token, if the session is still inside both limits. The refresh
    token is rotated each time; presenting an old one again closes the session (token theft).
    Failures are returned, not raised, so the session end and its audit row are committed."""
    sid_text, _, secret = (request.cookies.get(COOKIE) or "").partition(".")
    try:
        sid = UUID(sid_text)
    except ValueError:
        return _ended(settings, "reuse")
    row = conn.execute(
        text("""SELECT s.*, u.name, u.email, u.role, u.active
                FROM user_sessions s JOIN users u ON u.id = s.user_id
                WHERE s.id = :s FOR UPDATE OF s"""),
        {"s": sid},
    ).first()
    presented = hash_refresh(secret)
    if row is None or row.revoked_at is not None or not secret:
        return _ended(settings, "reuse")
    now = datetime.now(UTC)
    is_current = hmac.compare_digest(presented, row.refresh_hash)
    is_previous = row.prev_refresh_hash is not None         and hmac.compare_digest(presented, row.prev_refresh_hash)  # fmt: skip
    if not (is_current or is_previous):
        return _ended(settings, "reuse")  # a guess: nothing to prove, so the session stays
    if not row.active:
        _end(conn, sid, row.user_id, "inactive")
        return _ended(settings, "inactive")
    over = session_over(settings, row, now)
    if over:
        _end(conn, sid, row.user_id, over)
        return _ended(settings, over)
    if not is_current:  # an already-used token
        if row.rotated_at and now - row.rotated_at <= timedelta(
            seconds=settings.refresh_grace_seconds
        ):
            # a second tab, a moment after the first rotated it: a token, but no new cookie
            return {"access_token": create_token(settings, str(row.user_id), row.role, str(sid)),
                    "token_type": "bearer", "user": _user_json(User(row.user_id, row.name, row.email, row.role)),
                    "session": _session_json(settings, row.started_at)}  # fmt: skip
        _end(conn, sid, row.user_id, "reuse")
        return _ended(settings, "reuse")
    new_secret = new_refresh_secret()
    conn.execute(
        text("""UPDATE user_sessions SET prev_refresh_hash = refresh_hash, refresh_hash = :h,
                rotated_at = now() WHERE id = :s"""),
        {"h": hash_refresh(new_secret), "s": sid},
    )
    _set_cookie(response, settings, sid, new_secret)
    user = User(row.user_id, row.name, row.email, row.role)
    return {"access_token": create_token(settings, str(row.user_id), row.role, str(sid)),
            "token_type": "bearer", "user": _user_json(user),
            "session": _session_json(settings, row.started_at)}  # fmt: skip


@router.post("/auth/ping")
def ping(
    user: User = Depends(current_user), conn: Connection = Depends(get_conn)
) -> dict[str, bool]:
    """The browser says the person is still working (a click or key press). Background polling
    never calls this, so an idle screen cannot keep a session alive."""
    conn.execute(
        text("UPDATE user_sessions SET last_active = now() WHERE id = :s"), {"s": user.sid}
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(
    request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> Any:  # fmt: skip
    """Ends the session on the server and drops the cookie. Needs only the cookie, so it works
    even after the access token has expired."""
    try:
        sid = UUID((request.cookies.get(COOKIE) or "").partition(".")[0])
    except ValueError:
        sid = None
    row = None if sid is None else conn.execute(
        text("SELECT user_id FROM user_sessions WHERE id = :s AND revoked_at IS NULL"), {"s": sid}
    ).first()  # fmt: skip
    if sid is not None and row is not None:
        _end(conn, sid, row.user_id, "logout")
    res = JSONResponse({"ok": True})
    res.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="strict",
                      secure=settings.app_env != "dev")  # fmt: skip
    return res


@router.get("/auth/me")
def me(user: User = Depends(current_user)) -> dict[str, Any]:
    return _user_json(user)


@router.get("/meta/loan-types")
def loan_types(request: Request, _: User = Depends(current_user)) -> dict[str, Any]:
    """The loan-specific form sections, the co-applicant rule and, from the rules file, the
    documents each loan type needs (shown on the New case page before the case is opened)."""
    rs = request.app.state.ruleset
    documents = {
        loan: [
            d.model_dump(include={"type", "kyc", "min_count", "applicant", "when", "any_of"})
            for d in rs.required_documents(loan)
        ]
        for loan in CO_APPLICANT
    }
    return {"fields": LOAN_FIELDS, "co_applicant": CO_APPLICANT, "documents": documents}
