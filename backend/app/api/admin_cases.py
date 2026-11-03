"""Admin routes for cases and the work around them. Only admin accounts reach these.

The admin corrects, and only after the officer has decided: `override` adds an `admin_actions`
row (reason, second click) beside the officer's decision and never edits it. A case that failed a
hard rule cannot be corrected. `reassign` hands a case the officer has not decided to another
active officer, so every case is still decided by an officer first. Sent messages are
listed here read-only. The system-wide audit log is the auditor's alone.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection, text

from app.api import display
from app.api.decisions import REASSIGNABLE, decision_in_force, override_block
from app.api.deps import User, admin_only, get_conn, write_audit
from app.api.schemas import AdminOverrideIn, ReassignIn
from app.notifications import templates

router = APIRouter(prefix="/admin", tags=["admin"])
MIN_REASON = 15
TEMPLATE_LABEL = {k: t.label for k, t in templates.TEMPLATES.items()}


def _case(conn: Connection, case_id: UUID) -> Any:
    row = conn.execute(text("SELECT * FROM cases WHERE id = :i FOR UPDATE"), {"i": case_id}).first()
    if row is None:
        raise HTTPException(404, "Case not found.")
    return row


def _checked(body: AdminOverrideIn | ReassignIn) -> str:
    if body.second_click is not True:
        raise HTTPException(422, "This needs a second confirmation click.")
    reason = body.reason.strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(422, f"Write the reason (at least {MIN_REASON} characters).")
    return reason


@router.post("/cases/{case_id}/override")
def override_case(
    case_id: UUID, body: AdminOverrideIn, admin: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    reason = _checked(body)
    row = _case(conn, case_id)
    report = conn.execute(
        text("SELECT report_json FROM reports WHERE case_id = :c ORDER BY version DESC LIMIT 1"),
        {"c": case_id},
    ).scalar()  # fmt: skip
    blocked = override_block(row, report)
    if blocked:
        raise HTTPException(409, blocked)
    current = decision_in_force(conn, case_id)
    if current is None:  # decided cases always have an officer row; guard the odd case anyway
        raise HTTPException(409, "The officer has not decided this case.")
    if body.final_decision == current:
        raise HTTPException(422, f"The decision in force is already {current}.")
    conn.execute(
        text("""INSERT INTO admin_actions (case_id, admin_id, action, previous_decision,
                    final_decision, reason, second_click_at)
                VALUES (:c, :a, 'override', :p, :f, :r, now())"""),
        {"c": case_id, "a": admin.id, "p": current, "f": body.final_decision, "r": reason},
    )  # fmt: skip
    conn.execute(text("UPDATE cases SET updated_at = now() WHERE id = :c"), {"c": case_id})
    write_audit(conn, admin.id, "admin_override", "case", case_id,
                before={"decision": current}, after={"final": body.final_decision})  # fmt: skip
    return {"decision_in_force": body.final_decision}


@router.post("/cases/{case_id}/reassign")
def reassign_case(
    case_id: UUID, body: ReassignIn, admin: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    reason = _checked(body)
    row = _case(conn, case_id)
    if row.status not in REASSIGNABLE:
        raise HTTPException(
            409,
            "Only a case the officer has not decided, and that is not running, can be reassigned.",
        )
    target = conn.execute(
        text("SELECT id, name FROM users WHERE id = :i AND role = 'officer' AND active"),
        {"i": body.officer_id},
    ).first()
    if target is None:
        raise HTTPException(422, "Choose an active loan officer.")
    if target.id == row.created_by:
        raise HTTPException(422, "The case already belongs to this officer.")
    previous = conn.execute(
        text("SELECT name FROM users WHERE id = :i"), {"i": row.created_by}
    ).scalar()
    conn.execute(
        text("UPDATE cases SET created_by = :o, updated_at = now() WHERE id = :c"),
        {"o": target.id, "c": case_id},
    )
    write_audit(conn, admin.id, "case_reassigned", "case", case_id,
                before={"officer": previous}, after={"officer": target.name, "reason": reason})  # fmt: skip
    return {"officer": target.name}


@router.get("/recent-decisions")
def recent_decisions(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    """The cases officers decided most recently, newest first, so the admin can find one to correct."""
    rows = conn.execute(
        text("""SELECT c.id, c.case_no, c.loan_type, c.status, u.name AS officer,
                       o.created_at AS decided_at,
                       EXISTS (SELECT 1 FROM admin_actions a WHERE a.case_id = c.id) AS corrected
                FROM cases c JOIN users u ON u.id = c.created_by
                JOIN LATERAL (SELECT created_at FROM officer_actions WHERE case_id = c.id
                              ORDER BY created_at DESC LIMIT 1) o ON true
                WHERE c.status IN ('confirmed', 'overridden')
                ORDER BY o.created_at DESC LIMIT 10""")
    )  # fmt: skip
    return [{"id": r.id, "case_no": r.case_no, "loan_type": r.loan_type, "status": r.status,
             "officer": r.officer, "decided_at": r.decided_at, "corrected": r.corrected}
            for r in rows]  # fmt: skip


@router.get("/messages")
def sent_messages(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    """Messages officers actually sent (no drafts), newest first. Filtering is done on the screen."""
    rows = conn.execute(
        text("""SELECT o.id, o.case_id, c.case_no, u.id AS officer_id, u.name AS officer,
                       o.recipient_email, o.template, o.subject, o.final_text, o.body, o.sent_at
                FROM outbox o JOIN cases c ON c.id = o.case_id JOIN users u ON u.id = o.sent_by
                WHERE o.status = 'sent' ORDER BY o.sent_at DESC NULLS LAST LIMIT 500""")
    )  # fmt: skip
    return [{
        "id": r.id, "case_id": r.case_id, "case_no": r.case_no, "officer_id": r.officer_id,
        "officer": r.officer, "recipient": display.display_text(r.recipient_email),
        "template": r.template, "template_label": TEMPLATE_LABEL.get(r.template, r.template),
        "subject": r.subject, "text": r.final_text or r.body, "sent_at": r.sent_at,
    } for r in rows]  # fmt: skip
