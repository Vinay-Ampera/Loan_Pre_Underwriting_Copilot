"""The read-only auditor (SECURITY.md D3): 403 on every write route, reads every case masked and
without documents, cannot be managed from the admin API, and the CLI allows only one."""

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from app.api import display, users_cli
from app.api.main import create_app
from app.api.security import hash_password
from app.core.config import Settings
from app.db.migrate import alembic_config
from app.eval.fairness import rates
from app.monitoring.auditor_view import shown
from app.rag.index import reindex
from app.rag.retrieve import PolicyRetriever
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector
from tests.test_api import PASSWORD, add_precedent, create, login, minimal

pytestmark = pytest.mark.db
V1 = "/api/v1"


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        reindex(conn, embed=fake_embed_passages)
        for name, role in (("Asha Officer", "officer"), ("Ben Officer", "officer"),
                           ("Ada Admin", "admin"), ("Aud Auditor", "auditor")):  # fmt: skip
            conn.execute(
                text("INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)"),
                {"n": name, "e": f"{name.split()[0].lower()}@example.test",
                 "h": hash_password(PASSWORD), "r": role},
            )  # fmt: skip
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine, tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("test-secret-" + "x" * 32),
        upload_dir=tmp_path / "uploads",
    )
    app = create_app(
        settings, engine=engine, saver=InMemorySaver(), use_llm=False, embed=fake_embed_passages,
        ctx_kwargs={"retriever_factory": lambda c: PolicyRetriever(
            c, embed=fake_vector, rerank_fn=fake_rerank)},
    )  # fmt: skip
    with TestClient(app) as c:
        yield c


def seed_case(client: TestClient, engine: Engine) -> tuple[str, str]:
    """A case by Asha with a report, a document row, an override and a message."""
    asha = login(client, "asha")
    body = minimal(applicants=[{**minimal()["applicants"][0], "email": "test.person@example.com"}])
    case_id = create(client, asha, body)
    with engine.begin() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = 'asha@example.test'")).scalar_one()
        c.execute(
            text("""INSERT INTO reports (case_id, report_json) VALUES (:c,
                    CAST(:r AS jsonb))"""),
            {"c": case_id, "r": '{"summary": "Test Person earns well. PAN ABCDE1234F."}'},
        )
        c.execute(text("""INSERT INTO documents (case_id, doc_type, original_name, mime, status, file_path)
                          VALUES (:c, 'pan_card', 'Test_Person_pan.pdf', 'application/pdf', 'accepted', '/nope')"""),
                  {"c": case_id})  # fmt: skip
        c.execute(
            text("""INSERT INTO outbox (case_id, sent_by, recipient_email, template, subject, body,
                        final_text, status) VALUES (:c, :u, 'test.person@example.com', 'blank',
                        'Hello', 'Please call me.', 'Please call me. Bank staff never ask for an OTP.', 'sent')"""),
            {"c": case_id, "u": uid},
        )  # fmt: skip
    return case_id, asha["Authorization"]


# --------------------------------------------------------------------------- read only
def test_auditor_gets_403_on_every_write_route_and_on_every_other_role_route(
    client: TestClient,
) -> None:
    h = login(client, "aud")
    reads_ok = {"/auth/me", "/meta/loan-types"}
    checked = 0
    for full, methods in client.app.openapi()["paths"].items():  # type: ignore[attr-defined]
        path = full.removeprefix(V1)
        if (
            not full.startswith(V1)
            or path == "/auth/login"
            or path in reads_ok
            or path.startswith("/auditor/")
        ):
            continue
        url = V1 + path
        for part in ("case_id", "doc_id", "message_id", "user_id", "precedent_id", "issue_id"):
            url = url.replace("{" + part + "}", str(uuid.uuid4()))
        for method in methods:
            r = client.request(method.upper(), url, headers=h, json={})
            is_case_read = method == "get" and path.startswith("/cases") \
                and not any(x in path for x in ("documents", "messages", ".pdf"))  # fmt: skip
            if is_case_read:
                assert r.status_code in (200, 404), (method, path, r.status_code)
            else:
                assert r.status_code == 403, (method, path, r.status_code)
            checked += 1
    assert checked > 25


def test_auditor_routes_are_get_only(client: TestClient) -> None:
    paths = {p: m for p, m in client.app.openapi()["paths"].items() if "/auditor/" in p}  # type: ignore[attr-defined]
    assert paths and all(set(m) == {"get"} for m in paths.values())


