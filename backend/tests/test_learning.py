"""Learning loop: override -> proposed precedent -> code check -> bonus on a similar case.

The hard-rule guarantee is tested twice: in the scoring engine (a stopped case ignores any bonus)
and end to end (an override that approves over a hard rule is `held`, never reaches retrieval).
"""

import asyncio
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from app.agents import store
from app.agents.checkpoint import memory_saver
from app.agents.graph import Pipeline
from app.db.migrate import alembic_config
from app.learning.bonus import precedent_bonus
from app.learning.proposal import code_summary, hard_rule_breach
from app.rag.index import reindex
from app.rag.precedents import precedent_text
from app.rag.schemas import PrecedentMatch
from app.scoring.engine import score_case
from app.scoring.rules import RuleSet, load_rules
from tests.rag_helpers import fake_embed_passages, fake_vector
from tests.scoring_cases import income_docs, kyc_docs, person, personal_case
from tests.test_pipeline import make_ctx, new_case


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        reindex(conn, embed=fake_embed_passages)
    yield eng
    eng.dispose()


REASON = "Stable business income is not fully captured by the statement analysis"


@pytest.fixture(scope="module")
def rs() -> RuleSet:
    return load_rules()


def _old_applicant() -> Any:
    docs = [*kyc_docs(dob="1973-01-01"), *income_docs()]
    return personal_case(persons=[person(dob=date(1973, 1, 1))], documents=docs, tenure_months=60)


def match(sim: float, decision: str = "approve", pid: str = "p1") -> PrecedentMatch:
    return PrecedentMatch(id=pid, similarity=sim, summary="x", final_decision=decision)


# --- the bonus is code, capped, and only from an "approve" precedent ----------------------------
def test_bonus_is_capped_and_scales_with_similarity(rs: RuleSet) -> None:
    bonus, used = precedent_bonus([match(0.9, pid="a"), match(0.85, pid="b")], rs)
    assert used == "a" and 0 < bonus <= rs.precedent.bonus_max
    assert bonus == round(rs.precedent.bonus_max * 0.9, 2)


def test_bonus_ignores_non_approve_and_low_similarity(rs: RuleSet) -> None:
    assert precedent_bonus([match(0.95, "reject"), match(0.95, "refer")], rs) == (0.0, None)
    assert precedent_bonus([match(rs.precedent.similarity_min - 0.01)], rs) == (0.0, None)
    assert precedent_bonus([], rs) == (0.0, None)


def test_a_stopped_case_ignores_any_bonus(rs: RuleSet) -> None:
    """Hard rules win: a fix-type stop, an eligibility stop and a cap-to-refer rule stay as they are."""
    case = personal_case(persons=[person().model_copy(update={"pan": "BAD"})])
    docs = [d for d in case.documents if d.doc_type != "pan_card"]
    stopped = score_case(case.model_copy(update={"documents": docs}), rs, precedent_bonus=99)
    assert stopped.recommendation == "fix_required" and stopped.precedent_bonus == 0.0
    assert stopped.total_score is None

    old = score_case(_old_applicant(), rs, precedent_bonus=99)
    assert old.band == "reject" and old.precedent_bonus == 0.0


def test_a_bonus_can_lift_the_label_of_a_borderline_case(rs: RuleSet) -> None:
    from app.scoring.engine import apply_precedent_bonus

    total, band, applied = apply_precedent_bonus(82.0, "refer", False, 4.5, rs)
    assert (band, applied) == ("approve", 4.5) and total == 86.5


# --- the code-side hard-rule check ----------------------------------------------------------------
def test_summary_is_masked_and_names_the_rules(rs: RuleSet) -> None:
    score = score_case(personal_case(), rs)
    out = code_summary(score, "refer", "approve", "Applicant 9876543210 has steady income")
    assert "refer" in out and "approve" in out and len(out) <= 600


def run_override(engine: Engine, case: str, final: str) -> tuple[Any, dict[str, Any]]:
    async def go() -> dict[str, Any]:
        async with memory_saver() as saver:
            sub, cid = new_case(engine, case)
            pipe = Pipeline(make_ctx(engine), saver)
            await pipe.start(sub, cid)
            with engine.begin() as conn:
                officer = store.ensure_system_user(conn)
            done = await pipe.officer_action(
                cid, action="override", second_click=True, officer_id=officer, reason=REASON,
                final_decision=final,
            )  # fmt: skip
            return dict(done["officer"])

    result = asyncio.run(go())
    return None, result


