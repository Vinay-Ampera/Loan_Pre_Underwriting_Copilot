"""Admin user management: list, create, disable or enable, reset a password.

The server generates the temporary password and returns it once in the response; it is never
stored in the clear, logged, or written to the audit log (only the fact that it happened).
The officer profile lists that officer's cases (the admin may open any case). The read-only auditor account is
created and reset only from the command line: disable, enable and reset refuse it here. An admin cannot disable their own
account, and the last active admin cannot be disabled, so the system cannot lock itself out.
"""

import secrets
import string
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import User, admin_only, get_conn, write_audit
from app.api.schemas import UserCreateIn
from app.api.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])
_ALPHABET = string.ascii_letters + string.digits
_COLUMNS = "id, name, email, role, active, created_at, locked_until"


def temporary_password() -> str:
    """Three groups of four (14 characters with dashes), easy to read out, from a CSPRNG."""
    groups = ("".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3))
    return "-".join(groups)


def _row(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "email": r.email, "role": r.role, "active": r.active,
            "created_at": r.created_at, "locked": r.locked_until is not None}  # fmt: skip


def _target(conn: Connection, user_id: UUID) -> Any:
    row = conn.execute(
        text(f"SELECT {_COLUMNS} FROM users WHERE id = :i FOR UPDATE"), {"i": user_id}
    ).first()  # noqa: S608 - constant column list
    if row is None:
        raise HTTPException(404, "User not found.")
    return row


def _not_auditor(target: Any) -> None:
    if target.role == "auditor":
        raise HTTPException(403, "The auditor account is managed from the command line only.")


