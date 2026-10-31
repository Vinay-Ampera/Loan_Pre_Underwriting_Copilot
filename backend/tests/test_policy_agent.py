"""Policy agent with a fake LLM router: grounding, retry-once, unverified fallback, masking."""

import asyncio
import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Connection, create_engine

from app.agents.policy import build_queries, run_policy_agent
from app.db.migrate import alembic_config
from app.rag.index import reindex
from app.rag.policy_loader import load_all
from app.rag.retrieve import PolicyRetriever
from app.scoring.engine import score_case
from app.scoring.models import ScoreReport
from app.scoring.rules import RuleSet, load_rules
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector
from tests.scoring_cases import personal_case

pytestmark = pytest.mark.db


class FakeRouter:
    """Stands in for litellm's Router: each call returns the next scripted reply (or raises)."""

    def __init__(self, replies: list[Callable[[], str] | Exception]) -> None:
        self.replies = replies
        self.calls: list[list[dict[str, str]]] = []

    async def acompletion(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs["messages"])
        reply = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        msg = SimpleNamespace(content=reply())
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], model="fake", usage=usage)


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return load_rules()


@pytest.fixture
def conn(clean_db_url: str) -> Iterator[Connection]:
    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)
    with engine.connect() as c:
        reindex(c, embed=fake_embed_passages)
        yield c
    engine.dispose()


@pytest.fixture
def score(ruleset: RuleSet) -> ScoreReport:
    return score_case(personal_case(), ruleset)


def clause_text(clause_id: str) -> str:
    return next(c.text for d in load_all() for c in d.clauses if c.clause_id == clause_id)


def good_reply(score: ScoreReport) -> Callable[[], str]:
    out = next(r for r in score.results if r.clause_id.startswith("PL-"))
    quote = " ".join(clause_text(out.clause_id).split()[:6])
    body = {
        "fit_findings": [
            {
                "rule_id": out.rule_id,
                "clause_ids": [out.clause_id],
                "assessment": "fits",
                "statement": "The case meets this requirement.",
                "quote": quote,
            }
        ]  # fmt: skip
    }
    return lambda: json.dumps(body)


def bad_reply() -> str:
    body = {
        "fit_findings": [
            {
                "rule_id": None,
                "clause_ids": ["PL-FAKE-99"],
                "assessment": "concern",
                "statement": "Invented.",
                "quote": "nothing like this exists",
            }
        ]  # fmt: skip
    }
    return json.dumps(body)


def run(conn: Connection, router: FakeRouter, score: ScoreReport, ruleset: RuleSet) -> Any:
    retriever = PolicyRetriever(conn, embed=fake_vector, rerank_fn=fake_rerank)
    return asyncio.run(
        run_policy_agent(
            conn,
            router,
            personal_case(),
            score,
            ruleset,
            retriever=retriever,  # type: ignore[arg-type]
        )
    )


def test_grounded_answer_is_accepted_and_score_comes_from_code(
    conn: Connection, score: ScoreReport, ruleset: RuleSet
) -> None:
    router = FakeRouter([good_reply(score)])
    result = run(conn, router, score, ruleset)
    assert not result.unverified and not result.grounding_issues
    assert result.fit_findings and result.fit_findings[0].source == "model"
    assert result.score == score.stage_scores["policy"]
    assert len(router.calls) == 1
    retrieved_ids = {c.clause_id for c in result.clauses}
    assert {cid for f in result.fit_findings for cid in f.clause_ids} <= retrieved_ids


def test_invented_clause_is_retried_once_then_marked_unverified(
    conn: Connection, score: ScoreReport, ruleset: RuleSet
) -> None:
    router = FakeRouter([bad_reply])
    result = run(conn, router, score, ruleset)
    assert len(router.calls) == 2  # one retry, no more
    assert "failed these checks" in router.calls[1][1]["content"]
    assert result.unverified and result.grounding_issues
    assert all(f.source == "code" for f in result.fit_findings)
    retrieved_ids = {c.clause_id for c in result.clauses}
    assert {cid for f in result.fit_findings for cid in f.clause_ids} <= retrieved_ids


def test_retry_can_recover(conn: Connection, score: ScoreReport, ruleset: RuleSet) -> None:
    router = FakeRouter([bad_reply, good_reply(score)])
    result = run(conn, router, score, ruleset)
    assert len(router.calls) == 2 and not result.unverified
    assert result.tokens_in == 200  # both calls are counted for cost
    assert result.fit_findings[0].source == "model"


def test_extra_fields_such_as_a_score_are_rejected(
    conn: Connection, score: ScoreReport, ruleset: RuleSet
) -> None:
    body = json.dumps({"fit_findings": [], "score": 10, "recommendation": "approved"})
    result = run(conn, FakeRouter([lambda: body]), score, ruleset)
    assert result.unverified and result.score == score.stage_scores["policy"]


def test_provider_failure_does_not_fail_the_case(
    conn: Connection, score: ScoreReport, ruleset: RuleSet
) -> None:
    router = FakeRouter([RuntimeError("503 high demand")])
    result = run(conn, router, score, ruleset)
    assert result.unverified and result.grounding_issues == ["llm_error: RuntimeError"]
    assert result.clauses  # retrieval still delivered


def test_prompt_is_masked_and_treats_text_as_data(
    conn: Connection, score: ScoreReport, ruleset: RuleSet
) -> None:
    router = FakeRouter([good_reply(score)])
    run(conn, router, score, ruleset)
    sent = " ".join(m["content"] for m in router.calls[0])
    assert "ABCPS1234F" not in sent and "Rekha" not in sent
    assert "DATA" in router.calls[0][0]["content"]


def test_stopped_case_has_no_policy_score_and_no_precedents(
    conn: Connection, ruleset: RuleSet
) -> None:
    case = personal_case()
    case = case.model_copy(
        update={"persons": [case.persons[0].model_copy(update={"residential_status": "nri"})]}
    )
    stopped = score_case(case, ruleset)
    assert stopped.stop_class is not None
    retriever = PolicyRetriever(conn, embed=fake_vector, rerank_fn=fake_rerank)
    router = FakeRouter([lambda: json.dumps({"fit_findings": []})])
    result = asyncio.run(
        run_policy_agent(conn, router, case, stopped, ruleset, retriever=retriever)  # type: ignore[arg-type]
    )
    assert result.score is None and result.precedent_matches == []


def test_queries_are_built_from_rules_and_carry_no_personal_data(
    score: ScoreReport, ruleset: RuleSet
) -> None:
    queries = build_queries(personal_case(), score, ruleset)
    assert queries and len(queries) == len(set(queries))
    assert not any("Rekha" in q or "ABCPS" in q for q in queries)
