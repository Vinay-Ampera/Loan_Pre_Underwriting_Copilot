"""Email to staff (Notifications Part 2): what is sent, when, and how it is delivered.

Three kinds, each with fixed text in this file and nothing from a case: a new notice in the inbox
("sign in to read it"), an account created and a password reset (both say to ask the admin for the
temporary password: **a password is never emailed**). A row is queued in `email_outbox` inside the
transaction of its event; `deliver_pending` sends queued rows after the commit, through the
guarded sender (allow-list, demo redirect), and audits every outcome with a masked address.

Notice emails respect the person's choice (`users.notice_emails`) and go at most once per
`NOTICE_EMAIL_GAP_MINUTES` per person, so a busy day sends one email, not twenty.
"""

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from app.api.deps import write_audit
from app.notifications.check import check_notification_text
from app.notifications.sender import NotAllowedError, Outgoing, Sender, SendError, mask_email

log = logging.getLogger("loan_copilot.mailer")
MAX_ATTEMPTS = 3
_config = {"base_url": "http://localhost:5173", "gap_minutes": 30}

_SIGN_IN = "Sign in to Pramaan: {url}/login"
FOOTER = ("This is an automatic message from Pramaan. Do not reply to it. Bank staff never ask "
          "for an OTP, PIN or password by email.")  # fmt: skip
MAILS: dict[str, tuple[str, str]] = {
    "notice": (
        "Pramaan: you have a new notice",
        "Something in Pramaan needs your attention. The details are in your inbox after you "
        "sign in; they are never sent by email.\n\n" + _SIGN_IN,
    ),
    "account_created": (
        "Pramaan: your account is ready",
        "An account was created for you in Pramaan, with this email address as the sign-in "
        "name. Your admin will give you the temporary password in person; it is never sent by "
        "email.\n\n" + _SIGN_IN,
    ),
    "password_reset": (
        "Pramaan: your password was reset",
        "Your admin reset your Pramaan password. Ask the admin for the temporary one; it is "
        "never sent by email. If you did not expect this, tell your admin.\n\n" + _SIGN_IN,
    ),
}


def configure(*, base_url: str, gap_minutes: int) -> None:
    _config["base_url"] = base_url.rstrip("/")
    _config["gap_minutes"] = gap_minutes


def compose(kind: str) -> tuple[str, str]:
    subject, body = MAILS[kind]
    return subject, f"{body.format(url=_config['base_url'])}\n\n{FOOTER}"


def _queue(conn: Connection, user_id: UUID | str, kind: str, where: str = "") -> bool:
    subject, body = compose(kind)
    return conn.execute(
        text(f"""INSERT INTO email_outbox (user_id, kind, recipient, subject, body)
                 SELECT u.id, :k, u.email, :s, :b FROM users u
                 WHERE u.id = :u AND u.active AND u.role IN ('officer', 'admin') {where}
                 RETURNING id"""),  # noqa: S608 - `where` is a constant from this file
        {"u": user_id, "k": kind, "s": subject, "b": body, "gap": _config["gap_minutes"]},
    ).first() is not None  # fmt: skip


def queue_notice_email(conn: Connection, user_id: UUID | str) -> bool:
    """A "you have a new notice" email, if the person wants them and had none lately."""
    return _queue(
        conn,
        user_id,
        "notice",
        """AND u.notice_emails AND NOT EXISTS (
        SELECT 1 FROM email_outbox e WHERE e.user_id = u.id AND e.kind = 'notice'
          AND e.created_at > now() - make_interval(mins => :gap))""",
    )


def queue_account_email(conn: Connection, user_id: UUID | str, kind: str) -> bool:
    """`account_created` or `password_reset`: always sent (not a preference), no password."""
    if kind not in ("account_created", "password_reset"):
        raise ValueError(kind)
    return _queue(conn, user_id, kind)


def _outcome(conn: Connection, row: Any, status: str, error: str | None) -> None:
    conn.execute(
        text("""UPDATE email_outbox SET status = :s, attempts = attempts + 1, last_error = :e,
                    sent_at = CASE WHEN :s IN ('printed', 'sent', 'redirected') THEN now()
                                   ELSE sent_at END
                WHERE id = :i"""),
        {"s": status, "e": error, "i": row.id},
    )  # fmt: skip
    if status == "queued":
        return  # tried again later; the final outcome is audited once
    action = {"failed": "email_failed", "held": "email_held"}.get(status, "email_sent")
    after = {"kind": row.kind, "to": mask_email(row.recipient), "delivery": status}
    write_audit(conn, None, action, "user", row.user_id, after=after)


def deliver_pending(engine: Engine, sender: Sender, limit: int = 20) -> int:
    """Send what is queued, oldest first. Each row is locked while it is sent, so two workers
    never send the same email. Returns how many rows were handled."""
    handled = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text("""SELECT id, user_id, kind, recipient, subject, body, attempts FROM email_outbox
                    WHERE status = 'queued' ORDER BY created_at LIMIT :n
                    FOR UPDATE SKIP LOCKED"""),
            {"n": limit},
        ).all()  # fmt: skip
        for row in rows:
            handled += 1
            if check_notification_text(row.subject):  # fixed text; a slip must not go out
                _outcome(conn, row, "failed", "the subject failed the content check")
                continue
            try:
                how = sender.send(Outgoing(str(row.id), row.recipient, row.subject, row.body))
            except NotAllowedError:
                _outcome(conn, row, "held", "not on the email allow-list")
            except SendError as exc:
                last = row.attempts + 1 >= MAX_ATTEMPTS
                _outcome(conn, row, "failed" if last else "queued", str(exc)[:300])
            else:
                _outcome(conn, row, how or "printed", None)
    return handled


async def run_worker(engine: Engine, sender: Sender, every_seconds: int) -> None:
    """The background loop started with the app. A failure is logged and the loop goes on."""
    while True:
        try:
            await asyncio.to_thread(deliver_pending, engine, sender)
        except Exception as exc:  # noqa: BLE001 - the loop must survive a bad moment
            log.error("sending queued email failed: %s", type(exc).__name__)
        await asyncio.sleep(every_seconds)
