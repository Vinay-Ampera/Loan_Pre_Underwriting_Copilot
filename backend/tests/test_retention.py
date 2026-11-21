"""The retention job (Stage 11 security pass): bureau-derived data after six months, old staff
email. Throwaway database; the run checkpoints are stand-in tables in the `langgraph` schema."""

from typing import Any

import pytest
from sqlalchemy import Engine, text

from app.db import retention
from app.scoring.rules import load_rules
from tests.test_pipeline import engine, one_shot  # noqa: F401 - the fixture

pytestmark = pytest.mark.db
RS = load_rules()
BUREAU = set(retention.bureau_rule_ids(RS))


def _fake_checkpoints(engine: Engine, threads: list[str]) -> None:  # noqa: F811
    with engine.begin() as c:
        c.execute(text("CREATE SCHEMA IF NOT EXISTS langgraph"))
        for t in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            c.execute(text(f"CREATE TABLE IF NOT EXISTS langgraph.{t} (thread_id text, data text)"))
            for th in threads:
                c.execute(
                    text(f"INSERT INTO langgraph.{t} VALUES (:t, 'bureau record')"), {"t": th}
                )


def _evidence(engine: Engine, case_id: Any) -> dict[str, dict[str, Any]]:  # noqa: F811
    with engine.connect() as c:
        rows = c.execute(
            text("""SELECT rr.rule_id, rr.evidence, rr.passed FROM rule_results rr
                    JOIN stage_runs s ON s.id = rr.stage_run_id WHERE s.case_id = :c"""),
            {"c": case_id},
        ).all()  # fmt: skip
    return {r.rule_id: {**r.evidence, "_passed": r.passed} for r in rows}


def _count(engine: Engine, sql: str, **kw: Any) -> int:  # noqa: F811
    with engine.connect() as c:
        return int(c.execute(text(sql), kw).scalar_one())


def test_the_bureau_rules_are_the_credit_score_dpd_and_enquiry_rules() -> None:
    assert {"PL-CIBIL-01", "CM-CRD-10", "CM-CRD-12", "CM-CRD-13"} <= BUREAU
    assert not {r for r in BUREAU if "FOIR" in r or "KYC" in r}


def test_bureau_values_go_after_six_months_and_checkpoints_after_the_decision(
    engine: Engine,  # noqa: F811
) -> None:
    one_shot(engine, "SYN-PL-D02")
    with engine.begin() as c:
        old = c.execute(text("SELECT id FROM cases")).scalar_one()
    one_shot(engine, "SYN-PL-D03")  # a recent case: never touched
    with engine.begin() as c:
        new = c.execute(text("SELECT id FROM cases WHERE id <> :o"), {"o": old}).scalar_one()
        c.execute(text("UPDATE cases SET created_at = now() - interval '7 months' WHERE id = :c"),
                  {"c": old})  # fmt: skip
    _fake_checkpoints(engine, [str(old), str(new)])
    before = _evidence(engine, old)
    assert BUREAU & set(before) and all("removed" not in v for v in before.values())

    # still waiting for the officer: values go, the checkpoint stays (the run must resume)
    out = retention.run(engine, RS)
    assert out is not None and out.cases == 1 and out.rule_results >= 1 and out.reports == 1
    after = _evidence(engine, old)
    for rule, ev in after.items():
        if rule in BUREAU:
            assert ev["removed"] == retention.REMOVED and ev["_passed"] == before[rule]["_passed"]
            assert set(ev) <= {"removed", "role", "_passed"}
        else:
            assert ev == before[rule]  # every other rule keeps its evidence
    with engine.connect() as c:
        report = c.execute(text("SELECT report_json FROM reports WHERE case_id = :c"),
                           {"c": old}).scalar_one()  # fmt: skip
        stamped = c.execute(text("SELECT bureau_removed_at FROM cases WHERE id = :c"),
                            {"c": old}).scalar_one()  # fmt: skip
    for f in report["findings"]:
        if f["rule_id"] in BUREAU:
            assert f["evidence"] == {"removed": retention.REMOVED} and f["message"]
    assert stamped is None
    assert _count(engine, "SELECT count(*) FROM langgraph.checkpoints WHERE thread_id = :t",
                  t=str(old)) == 1  # fmt: skip

    # decided: the checkpoints go too and the case is stamped, once
    with engine.begin() as c:
        c.execute(text("UPDATE cases SET status = 'confirmed' WHERE id = :c"), {"c": old})
    out = retention.run(engine, RS)
    assert out is not None and out.checkpoints == 3 and out.rule_results == 0
    assert _count(engine, "SELECT count(*) FROM langgraph.checkpoints WHERE thread_id = :t",
                  t=str(old)) == 0  # fmt: skip
    assert _count(engine, "SELECT count(*) FROM langgraph.checkpoints WHERE thread_id = :t",
                  t=str(new)) == 1  # fmt: skip
    assert _count(engine, "SELECT count(*) FROM cases WHERE bureau_removed_at IS NOT NULL") == 1
    again = retention.run(engine, RS)
    assert again is not None and not again.changed
    assert _count(engine, "SELECT count(*) FROM audit_log WHERE action = 'retention_run'") == 2
    assert all("removed" not in v for v in _evidence(engine, new).values())


def test_old_staff_email_goes_but_a_queued_one_stays_and_a_dry_run_changes_nothing(
    engine: Engine,  # noqa: F811
) -> None:
    with engine.begin() as c:
        c.execute(text("""INSERT INTO users (name, email, password_hash, role)
                          VALUES ('R', 'r@example.test', 'x', 'officer')"""))  # fmt: skip
        uid = c.execute(text("SELECT id FROM users WHERE email = 'r@example.test'")).scalar_one()
        for status, days in (("sent", 100), ("failed", 120), ("queued", 100), ("sent", 10)):
            c.execute(
                text("""INSERT INTO email_outbox (user_id, kind, recipient, subject, body, status,
                            created_at) VALUES (:u, 'notice', 'r@example.test', 's', 'b', :s,
                            now() - make_interval(days => :d))"""),
                {"u": uid, "s": status, "d": days},
            )  # fmt: skip
    dry = retention.run(engine, RS, dry_run=True)
    assert dry is not None and dry.emails == 2
    assert _count(engine, "SELECT count(*) FROM email_outbox") == 4
    assert _count(engine, "SELECT count(*) FROM audit_log WHERE action = 'retention_run'") == 0
    out = retention.run(engine, RS)
    assert out is not None and out.emails == 2
    with engine.connect() as c:
        left = sorted(r[0] for r in c.execute(text("SELECT status FROM email_outbox")))
    assert left == ["queued", "sent"]


def test_two_processes_never_run_it_at_once(engine: Engine) -> None:  # noqa: F811
    with engine.connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(hashtext('retention_job'))"))
        assert retention.run(engine, RS) is None
        holder.execute(text("SELECT pg_advisory_unlock(hashtext('retention_job'))"))
    assert retention.run(engine, RS) is not None
