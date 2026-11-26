"""Queue export and the due state over the API (Stage 12 Part C, EDGE_CASES E-117 to E-119)."""

import csv
import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, create_engine, text

from app.api.auditlog import _cell, csv_response
from app.api.export import HEADER
from app.api.main import create_app
from app.api.security import hash_password
from app.core.config import Settings
from app.db.migrate import alembic_config
from tests.rag_helpers import fake_embed_passages

pytestmark = pytest.mark.db
PASSWORD = "correct horse battery staple"
NOW = datetime.now(UTC)
APPLICANT = "Zebedee Quintrell"  # searched for in every file: it must never appear


def seed(conn: Connection) -> dict[str, Any]:
    ids: dict[str, Any] = {}
    for key, name, role in (("asha", "Asha Officer", "officer"), ("ben", "=Ben Officer", "officer"),
                            ("ada", "Ada Admin", "admin"), ("aud", "Aud Auditor", "auditor")):  # fmt: skip
        ids[key] = conn.execute(
            text("""INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)
                    RETURNING id"""),
            {"n": name, "e": f"{key}@example.test", "h": hash_password(PASSWORD), "r": role},
        ).scalar_one()  # fmt: skip
    # no, owner, loan, status, band, score, due (hours from now)
    for no, owner, loan, status, band, score, due in (
        (1, "asha", "personal", "awaiting_confirmation", "refer", 72.5, -2),  # overdue
        (2, "asha", "home", "awaiting_confirmation", "approve", 90, 60),  # due later
        (3, "asha", "personal", "confirmed", "reject", 40, -100),  # decided: not timed
        (4, "ben", "vehicle", "awaiting_confirmation", "refer", 70, -3),  # ben's, overdue
        (5, "asha", "education", "stopped", None, None, None),  # a fix-type stop
    ):
        cid = conn.execute(
            text("""INSERT INTO cases (case_no, loan_type, created_by, status, band, total_score,
                        sla_due_at, form_data) VALUES (:n, :lt, :o, :s, :b, :t, :d, '{}')
                    RETURNING id"""),
            {"n": f"CASE-2026-{no:04d}", "lt": loan, "o": ids[owner], "s": status, "b": band,
             "t": score, "d": None if due is None else NOW + timedelta(hours=due)},
        ).scalar_one()  # fmt: skip
        ids[no] = cid
        conn.execute(
            text("""INSERT INTO applicants (case_id, role, full_name, dob)
                    VALUES (:c, 'primary', :n, '1990-01-01')"""),
            {"c": cid, "n": APPLICANT},
        )  # fmt: skip
    conn.execute(
        text("""INSERT INTO officer_actions (case_id, officer_id, action, original_recommendation,
                    final_decision, second_click_at) VALUES (:c, :o, 'confirm', 'recommend_reject',
                    'reject', now())"""),
        {"c": ids[3], "o": ids["asha"]},
    )  # fmt: skip
    return ids


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def ids(engine: Engine) -> dict[str, Any]:
    with engine.begin() as conn:
        return seed(conn)


@pytest.fixture
def client(engine: Engine, ids: dict[str, Any], tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("test-secret-" + "x" * 32),
        upload_dir=tmp_path / "uploads",
        mfa_roles="",
    )
    app = create_app(settings, engine=engine, saver=InMemorySaver(), use_llm=False,
                     embed=fake_embed_passages, recover=False)  # fmt: skip
    with TestClient(app) as c:
        yield c


def login(client: TestClient, who: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login", json={"email": f"{who}@example.test", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def export(client: TestClient, who: str, path: str, **params: Any) -> list[list[str]]:
    r = client.get(f"/api/v1{path}", headers=login(client, who), params=params)
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"\xef\xbb\xbf"), "Excel needs the byte-order mark"
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"].startswith('attachment; filename="pramaan-cases-')
    assert APPLICANT.split()[1] not in r.text  # no applicant name, whatever was searched
    return list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))


def audit_rows(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(
            text("SELECT after FROM audit_log WHERE action = 'cases_exported' ORDER BY at"))]  # fmt: skip


# --- the export ------------------------------------------------------------------------------
def test_an_officer_exports_only_their_own_cases_with_the_columns(
    client: TestClient, engine: Engine
) -> None:
    rows = export(client, "asha", "/cases/export.csv")
    assert rows[0] == HEADER
    by_ref = {r[0]: r for r in rows[1:]}
    assert sorted(by_ref) == [
        "CASE-2026-0001",
        "CASE-2026-0002",
        "CASE-2026-0003",
        "CASE-2026-0005",
    ]
    one = by_ref["CASE-2026-0001"]
    assert one[1:6] == ["personal", "Awaiting confirmation", "refer", "72.5", "Asha Officer"]
    assert one[9] and one[10] == "yes"  # due, overdue
    assert by_ref["CASE-2026-0002"][10] == "no"
    assert by_ref["CASE-2026-0003"][8] == "reject" and by_ref["CASE-2026-0003"][9:] == ["", ""]
    assert by_ref["CASE-2026-0005"][3:5] == ["", ""]  # stopped: no band, no score, not timed
    assert audit_rows(engine) == [{"filters": {}, "officer": None, "rows": 4}]


