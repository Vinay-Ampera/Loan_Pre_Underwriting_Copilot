"""Metrics, JSON logs and content-free tracing. A fake Langfuse client records what would be sent."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, text

from app.agents.submission import load_case_dir
from app.db.migrate import alembic_config
from app.intake.masker import find_leaks
from app.observability import metrics, tracing
from app.observability.logs import JsonFormatter
from app.rag.index import reindex
from tests.rag_helpers import fake_embed_passages
from tests.test_pipeline import OUTPUT, ScriptedRouter, one_shot


class FakeObservation:
    def __init__(self, sent: list[dict[str, Any]], kwargs: dict[str, Any]) -> None:
        self.sent, self.record = sent, {"start": kwargs}
        sent.append(self.record)

    def update(self, **kw: Any) -> None:
        self.record["update"] = kw


class FakeLangfuse:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.scores: list[dict[str, Any]] = []

    @contextmanager
    def start_as_current_observation(self, **kw: Any) -> Iterator[FakeObservation]:
        yield FakeObservation(self.sent, kw)

    @staticmethod
    def create_trace_id(*, seed: str | None = None) -> str:
        return "t" + (seed or "").replace("-", "")[:31]

    def create_score(self, **kw: Any) -> None:
        self.scores.append(kw)

    def flush(self) -> None: ...


@pytest.fixture
def lf() -> Iterator[FakeLangfuse]:
    fake = FakeLangfuse()
    tracing.set_langfuse(fake)
    yield fake
    tracing.set_langfuse(None)


@pytest.fixture
def engine(clean_db_url: str) -> Iterator[Engine]:
    command.upgrade(alembic_config(clean_db_url), "head")
    eng = create_engine(clean_db_url)
    with eng.begin() as conn:
        reindex(conn, embed=fake_embed_passages)
    yield eng
    eng.dispose()


def test_json_log_line_has_the_standard_fields_and_extras() -> None:
    record = logging.LogRecord("loan_copilot", logging.INFO, "f.py", 1, "case finished", None, None)
    record.stage = "kyc"
    out = json.loads(JsonFormatter().format(record))
    assert out["level"] == "info" and out["event"] == "case finished" and out["stage"] == "kyc"


def test_metrics_endpoint_text_has_no_case_identifiers() -> None:
    metrics.CASES.labels("awaiting_confirmation", "refer").inc()
    body, _ = metrics.render()
    assert b"lc_cases_total" in body and b"SYN-" not in body


def test_tracing_is_a_no_op_without_a_client() -> None:
    tracing.set_langfuse(None)
    with tracing.stage_span("c1", "kyc"), tracing.generation("kyc") as done:
        done("m", 1, 2, 0.0, 5, False)
    tracing.score_case("c1", {"kyc.x": 1.0})  # nothing to send, nothing raised


def test_a_traced_call_carries_tokens_cost_and_latency_but_no_content(lf: FakeLangfuse) -> None:
    with tracing.stage_span("c1", "kyc"), tracing.generation("kyc") as done:
        done("groq/gpt", 120, 30, 0.002, 800, True)
    stage, gen = lf.sent
    assert stage["start"]["name"] == "kyc" and stage["start"]["trace_context"]["trace_id"]
    assert gen["update"]["usage_details"] == {"input": 120, "output": 30}
    assert gen["update"]["cost_details"] == {"total": 0.002}
    assert gen["update"]["metadata"] == {"latency_ms": 800, "fallback_used": True}
    assert not {"input", "output"} & (set(gen["start"]) | set(gen["update"]))


def test_a_tracing_failure_never_breaks_the_call() -> None:
    class Broken:
        def start_as_current_observation(self, **_: Any) -> Any:
            raise RuntimeError("langfuse is down")

        @staticmethod
        def create_trace_id(**_: Any) -> str:
            return "t"

    tracing.set_langfuse(Broken())
    try:
        with tracing.stage_span("c1", "kyc"), tracing.generation("kyc") as done:
            done("m", 1, 1, 0.0, 1, False)
    finally:
        tracing.set_langfuse(None)


@pytest.mark.db
def test_a_full_case_sends_per_agent_traces_and_scores_without_any_personal_data(
    engine: Engine, lf: FakeLangfuse
) -> None:
    state = one_shot(engine, "SYN-PL-D02", ScriptedRouter("good"))
    assert state["status"] == "awaiting_confirmation"
    names = {s["start"]["name"] for s in lf.sent}
    assert {"supervisor", "extraction", "kyc", "policy", "risk", "decision"} <= names
    generations = [s for s in lf.sent if "update" in s]
    assert generations and all(g["update"]["usage_details"]["input"] > 0 for g in generations)
    assert lf.scores and all(s["trace_id"] == lf.scores[0]["trace_id"] for s in lf.scores)
    blob = json.dumps(lf.sent, default=str) + json.dumps(lf.scores, default=str)
    assert find_leaks(blob) == []
    sub = load_case_dir(OUTPUT / "cases" / "SYN-PL-D02")
    for a in sub.application["applicants"]:  # no applicant name in what is sent
        assert a["full_name"].lower() not in blob.lower()
    with engine.connect() as c:
        ids = {r[0] for r in c.execute(text("SELECT langfuse_trace_id FROM llm_calls"))}
        assert ids == {lf.scores[0]["trace_id"]}
