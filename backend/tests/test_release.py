"""The release manifest (Stage 11): models, prompts, rules and policies a release runs with."""

import json
import re

import pytest
from sqlalchemy import Engine, text

from app.rag.policy_loader import load_all
from app.release import manifest
from app.scoring.rules import load_rules
from tests.test_pipeline import engine  # noqa: F401 - the fixture


def test_the_file_manifest_names_every_version_and_no_key() -> None:
    m = manifest("v0.0.0-test")
    assert m["tag"] == "v0.0.0-test" and m["policy_source"] == "files"
    assert m["rules"] == {"version": load_rules().version, "checksum": load_rules().checksum}
    assert m["policy_versions"] == {d.loan_type: d.version for d in load_all()}
    assert re.fullmatch(r"\d{4}", m["migration_head"])
    assert set(m["models"]) >= {
        "supervisor",
        "extraction",
        "kyc",
        "policy",
        "risk",
        "decision",
        "judge",
    }
    assert all("/" in spec["primary"] for spec in m["models"].values())  # provider model ids
    assert set(m["prompt_versions"]) >= {"decision", "policy"}
    assert m["local_models"]["embedding"].startswith("BAAI/")
    blob = json.dumps(m).lower()
    assert "api_key" not in blob and "secret" not in blob and "password" not in blob


@pytest.mark.db
def test_the_database_manifest_reads_the_policy_versions_in_force(engine: Engine) -> None:  # noqa: F811
    with engine.connect() as c:
        active = dict(c.execute(text(
            "SELECT loan_type, version FROM policy_documents WHERE status = 'active'")).all())  # fmt: skip
    m = manifest("v0.0.0-test", engine)
    assert m["policy_source"] == "database" and m["policy_versions"] == active
    assert m["ai_config_version"] == 0  # nothing saved on the AI control page yet
