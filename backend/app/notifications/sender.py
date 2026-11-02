"""The sender interface. v1 has one implementation, the console sender: it prints the message in
the backend terminal. A real mail or SMS sender can replace it by config later, but only after a
review (the recipient is customer data; use consented, test or synthetic addresses).
"""

import sys
from dataclasses import dataclass
from typing import Protocol


class SendError(Exception):
    """The sender could not deliver. The message is shown to the officer, so keep it plain."""


@dataclass(frozen=True)
class Outgoing:
    message_id: str
    recipient: str
    subject: str
    text: str


class Sender(Protocol):
    def send(self, message: Outgoing) -> None: ...


def mask_email(email: str) -> str:
    return "****@" + email.split("@", 1)[1] if "@" in email else "****"


class ConsoleSender:
    def send(self, message: Outgoing) -> None:
        rule = "-" * 60
        head = f"OUTBOX {message.message_id}\nTo: {mask_email(message.recipient)}"
        print(
            f"\n{rule}\n{head}\nSubject: {message.subject}\n\n{message.text}\n{rule}",
            file=sys.stdout,
            flush=True,
        )


def build_sender(kind: str) -> Sender:
    if kind == "console":
        return ConsoleSender()
    raise RuntimeError(f"Unknown NOTIFICATION_SENDER {kind!r}; v1 supports 'console' only")