@pytest.mark.db
def test_override_creates_a_pending_precedent(engine: Engine) -> None:
    _, officer = run_override(engine, "SYN-PL-D03", "approve")
    assert officer["precedent"]["status"] == "pending"
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT status, loan_type, final_decision, embedding IS NULL AS no_emb FROM precedents"
            )
        ).one()
        assert tuple(row) == ("pending", "personal", "approve", True)  # the admin step adds it
        assert (
            c.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'precedent_proposed'")
            ).scalar_one()
            == 1
        )


@pytest.mark.db
def test_approving_over_a_hard_rule_is_held_and_never_retrieved(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)
    _, officer = run_override(engine, "SYN-PL-D11", "approve")  # eligibility stop -> reject
    assert officer["precedent"]["status"] == "held" and officer["precedent"]["held_reason"]
    with engine.connect() as c:
        assert c.execute(text("SELECT status FROM precedents")).scalar_one() == "held"


@pytest.mark.db
def test_hard_rule_breach_only_blocks_an_approve_override() -> None:
    from tests.test_pipeline import one_shot  # noqa: F401  (kept local: heavy import)

    score = score_case(_old_applicant(), load_rules())
    assert hard_rule_breach(score, "approve")
    assert hard_rule_breach(score, "reject") is None and hard_rule_breach(score, "refer") is None


@pytest.mark.db
def test_demo_override_approve_rerun_shows_the_precedent(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage 7 demo: override a borderline case, approve the precedent, rerun a similar case."""
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)
    base = _report(engine, "SYN-PL-D03")
    assert base["precedents"] == [] and base["precedent_bonus"] == 0.0

    run_override(engine, "SYN-PL-D03", "approve")
    with engine.begin() as c:  # the admin's approval, as the admin endpoint writes it
        row = c.execute(text("SELECT id, loan_type, rule_ids FROM precedents")).one()
        admin = store.ensure_system_user(c)
        vec = fake_vector(precedent_text(row.loan_type, row.rule_ids, "refer"))
        c.execute(
            text("""UPDATE precedents SET status = 'approved', reviewed_by = :u, reviewed_at = now(),
                    valid_until = :v, embedding = CAST(:e AS vector) WHERE id = :i"""),
            {"u": admin, "v": date.today() + timedelta(days=365), "e": str(vec), "i": row.id},
        )  # fmt: skip

    again = _report(engine, "SYN-PL-D03")
    assert again["precedents"] and again["precedents"][0]["id"] == str(row.id)
    assert 0 < again["precedent_bonus"] <= load_rules().precedent.bonus_max
    assert again["total_score"] == round(base["total_score"] + again["precedent_bonus"], 2)
    assert again["recommendation"] == "refer"  # the officer still confirms; label moves only at 85+
    with engine.connect() as c:
        assert c.execute(text("SELECT times_used FROM precedents")).scalar_one() == 1


@pytest.mark.db
def test_a_hard_fail_case_never_passes_because_of_a_precedent(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.rag.precedents.embed_passages", fake_embed_passages)
    run_override(engine, "SYN-PL-D03", "approve")
    with engine.begin() as c:
        row = c.execute(text("SELECT id, loan_type, rule_ids FROM precedents")).one()
        vec = fake_vector(precedent_text(row.loan_type, row.rule_ids, "refer"))
        c.execute(
            text("""UPDATE precedents SET status = 'approved', reviewed_by = :u, reviewed_at = now(),
                    valid_until = :v, embedding = CAST(:e AS vector) WHERE id = :i"""),
            {"u": store.ensure_system_user(c), "v": date.today() + timedelta(days=365),
             "e": str(vec), "i": row.id},
        )  # fmt: skip
    for case in ("SYN-PL-D11", "SYN-PL-D09", "SYN-PL-D12"):  # eligibility, fix and risk stops
        rep = _report(engine, case)
        assert rep["precedent_bonus"] == 0.0 and rep["precedents"] == []
        assert rep["recommendation"] in ("recommend_reject", "fix_required")


def _report(engine: Engine, case: str) -> dict[str, Any]:
    async def go() -> dict[str, Any]:
        async with memory_saver() as saver:
            sub, cid = new_case(engine, case)
            state = await Pipeline(make_ctx(engine), saver).start(sub, cid)
            return dict(state["report"])

    return asyncio.run(go())
