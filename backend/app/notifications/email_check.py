"""Send one test email with the settings in `.env`, to check the email setup by hand.

    python -m app.notifications.email_check            # to the first address on EMAIL_ALLOWLIST
    python -m app.notifications.email_check --to ADDR  # ADDR must be on EMAIL_ALLOWLIST

It goes through the same guarded sender as the app, so it cannot reach an address that is not
allowed. It prints the outcome and never a key. With NOTIFICATION_SENDER=console it only prints.
"""

import argparse
import sys

from app.core.config import Settings, get_settings
from app.notifications.sender import Outgoing, SendError, build_sender, mask_email

SUBJECT = "Pramaan: email check"
BODY = ("This is a test email from Pramaan. If you can read it, the email settings work.\n\n"
        "Nothing needs to be done.")  # fmt: skip


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", help="an address on EMAIL_ALLOWLIST (default: the first one)")
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    allow = [a.strip() for a in settings.email_allowlist.split(",") if a.strip()]
    to = args.to or (allow[0] if allow else "")
    if not to:
        print("EMAIL_ALLOWLIST is empty: there is no address to send the check to.")
        return 2
    try:
        sender = build_sender(settings)
        how = sender.send(Outgoing("email-check", to, SUBJECT, BODY)) or "printed"
    except (RuntimeError, SendError) as exc:
        print(f"Not sent: {exc}")
        return 1
    where = {"sent": "sent by email", "redirected": "sent to the demo inbox", "printed":
             "printed above (NOTIFICATION_SENDER is console)"}[how]  # fmt: skip
    print(f"Email check to {mask_email(to)}: {where}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
