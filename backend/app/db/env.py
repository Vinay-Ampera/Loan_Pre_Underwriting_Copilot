"""Alembic environment. Connection string comes from Settings, not alembic.ini."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

config = context.config


def run_migrations_online() -> None:
    # tests pass a throwaway database URL through config.attributes
    url = config.attributes.get("url") or get_settings().sqlalchemy_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