def test_auditor_cannot_reach_documents_or_act(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    h = login(client, "aud")
    with engine.connect() as c:
        doc = c.execute(text("SELECT id FROM documents")).scalar_one()
    assert client.get(f"{V1}/cases/{case_id}/documents/{doc}/file", headers=h).status_code == 403
    for tail in ("confirm", "override", "submit", "resume", "documents"):
        r = client.post(f"{V1}/cases/{case_id}/{tail}", headers=h, json={})
        assert r.status_code == 403, tail
    assert client.delete(f"{V1}/cases/{case_id}/documents/{doc}", headers=h).status_code == 403
    assert client.post(f"{V1}/cases/{case_id}/messages", headers=h, json={}).status_code == 403


def test_auditor_reads_another_officers_case_masked_and_officers_still_get_404(
    client: TestClient, engine: Engine
) -> None:
    case_id, _ = seed_case(client, engine)
    aud, ben, asha = login(client, "aud"), login(client, "ben"), login(client, "asha")
    assert client.get(f"{V1}/cases/{case_id}", headers=ben).status_code == 404
    assert client.get(f"{V1}/cases/{case_id}/report", headers=ben).status_code == 404
    assert client.get(f"{V1}/cases/{case_id}", headers=asha).status_code == 200

    got = client.get(f"{V1}/cases/{case_id}", headers=aud)
    assert got.status_code == 200
    body = got.json()
    assert body["read_only"] is True and body["officer"] == "Asha Officer"
    a = body["applicants"][0]
    assert a["full_name"] == "T*** P***" and a["pan"] == "ABCDE****F"
    assert a["phone"] == "******3210" and a["email"] == "****@example.com"
    assert a["address"] == "masked" and a["dob"] == "1990-**-**"
    flat = got.text
    assert "Test Person" not in flat and "Person" not in flat and "ABCDE1234F" not in flat
    assert "9876543210" not in flat and "1 Test Street" not in flat
    rep = client.get(f"{V1}/cases/{case_id}/report", headers=aud).json()["report"]
    assert "Test Person" not in str(rep) and "ABCDE1234F" not in str(rep)


def test_auditor_lists_every_case_but_cannot_search_by_name(
    client: TestClient, engine: Engine
) -> None:
    seed_case(client, engine)
    create(client, login(client, "ben"), minimal())
    aud = login(client, "aud")
    rows = client.get(f"{V1}/cases", headers=aud).json()
    assert len(rows) == 2 and {r["officer"] for r in rows} == {"Asha Officer", "Ben Officer"}
    assert all(r["applicant"] == "T*** P***" for r in rows)
    assert client.get(f"{V1}/cases", params={"q": "Test Person"}, headers=aud).json() == []
    assert len(client.get(f"{V1}/cases", params={"q": rows[0]["case_no"]}, headers=aud).json()) == 1
    assert len(client.get(f"{V1}/cases", headers=login(client, "ben")).json()) == 1


def test_admin_still_has_no_case_access(client: TestClient, engine: Engine) -> None:
    case_id, _ = seed_case(client, engine)
    ada = login(client, "ada")
    assert client.get(f"{V1}/cases", headers=ada).status_code == 403
    assert client.get(f"{V1}/cases/{case_id}", headers=ada).status_code == 403
    assert client.get(f"{V1}/auditor/summary", headers=ada).status_code == 403
    assert client.get(f"{V1}/auditor/summary", headers=login(client, "asha")).status_code == 403


# --------------------------------------------------------------------------- auditor reads
def test_auditor_data_routes(client: TestClient, engine: Engine) -> None:
    seed_case(client, engine)
    add_precedent(engine)
    aud = login(client, "aud")

    s = client.get(f"{V1}/auditor/summary", headers=aud).json()
    assert s["cases"] >= 1 and s["pending_precedents"] == 1 and s["messages_sent"] == 1

    c = client.get(f"{V1}/auditor/charts", headers=aud).json()
    assert set(c["cases_by_band"]) == {"approve", "refer", "reject"}
    assert len(c["score_histogram"]) == 10 and c["cases_by_loan_type"]["personal"] >= 1

    log = client.get(f"{V1}/auditor/audit-log", headers=aud).json()
    assert log["total"] >= 2 and {"login", "case_created"} <= {r["action"] for r in log["rows"]}
    only = client.get(f"{V1}/auditor/audit-log", params={"action": "login"}, headers=aud).json()
    assert {r["action"] for r in only["rows"]} == {"login"}
    assert "case_created" in client.get(f"{V1}/auditor/audit-log/actions", headers=aud).json()

    users = client.get(f"{V1}/auditor/users", headers=aud).json()
    assert {u["role"] for u in users} == {"officer", "admin", "auditor"}
    assert all("password" not in k for u in users for k in u)

    pre = client.get(f"{V1}/auditor/precedents", headers=aud).json()
    assert len(pre) == 1 and pre[0]["status"] == "pending"

    msgs = client.get(f"{V1}/auditor/messages", headers=aud).json()
    assert len(msgs) == 1 and msgs[0]["recipient"] == "****@example.com"
    assert "example.com" in msgs[0]["recipient"] and "test.person" not in str(msgs)
    assert msgs[0]["officer"] == "Asha Officer" and "OTP" in msgs[0]["text"]


def test_auditor_changes_nothing_in_the_database(client: TestClient, engine: Engine) -> None:
    seed_case(client, engine)
    aud = login(client, "aud")
    tables = ("cases", "applicants", "documents", "reports", "outbox", "officer_actions",
              "precedents", "issue_reports")  # fmt: skip

    def counts() -> dict[str, int]:
        with engine.connect() as c:
            return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in tables}  # noqa: S608

    before = counts()
    for path in ("summary", "charts", "audit-log", "users", "precedents", "messages"):
        assert client.get(f"{V1}/auditor/{path}", headers=aud).status_code == 200
    assert client.get(f"{V1}/cases", headers=aud).status_code == 200
    assert counts() == before


