"""Insights (Stage 12 Part B): every figure equals a hand count on a seeded database; roles and the
auditor's copy hold no way into a case; no model is called; migration 0026 backfills and rolls
back."""

import json
import re
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

from app.api.main import create_app
from app.api.security import hash_password
from app.core.config import Settings
from app.db.migrate import alembic_config
from app.rag.index import reindex
from app.rag.retrieve import PolicyRetriever
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector

pytestmark = pytest.mark.db
PASSWORD = "correct horse battery staple"
H = 3600  # seconds in an hour
D = 24 * H
# every time is an offset from BASE, 20 days ago, so the officer's "last 30 days" holds them all
BASE = datetime.now(UTC).replace(microsecond=0) - timedelta(days=20)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class NoModel:
    """Insights never call a model: any call fails the test."""

    async def acompletion(self, **_: Any) -> Any:
        raise AssertionError("a model was called")


def at(days: float, hours: float = 0) -> datetime:
    return BASE + timedelta(days=days, hours=hours)


# --- the seeded set ---------------------------------------------------------------------------
# no, loan, owner, status, created (days), submitted (h after), ready (h after created),
# action (kind, original recommendation, final, hours after ready)
CASES: list[tuple[Any, ...]] = [
    (1, "personal", "asha", "confirmed", 0, 1, 2, ("confirm", "refer", "refer", 24)),
    (2, "personal", "asha", "overridden", 1, 1, 4, ("override", "refer", "approve", 48)),
    (3, "home", "ben", "confirmed", 3, 1, 6, ("confirm", "recommend_reject", "reject", 3)),
    (4, "home", "ben", "overridden", 4, 1, 8, ("override", "recommend_reject", "refer", 1)),
    (5, "personal", "asha", "stopped", 5, 1, None, None),
    (6, "vehicle", "asha", "awaiting_confirmation", 6, 1, 5, None),
    (7, "education", "ben", "draft", 7, None, None, None),
    (8, "business", "ben", "running", -10, 1, None, None),
    (9, "personal", "asha", "awaiting_confirmation", 8, 1, 1, None),
    (10, "home", "ben", "awaiting_confirmation", 9, 1, 2, None),
]


