"""Create or reset a user. The password is typed at a prompt and never written anywhere.

python -m app.api.users_cli create --email a@b.c --name "Asha" --role officer|admin|auditor
python -m app.api.users_cli password --email a@b.c
"""

import argparse
import getpass
import sys

from sqlalchemy import create_engine, text

from app.api.security import hash_password
from app.core.config import get_settings

MIN_LENGTH = 10


def ask_password() -> str:
    first = getpass.getpass("Password: ")
    if len(first) < MIN_LENGTH:
        raise SystemExit(f"Use at least {MIN_LENGTH} characters.")
    if first != getpass.getpass("Repeat: "):
        raise SystemExit("The two entries differ.")
    return first


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", choices=["officer", "admin", "auditor"], required=True)
    p = sub.add_parser("password")
    p.add_argument("--email", required=True)
    args = ap.parse_args(argv)
    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.begin() as conn:
        if args.cmd == "create":
            if args.role == "auditor":
                # one read-only auditor for now: the check and the insert share one transaction
                conn.execute(text("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE"))
                if conn.execute(
                    text("SELECT count(*) FROM users WHERE role = 'auditor' AND active")
                ).scalar_one():
                    raise SystemExit("An active auditor already exists. Only one is allowed.")
            conn.execute(
                text(
                    "INSERT INTO users (name, email, password_hash, role) VALUES (:n, lower(:e), :h, :r)"
                ),
                {
                    "n": args.name,
                    "e": args.email,
                    "h": hash_password(ask_password()),
                    "r": args.role,
                },
            )
            print(f"created {args.role} {args.email}")
        else:
            n = conn.execute(
                text("UPDATE users SET password_hash = :h, failed_logins = 0, locked_until = NULL "
                     "WHERE lower(email) = lower(:e)"),
                {"h": hash_password(ask_password()), "e": args.email},
            ).rowcount  # fmt: skip
            print("password updated" if n else "no such user")
            return 0 if n else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