def test_the_officers_filters_apply_and_each_download_is_audited(
    client: TestClient, engine: Engine
) -> None:
    assert [r[0] for r in export(client, "asha", "/cases/export.csv", due="overdue")[1:]] == [
        "CASE-2026-0001"]  # fmt: skip
    assert [r[0] for r in export(client, "asha", "/cases/export.csv", loan_type="home")[1:]] == [
        "CASE-2026-0002"]  # fmt: skip
    assert len(export(client, "asha", "/cases/export.csv", view="awaiting")) == 3
    assert [r[0] for r in export(client, "asha", "/cases/export.csv", status="stopped")[1:]] == [
        "CASE-2026-0005"]  # fmt: skip
    found = export(client, "asha", "/cases/export.csv", q="Quintrell")  # matches the name...
    assert len(found) == 5  # ...and the name is still not in the file (checked in `export`)
    rows = audit_rows(engine)
    assert len(rows) == 5 and rows[0] == {"filters": {"due": "overdue"}, "officer": None, "rows": 1}
    assert rows[-1]["filters"] == {"q": "Quintrell"}


def test_the_admin_exports_every_case_or_one_officers(
    client: TestClient, engine: Engine, ids: dict[str, Any]
) -> None:
    rows = export(client, "ada", "/admin/cases/export.csv")
    assert len(rows) == 6
    ben = next(r for r in rows if r[0] == "CASE-2026-0004")
    assert ben[5] == "'=Ben Officer"  # a formula-like cell is written as text (E-119)
    only_ben = export(client, "ada", "/admin/cases/export.csv", officer=str(ids["ben"]))
    assert [r[0] for r in only_ben[1:]] == ["CASE-2026-0004"]
    assert audit_rows(engine)[-1] == {"filters": {}, "officer": str(ids["ben"]), "rows": 1}


def test_export_routes_are_for_their_role_only(client: TestClient) -> None:
    for who, path in (("aud", "/cases/export.csv"), ("aud", "/admin/cases/export.csv"),
                      ("asha", "/admin/cases/export.csv"), ("ada", "/cases/export.csv")):  # fmt: skip
        assert client.get(f"/api/v1{path}", headers=login(client, who)).status_code == 403, (
            who,
            path,
        )
    assert client.get("/api/v1/cases/export.csv").status_code == 401


def test_every_formula_start_is_written_as_text() -> None:
    for bad in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert _cell(bad) == "'" + bad
    plain = csv_response("x.csv", ["a"], [["b"]])
    assert not plain.body.startswith(b"\xef\xbb\xbf")  # the auditor's files are unchanged


# --- the due state in the queue ----------------------------------------------------------------
def test_the_queue_carries_the_due_state_and_filters_by_it(client: TestClient) -> None:
    h = login(client, "asha")
    rows = {r["case_no"]: r for r in client.get("/api/v1/cases", headers=h).json()}
    assert rows["CASE-2026-0001"]["due_state"] == "overdue" and rows["CASE-2026-0001"]["sla_due_at"]
    assert rows["CASE-2026-0002"]["due_state"] is None  # due in 60 hours
    assert (
        rows["CASE-2026-0003"]["due_state"] is None and rows["CASE-2026-0003"]["sla_due_at"] is None
    )
    overdue = client.get("/api/v1/cases", headers=h, params={"due": "overdue"}).json()
    assert [r["case_no"] for r in overdue] == ["CASE-2026-0001"]
    assert client.get("/api/v1/me/insights", headers=h).json()["overdue"] == 1


def test_reassignment_keeps_the_due_time(
    client: TestClient, engine: Engine, ids: dict[str, Any]
) -> None:
    with engine.connect() as c:
        before = c.execute(
            text("SELECT sla_due_at FROM cases WHERE id = :c"), {"c": ids[1]}
        ).scalar()
    r = client.post(f"/api/v1/admin/cases/{ids[1]}/reassign", headers=login(client, "ada"),
                    json={"officer_id": str(ids["ben"]), "reason": "Asha is on leave this week.",
                          "second_click": True})  # fmt: skip
    assert r.status_code == 200, r.text
    with engine.connect() as c:
        after = c.execute(
            text("SELECT sla_due_at FROM cases WHERE id = :c"), {"c": ids[1]}
        ).scalar()
    assert after == before
    ben = client.get(
        "/api/v1/cases", headers=login(client, "ben"), params={"due": "overdue"}
    ).json()
    assert sorted(r["case_no"] for r in ben) == ["CASE-2026-0001", "CASE-2026-0004"]
    page = client.get(f"/api/v1/admin/users/{ids['ben']}/activity", headers=login(client, "ada"))
    assert {c["case_no"]: c["due_state"] for c in page.json()["cases"]}[
        "CASE-2026-0001"
    ] == "overdue"
    assert json.dumps(page.json()).count("overdue") == 2
