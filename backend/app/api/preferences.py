"""A person's own settings (Notifications Part 2): for now, whether to get "you have a new notice"
emails. Officers and admins only; the auditor has no inbox and gets 403. Account emails (created,
password reset) are not optional: they tell a person something happened to their account.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, text

from app.api.deps import User, case_reader, get_conn, write_audit

router = APIRouter(tags=["preferences"])


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notice_emails: bool


@router.get("/me/preferences")
def my_preferences(
    user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    on = conn.execute(
        text("SELECT notice_emails FROM users WHERE id = :u"), {"u": user.id}
    ).scalar_one()
    return {"notice_emails": on}


@router.put("/me/preferences")
def set_preferences(
    body: PreferencesIn, user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    before = conn.execute(
        text("SELECT notice_emails FROM users WHERE id = :u FOR UPDATE"), {"u": user.id}
    ).scalar_one()
    if before != body.notice_emails:
        conn.execute(text("UPDATE users SET notice_emails = :n, updated_at = now() WHERE id = :u"),
                     {"n": body.notice_emails, "u": user.id})  # fmt: skip
        write_audit(conn, user.id, "notice_emails_changed", "user", user.id,
                    before={"notice_emails": before}, after={"notice_emails": body.notice_emails})  # fmt: skip
    return {"notice_emails": body.notice_emails}
