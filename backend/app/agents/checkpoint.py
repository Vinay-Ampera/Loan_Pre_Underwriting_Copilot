"""LangGraph checkpoints in Postgres, in their own schema (`langgraph`), as DATABASE.md says.

A run can be killed at any point; `Pipeline.resume` continues from the last saved checkpoint
and reaches the same result, because every node is a function of the saved state and the files.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row

SCHEMA = "langgraph"


def libpq_url(url: str) -> str:
    """The SQLAlchemy form (postgresql+psycopg://) rewritten for psycopg itself. A Neon pooled host
    (`-pooler`) is swapped for the direct one: the saver relies on `SET search_path`, which a
    transaction pooler does not keep between statements."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace("-pooler.", ".", 1)


@asynccontextmanager
async def postgres_saver(url: str) -> AsyncIterator[BaseCheckpointSaver[str]]:
    conn = await psycopg.AsyncConnection.connect(
        libpq_url(url),
        autocommit=True,
        row_factory=dict_row,
    )
    try:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        await conn.execute(f"SET search_path TO {SCHEMA}, public")
        saver = AsyncPostgresSaver(conn)
        await saver.setup()
        yield saver
    finally:
        await conn.close()


@asynccontextmanager
async def memory_saver() -> AsyncIterator[BaseCheckpointSaver[str]]:
    """For tests that do not need a database, and for a throwaway run."""
    yield InMemorySaver()