# --------------------------------------------------------------------------- admin and CLI
def test_admin_cannot_create_disable_enable_or_reset_the_auditor(
    client: TestClient, engine: Engine
) -> None:
    ada = login(client, "ada")
    aud = next(
        u for u in client.get(f"{V1}/admin/users", headers=ada).json() if u["role"] == "auditor"
    )
    assert aud["email"] == "aud@example.test"  # shown, but not manageable
    for action in ("disable", "enable", "reset-password"):
        r = client.post(f"{V1}/admin/users/{aud['id']}/{action}", headers=ada)
        assert r.status_code == 403, action
    made = client.post(f"{V1}/admin/users", headers=ada,
                       json={"name": "X", "email": "x@example.test", "role": "auditor"})  # fmt: skip
    assert made.status_code == 422
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT active FROM users WHERE role = 'auditor'")).scalar_one() is True
        )
        assert (
            c.execute(
                text("SELECT count(*) FROM users WHERE email = 'x@example.test'")
            ).scalar_one()
            == 0
        )
    # the auditor still signs in and the sign-in stays read-only
    assert client.get(f"{V1}/auth/me", headers=login(client, "aud")).json()["role"] == "auditor"


def test_an_admin_cannot_lock_themselves_out_even_with_an_auditor_around(
    client: TestClient,
) -> None:
    ada = login(client, "ada")
    me = client.get(f"{V1}/auth/me", headers=ada).json()
    assert client.post(f"{V1}/admin/users/{me['id']}/disable", headers=ada).status_code == 409


def test_the_cli_allows_only_one_active_auditor(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(users_cli, "create_engine", lambda *_a, **_k: engine)
    monkeypatch.setattr(users_cli, "ask_password", lambda: PASSWORD)

    def create_cli(email: str) -> int | str:
        try:
            return users_cli.main(
                ["create", "--email", email, "--name", "Second", "--role", "auditor"]
            )
        except SystemExit as exc:
            return str(exc.code)

    assert "only one" in str(create_cli("second@example.test")).lower()
    with engine.begin() as c:
        c.execute(text("UPDATE users SET active = false WHERE role = 'auditor'"))
    assert create_cli("second@example.test") == 0
    assert "only one" in str(create_cli("third@example.test")).lower()
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM users WHERE role='auditor' AND active")
            ).scalar_one()
            == 1
        )


