"""Customer contact messages (Stage 9). Officer-only, and only the officer's own cases and rows:
another officer's case or message is a 404, an admin gets 403 (the admin sees counts in the
summary and nothing else). A message carries no case data by design; the server composes the
final text (body, optional case reference, contact lines, fixed fraud footer), runs the content
check on every create, edit and send, and sends only after a second confirming click.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.api import display
from app.api.cases import get_case
from app.api.deps import User, get_conn, get_settings_dep, officer_only, write_audit
from app.api.links import hash_token
from app.api.schemas import MessageEditIn, MessageIn, MessageSendIn
from app.core.config import Settings
from app.notifications import templates
from app.notifications.check import check_link_line, check_message
from app.notifications.sender import Outgoing, Sender, SendError

router = APIRouter(tags=["messages"])
SENDABLE = ("confirmed", "overridden", "stopped")
LINK_SENDABLE = ("draft", "uploaded", "applicant_submitted")  # the upload link goes out early
_COLUMNS = """o.id, o.case_id, c.case_no, o.sent_by, o.recipient_email, o.template, o.subject,
              o.body, o.final_text, o.case_ref_included, o.status, o.block_reason, o.error,
              o.created_at, o.sent_at, o.link_id"""


class PhoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    phone: str | None = Field(default=None, pattern=r"^[6-9][0-9]{9}$")


# --------------------------------------------------------------------------- helpers
def _sender(request: Request) -> Sender:
    sender: Sender = request.app.state.sender
    return sender


def _contact(conn: Connection, user: User, settings: Settings) -> list[str]:
    phone = conn.execute(text("SELECT phone FROM users WHERE id = :i"), {"i": user.id}).scalar()
    return templates.contact_lines(user.name, user.email, phone,
                                   branch_email=settings.branch_contact_email,
                                   branch_phone=settings.branch_contact_phone)  # fmt: skip


def _names(conn: Connection, case_id: UUID) -> list[str]:
    rows = conn.execute(text("SELECT full_name FROM applicants WHERE case_id = :c"), {"c": case_id})
    return [r.full_name for r in rows]


def _primary_email(conn: Connection, case_id: UUID) -> str | None:
    return conn.execute(
        text("SELECT email FROM applicants WHERE case_id = :c AND role = 'primary'"), {"c": case_id}
    ).scalar()


LINK_PLACEHOLDER = "[your secure upload link]"  # what is kept and previewed; the token never is


def _subject(template: str) -> str:
    return templates.LINK_SUBJECT if template == "upload_link" else templates.SUBJECT


def _final(body: str, contact: list[str], case_no: str, include_ref: bool,
           link: str | None = None) -> str:  # fmt: skip
    return templates.compose(body, contact, case_no if include_ref else None, link)


def _problems(conn: Connection, case_id: UUID, body: str, final_text: str,
              template: str = "blank", link: str | None = None) -> list[str]:  # fmt: skip
    reasons = check_message(_subject(template), body, final_text=final_text,
                            names=_names(conn, case_id))  # fmt: skip
    return [*reasons, *check_link_line(final_text, link)]


def _link_url(conn: Connection, link_id: UUID | None, token: str | None, case_id: UUID,
              user: User, settings: Settings) -> str:  # fmt: skip
    """The full address for an upload-link message, after checking the token belongs to a live
    link of this officer that is bound to this case. The token is not stored anywhere."""
    row = conn.execute(
        text("""SELECT token_hash FROM upload_links WHERE id = :i AND officer_id = :u
                AND case_id = :c AND disabled_at IS NULL AND expires_at > now()"""),
        {"i": link_id, "u": user.id, "c": case_id}).first()  # fmt: skip
    if row is None or not token or hash_token(token) != row.token_hash:
        raise HTTPException(
            422, "This upload link cannot be used. Create a new link and try again."
        )
    return f"{settings.public_base_url.rstrip('/')}/u#{token}"


def _view(row: Any, preview: str) -> dict[str, Any]:
    return {
        "id": row.id, "case_id": row.case_id, "case_no": row.case_no, "template": row.template,
        "template_label": templates.TEMPLATES[row.template].label,
        "recipient": display.display_text(row.recipient_email), "subject": row.subject,
        "body": row.body, "text": row.final_text or preview, "case_ref_included": row.case_ref_included,
        "status": row.status, "block_reason": row.block_reason, "error": row.error,
        "created_at": row.created_at, "sent_at": row.sent_at,
    }  # fmt: skip


def _load(conn: Connection, message_id: UUID, user: User, *, lock: bool = False) -> Any:
    row = conn.execute(
        text(
            f"""SELECT {_COLUMNS} FROM outbox o JOIN cases c ON c.id = o.case_id
                 WHERE o.id = :i AND o.sent_by = :u"""
            + (" FOR UPDATE OF o" if lock else "")
        ),  # noqa: S608
        {"i": message_id, "u": user.id},
    ).first()
    if row is None:  # not yours looks the same as not there
        raise HTTPException(404, "Message not found.")
    return row


def _view_row(conn: Connection, row: Any, user: User, settings: Settings) -> dict[str, Any]:
    link = LINK_PLACEHOLDER if row.template == "upload_link" else None
    preview = _final(row.body, _contact(conn, user, settings), row.case_no,
                     row.case_ref_included, link)  # fmt: skip
    return _view(row, preview)


def _write_state(conn: Connection, message_id: UUID, status: str, *, reason: str | None = None,
                 error: str | None = None, final_text: str | None = None) -> None:  # fmt: skip
    conn.execute(
        text("""UPDATE outbox SET status = :s, block_reason = :r, error = :e,
                    final_text = COALESCE(:f, final_text), updated_at = now(),
                    sent_at = CASE WHEN :s = 'sent' THEN now() ELSE sent_at END
                WHERE id = :i"""),
        {"s": status, "r": reason, "e": error, "f": final_text, "i": message_id},
    )


# --------------------------------------------------------------------------- templates, profile
@router.get("/messages/templates")
def message_templates(
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    phone = conn.execute(text("SELECT phone FROM users WHERE id = :i"), {"i": user.id}).scalar()
    return {
        "subject": templates.SUBJECT, "link_subject": templates.LINK_SUBJECT, "footer": templates.FOOTER, "max_body": templates.MAX_BODY,
        "contact": _contact(conn, user, settings), "phone_set": bool(phone),
        "templates": [{"code": t.code, "label": t.label, "body": t.body}
                      for t in templates.TEMPLATES.values()],
    }  # fmt: skip


@router.put("/profile/phone")
def set_phone(
    body: PhoneIn, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    conn.execute(text("UPDATE users SET phone = :p, updated_at = now() WHERE id = :i"),
                 {"p": body.phone, "i": user.id})  # fmt: skip
    write_audit(conn, user.id, "user_phone_changed", "user", user.id,
                after={"phone_set": body.phone is not None})  # fmt: skip
    return {"phone_set": body.phone is not None}


# --------------------------------------------------------------------------- draft, edit
@router.post("/cases/{case_id}/messages", status_code=201)
def create_draft(
    case_id: UUID, body: MessageIn, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    case = get_case(conn, case_id, user)
    is_link = body.template == "upload_link"
    if case.status not in (LINK_SENDABLE if is_link else SENDABLE):
        raise HTTPException(409, "A message can be drafted after the case is confirmed, "
                                 "overridden or stopped.")  # fmt: skip
    if is_link:
        _link_url(conn, body.link_id, body.link_token, case_id, user, settings)  # checked, not kept
    elif body.link_id or body.link_token:
        raise HTTPException(422, "Only the upload-link message carries a link.")
    recipient = body.recipient_email or _primary_email(conn, case_id)
    if not recipient:
        raise HTTPException(422, "There is no customer email on this case. Enter one to continue.")
    text_body = body.body if body.body is not None else templates.TEMPLATES[body.template].body
    contact = _contact(conn, user, settings)
    final = _final(text_body, contact, case.case_no, body.include_case_ref,
                   LINK_PLACEHOLDER if is_link else None)  # fmt: skip
    reasons = _problems(conn, case_id, text_body, final, body.template)
    status = "blocked" if reasons else "draft"
    message_id = conn.execute(
        text("""INSERT INTO outbox (case_id, sent_by, recipient_email, template, subject, body,
                    case_ref_included, status, block_reason, link_id)
                VALUES (:c, :u, :r, :t, :s, :b, :ref, :st, :why, :link) RETURNING id"""),
        {"c": case_id, "u": user.id, "r": recipient, "t": body.template, "s": _subject(body.template),
         "b": text_body, "ref": body.include_case_ref, "st": status,
         "why": "; ".join(reasons) or None, "link": body.link_id if is_link else None},
    ).scalar_one()  # fmt: skip
    write_audit(conn, user.id, "message_drafted", "message", message_id,
                after={"template": body.template, "status": status})  # fmt: skip
    if reasons:
        write_audit(conn, user.id, "message_blocked", "message", message_id,
                    after={"reasons": reasons})  # fmt: skip
    return _view_row(conn, _load(conn, message_id, user), user, settings)


@router.put("/messages/{message_id}")
def edit_draft(
    message_id: UUID, body: MessageEditIn, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    row = _load(conn, message_id, user, lock=True)
    if row.status == "sent":
        raise HTTPException(409, "This message has been sent and cannot be changed.")
    contact = _contact(conn, user, settings)
    link = LINK_PLACEHOLDER if row.template == "upload_link" else None
    final = _final(body.body, contact, row.case_no, body.include_case_ref, link)
    reasons = _problems(conn, row.case_id, body.body, final, row.template)
    conn.execute(
        text("""UPDATE outbox SET body = :b, case_ref_included = :ref,
                    recipient_email = COALESCE(:r, recipient_email), error = NULL,
                    final_text = NULL WHERE id = :i"""),
        {"b": body.body, "ref": body.include_case_ref, "r": body.recipient_email, "i": message_id},
    )
    _write_state(
        conn, message_id, "blocked" if reasons else "draft", reason="; ".join(reasons) or None
    )
    write_audit(conn, user.id, "message_edited", "message", message_id,
                after={"status": "blocked" if reasons else "draft"})  # fmt: skip
    if reasons:
        write_audit(conn, user.id, "message_blocked", "message", message_id,
                    after={"reasons": reasons})  # fmt: skip
    return _view_row(conn, _load(conn, message_id, user), user, settings)


@router.delete("/messages/{message_id}", status_code=204)
def delete_draft(
    message_id: UUID, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> None:  # fmt: skip
    """Only an unsent draft or a blocked message can be removed. Sent and failed rows are the
    record of what was (or was tried to be) sent to a customer, so they stay."""
    row = _load(conn, message_id, user, lock=True)
    if row.status not in ("draft", "blocked"):
        raise HTTPException(409, "Only a draft or a blocked message can be deleted.")
    conn.execute(text("DELETE FROM outbox WHERE id = :i"), {"i": message_id})
    write_audit(conn, user.id, "message_deleted", "message", message_id,
                before={"status": row.status, "template": row.template})  # fmt: skip


# --------------------------------------------------------------------------- send
@router.post("/messages/{message_id}/send")
def send_message(
    message_id: UUID, body: MessageSendIn, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> Any:  # fmt: skip
    """The second click. Also the retry of a failed send. Block and failure are returned (not
    raised) so the new status and the audit row are committed."""
    if not body.second_click:
        raise HTTPException(422, "Confirm the final text before sending.")
    row = _load(conn, message_id, user, lock=True)
    if row.status == "sent":
        raise HTTPException(409, "This message has already been sent.")
    contact = _contact(conn, user, settings)
    is_link = row.template == "upload_link"
    url = (
        _link_url(conn, row.link_id, body.link_token, row.case_id, user, settings)
        if is_link
        else None
    )
    final = _final(row.body, contact, row.case_no, row.case_ref_included, url)
    kept = _final(row.body, contact, row.case_no, row.case_ref_included,
                  LINK_PLACEHOLDER if is_link else None)  # what is saved: never the token  # fmt: skip
    reasons = _problems(conn, row.case_id, row.body, final, row.template, url)  # checked again
    if reasons:
        _write_state(conn, message_id, "blocked", reason="; ".join(reasons))
        write_audit(conn, user.id, "message_blocked", "message", message_id,
                    after={"reasons": reasons, "at": "send"})  # fmt: skip
        return JSONResponse({"detail": "Not sent: " + "; ".join(reasons) + ".",
                             "reasons": reasons}, 422)  # fmt: skip
    try:
        _sender(request).send(Outgoing(str(message_id), row.recipient_email, row.subject, final))
    except SendError as exc:
        _write_state(conn, message_id, "failed", error=str(exc)[:300], final_text=kept)
        write_audit(conn, user.id, "message_failed", "message", message_id)
        return JSONResponse({"detail": "The message could not be sent. It is saved as failed; "
                                       "you can retry it from Sent items."}, 502)  # fmt: skip
    _write_state(conn, message_id, "sent", final_text=kept)
    write_audit(conn, user.id, "message_sent", "message", message_id,
                after={"template": row.template})  # fmt: skip
    return _view_row(conn, _load(conn, message_id, user), user, settings)


# --------------------------------------------------------------------------- read
@router.get("/messages")
def list_messages(
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS} FROM outbox o JOIN cases c ON c.id = o.case_id
                 WHERE o.sent_by = :u ORDER BY o.created_at DESC LIMIT 200"""),  # noqa: S608
        {"u": user.id},
    )
    return [_view(r, "") | {"text": None} for r in rows]


@router.get("/cases/{case_id}/messages")
def case_messages(
    case_id: UUID, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    get_case(conn, case_id, user)
    rows = conn.execute(
        text(f"""SELECT {_COLUMNS} FROM outbox o JOIN cases c ON c.id = o.case_id
                 WHERE o.case_id = :c AND o.sent_by = :u ORDER BY o.created_at DESC"""),  # noqa: S608
        {"c": case_id, "u": user.id},
    )
    return [_view(r, "") | {"text": None} for r in rows]


@router.get("/messages/{message_id}")
def read_message(
    message_id: UUID, user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    return _view_row(conn, _load(conn, message_id, user), user, settings)
