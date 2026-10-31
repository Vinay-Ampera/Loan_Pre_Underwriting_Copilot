"""KYC and compliance agent. Rule outcomes come from the scoring engine; the model only explains
the checks that did not pass cleanly. Output: `KycResult` (20 points)."""

from typing import Any

from pydantic import BaseModel, Field

from app.agents.explain import explain
from app.agents.results import RuleCheck, checks_for, hard_fail, stage_points
from app.agents.runtime import AgentContext, prompt_text
from app.agents.state import LLMCallRecord
from app.scoring.models import CaseInput, ScoreReport

STAGES = ("kyc",)


class KycResult(BaseModel):
    checks: list[RuleCheck]
    hard_fail: bool
    fail_class: str | None
    score: float
    max_score: float
    notes: list[str] = Field(default_factory=list)  # name variants, PAN mismatches
    unverified: bool = False
    llm_skipped: bool = False
    model: str | None = None
    prompt_version: int = 0
    retries: int = 0
    fallback_used: bool = False
    issues: list[str] = Field(default_factory=list)


def _item(c: RuleCheck) -> dict[str, Any]:
    return {"key": c.key, "rule_id": c.rule_id, "role": c.role, "passed": c.passed,
            "points": f"{c.points:g}/{c.points_max:g}", "result": c.message}  # fmt: skip


async def run_kyc_agent(
    ctx: AgentContext, inp: CaseInput, score: ScoreReport
) -> tuple[KycResult, list[LLMCallRecord]]:
    checks = checks_for(score, STAGES)
    fail, klass = hard_fail(checks)
    pts, mx = stage_points(score, STAGES)
    notes = [
        f.message for f in score.findings if f.code in ("NAME_VARIANT", "PAN_MISMATCH_INCOME_DOC")
    ]
    need = [c for c in checks if not c.clean]
    items = [_item(c) for c in need]
    texts, asked = await explain(ctx, "kyc", "kyc", items, "checks")
    for c in need:
        c.explanation = texts.get(c.key)
    return (
        KycResult(
            checks=checks,
            hard_fail=fail,
            fail_class=klass,
            score=pts,
            max_score=mx,
            notes=notes,
            unverified=asked.unverified,
            llm_skipped=asked.skipped or not items,
            model=asked.model,
            prompt_version=prompt_text("kyc")[1],
            retries=asked.retries,
            fallback_used=asked.fallback_used,
            issues=asked.issues,
        ),
        asked.calls,
    )
