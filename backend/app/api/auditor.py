"""Read-only endpoints for the auditor (SECURITY.md D3). Every route is GET and `auditor_only`;
there is no write here, and the data comes from our own database. The auditor sees counts, charts
and static tables (one row per case with no applicant, document or report content), the audit
log with identifiers masked, and the staff list. There is no case page, no document and no
message text. The auditor does not care what a loan is, only how many cases are in which state.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Connection, text

from app.api import auditlog
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
                  (SELECT count(DISTINCT case_id) FROM admin_actions) AS corrected,
                  (SELECT count(*) FROM users WHERE active) AS users""")
    ).one()
    return {"cases": r.cases, "awaiting_confirmation": r.waiting, "confirmed": r.confirmed,
            "overridden": r.overridden, "admin_corrected": r.corrected,
            "active_users": r.users}  # fmt: skip


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
    per_officer = _rows(
        conn, """SELECT u.name, count(c.id) AS n FROM cases c JOIN users u ON u.id = c.created_by
                 GROUP BY u.name ORDER BY n DESC, u.name LIMIT 20""")  # fmt: skip
    return {
        "cases_by_status": by_status,
        "cases_by_loan_type": by_loan,
        "cases_by_band": {b: by_band.get(b, 0) for b in BANDS},
        "score_histogram": [{"from": i * 10, "to": i * 10 + 9 if i < 9 else 100, "count": scores.get(i, 0)}
                            for i in range(10)],
        "officer_actions_by_loan_type": [{"loan_type": r.loan_type, "action": r.action, "count": r.n}
                                         for r in actions],
        "cases_per_week": [{"week": r.week, "count": r.n} for r in weekly],
        "cases_per_officer": [{"officer": r.name, "count": r.n} for r in per_officer],
        "top_failed_rules": [{"rule_id": r.rule_id, "kind": r.kind, "count": r.n} for r in rules],
    }  # fmt: skip


_CASE_WHERE = """(CAST(:st AS text) IS NULL OR c.status = :st)
                 AND (CAST(:lt AS text) IS NULL OR c.loan_type = :lt)
                 AND (CAST(:bd AS text) IS NULL OR c.band = :bd)
                 AND (CAST(:of AS uuid) IS NULL OR c.created_by = CAST(:of AS uuid))
                 AND (CAST(:q AS text) IS NULL OR c.case_no ILIKE '%' || :q || '%')
                 AND (CAST(:ov AS text) IS NULL
                      OR (:ov = 'officer' AND EXISTS (SELECT 1 FROM officer_actions o
                                                      WHERE o.case_id = c.id AND o.action = 'override'))
                      OR (:ov = 'admin' AND EXISTS (SELECT 1 FROM admin_actions a WHERE a.case_id = c.id)))
                 AND (CAST(:f AS date) IS NULL OR c.created_at >= CAST(:f AS date))
                 AND (CAST(:t AS date) IS NULL OR c.created_at < CAST(:t AS date) + 1)"""

_CASE_COLUMNS = """c.case_no, c.loan_type, u.name AS officer, c.status, c.band, c.total_score,
        (SELECT o.action FROM officer_actions o WHERE o.case_id = c.id
          ORDER BY o.created_at DESC LIMIT 1) AS officer_decision,
        EXISTS (SELECT 1 FROM admin_actions a WHERE a.case_id = c.id) AS admin_corrected,
        c.created_at, c.updated_at"""


