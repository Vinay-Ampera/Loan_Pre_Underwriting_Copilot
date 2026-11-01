"""Admin endpoints: the precedent queue. Only admin accounts reach these (403 for officers).

A precedent reaches this queue as `pending` only after the code-side hard-rule check; `held` rows
never get here and cannot be approved. Approving stores the embedding, the reviewer, the review
time and an expiry date (the database refuses an approved row without all four).
"""

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import Connection, text

from app.api.deps import User, admin_only, get_conn, write_audit
from app.api.schemas import PrecedentApproveIn, PrecedentRejectIn
from app.rag.precedents import precedent_text
from app.scoring.rules import RuleSet

router = APIRouter(prefix="/admin", tags=["admin"])
STATUSES = ("pending", "held", "approved", "rejected", "expired")


def _latest(ruleset: RuleSet) -> date:
    return date.today() + timedelta(days=30 * ruleset.precedent.valid_months)


def _card(conn: Connection, r: Any, latest: date) -> dict[str, Any]:
    similar = conn.execute(
        text("""SELECT id, report_summary, final_decision, valid_until,
                       (SELECT count(*) FROM unnest(rule_ids) x WHERE x = ANY(:ids)) AS shared
                FROM precedents
                WHERE status = 'approved' AND loan_type = :lt AND id <> :i AND rule_ids && :ids
                ORDER BY shared DESC, created_at DESC LIMIT 3"""),
        {"ids": list(r.rule_ids), "lt": r.loan_type, "i": r.id},
    )  # fmt: skip
    return {
        "id": r.id, "max_valid_until": latest, "status": r.status, "case_no": r.case_no,
        "loan_type": r.loan_type,
        "rule_ids": list(r.rule_ids),
        "original_score": None if r.original_score is None else float(r.original_score),
        "original_recommendation": r.original_recommendation, "final_decision": r.final_decision,
        "officer_reason": r.officer_reason, "report_summary": r.report_summary,
        "proposed_by": r.proposed_by_name, "created_at": r.created_at, "reviewed_by": r.reviewed_by_name,
        "reviewed_at": r.reviewed_at, "valid_until": r.valid_until,
        "similar": [{"id": s.id, "summary": s.report_summary, "final_decision": s.final_decision,
                     "valid_until": s.valid_until, "shared_rules": s.shared} for s in similar],
    }  # fmt: skip


_SELECT = """SELECT p.*, c.case_no, pu.name AS proposed_by_name, ru.name AS reviewed_by_name
             FROM precedents p LEFT JOIN cases c ON c.id = p.source_case_id
             JOIN users pu ON pu.id = p.proposed_by LEFT JOIN users ru ON ru.id = p.reviewed_by"""


@router.get("/precedents")
def list_precedents(
    request: Request,
    status: str = "pending",
    _: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> list[dict[str, Any]]:  # fmt: skip
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, "Unknown status.")
    rows = conn.execute(
        text(_SELECT + " WHERE (:s = 'all' OR p.status = :s) ORDER BY p.created_at DESC LIMIT 200"),
        {"s": status},
    ).all()  # fmt: skip
    latest = _latest(request.app.state.ruleset)
    return [_card(conn, r, latest) for r in rows]


def _pending(conn: Connection, precedent_id: UUID) -> Any:
    row = conn.execute(
        text(_SELECT + " WHERE p.id = :i FOR UPDATE OF p"), {"i": precedent_id}
    ).first()
    if row is None:
        raise HTTPException(404, "Precedent not found.")
    if row.status != "pending":
        raise HTTPException(409, f"This precedent is {row.status}, not pending.")
    return row


@router.post("/precedents/{precedent_id}/approve")
def approve_precedent(
    precedent_id: UUID, body: PrecedentApproveIn, request: Request,
    user: User = Depends(admin_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    row = _pending(conn, precedent_id)
    ruleset: RuleSet = request.app.state.ruleset
    today = date.today()
    latest = _latest(ruleset)
    valid_until = body.valid_until or latest
    if not today < valid_until <= latest:
        raise HTTPException(422, f"Choose an expiry date after today and no later than {latest}.")
    vector = request.app.state.embed([precedent_text(row.loan_type, row.rule_ids, "refer")])[0]
    conn.execute(
        text("""UPDATE precedents SET status = 'approved', reviewed_by = :u, reviewed_at = now(),
                    valid_until = :v, embedding = CAST(:e AS vector) WHERE id = :i"""),
        {"u": user.id, "v": valid_until, "e": str(vector), "i": precedent_id},
    )  # fmt: skip
    write_audit(conn, user.id, "precedent_approved", "precedent", precedent_id,
                before={"status": "pending"}, after={"status": "approved", "valid_until": valid_until})  # fmt: skip
    return {"id": precedent_id, "status": "approved", "valid_until": valid_until}


@router.post("/precedents/{precedent_id}/reject")
def reject_precedent(
    precedent_id: UUID, body: PrecedentRejectIn, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    _pending(conn, precedent_id)
    conn.execute(
        text("UPDATE precedents SET status = 'rejected', reviewed_by = :u, reviewed_at = now() WHERE id = :i"),
        {"u": user.id, "i": precedent_id},
    )  # fmt: skip
    write_audit(conn, user.id, "precedent_rejected", "precedent", precedent_id,
                before={"status": "pending"}, after={"status": "rejected", "note": body.note})  # fmt: skip
    return {"id": precedent_id, "status": "rejected"}
