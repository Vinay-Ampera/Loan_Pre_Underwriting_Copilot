"""Email to staff (Notifications Part 2): what is sent, when, and how it is delivered.

Four kinds, each with fixed text in this file and nothing from a case: a new notice in the inbox
("sign in to read it"), an account created and a password reset (both say to ask the admin for the
temporary password: **a password is never emailed**), and a 2-step verification reset (set it up
again at the next sign-in; no code or key is ever emailed). A row is queued in `email_outbox`
inside the transaction of its event; `deliver_pending` sends queued rows after the commit, through
the guarded sender (allow-list, demo redirect), and audits every outcome with a masked address.

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
from app.observability import metrics

log = logging.getLogger("loan_copilot.mailer")
MAX_ATTEMPTS = 3
RETRY_AFTER_MINUTES = (1, 5)  # wait after the first and the second failed try
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
    "two_step_reset": (
        "Pramaan: your 2-step verification was reset",
        "Your admin reset your 2-step verification for Pramaan. At your next sign-in, after your "
        "password, you will scan a new QR code with Microsoft Authenticator on your phone. If "
        "you did not expect this, tell your admin.\n\n" + _SIGN_IN,
    ),
}
ACCOUNT_KINDS = ("account_created", "password_reset", "two_step_reset")


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
    """An `ACCOUNT_KINDS` email: always sent (not a preference), never a password or a code."""
    if kind not in ACCOUNT_KINDS:
        raise ValueError(kind)
    return _queue(conn, user_id, kind)


def _outcome(conn: Connection, row: Any, status: str, error: str | None) -> None:
    wait = RETRY_AFTER_MINUTES[min(row.attempts, len(RETRY_AFTER_MINUTES) - 1)]
    conn.execute(
        text("""UPDATE email_outbox SET status = :s, attempts = attempts + 1, last_error = :e,
                    sent_at = CASE WHEN :s IN ('printed', 'sent', 'redirected') THEN now()
                                   ELSE sent_at END,
                    next_attempt_at = CASE WHEN :s = 'queued'
                                           THEN now() + make_interval(mins => :w)
                                           ELSE next_attempt_at END
                WHERE id = :i"""),
        {"s": status, "e": error, "i": row.id, "w": wait},
    )  # fmt: skip
    metrics.EMAILS.labels(row.kind, status).inc()
    if status == "queued":
        return  # tried again later; the final outcome is audited once
    action = {"failed": "email_failed", "held": "email_held"}.get(status, "email_sent")
    after = {"kind": row.kind, "to": mask_email(row.recipient), "delivery": status}
    write_audit(conn, None, action, "user", row.user_id, after=after)


def _send_one(conn: Connection, sender: Sender, row: Any) -> None:
    if check_notification_text(row.subject):  # fixed text; a slip must not go out
        _outcome(conn, row, "failed", "the subject failed the content check")
        return
    last = row.attempts + 1 >= MAX_ATTEMPTS
    try:
        how = sender.send(Outgoing(str(row.id), row.recipient, row.subject, row.body))
    except NotAllowedError:
        _outcome(conn, row, "held", "not on the email allow-list")
    except SendError as exc:
        _outcome(conn, row, "failed" if last else "queued", str(exc)[:300])
    except Exception as exc:  # noqa: BLE001 - an unexpected error counts as a failed try
        log.error("sending email %s failed: %s", row.id, type(exc).__name__)
        why = f"unexpected error ({type(exc).__name__})"
        _outcome(conn, row, "failed" if last else "queued", why)
    else:
        _outcome(conn, row, how or "printed", None)


def deliver_pending(engine: Engine, sender: Sender, limit: int = 20) -> int:
    """Send what is due, oldest first, **one row per transaction**. The row is locked while it
    is sent, so two workers never send the same email, and a problem with one row can never undo
    the outcome already recorded for another (which would send that email again). A row that
    failed waits `RETRY_AFTER_MINUTES` before its next try. If the process stops between the
    send and the commit, the row is still queued and goes once more (at least once, never lost).
    Returns how many rows were handled."""
    handled = 0
    for _ in range(limit):
        with engine.begin() as conn:
            row = conn.execute(
                text("""SELECT id, user_id, kind, recipient, subject, body, attempts
                        FROM email_outbox WHERE status = 'queued' AND next_attempt_at <= now()
                        ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"""),
            ).first()  # fmt: skip
            if row is None:
                break
            _send_one(conn, sender, row)
            handled += 1
    return handled


async def run_worker(engine: Engine, sender: Sender, every_seconds: int) -> None:
    """The background loop started with the app. A failure is logged and the loop goes on."""
    while True:
        try:
            await asyncio.to_thread(deliver_pending, engine, sender)
        except Exception as exc:  # noqa: BLE001 - the loop must survive a bad moment
            log.error("sending queued email failed: %s", type(exc).__name__)
        await asyncio.sleep(every_seconds)
