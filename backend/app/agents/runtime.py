"""What every node needs: rules, database, mock services, the model router; and the one place a
node asks a model something (`ask`): validate, run guardrails, retry once with the reasons, and
return `unverified` instead of raising when the model still fails.
"""

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litellm.router import Router
from pydantic import BaseModel
from sqlalchemy import Connection, Engine

from app.agents.state import LLMCallRecord
from app.intake.masker import MaskingError
from app.rag.retrieve import PolicyRetriever
from app.scoring.rules import RuleSet
from app.services.llm import LLMOutputError, LLMResult, complete
from app.services.mock_services import (
    BureauService,
    GstService,
    IdentityService,
    RecordStore,
)

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


def prompt_text(name: str) -> tuple[str, int]:
    """(prompt body without its header, version) for `prompts/<name>.md`."""
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    header, _, body = raw.partition("-->")
    version = int(header.split("version:")[1].split("|")[0].strip())
    return body.strip(), version


@dataclass
class Services:
    identity: IdentityService
    bureau: BureauService
    gst: GstService

    @classmethod
    def from_store(cls, store: RecordStore | None = None) -> "Services":
        store = store or RecordStore()
        return cls(IdentityService(store), BureauService(store), GstService(store))


@dataclass
class AgentContext:
    ruleset: RuleSet
    engine: Engine
    services: Services
    router: Router | None  # None = offline run: models are skipped, code writes the text
    retriever_factory: Callable[[Connection], PolicyRetriever] | None = None
    crash_before: str | None = None  # test hook: die as this stage begins (checkpoint is kept)
    crash_action: Callable[[], None] = lambda: os._exit(137)  # tests swap in a raise
    intake_slots: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))
    judge_inconclusive: bool = True
    intake_cache: Path | None = None  # dev speed-up for repeated evaluation runs; off by default


def to_record(stage: str, role: str, res: LLMResult[Any]) -> LLMCallRecord:
    return LLMCallRecord(
        stage=stage, role=role, provider=res.provider, model=res.model,
        tokens_in=res.tokens_in, tokens_out=res.tokens_out, cost_usd=res.cost_usd,
        latency_ms=res.latency_ms, fallback_used=res.fallback_used,
    )  # fmt: skip


@dataclass
class Asked[T: BaseModel]:
    output: T | None
    calls: list[LLMCallRecord] = field(default_factory=list)
    retries: int = 0
    issues: list[str] = field(default_factory=list)
    skipped: bool = False  # no router: the caller writes the text itself

    @property
    def unverified(self) -> bool:
        return self.output is None and not self.skipped

    @property
    def model(self) -> str | None:
        return self.calls[-1].model if self.calls else None

    @property
    def fallback_used(self) -> bool:
        return any(c.fallback_used for c in self.calls)


async def ask[T: BaseModel](
    ctx: AgentContext,
    stage: str,
    role: str,
    build: Callable[[list[str]], list[dict[str, str]]],
    schema: type[T],
    check: Callable[[T], list[str]],
    max_tokens: int = 1500,
) -> Asked[T]:
    """One model call with the gate rules: schema, guardrails, one retry with the reasons fed
    back, then `unverified`. `build(issues)` makes the (already masked) messages."""
    if ctx.router is None:
        return Asked(output=None, skipped=True)
    out = Asked[T](output=None)
    issues: list[str] = []
    for attempt in range(2):
        out.retries = attempt
        try:
            res = await complete(ctx.router, role, build(issues), schema, max_tokens=max_tokens)
        except LLMOutputError as exc:
            issues = [f"reply was not valid JSON for the schema ({exc})"]
            continue
        except MaskingError:
            issues = ["blocked: the prompt held a raw identifier"]
            break  # retrying the same prompt cannot help
        except Exception as exc:  # provider outage after every fallback: do not fail the case
            issues = [f"model unavailable ({type(exc).__name__})"]
            break
        out.calls.append(to_record(stage, role, res))
        issues = check(res.output)
        if not issues:
            out.output = res.output
            break
    out.issues = issues
    return out
