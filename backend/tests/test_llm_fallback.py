"""A 429 from the primary model must hand the call to the fallback (Stage 5 exit criterion).

Uses LiteLLM's own `mock_response`, so the real Router runs its real fallback logic with no
network and no API key: the primary raises `RateLimitError`, the fallback returns canned JSON.
"""

import asyncio
from typing import Any

from app.agents.runtime import AgentContext, Services, ask
from app.agents.supervisor import Briefing
from app.scoring.rules import load_rules
from app.services.llm import build_router, complete


def _config(primary_reply: str, fallback_reply: str) -> dict[str, Any]:
    return {
        "providers": {
            "primary": {"model": "gemini/gemini-test-primary", "key": "gemini_api_key",
                        "mock_response": primary_reply},
            "backup": {"model": "groq/openai/gpt-oss-test-backup", "key": "groq_api_key",
                       "mock_response": fallback_reply},
        },
        "roles": {"supervisor": {"primary": "primary", "fallbacks": ["backup"]}},
        "router": {"num_retries": 0, "timeout": 10, "cooldown_time": 1},
    }  # fmt: skip


MESSAGES = [{"role": "system", "content": "Reply with JSON."}, {"role": "user", "content": "go"}]


def test_429_on_the_primary_is_answered_by_the_fallback() -> None:
    router = build_router(config=_config("litellm.RateLimitError", '{"notes": "from the backup"}'))
    res = asyncio.run(complete(router, "supervisor", MESSAGES, Briefing))
    assert res.output.notes == "from the backup"
    assert res.fallback_used is True
    assert res.latency_ms >= 0 and res.cost_usd == 0.0


def test_a_healthy_primary_is_not_reported_as_a_fallback() -> None:
    router = build_router(config=_config('{"notes": "from the primary"}', '{"notes": "backup"}'))
    res = asyncio.run(complete(router, "supervisor", MESSAGES, Briefing))
    assert res.output.notes == "from the primary" and res.fallback_used is False


def test_ask_retries_once_then_reports_unverified() -> None:
    """The model keeps answering with banned wording: one retry, then `unverified`, no exception."""
    router = build_router(config=_config('{"notes": "The loan is approved."}', "{}"))
    ctx = AgentContext(ruleset=load_rules(), engine=None, router=router,  # type: ignore[arg-type]
                       services=Services.from_store())  # fmt: skip
    from app.agents.guardrails import check_text

    asked = asyncio.run(ask(ctx, "supervisor", "supervisor", lambda issues: MESSAGES, Briefing,
                            lambda o: check_text(o.notes)))  # fmt: skip
    assert asked.output is None and asked.unverified and asked.retries == 1
    assert len(asked.calls) == 2 and any("approved" in i for i in asked.issues)


def test_ask_without_a_router_is_skipped_not_unverified() -> None:
    ctx = AgentContext(ruleset=load_rules(), engine=None, router=None,  # type: ignore[arg-type]
                       services=Services.from_store())  # fmt: skip
    asked = asyncio.run(
        ask(ctx, "supervisor", "supervisor", lambda i: MESSAGES, Briefing, lambda o: [])
    )
    assert asked.skipped and not asked.unverified and asked.output is None