@router.get("/users")
def list_users(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS},
                        (SELECT count(*) FROM cases c WHERE c.created_by = users.id
                           AND c.status IN ('draft', 'uploaded', 'stopped', 'awaiting_confirmation')
                        ) AS open_cases
                 FROM users ORDER BY role, lower(name)""")  # noqa: S608
    )
    return [{**_row(r), "open_cases": r.open_cases} for r in rows]


@router.get("/summary")
def summary(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, int]:  # fmt: skip
    r = conn.execute(
        text("""SELECT
                  (SELECT count(*) FROM precedents WHERE status = 'pending') AS pending,
                  (SELECT count(*) FROM users WHERE role = 'officer' AND active) AS officers,
                  (SELECT count(*) FROM users WHERE role = 'admin' AND active) AS admins,
                  (SELECT count(*) FROM users WHERE NOT active) AS disabled,
                  (SELECT count(*) FROM issue_reports WHERE status = 'open') AS issues,
                  (SELECT count(*) FROM outbox WHERE status = 'sent') AS sent,
                  (SELECT count(*) FROM outbox WHERE status = 'failed') AS failed""")
    ).one()
    return {"pending_precedents": r.pending, "active_officers": r.officers,
            "active_admins": r.admins, "disabled_accounts": r.disabled,
            "open_issues": r.issues, "messages_sent": r.sent, "messages_failed": r.failed}  # fmt: skip


@router.get("/users/{user_id}/activity")
def user_activity(
    user_id: UUID, _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    """An officer profile for the admin: counts, and every case the officer owns."""
    user = _target(conn, user_id)
    by_status = {r.status: r.n for r in conn.execute(
        text("SELECT status, count(*) AS n FROM cases WHERE created_by = :u GROUP BY status"),
        {"u": user_id})}  # fmt: skip
    by_band = {r.band: r.n for r in conn.execute(
        text("""SELECT band, count(*) AS n FROM cases
                WHERE created_by = :u AND band IS NOT NULL GROUP BY band"""), {"u": user_id})}  # fmt: skip
    actions = {r.action: r.n for r in conn.execute(
        text("SELECT action, count(*) AS n FROM officer_actions WHERE officer_id = :u GROUP BY action"),
        {"u": user_id})}  # fmt: skip
    precedents = {r.status: r.n for r in conn.execute(
        text("SELECT status, count(*) AS n FROM precedents WHERE proposed_by = :u GROUP BY status"),
        {"u": user_id})}  # fmt: skip
    corrected = conn.execute(
        text("""SELECT count(DISTINCT a.case_id) FROM admin_actions a
                JOIN cases c ON c.id = a.case_id WHERE c.created_by = :u"""),
        {"u": user_id},
    ).scalar_one()
    cases = conn.execute(
        text("""SELECT c.id, c.case_no, c.loan_type, c.status, c.band, c.recommendation,
                       c.updated_at, c.loan_amount,
                       (SELECT a.full_name FROM applicants a
                         WHERE a.case_id = c.id AND a.role = 'primary') AS applicant,
                       EXISTS (SELECT 1 FROM admin_actions x WHERE x.case_id = c.id) AS corrected
                FROM cases c WHERE c.created_by = :u ORDER BY c.updated_at DESC LIMIT 300"""),
        {"u": user_id},
    )
    last_login = conn.execute(
        text("SELECT max(at) FROM audit_log WHERE actor_id = :u AND action = 'login'"),
        {"u": user_id},
    ).scalar()
    return {
        "user": _row(user), "last_login": last_login, "cases_total": sum(by_status.values()),
        "cases_by_status": by_status, "cases_by_band": by_band,
        "confirmed": actions.get("confirm", 0), "overridden": actions.get("override", 0),
        "admin_corrected": corrected, "precedents_by_status": precedents,
        "cases": [{"id": r.id, "case_no": r.case_no, "loan_type": r.loan_type, "status": r.status,
                   "band": r.band, "recommendation": r.recommendation, "applicant": r.applicant,
                   "loan_amount": None if r.loan_amount is None else float(r.loan_amount), "corrected": r.corrected,
                   "updated_at": r.updated_at} for r in cases],
    }  # fmt: skip


@router.post("/users", status_code=201)
def create_user(
    body: UserCreateIn, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    password = temporary_password()
    try:
        with conn.begin_nested():
            created = conn.execute(
                text(f"""INSERT INTO users (name, email, password_hash, role)
                         VALUES (:n, lower(:e), :h, :r) RETURNING {_COLUMNS}"""),  # noqa: S608
                {"n": body.name, "e": body.email, "h": hash_password(password), "r": body.role},
            ).one()
    except IntegrityError:
        raise HTTPException(409, "An account with this email already exists.") from None
    write_audit(conn, admin.id, "user_created", "user", created.id,
                after={"role": body.role, "email": created.email})  # fmt: skip
    return {**_row(created), "temporary_password": password}


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: UUID, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    target = _target(conn, user_id)
    _not_auditor(target)
    if target.id == admin.id:
        raise HTTPException(409, "You cannot disable your own account.")
    if target.role == "admin" and target.active:
        others = conn.execute(
            text("SELECT count(*) FROM users WHERE role = 'admin' AND active AND id <> :i"),
            {"i": user_id},
        ).scalar_one()
        if others == 0:
            raise HTTPException(409, "This is the last active admin account.")
    conn.execute(text("UPDATE users SET active = false, updated_at = now() WHERE id = :i"),
                 {"i": user_id})  # fmt: skip
    write_audit(conn, admin.id, "user_disabled", "user", user_id,
                before={"active": target.active}, after={"active": False})  # fmt: skip
    return {**_row(target), "active": False}


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: UUID, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    target = _target(conn, user_id)
    _not_auditor(target)
    conn.execute(
        text("""UPDATE users SET active = true, failed_logins = 0, locked_until = NULL,
                    updated_at = now() WHERE id = :i"""), {"i": user_id})  # fmt: skip
    write_audit(conn, admin.id, "user_enabled", "user", user_id,
                before={"active": target.active}, after={"active": True})  # fmt: skip
    return {**_row(target), "active": True, "locked": False}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: UUID, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    target = _target(conn, user_id)
    _not_auditor(target)
    password = temporary_password()
    conn.execute(
        text("""UPDATE users SET password_hash = :h, failed_logins = 0, locked_until = NULL,
                    updated_at = now() WHERE id = :i"""),
        {"h": hash_password(password), "i": user_id})  # fmt: skip
    write_audit(conn, admin.id, "user_password_reset", "user", user_id)
    return {"id": target.id, "email": target.email, "temporary_password": password}