def _case_rows(
    conn: Connection, *, status: str | None, loan_type: str | None, band: str | None,
    officer: str | None, q: str | None, overridden: str | None, date_from: date | None,
    date_to: date | None, limit: int, offset: int,
) -> dict[str, Any]:  # fmt: skip
    p = {"st": status or None, "lt": loan_type or None, "bd": band or None, "of": officer or None,
         "q": (q or "").strip() or None, "ov": overridden or None, "f": date_from, "t": date_to}  # fmt: skip
    rows = _rows(
        conn, f"""SELECT {_CASE_COLUMNS} FROM cases c JOIN users u ON u.id = c.created_by
                  WHERE {_CASE_WHERE} ORDER BY c.updated_at DESC, c.case_no LIMIT :n OFFSET :o""",  # noqa: S608
        n=limit, o=offset, **p)  # fmt: skip
    total = conn.execute(
        text(f"SELECT count(*) FROM cases c WHERE {_CASE_WHERE}"),
        p,  # noqa: S608
    ).scalar_one()
    return {"total": total, "rows": [
        {"case_no": r.case_no, "loan_type": r.loan_type, "officer": r.officer, "status": r.status,
         "band": r.band, "score": None if r.total_score is None else float(r.total_score),
         "officer_decision": r.officer_decision, "admin_corrected": r.admin_corrected,
         "created_at": r.created_at, "updated_at": r.updated_at} for r in rows]}  # fmt: skip


@router.get("/cases")
def cases(
    status: str | None = None, loan_type: str | None = None, band: str | None = None,
    officer: str | None = None, q: str | None = None, overridden: str | None = Query(None, pattern="^(officer|admin)$"),
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """One row per case with no applicant, document or report content: a static table."""
    return _case_rows(conn, status=status, loan_type=loan_type, band=band, officer=officer, q=q,
                      overridden=overridden, date_from=date_from, date_to=date_to,
                      limit=limit, offset=offset)  # fmt: skip


@router.get("/cases.csv")
def cases_csv(
    status: str | None = None, loan_type: str | None = None, band: str | None = None,
    officer: str | None = None, q: str | None = None, overridden: str | None = Query(None, pattern="^(officer|admin)$"),
    date_from: date | None = None, date_to: date | None = None,
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> Response:  # fmt: skip
    res = _case_rows(conn, status=status, loan_type=loan_type, band=band, officer=officer, q=q,
                     overridden=overridden, date_from=date_from, date_to=date_to,
                     limit=auditlog.CSV_LIMIT, offset=0)  # fmt: skip
    return auditlog.csv_response(
        "cases.csv",
        ["Case", "Loan type", "Officer", "Status", "Band", "Score", "Officer decision",
         "Admin corrected", "Created", "Updated"],
        [[r["case_no"], r["loan_type"], r["officer"], r["status"], r["band"], r["score"],
          r["officer_decision"], "yes" if r["admin_corrected"] else "no", r["created_at"],
          r["updated_at"]] for r in res["rows"]],
    )  # fmt: skip


@router.get("/audit-log")
def audit_log(
    action: str | None = None, entity: str | None = None, actor: str | None = None,
    case_no: str | None = None, date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    return auditlog.query(conn, auditor=True, action=action, entity=entity, actor=actor,
                          case_no=case_no, date_from=date_from, date_to=date_to,
                          limit=limit, offset=offset)  # fmt: skip


@router.get("/audit-log/actions")
def audit_actions(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[str]:  # fmt: skip
    return auditlog.actions(conn)


@router.get("/audit-log.csv")
def audit_log_csv(
    action: str | None = None, entity: str | None = None, actor: str | None = None,
    case_no: str | None = None, date_from: date | None = None, date_to: date | None = None,
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> Response:  # fmt: skip
    result = auditlog.query(conn, auditor=True, action=action, entity=entity, actor=actor,
                            case_no=case_no, date_from=date_from, date_to=date_to,
                            limit=auditlog.CSV_LIMIT)  # fmt: skip
    return auditlog.log_csv(result, "audit-log.csv")


@router.get("/users")
def users(
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    """Name, role, status and last sign-in. No email, no actions."""
    rows = _rows(conn, """SELECT u.id, u.name, u.role, u.active, u.locked_until,
                                 (SELECT max(at) FROM audit_log l
                                   WHERE l.actor_id = u.id AND l.action = 'login') AS last_login
                          FROM users u ORDER BY u.role, lower(u.name)""")  # fmt: skip
    return [{"id": r.id, "name": r.name, "role": r.role, "active": r.active,
             "locked": r.locked_until is not None, "last_login": r.last_login}
            for r in rows]  # fmt: skip