def test_the_database_also_refuses_a_second_active_auditor(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(text("INSERT INTO users (name, email, password_hash, role) "
                       "VALUES ('B', 'b@example.test', 'x', 'auditor')"))  # fmt: skip


# --------------------------------------------------------------------------- masking helpers
def test_mask_helpers() -> None:
    assert display.mask_name("Asha Rao") == "A*** R**"
    assert display.mask_name(None) is None and display.mask_dob("1990-05-06") == "1990-**-**"
    out: Any = display.scrub_for_auditor({"a": ["Asha Rao paid", {"b": "asha@x.in"}]}, ["Asha Rao"])
    assert out == {"a": ["A*** R** paid", {"b": "****@x.in"}]}


def test_migration_0011_widens_the_role_check_and_rolls_back(clean_db_url: str) -> None:
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as c:
        c.execute(text("INSERT INTO users (name, email, password_hash, role) "
                       "VALUES ('A', 'a@example.test', 'x', 'auditor')"))  # fmt: skip
        c.execute(text("INSERT INTO audit_log (actor_id, action, entity) "
                       "SELECT id, 'login', 'user' FROM users"))  # fmt: skip
    command.downgrade(cfg, "0010")  # the auditor becomes a disabled officer; the audit trail stays
    with eng.connect() as c:
        row = c.execute(text("SELECT role, active, password_hash FROM users")).one()
        assert (row.role, row.active, row.password_hash) == ("officer", False, "!")
        assert c.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 1
    with pytest.raises(IntegrityError), eng.begin() as c:
        c.execute(text("INSERT INTO users (name, email, password_hash, role) "
                       "VALUES ('B', 'b@example.test', 'x', 'auditor')"))  # fmt: skip
    command.upgrade(cfg, "head")
    eng.dispose()


# --------------------------------------------------------------------------- group charts (part 2)
def seed_groups(engine: Engine) -> None:
    """Six women (4 approve) and three men (all approve): the men's group is too small to show."""
    people = (
        [("F", "recommend_approve")] * 4 + [("F", "refer")] * 2 + [("M", "recommend_approve")] * 3
    )
    with engine.begin() as c:
        uid = c.execute(text("SELECT id FROM users WHERE email = 'asha@example.test'")).scalar_one()
        for i, (gender, rec) in enumerate(people):
            key = f"SYN-PL-D{i:02d}"
            c.execute(
                text("""INSERT INTO test_cases (case_id, split, loan_type, scenario)
                              VALUES (:k, 'dev', 'personal', 's')"""),
                {"k": key},
            )
            c.execute(
                text("""INSERT INTO fairness_attributes (case_id, applicant_role, gender, age_band, city_tier)
                              VALUES (:k, 'primary', :g, '30-44', 'tier1')"""),
                {"k": key, "g": gender},
            )
            c.execute(text("""INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months,
                                  status, recommendation, form_data)
                              VALUES (:n, 'personal', :u, 1000, 12, 'confirmed', :r,
                                      CAST(:f AS jsonb))"""),
                      {"n": f"CASE-2026-{7000 + i}", "u": uid, "r": rec,
                       "f": f'{{"external_id": "{key}"}}'})  # fmt: skip


def test_group_outcomes_are_aggregate_only_and_hide_small_groups(
    client: TestClient, engine: Engine
) -> None:
    seed_groups(engine)
    got = client.get(f"{V1}/auditor/fairness", headers=login(client, "aud"))
    assert got.status_code == 200
    gender = got.json()["attributes"]["gender"]["groups"]
    assert gender == [
        {"group": "F", "n": 6, "approve_rate": 0.6667},
        {"group": "M", "too_few": True},  # no count and no rate for a group under 5
    ]
    flat = got.text
    assert "SYN-PL" not in flat and "CASE-2026" not in flat and "recommend_approve" not in flat
    assert got.json()["min_group"] == 5 and "total" not in flat


def test_group_outcomes_are_for_the_auditor_only(client: TestClient) -> None:
    for who in ("asha", "ada"):
        assert client.get(f"{V1}/auditor/fairness", headers=login(client, who)).status_code == 403
    assert client.get(f"{V1}/auditor/fairness").status_code == 401


def test_shown_never_carries_a_small_groups_numbers() -> None:
    rows = [("F", "<30", "tier1", "recommend_approve")] * 2
    out = shown(rates(rows))  # type: ignore[arg-type]
    assert out["gender"]["groups"] == [{"group": "F", "too_few": True}]


def test_the_pipeline_role_cannot_read_the_group_table(engine: Engine) -> None:
    with engine.connect() as c:
        if not c.execute(
            text("SELECT count(*) FROM pg_roles WHERE rolname = 'app_rw'")
        ).scalar_one():
            pytest.skip("roles could not be created on this server")
        for role, allowed in (("app_rw", False), ("report_ro", True)):
            ok = c.execute(text("SELECT has_table_privilege(:r, 'fairness_attributes', 'SELECT')"),
                           {"r": role}).scalar_one()  # fmt: skip
            assert ok is allowed, role
