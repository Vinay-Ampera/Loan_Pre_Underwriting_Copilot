"""Connection check: `python -m app.db.check`. Prints facts about the server, never the URL."""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def main() -> int:
    try:
        engine = create_engine(get_settings().sqlalchemy_url())
        with engine.connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
            vector = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one_or_none()
            tables = conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            ).scalar_one()
            alembic = conn.execute(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            ).scalar_one()
            head = (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
                if alembic
                else None
            )
    except (RuntimeError, SQLAlchemyError) as exc:
        # SQLAlchemy errors can embed the URL; print only the exception type.
        print(f"FAIL: {type(exc).__name__}")
        return 1
    print(f"OK  postgres={version}  pgvector={vector or 'NOT INSTALLED'}")
    print(f"    public tables={tables}  alembic_head={head or 'none (migrations not applied)'}")
    return 0 if vector else 1


if __name__ == "__main__":
    sys.exit(main())
