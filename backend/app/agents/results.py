"""Stage results shared by the agents, the report and the database writer."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.scoring.models import RuleOutcome, ScoreReport

StageStatus = Literal["passed", "failed", "stopped", "unverified"]


class RuleCheck(BaseModel):
    """One rule result as shown to the officer: the code's outcome plus an optional explanation."""

    rule_id: str
    clause_id: str
    stage: str
    role: str | None = None
    kind: Literal["hard", "soft"]
    passed: bool
    points: float
    points_max: float
    on_fail: str | None = None
    fail_class: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    message: str = ""  # written by code from the evidence
    explanation: str | None = None  # written by the model, checked by guardrails

    @property
    def key(self) -> str:
        return f"{self.rule_id}:{self.role}" if self.role else self.rule_id

    @property
    def clean(self) -> bool:
        return self.passed and self.points >= self.points_max


def evidence_text(ev: dict[str, Any]) -> str:
    value, threshold = ev.get("value"), ev.get("threshold")
    field = str(ev.get("field", "value")).replace("_", " ")
    if value is None:
        return f"{field}: could not be verified"
    text = f"{field}: {value}"
    return f"{text} (needed {threshold})" if threshold is not None else text


def message_for(r: RuleOutcome) -> str:
    tail = evidence_text(r.evidence)
    if r.kind == "hard":
        verdict = "passed" if r.passed else "failed"
        return f"{r.rule_id} {verdict}: {tail}"
    return f"{r.rule_id} earned {r.points_awarded:g} of {r.points_max:g} points: {tail}"


def checks_for(score: ScoreReport, stages: tuple[str, ...]) -> list[RuleCheck]:
    return [
        RuleCheck(
            rule_id=r.rule_id, clause_id=r.clause_id, stage=r.stage, role=r.role, kind=r.kind,
            passed=r.passed, points=r.points_awarded, points_max=r.points_max,
            on_fail=r.on_fail, fail_class=r.fail_class, evidence=r.evidence, message=message_for(r),
        )
        for r in score.results
        if r.stage in stages
    ]  # fmt: skip


def stage_points(score: ScoreReport, stages: tuple[str, ...]) -> tuple[float, float]:
    return (
        round(sum(score.stage_scores.get(s, 0.0) for s in stages), 2),
        round(sum(score.stage_max.get(s, 0.0) for s in stages), 2),
    )


def hard_fail(checks: list[RuleCheck]) -> tuple[bool, str | None]:
    """(is there a stopping failure, its class). Fix wins over eligibility, as in the engine."""
    stops = [c for c in checks if not c.passed and c.on_fail == "stop"]
    if not stops:
        return False, None
    return True, "fix" if any(c.fail_class == "fix" for c in stops) else "eligibility"
