"""How a message leaves the system. Two senders behind one interface:

  ConsoleSender   prints it in the backend terminal (the default; nothing leaves the machine)
  SmtpSender      really sends it by email over SMTP (Resend, Mailpit or any SMTP server)

A real sender is always wrapped in `GuardedSender`, which decides who may receive real email: an
address on EMAIL_ALLOWLIST is delivered; any other address goes to EMAIL_REDIRECT_TO (a demo inbox,
with the intended recipient masked in the subject) or, with no redirect, is printed in the terminal
and refused (`NotAllowedError`). The data is synthetic, so no email may ever reach a stranger.

`send` returns how the message went: "printed", "sent" or "redirected". The SMTP password (the
Resend API key) is never logged, raised or returned.
"""

import smtplib
import ssl
import sys
from dataclasses import dataclass, replace
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Protocol

from app.core.config import Settings


class SendError(Exception):
    """The sender could not deliver. The message is shown to the officer, so keep it plain."""


class NotAllowedError(SendError):
    """The address is not on the allow-list and there is no redirect: printed, not sent."""


@dataclass(frozen=True)
class Outgoing:
    message_id: str
    recipient: str
    subject: str
    text: str


class Sender(Protocol):
    def send(self, message: Outgoing) -> str | None: ...


def mask_email(email: str) -> str:
    return "****@" + email.split("@", 1)[1] if "@" in email else "****"


class ConsoleSender:
    def send(self, message: Outgoing) -> str:
        rule = "-" * 60
        head = f"OUTBOX {message.message_id}\nTo: {mask_email(message.recipient)}"
        print(
            f"\n{rule}\n{head}\nSubject: {message.subject}\n\n{message.text}\n{rule}",
            file=sys.stdout,
            flush=True,
        )
        return "printed"


class SmtpSender:
    """One connection per message: simple, and enough for the volume of a branch."""

    def __init__(self, settings: Settings) -> None:
        self.host, self.port = settings.smtp_host, settings.smtp_port
        self.security, self.timeout = settings.smtp_security, settings.smtp_timeout_seconds
        self.username = settings.smtp_username
        self._password = settings.smtp_password
        self.sender = settings.email_from

    def _message(self, message: Outgoing) -> EmailMessage:
        if not _valid(message.recipient) or any(c in message.recipient for c in "\r\n,;<>"):
            raise SendError("The recipient address is not valid.")
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = self.sender, message.recipient, message.subject
        m["Date"], m["Message-ID"] = formatdate(localtime=True), make_msgid(domain="pramaan.local")
        m["Auto-Submitted"] = "auto-generated"  # no auto-replies to a no-reply message
        m.set_content(message.text)
        return m

    def send(self, message: Outgoing) -> str:
        try:
            mail = self._message(message)  # checked before any connection is opened
            context = ssl.create_default_context()
            if self.security == "ssl":
                client: smtplib.SMTP = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                )
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with client:
                if self.security == "starttls":
                    client.starttls(context=context)
                if self.username:
                    password = self._password.get_secret_value() if self._password else ""
                    client.login(self.username, password)
                client.send_message(mail)
        except smtplib.SMTPAuthenticationError:
            raise SendError(
                "The mail server refused the sign-in. Check the SMTP settings."
            ) from None
        except smtplib.SMTPRecipientsRefused:
            raise SendError("The mail server refused the recipient address.") from None
        except smtplib.SMTPResponseException as exc:
            raise SendError(f"The mail server refused the message ({exc.smtp_code}).") from None
        except (smtplib.SMTPException, OSError):
            raise SendError("The mail server could not be reached. Try again later.") from None
        except SendError:
            raise
        except Exception as exc:  # a header or encoding problem: plain words, no detail
            raise SendError(f"The message could not be sent ({type(exc).__name__}).") from None
        return "sent"


def _addresses(raw: str) -> set[str]:
    return {a.strip().lower() for a in raw.split(",") if a.strip()}


class GuardedSender:
    """Real email only to the allow-list; everyone else to the demo inbox, or nowhere."""

    def __init__(self, inner: Sender, allow: set[str], redirect: str | None,
                 fallback: Sender | None = None) -> None:  # fmt: skip
        self.inner, self.allow, self.redirect = inner, allow, redirect
        self.fallback = fallback or ConsoleSender()

    def send(self, message: Outgoing) -> str:
        to = message.recipient.strip().lower()
        if to in self.allow:
            self.inner.send(message)
            return "sent"
        if self.redirect:
            tagged = f"[demo, for {mask_email(to)}] {message.subject}"
            self.inner.send(replace(message, recipient=self.redirect, subject=tagged))
            return "redirected"
        self.fallback.send(message)
        raise NotAllowedError(
            "Not sent: the address is not on the email allow-list. It was printed in the "
            "backend terminal instead."
        )


def _valid(address: str) -> bool:
    _, parsed = parseaddr(address)
    return "@" in parsed and "." in parsed.split("@", 1)[1] and " " not in parsed


def check_email_settings(settings: Settings) -> None:
    """Refuse to start with an email setup that could send to the wrong place. Messages name the
    variable, never a value of a secret."""
    if settings.notification_sender == "console":
        return
    if settings.notification_sender != "smtp":
        raise RuntimeError(f"Unknown NOTIFICATION_SENDER {settings.notification_sender!r}; "
                           "use 'console' or 'smtp'")  # fmt: skip
    problems = []
    if not settings.smtp_host:
        problems.append("SMTP_HOST is empty")
    if settings.smtp_security not in ("ssl", "starttls", "none"):
        problems.append("SMTP_SECURITY must be ssl, starttls or none")
    if settings.smtp_username and not settings.smtp_password:
        problems.append("SMTP_PASSWORD is empty")
    if not _valid(settings.email_from):
        problems.append("EMAIL_FROM is not an email address")
    allow = _addresses(settings.email_allowlist)
    problems += [f"EMAIL_ALLOWLIST has a value that is not an address ({mask_email(a)})"
                 for a in allow if not _valid(a)]  # fmt: skip
    redirect = settings.email_redirect_to.strip().lower()
    if redirect and redirect not in allow:
        problems.append("EMAIL_REDIRECT_TO must also be on EMAIL_ALLOWLIST")
    if problems:
        raise RuntimeError("Email settings: " + "; ".join(problems))


def build_sender(settings: Settings) -> Sender:
    check_email_settings(settings)
    if settings.notification_sender == "console":
        return ConsoleSender()
    redirect = settings.email_redirect_to.strip().lower() or None
    return GuardedSender(SmtpSender(settings), _addresses(settings.email_allowlist), redirect)
