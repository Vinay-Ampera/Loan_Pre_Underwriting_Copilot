"""Issue reports (Stage 9): an officer tells the admin about a problem with the tool.

Only a case reference (plain text, not a link), a category and short text. The same personal-data
patterns the customer-message check uses (PAN, Aadhaar, phone, account number, email) block the
report, so the admin inbox never receives personal data and never joins to case data. An officer
sees only their own reports; the admin sees all of them.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text

from app.api.deps import User, admin_only, get_conn, officer_only, write_audit
from app.api.schemas import IssueIn
from app.notifications.check import check_issue_text

router = APIRouter(tags=["issues"])
_COLUMNS = "i.id, i.case_ref, i.category, i.body, i.status, i.created_at, i.read_at, i.closed_at"


def _row(r: Any) -> dict[str, Any]:
    return {"id": r.id, "case_ref": r.case_ref, "category": r.category, "body": r.body,
            "status": r.status, "created_at": r.created_at, "read_at": r.read_at,
            "closed_at": r.closed_at}  # fmt: skip


@router.post("/issues", status_code=201)
def file_issue(
    body: IssueIn, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> Any:  # fmt: skip
    reasons = check_issue_text(body.body)
    if reasons:  # nothing is stored; the refusal itself is audited without the text
        write_audit(conn, user.id, "issue_blocked", "issue", None, after={"reasons": reasons})
        return JSONResponse({"detail": "Not sent: " + "; ".join(reasons).lower()
                             + ". Remove personal details and try again."}, 422)  # fmt: skip
    r = conn.execute(
        text(f"""INSERT INTO issue_reports AS i (reported_by, case_ref, category, body)
                 VALUES (:u, :c, :k, :b) RETURNING {_COLUMNS}"""),  # noqa: S608
        {"u": user.id, "c": body.case_ref, "k": body.category, "b": body.body},
    ).one()
    write_audit(conn, user.id, "issue_filed", "issue", r.id, after={"category": body.category})
    return _row(r)


@router.get("/issues")
def my_issues(
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS} FROM issue_reports i WHERE i.reported_by = :u
                 ORDER BY i.created_at DESC LIMIT 100"""),
        {"u": user.id},
    )  # noqa: S608
    return [_row(r) for r in rows]


# --------------------------------------------------------------------------- admin inbox
@router.get("/admin/issues")
def inbox(
    status: str | None = None, _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    if status not in (None, "open", "read", "closed"):
        raise HTTPException(422, "Unknown status.")
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS}, u.name AS reporter FROM issue_reports i
                 JOIN users u ON u.id = i.reported_by
                 WHERE (CAST(:s AS text) IS NULL OR i.status = :s)
                 ORDER BY (i.status = 'closed'), i.created_at DESC LIMIT 200"""),  # noqa: S608
        {"s": status},
    )
    return [{**_row(r), "reporter": r.reporter} for r in rows]


def _issue(conn: Connection, issue_id: UUID) -> Any:
    row = conn.execute(
        text(f"""SELECT {_COLUMNS}, u.name AS reporter FROM issue_reports i
                 JOIN users u ON u.id = i.reported_by WHERE i.id = :i FOR UPDATE OF i"""),  # noqa: S608
        {"i": issue_id},
    ).first()
    if row is None:
        raise HTTPException(404, "Issue not found.")
    return row


@router.post("/admin/issues/{issue_id}/read")
def read_issue(
    issue_id: UUID, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    """Opening an issue marks it read (once)."""
    row = _issue(conn, issue_id)
    if row.status == "open":
        conn.execute(text("UPDATE issue_reports SET status = 'read', read_at = now() WHERE id = :i"),
                     {"i": issue_id})  # fmt: skip
        write_audit(conn, admin.id, "issue_read", "issue", issue_id)
        row = _issue(conn, issue_id)
    return {**_row(row), "reporter": row.reporter}


@router.post("/admin/issues/{issue_id}/close")
def close_issue(
    issue_id: UUID, admin: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    row = _issue(conn, issue_id)
    if row.status != "closed":
        conn.execute(
            text("""UPDATE issue_reports SET status = 'closed', closed_at = now(),
                        read_at = COALESCE(read_at, now()) WHERE id = :i"""),
            {"i": issue_id},
        )
        write_audit(conn, admin.id, "issue_closed", "issue", issue_id)
        row = _issue(conn, issue_id)
    return {**_row(row), "reporter": row.reporter}
