"""Run Alembic migrations: `python -m app.db.migrate [upgrade|downgrade|current|history] [rev]`."""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db"))
    if url is not None:
        cfg.attributes["url"] = url
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        nargs="?",
        default="upgrade",
        choices=["upgrade", "downgrade", "current", "history"],
    )
    parser.add_argument("revision", nargs="?", default=None)
    args = parser.parse_args()

    cfg = alembic_config()
    if args.action == "upgrade":
        command.upgrade(cfg, args.revision or "head")
    elif args.action == "downgrade":
        command.downgrade(cfg, args.revision or "-1")
    elif args.action == "current":
        command.current(cfg, verbose=True)
    else:
        command.history(cfg)


if __name__ == "__main__":
    main()
