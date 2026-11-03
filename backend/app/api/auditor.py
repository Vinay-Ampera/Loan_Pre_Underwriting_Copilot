"""Read-only endpoints for the auditor (SECURITY.md D3). Every route is GET and `auditor_only`;
there is no write here, and the data comes from our own database. Recipient emails, identifiers
and free text are masked on the way out, and nothing here reads or serves a document file.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Connection, text

from app.api import display
from app.api.deps import User, auditor_only, get_conn

router = APIRouter(prefix="/auditor", tags=["auditor"])
BANDS = ("approve", "refer", "reject")


def _rows(conn: Connection, sql: str, **params: Any) -> list[Any]:
    return list(conn.execute(text(sql), params))


@router.get("/summary")
def summary(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> dict[str, int]:
    r = conn.execute(
        text("""SELECT
                  (SELECT count(*) FROM cases) AS cases,
                  (SELECT count(*) FROM cases WHERE status = 'awaiting_confirmation') AS waiting,
                  (SELECT count(*) FROM officer_actions WHERE action = 'confirm') AS confirmed,
                  (SELECT count(*) FROM officer_actions WHERE action = 'override') AS overridden,
                  (SELECT count(*) FROM precedents WHERE status = 'pending') AS pending,
                  (SELECT count(*) FROM precedents WHERE status = 'approved') AS approved,
                  (SELECT count(*) FROM users WHERE active) AS users,
                  (SELECT count(*) FROM outbox WHERE status = 'sent') AS sent,
                  (SELECT count(*) FROM outbox WHERE status = 'failed') AS failed""")
    ).one()
    return {"cases": r.cases, "awaiting_confirmation": r.waiting, "confirmed": r.confirmed,
            "overridden": r.overridden, "pending_precedents": r.pending,
            "approved_precedents": r.approved, "active_users": r.users,
            "messages_sent": r.sent, "messages_failed": r.failed}  # fmt: skip


@router.get("/charts")
def charts(_: User = Depends(auditor_only), conn: Connection = Depends(get_conn)) -> dict[str, Any]:
    """Counts only, built from Postgres at request time. Case-level rows never appear here."""
    by_status = {r.k: r.n for r in _rows(
        conn, "SELECT status AS k, count(*) AS n FROM cases GROUP BY 1")}  # fmt: skip
    by_loan = {r.k: r.n for r in _rows(
        conn, "SELECT loan_type AS k, count(*) AS n FROM cases GROUP BY 1")}  # fmt: skip
    by_band = {r.k: r.n for r in _rows(
        conn, "SELECT band AS k, count(*) AS n FROM cases WHERE band IS NOT NULL GROUP BY 1")}  # fmt: skip
    scores = {r.b: r.n for r in _rows(
        conn, """SELECT least(floor(total_score / 10), 9)::int AS b, count(*) AS n FROM cases
                 WHERE total_score IS NOT NULL GROUP BY 1""")}  # fmt: skip
    actions = _rows(
        conn, """SELECT c.loan_type, o.action, count(*) AS n FROM officer_actions o
                 JOIN cases c ON c.id = o.case_id GROUP BY 1, 2""")  # fmt: skip
    weekly = _rows(
        conn, """SELECT to_char(date_trunc('week', created_at), 'YYYY-MM-DD') AS week, count(*) AS n
                 FROM cases WHERE created_at > now() - interval '12 weeks' GROUP BY 1 ORDER BY 1""")  # fmt: skip
    rules = _rows(
        conn, """SELECT rule_id, kind, count(*) AS n FROM rule_results WHERE NOT passed
                 GROUP BY 1, 2 ORDER BY n DESC, rule_id LIMIT 10""")  # fmt: skip
    return {
        "cases_by_status": by_status,
        "cases_by_loan_type": by_loan,
        "cases_by_band": {b: by_band.get(b, 0) for b in BANDS},
        "score_histogram": [{"from": i * 10, "to": i * 10 + 9 if i < 9 else 100, "count": scores.get(i, 0)}
                            for i in range(10)],
        "officer_actions_by_loan_type": [{"loan_type": r.loan_type, "action": r.action, "count": r.n}
                                         for r in actions],
        "cases_per_week": [{"week": r.week, "count": r.n} for r in weekly],
        "top_failed_rules": [{"rule_id": r.rule_id, "kind": r.kind, "count": r.n} for r in rules],
    }  # fmt: skip


@router.get("/audit-log")
def audit_log(
    action: str | None = None, entity: str | None = None,
    limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0),
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    where = "(CAST(:a AS text) IS NULL OR l.action = :a) AND (CAST(:e AS text) IS NULL OR l.entity = :e)"
    params = {"a": action or None, "e": entity or None}
    rows = _rows(
        conn, f"""SELECT l.at, l.action, l.entity, l.entity_id, l.before, l.after, u.name AS actor,
                         u.role AS actor_role, c.case_no
                  FROM audit_log l LEFT JOIN users u ON u.id = l.actor_id
                  LEFT JOIN cases c ON l.entity = 'case' AND c.id::text = l.entity_id
                  WHERE {where} ORDER BY l.at DESC, l.id LIMIT :n OFFSET :o""",  # noqa: S608
        n=limit, o=offset, **params)  # fmt: skip
    total = conn.execute(
        text(f"SELECT count(*) FROM audit_log l WHERE {where}"),
        params,  # noqa: S608
    ).scalar_one()
    return {"total": total, "rows": [
        {"at": r.at, "action": r.action, "entity": r.entity, "case_no": r.case_no,
         "actor": r.actor or "System", "actor_role": r.actor_role,
         "before": display.scrub_for_auditor(r.before, []), "after": display.scrub_for_auditor(r.after, [])}
        for r in rows
    ]}  # fmt: skip


@router.get("/audit-log/actions")
def audit_actions(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[str]:  # fmt: skip
    return [r.action for r in _rows(conn, "SELECT DISTINCT action FROM audit_log ORDER BY 1")]


@router.get("/users")
def users(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    rows = _rows(conn, """SELECT id, name, email, role, active, created_at, locked_until
                          FROM users ORDER BY role, lower(name)""")  # fmt: skip
    return [{"id": r.id, "name": r.name, "email": display.display_text(r.email), "role": r.role,
             "active": r.active, "created_at": r.created_at, "locked": r.locked_until is not None}
            for r in rows]  # fmt: skip


@router.get("/precedents")
def precedents(
    status: str = "all", _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    rows = _rows(
        conn, """SELECT p.id, p.status, p.loan_type, p.rule_ids, p.original_score,
                        p.original_recommendation, p.final_decision, p.officer_reason,
                        p.report_summary, p.created_at, p.reviewed_at, p.valid_until, c.case_no,
                        pu.name AS proposed_by, ru.name AS reviewed_by
                 FROM precedents p LEFT JOIN cases c ON c.id = p.source_case_id
                 JOIN users pu ON pu.id = p.proposed_by LEFT JOIN users ru ON ru.id = p.reviewed_by
                 WHERE (:s = 'all' OR p.status = :s) ORDER BY p.created_at DESC LIMIT 200""", s=status)  # fmt: skip
    return [{
        "id": r.id, "status": r.status, "case_no": r.case_no, "loan_type": r.loan_type,
        "rule_ids": list(r.rule_ids),
        "original_score": None if r.original_score is None else float(r.original_score),
        "original_recommendation": r.original_recommendation, "final_decision": r.final_decision,
        "officer_reason": display.display_text(r.officer_reason or ""),
        "report_summary": display.display_text(r.report_summary or ""),
        "proposed_by": r.proposed_by, "reviewed_by": r.reviewed_by, "created_at": r.created_at,
        "reviewed_at": r.reviewed_at, "valid_until": r.valid_until,
    } for r in rows]  # fmt: skip


@router.get("/messages")
def messages(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    """Officers' customer messages, read-only, recipient masked."""
    rows = _rows(
        conn, """SELECT o.id, c.case_no, u.name AS officer, o.recipient_email, o.template, o.subject,
                        o.body, o.final_text, o.status, o.block_reason, o.error, o.created_at, o.sent_at
                 FROM outbox o JOIN cases c ON c.id = o.case_id JOIN users u ON u.id = o.sent_by
                 ORDER BY o.created_at DESC LIMIT 200""")  # fmt: skip
    return [{
        "id": r.id, "case_no": r.case_no, "officer": r.officer,
        "recipient": display.display_text(r.recipient_email), "template": r.template,
        "subject": r.subject, "text": display.display_text(r.final_text or r.body),
        "status": r.status, "block_reason": r.block_reason, "error": r.error,
        "created_at": r.created_at, "sent_at": r.sent_at,
    } for r in rows]  # fmt: skip
