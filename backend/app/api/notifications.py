"""The in-app inbox: an officer or an admin reads their own notifications (docs/SECURITY.md 12).

A person reaches only their own rows: someone else's id answers 404, as if it did not exist. The
auditor gets 403 on every route (decision 9: counts, charts and tables only). There is no delete in
v1. Rows are written by `app/notifications/inbox.py`, in the transaction of the event itself.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Connection, text

from app.api.deps import User, case_reader, get_conn
from app.notifications import inbox

router = APIRouter(tags=["notifications"])
_COLUMNS = "id, kind, title, body, case_id, case_ref, created_at, read_at"


def _unread(conn: Connection, user: User) -> int:
    return int(conn.execute(
        text("SELECT count(*) FROM notifications WHERE user_id = :u AND read_at IS NULL"),
        {"u": user.id}).scalar_one())  # fmt: skip


def _sweep(conn: Connection, user: User) -> None:
    if user.role == "officer":
        inbox.sweep_expiring_links(conn, user.id)


_FILTER = """user_id = :u AND (NOT :unread OR read_at IS NULL)
             AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
             AND (CAST(:q AS text) IS NULL OR case_ref ILIKE CAST(:q AS text))"""


@router.get("/notifications")
def list_notifications(
    unread: bool = False, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
    group: str | None = None, case: str | None = Query(None, pattern=r"^[A-Za-z0-9-]{1,14}$"),
    user: User = Depends(case_reader), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """`group` keeps one group of kinds (see `groups` in the answer); `case` keeps the notices
    whose case number contains the text. Both are filters on the person's own rows."""
    kinds = None
    if group:
        kinds = inbox.kinds_in(group)
        if kinds is None:
            raise HTTPException(422, "Unknown group.")
    _sweep(conn, user)
    args = {"u": user.id, "unread": unread, "kinds": kinds, "q": f"%{case}%" if case else None}
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS} FROM notifications WHERE {_FILTER}
                 ORDER BY created_at DESC, id LIMIT :l OFFSET :o"""),  # noqa: S608
        {**args, "l": limit, "o": offset},
    ).all()
    total = conn.execute(
        text(f"SELECT count(*) FROM notifications WHERE {_FILTER}"), args
    ).scalar_one()  # noqa: S608
    return {"items": [inbox.row_view(r) for r in rows], "total": total,
            "unread": _unread(conn, user), "limit": limit, "offset": offset,
            "groups": inbox.groups_for(user.role)}  # fmt: skip


@router.get("/notifications/unread-count")
def unread_count(
    user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, int]:  # fmt: skip
    _sweep(conn, user)
    return {"unread": _unread(conn, user)}


@router.post("/notifications/read-all")
def read_all(
    user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, int]:  # fmt: skip
    marked = conn.execute(
        text("UPDATE notifications SET read_at = now() WHERE user_id = :u AND read_at IS NULL"),
        {"u": user.id},
    ).rowcount
    return {"marked": marked, "unread": 0}


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: UUID, user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    row = conn.execute(
        text(f"""UPDATE notifications SET read_at = coalesce(read_at, now())
                 WHERE id = :i AND user_id = :u RETURNING {_COLUMNS}"""),  # noqa: S608
        {"i": notification_id, "u": user.id},
    ).first()
    if row is None:
        raise HTTPException(404, "Notification not found.")
    return inbox.row_view(row)