def seed(conn: Connection) -> dict[str, Any]:
    ids: dict[str, Any] = {}
    for name, role in (("Asha Officer", "officer"), ("Ben Officer", "officer"),
                       ("Ada Admin", "admin"), ("Aud Auditor", "auditor")):  # fmt: skip
        key = name.split()[0].lower()
        ids[key] = conn.execute(
            text("""INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)
                    RETURNING id"""),
            {"n": name, "e": f"{key}@example.test", "h": hash_password(PASSWORD), "r": role},
        ).scalar_one()  # fmt: skip
    for no, loan, owner, status, day, sub, ready, act in CASES:
        created = at(day)
        cid = conn.execute(
            text("""INSERT INTO cases (case_no, loan_type, created_by, status, created_at,
                        submitted_at, report_ready_at) VALUES (:no, :lt, :o, :s, :c, :sub, :ready)
                    RETURNING id"""),
            {"no": f"CASE-2026-{no:04d}", "lt": loan, "o": ids[owner], "s": status, "c": created,
             "sub": None if sub is None else created + timedelta(hours=sub),
             "ready": None if ready is None else created + timedelta(hours=ready)},
        ).scalar_one()  # fmt: skip
        ids[no] = cid
        if act:
            kind, rec, final, after = act
            conn.execute(
                text("""INSERT INTO officer_actions (case_id, officer_id, action,
                            original_recommendation, final_decision, reason, second_click_at,
                            created_at) VALUES (:c, :o, :a, :rec, :f, :why, :t, :t)"""),
                {"c": cid, "o": ids[owner], "a": kind, "rec": rec, "f": final,
                 "why": "Reason given by the officer." if kind == "override" else None,
                 "t": created + timedelta(hours=ready + after)},
            )  # fmt: skip

    def failed_rules(no: int, rules: list[tuple[str, str, str]]) -> None:
        run = conn.execute(
            text("""INSERT INTO stage_runs (case_id, stage, status) VALUES (:c, 'risk', 'passed')
                    RETURNING id"""), {"c": ids[no]},
        ).scalar_one()  # fmt: skip
        for rule_id, kind, clause in rules:
            conn.execute(
                text("""INSERT INTO rule_results (stage_run_id, rule_id, kind, passed, clause_id)
                        VALUES (:r, :id, :k, false, :cl)"""),
                {"r": run, "id": rule_id, "k": kind, "cl": clause},
            )  # fmt: skip

    failed_rules(1, [("CM-INC-10", "soft", "CM-INC-01")])  # confirmed: not a changed decision
    failed_rules(2, [("CM-INC-10", "soft", "CM-INC-01"), ("PL-CIBIL-02", "hard", "PL-ELIG-03")])
    failed_rules(4, [("HL-POL-11B", "soft", "HL-PROD-02")])
    conn.execute(
        text("""INSERT INTO admin_actions (case_id, admin_id, action, previous_decision,
                    final_decision, reason, second_click_at)
                VALUES (:c, :a, 'override', 'approve', 'refer', 'Second look by the admin.', now())"""),
        {"c": ids[2], "a": ids["ada"]},
    )  # fmt: skip

    def report(no: int, version: int, body: dict[str, Any]) -> None:
        conn.execute(
            text("""INSERT INTO reports (case_id, version, report_json)
                    VALUES (:c, :v, CAST(:j AS jsonb))"""),
            {"c": ids[no], "v": version, "j": json.dumps(body)},
        )  # fmt: skip

    stop = {"severity": "hard_fail", "rule_id": "CM-KYC-03", "clause_id": "CM-KYC-03"}
    lost = {"severity": "points_lost", "rule_id": "CM-INC-10", "clause_id": "CM-INC-01"}
    report(1, 1, {"status": "awaiting_confirmation", "stopped_stage": None, "findings": [lost]})
    report(5, 1, {"status": "stopped", "stopped_stage": "kyc", "findings": [stop, lost]})
    # case 6 stopped for a fix, was corrected and scored: the stop still counts (E-114)
    report(6, 1, {"status": "stopped", "stopped_stage": "kyc", "findings": [stop]})
    report(6, 2, {"status": "awaiting_confirmation", "stopped_stage": None, "findings": [],
                  "total_score": 86, "band": "approve", "precedent_bonus": 3})  # fmt: skip
    report(9, 1, {"status": "awaiting_confirmation", "stopped_stage": None, "findings": [],
                  "total_score": 72, "band": "refer", "precedent_bonus": 2})  # fmt: skip
    report(10, 1, {"status": "awaiting_confirmation", "stopped_stage": "kyc", "findings": [
        {"severity": "hard_fail", "rule_id": "CM-ELIG-03", "clause_id": "CM-ELIG-03"}]})  # fmt: skip
    precedent = conn.execute(
        text("""INSERT INTO precedents (loan_type, final_decision, original_recommendation,
                    officer_reason, report_summary, proposed_by, status)
                VALUES ('personal', 'approve', 'refer', 'Stable salary.', 'A summary.', :u,
                        'pending') RETURNING id"""),
        {"u": ids["asha"]},
    ).scalar_one()  # fmt: skip
    for no, bonus in ((6, 3), (9, 2)):
        conn.execute(
            text("INSERT INTO precedent_uses (precedent_id, case_id, bonus) VALUES (:p, :c, :b)"),
            {"p": precedent, "c": ids[no], "b": bonus},
        )
    return ids


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        reindex(conn, embed=fake_embed_passages)
    yield eng
    eng.dispose()


@pytest.fixture
def seeded(engine: Engine) -> dict[str, Any]:
    with engine.begin() as conn:
        return seed(conn)


@pytest.fixture
def client(engine: Engine, seeded: dict[str, Any], tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("test-secret-" + "x" * 32),
        upload_dir=tmp_path / "uploads",
        mfa_roles="",  # 2-step verification has its own tests
    )
    app = create_app(
        settings, engine=engine, saver=InMemorySaver(), router=NoModel(), use_llm=False,
        embed=fake_embed_passages, recover=False,
        ctx_kwargs={"retriever_factory": lambda c: PolicyRetriever(
            c, embed=fake_vector, rerank_fn=fake_rerank)},
    )  # fmt: skip
    with TestClient(app) as c:
        yield c


