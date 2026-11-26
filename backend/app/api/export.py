"""Queue export as CSV (Stage 12 Part C, SECURITY.md 4j, EDGE_CASES E-119).

- `GET /cases/export.csv`: an officer's own cases, with the queue's filters (status, loan type,
  search, view and due state).
- `GET /admin/cases/export.csv`: the admin, every case, the same filters plus an officer.

No applicant name, PAN, phone, email, address or amount is written: the case reference is enough.
A search may match an applicant's name on the server, but the name never reaches the file. Cells
a spreadsheet would run as a formula are written as text (`auditlog._cell`) and the file starts
with a byte-order mark so Excel reads it as UTF-8. Every download writes one `cases_exported`
audit row with the filters and the row count. Mounted before the cases router, so
`/cases/export.csv` is never read as a case id.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import Connection, text

from app.api import auditlog
from app.api.deps import User, admin_only, get_conn, officer_only, write_audit
from app.workflow import sla

router = APIRouter(tags=["export"])
LoanType = Literal["personal", "home", "education", "business", "vehicle"]
Due = Literal["due_today", "overdue"]
View = Literal["awaiting", "referred", "stopped", "progress", "applicant", "corrected"]

# the queue's views (frontend lib/views.js), as SQL
VIEW_SQL: dict[str, str] = {
    "awaiting": "c.status = 'awaiting_confirmation'",
    "referred": "c.status = 'awaiting_confirmation' AND c.band = 'refer'",
    "stopped": "c.status = 'stopped'",
    "progress": "c.status IN ('draft', 'uploaded', 'running')",
    "applicant": "COALESCE(c.form_data ->> 'origin', 'officer') = 'applicant' "
                 "AND c.status = 'applicant_submitted'",
    "corrected": "EXISTS (SELECT 1 FROM admin_actions x WHERE x.case_id = c.id)",
}  # fmt: skip
STATUS = {
    "draft": "Draft", "uploaded": "Documents uploaded", "applicant_submitted": "Applicant submitted",
    "running": "Assessing", "stopped": "Stopped: needs correction",
    "awaiting_confirmation": "Awaiting confirmation", "confirmed": "Confirmed by the officer",
    "overridden": "Changed by the officer",
}  # fmt: skip
HEADER = ["Case reference", "Loan type", "Status", "Recommended band", "Score", "Officer",
          "Created", "Updated", "Officer decision", "Decision due", "Overdue"]  # fmt: skip


def _rows(conn: Connection, tz: str, *, officer: UUID | None, status: str | None,
          loan_type: str | None, q: str | None, view: str | None, due: str | None) -> list[Any]:  # fmt: skip
    state = sla.due_state_sql()
    when = "to_char({} AT TIME ZONE :sla_tz, 'YYYY-MM-DD HH24:MI')"
    sql = f"""
        SELECT c.case_no, c.loan_type, c.status, c.band, c.total_score, u.name AS officer,
               {when.format("c.created_at")} AS created, {when.format("c.updated_at")} AS updated,
               (SELECT o.final_decision FROM officer_actions o WHERE o.case_id = c.id
                 ORDER BY o.created_at LIMIT 1) AS decision,
               CASE WHEN c.status = 'awaiting_confirmation' AND c.sla_due_at IS NOT NULL
                    THEN {when.format("c.sla_due_at")} END AS due,
               {state} AS due_state
          FROM cases c JOIN users u ON u.id = c.created_by
         WHERE (CAST(:officer AS uuid) IS NULL OR c.created_by = CAST(:officer AS uuid))
           AND (CAST(:st AS text) IS NULL OR c.status = CAST(:st AS text))
           AND (CAST(:lt AS text) IS NULL OR c.loan_type = CAST(:lt AS text))
           AND (CAST(:q AS text) IS NULL OR c.case_no ILIKE '%' || CAST(:q AS text) || '%'
                OR EXISTS (SELECT 1 FROM applicants a WHERE a.case_id = c.id
                           AND a.full_name ILIKE '%' || CAST(:q AS text) || '%'))
           AND {VIEW_SQL[view] if view else "true"}
           AND (CAST(:due AS text) IS NULL OR {state} = CAST(:due AS text))
         ORDER BY c.updated_at DESC"""
    params = {"officer": officer, "st": status, "lt": loan_type, "q": (q or "").strip() or None,
              "due": due, "sla_tz": tz}  # fmt: skip
    return list(conn.execute(text(sql), params))


def _csv(request: Request, conn: Connection, user: User, filters: dict[str, Any],
         officer: UUID | None) -> Response:  # fmt: skip
    tz = request.app.state.settings.sla_timezone
    rows = _rows(conn, tz, officer=officer, **filters)
    write_audit(conn, user.id, "cases_exported", "case", None,
                after={"filters": {k: v for k, v in filters.items() if v},
                       "officer": str(officer) if officer and user.role == "admin" else None,
                       "rows": len(rows)})  # fmt: skip
    today = datetime.now(UTC).astimezone(sla.SlaConfig(timezone=tz).tz).date().isoformat()
    return auditlog.csv_response(
        f"pramaan-cases-{today}.csv", HEADER,
        [[r.case_no, r.loan_type, STATUS.get(r.status, r.status), r.band or "",
          "" if r.total_score is None else f"{float(r.total_score):g}", r.officer, r.created,
          r.updated, r.decision or "", r.due or "",
          "" if r.due is None else ("yes" if r.due_state == "overdue" else "no")] for r in rows],
        bom=True,
    )  # fmt: skip


@router.get("/cases/export.csv")
def export_own_cases(
    request: Request, status: str | None = None, loan_type: LoanType | None = None,
    q: str | None = None, view: View | None = None, due: Due | None = None,
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
) -> Response:  # fmt: skip
    filters = {"status": status or None, "loan_type": loan_type, "q": q, "view": view, "due": due}
    return _csv(request, conn, user, filters, officer=user.id)


@router.get("/admin/cases/export.csv")
def export_all_cases(
    request: Request, status: str | None = None, loan_type: LoanType | None = None,
    q: str | None = None, view: View | None = None, due: Due | None = None,
    officer: UUID | None = None, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> Response:  # fmt: skip
    filters = {"status": status or None, "loan_type": loan_type, "q": q, "view": view, "due": due}
    return _csv(request, conn, user, filters, officer=officer)
