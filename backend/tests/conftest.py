import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-llm", action="store_true", help="run tests that call real LLMs")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_llm = pytest.mark.skip(reason="needs --run-llm")
    skip_db = pytest.mark.skip(reason="DATABASE_URL not set")
    has_db = get_settings().database_url is not None
    for item in items:
        if "llm" in item.keywords and not config.getoption("--run-llm"):
            item.add_marker(skip_llm)
        if "db" in item.keywords and not has_db:
            item.add_marker(skip_db)


@pytest.fixture
def clean_db_url() -> Iterator[str]:
    base = make_url(get_settings().sqlalchemy_url())
    name = f"lc_test_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