def login(client: TestClient, who: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login", json={"email": f"{who}@example.test", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def get(client: TestClient, who: str, path: str, **params: Any) -> dict[str, Any]:
    r = client.get(f"/api/v1{path}", headers=login(client, who), params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# --- each panel against the hand count -------------------------------------------------------
def test_funnel_and_open_cases(client: TestClient) -> None:
    f = get(client, "ada", "/admin/insights")["funnel"]
    assert f == {"created": 10, "submitted": 9, "report_ready": 7, "decided": 4, "confirmed": 2,
                 "changed": 2, "not_submitted": 1, "running": 1, "stopped": 1, "waiting": 3}  # fmt: skip


def test_time_to_decide_medians_and_slowest(client: TestClient) -> None:
    t = get(client, "ada", "/admin/insights")["time_to_decide"]
    # created -> ready: 1, 2, 2, 4, 5, 6, 8 hours; ready -> decision: 1, 3, 24, 48 hours
    assert t["report_ready"] == {"n": 7, "median_s": 4 * H, "slowest_s": 8 * H}
    assert t["officer_decided"] == {"n": 4, "median_s": (3 * H + 24 * H) / 2, "slowest_s": 48 * H}
    assert [(r["loan_type"], r["n"], r["median_s"]) for r in t["by_loan_type"]] == [
        ("home", 2, 2 * H), ("personal", 2, 36 * H)]  # fmt: skip
    assert [(r["officer"], r["n"], r["median_s"]) for r in t["by_officer"]] == [
        ("Asha Officer", 2, 36 * H), ("Ben Officer", 2, 2 * H)]  # fmt: skip


def test_agreement_and_admin_corrections(client: TestClient) -> None:
    a = get(client, "ada", "/admin/insights")["agreement"]
    assert (a["confirmed"], a["changed"], a["admin_corrections"]) == (2, 2, 1)
    assert a["by_loan_type"] == [{"loan_type": "home", "confirmed": 1, "changed": 1},
                                 {"loan_type": "personal", "confirmed": 1, "changed": 1}]  # fmt: skip
    assert a["by_band"] == [{"band": "refer", "confirmed": 1, "changed": 1},
                            {"band": "reject", "confirmed": 1, "changed": 1}]  # fmt: skip


def test_rules_in_changed_decisions_with_direction_and_clause(
    client: TestClient, seeded: dict[str, Any]
) -> None:
    rules = get(client, "ada", "/admin/insights")["changed_rules"]
    got = [(r["rule_id"], r["clause_id"], r["from"], r["to"], r["n"]) for r in rules]
    assert got == [("CM-INC-10", "CM-INC-01", "refer", "approve", 1),
                   ("HL-POL-11B", "HL-PROD-02", "reject", "refer", 1),
                   ("PL-CIBIL-02", "PL-ELIG-03", "refer", "approve", 1)]  # fmt: skip
    assert rules[0]["cases"] == [{"id": str(seeded[2]), "case_no": "CASE-2026-0002"}]
    assert rules[0]["clause_doc"] == "common" and rules[0]["clause_title"]
    assert rules[2]["clause_doc"] == "personal"


def test_stop_reasons_count_every_report_version(client: TestClient) -> None:
    stops = get(client, "ada", "/admin/insights")["stop_reasons"]
    got = [(r["stage"], r["stage_label"], r["rule_id"], r["n"]) for r in stops]
    assert got == [("kyc", "KYC", "CM-KYC-03", 2), ("kyc", "KYC", "CM-ELIG-03", 1)]
    assert [c["case_no"] for c in stops[0]["cases"]] == ["CASE-2026-0005", "CASE-2026-0006"]
    assert stops[0]["clause_title"]


def test_precedent_use_and_band_moves(client: TestClient) -> None:
    p = get(client, "ada", "/admin/insights")["precedents"]
    assert (p["reached"], p["moved"]) == (2, 1)  # 86 with a bonus of 3 was 83, refer: moved
    assert [c["case_no"] for c in p["moved_cases"]] == ["CASE-2026-0006"]


def test_date_range_filter(client: TestClient) -> None:
    window = {"start": at(3).isoformat(), "end": at(7).isoformat()}  # cases 3, 4, 5 and 6
    page = get(client, "ada", "/admin/insights", **window)
    assert page["funnel"] == {"created": 4, "submitted": 4, "report_ready": 3, "decided": 2,
                              "confirmed": 1, "changed": 1, "not_submitted": 0, "running": 0,
                              "stopped": 1, "waiting": 1}  # fmt: skip
    assert page["agreement"]["admin_corrections"] == 0
    assert [(r["rule_id"], r["n"]) for r in page["stop_reasons"]] == [("CM-KYC-03", 2)]
    assert (page["precedents"]["reached"], page["precedents"]["moved"]) == (1, 1)
    assert [r["rule_id"] for r in page["changed_rules"]] == ["HL-POL-11B"]


def test_loan_type_filter(client: TestClient) -> None:
    page = get(client, "ada", "/admin/insights", loan_type="home")  # cases 3, 4 and 10
    assert (page["funnel"]["created"], page["funnel"]["decided"], page["funnel"]["waiting"]) == (
        3,
        2,
        1,
    )
    assert page["time_to_decide"]["officer_decided"]["median_s"] == 2 * H
    assert [(r["rule_id"], r["n"]) for r in page["stop_reasons"]] == [("CM-ELIG-03", 1)]
    assert [r["rule_id"] for r in page["changed_rules"]] == ["HL-POL-11B"]
    assert page["precedents"]["reached"] == 0
    assert page["scope"]["loan_type"] == "home"


def test_an_empty_period_counts_nothing(client: TestClient) -> None:
    page = get(client, "ada", "/admin/insights", start=at(30).isoformat(), end=at(31).isoformat())
    assert (
        page["funnel"]["created"] == 0
        and page["changed_rules"] == []
        and page["stop_reasons"] == []
    )
    assert page["time_to_decide"]["officer_decided"] == {
        "n": 0,
        "median_s": None,
        "slowest_s": None,
    }


def test_a_period_that_ends_before_it_starts_is_refused(client: TestClient) -> None:
    r = client.get("/api/v1/admin/insights", headers=login(client, "ada"),
                   params={"start": at(5).isoformat(), "end": at(1).isoformat()})  # fmt: skip
    assert r.status_code == 422


# --- who sees what ---------------------------------------------------------------------------
def test_routes_are_for_their_role_only(client: TestClient) -> None:
    for who, path in (("asha", "/admin/insights"), ("asha", "/auditor/insights"),
                      ("aud", "/admin/insights"), ("ada", "/auditor/insights"),
                      ("ada", "/me/insights"), ("aud", "/me/insights")):  # fmt: skip
        r = client.get(f"/api/v1{path}", headers=login(client, who))
        assert r.status_code == 403, (who, path)
    assert client.get("/api/v1/admin/insights").status_code == 401


def test_the_auditor_gets_the_same_counts_and_no_way_into_a_case(client: TestClient) -> None:
    admin = get(client, "ada", "/admin/insights")
    aud = get(client, "aud", "/auditor/insights")
    assert aud["funnel"] == admin["funnel"] and aud["agreement"] == admin["agreement"]
    assert aud["precedents"] == {"reached": 2, "moved": 1}
    assert [r["officer"] for r in aud["time_to_decide"]["by_officer"]] == [
        "Asha Officer",
        "Ben Officer",
    ]
    body = json.dumps(aud)
    assert not UUID_RE.search(body), "a case or user id reached the auditor"
    assert "CASE-" not in body and "/cases" not in body and "http" not in body

    def keys(v: Any) -> set[str]:
        if isinstance(v, dict):
            return set(v) | {k for x in v.values() for k in keys(x)}
        return {k for x in v for k in keys(x)} if isinstance(v, list) else set()

    assert not keys(aud) & {"cases", "moved_cases", "officer_id", "case_no", "id"}


def test_an_officer_sees_only_their_own_decisions(client: TestClient) -> None:
    asha = get(client, "asha", "/me/insights")
    ben = get(client, "ben", "/me/insights")
    pace = {"decided_30d": 2, "overdue": 0, "sla_working_days": 2}
    assert asha == {**pace, "median_decision_s": 36 * H}  # cases 1 and 2: 24 h, 48 h
    assert ben == {**pace, "median_decision_s": 2 * H}  # cases 3 and 4: 3 h, 1 h


# --- migration 0026 --------------------------------------------------------------------------
def test_migration_0026_backfills_both_times_and_rolls_back(clean_db_url: str) -> None:
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "0025")
    eng = create_engine(clean_db_url)
    t0 = datetime(2026, 11, 2, 10, tzinfo=UTC)
    with eng.begin() as c:
        user = c.execute(text("""INSERT INTO users (name, email, password_hash, role)
                                 VALUES ('O', 'o@example.test', 'x', 'officer') RETURNING id""")).scalar_one()  # fmt: skip
        ids = {}
        for no in (1, 2, 3):
            ids[no] = c.execute(
                text("""INSERT INTO cases (case_no, loan_type, created_by, status, created_at)
                        VALUES (:n, 'personal', :u, 'awaiting_confirmation', :t) RETURNING id"""),
                {"n": f"CASE-2026-{no:04d}", "u": user, "t": t0},
            ).scalar_one()  # fmt: skip
        for when in (t0 + timedelta(hours=2), t0 + timedelta(hours=1)):  # a retry: the first counts
            c.execute(text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, at)
                              VALUES (:u, 'case_submitted', 'case', :e, :t)"""),
                      {"u": user, "e": str(ids[1]), "t": when})  # fmt: skip
        for no, version, status, hours in ((1, 1, "stopped", 3), (1, 2, "awaiting_confirmation", 5),
                                           (2, 1, "awaiting_confirmation", 4)):  # fmt: skip
            c.execute(text("""INSERT INTO reports (case_id, version, report_json, created_at)
                              VALUES (:c, :v, CAST(:j AS jsonb), :t)"""),
                      {"c": ids[no], "v": version, "j": json.dumps({"status": status}),
                       "t": t0 + timedelta(hours=hours)})  # fmt: skip
    command.upgrade(cfg, "0026")
    with eng.connect() as c:
        got = {r.case_no: (r.submitted_at, r.report_ready_at) for r in c.execute(
            text("SELECT case_no, submitted_at, report_ready_at FROM cases"))}  # fmt: skip
    assert got["CASE-2026-0001"] == (t0 + timedelta(hours=1), t0 + timedelta(hours=5))
    assert got["CASE-2026-0002"] == (
        t0 + timedelta(hours=4),
        t0 + timedelta(hours=4),
    )  # no audit row
    assert got["CASE-2026-0003"] == (None, None)  # never submitted
    command.downgrade(cfg, "0025")
    with eng.connect() as c:
        cols = {r[0] for r in c.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'cases'"))}  # fmt: skip
    assert not cols & {"submitted_at", "report_ready_at"}
    eng.dispose()


def test_submit_and_report_set_the_times_once(engine: Engine) -> None:
    """`submitted_at` is set at the first run and never moved; `report_ready_at` at each report
    that waits for the officer, and not by a fix-type stop."""
    from app.agents import store  # noqa: PLC0415

    with engine.begin() as c:
        user = c.execute(text("""INSERT INTO users (name, email, password_hash, role)
                                 VALUES ('O', 'o@example.test', 'x', 'officer') RETURNING id""")).scalar_one()  # fmt: skip
        cid = c.execute(text("""INSERT INTO cases (case_no, loan_type, created_by, status)
                                VALUES ('CASE-2026-0001', 'personal', :u, 'uploaded') RETURNING id"""),
                        {"u": user}).scalar_one()  # fmt: skip
        store.update_case(c, cid, "running")
        first = c.execute(
            text("SELECT submitted_at FROM cases WHERE id = :c"), {"c": cid}
        ).scalar_one()
        c.execute(text("UPDATE cases SET submitted_at = submitted_at - interval '1 day' WHERE id = :c"),
                  {"c": cid})  # fmt: skip
        store.update_case(c, cid, "stopped")
        store.update_case(c, cid, "running")  # a resume after the fix
        row = c.execute(text("SELECT submitted_at, report_ready_at FROM cases WHERE id = :c"),
                        {"c": cid}).one()  # fmt: skip
        assert first is not None and row.submitted_at == first - timedelta(days=1)
        assert row.report_ready_at is None
        store.update_case(c, cid, "awaiting_confirmation")
        assert c.execute(text("SELECT report_ready_at FROM cases WHERE id = :c"),
                         {"c": cid}).scalar_one() is not None  # fmt: skip


def test_no_insights_code_calls_a_model() -> None:
    for f in ("app/reporting/insights.py", "app/api/insights.py"):
        src = (Path(__file__).resolve().parents[1] / f).read_text()
        assert not re.search(r"\b(llm|acompletion|litellm|ai_config)\b", src.lower()), f
