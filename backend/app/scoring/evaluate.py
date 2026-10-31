"""Reference evaluator: facts + rules file -> rule results, stage scores, band, stop.

Pure functions. This is the answer-key engine for the synthetic cases (Stage 1) and the base
the Stage 3 scorers build on (FOIR, age at maturity, matching and similar are computed there).

Facts shape
    case:     flat dict of case-level facts (aggregation rules are in rules.yaml's header)
    persons:  list of dicts, each with "role" (primary|co) plus person-level facts
"""

from dataclasses import dataclass, field
from typing import Any

from app.scoring.rules import Operator, Rule, RuleSet, Tier

# stage in the rules file -> pipeline stage that stops the run
STOP_STAGE = {
    "documents": "extraction",
    "kyc": "kyc",
    "income": "risk",
    "credit": "risk",
    "policy": "policy",
}
PIPELINE_ORDER = ["extraction", "kyc", "risk", "policy"]


class MissingFactError(KeyError):
    """A rule needs a fact the caller did not supply."""


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    stage: str
    kind: str
    passed: bool
    points_awarded: float
    points_max: float
    clause_id: str
    role: str | None = None
    on_fail: str | None = None
    fail_class: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseEvaluation:
    results: list[RuleResult]
    stage_scores: dict[str, float]
    total_score: float | None  # None when the run stopped early
    band: str | None  # approve | refer | reject; None for a fix-type stop
    stopped_stage: str | None
    stop_class: str | None
    capped_to_refer: bool
    failed_rule_ids: list[str]


def compare(op: Operator, value: Any, threshold: Any) -> bool:
    match op:
        case "gte":
            return bool(value >= threshold)
        case "lte":
            return bool(value <= threshold)
        case "gt":
            return bool(value > threshold)
        case "lt":
            return bool(value < threshold)
        case "eq":
            return bool(value == threshold)
        case "ne":
            return bool(value != threshold)
        case "in":
            return bool(value in threshold)


def _get(facts: dict[str, Any], name: str, rule_id: str) -> Any:
    if name not in facts:
        raise MissingFactError(f"{rule_id}: fact '{name}' missing")
    return facts[name]


def _applies(rule: Rule, loan_type: str, case: dict[str, Any]) -> bool:
    if loan_type not in rule.loan_types:
        return False
    return not rule.when or all(case.get(k) == v for k, v in rule.when.items())


def _tier_points(tiers: list[Tier], value: Any) -> float:
    for t in tiers:
        if compare(t.operator, value, t.threshold):
            return t.points
    return 0.0


def band_for(total: float, ruleset: RuleSet) -> str:
    b = ruleset.scoring.bands
    if total >= b["approve_min"]:
        return "approve"
    return "refer" if total >= b["refer_min"] else "reject"


def evaluate_case(
    ruleset: RuleSet, loan_type: str, case: dict[str, Any], persons: list[dict[str, Any]]
) -> CaseEvaluation:
    results: list[RuleResult] = []
    for rule in ruleset.rules_for(loan_type):
        results.extend(evaluate_rule(rule, loan_type, case, persons))
    return summarise(ruleset, results)


def evaluate_rule(
    rule: Rule, loan_type: str, case: dict[str, Any], persons: list[dict[str, Any]]
) -> list[RuleResult]:
    """Results of one rule: none when it does not apply, one per person for `each` hard rules."""
    if not _applies(rule, loan_type, case):
        return []
    if rule.kind == "hard":
        return _hard(rule, case, persons)
    return [_soft(rule, case)]


def summarise(ruleset: RuleSet, results: list[RuleResult]) -> CaseEvaluation:
    stage_scores: dict[str, float] = {s: 0.0 for s in ruleset.scoring.stage_weights}
    for r in results:
        if r.kind == "soft":
            stage_scores[r.stage] += r.points_awarded

    failed_stop = [r for r in results if not r.passed and r.on_fail == "stop"]
    stopped_stage = stop_class = None
    for agent_stage in PIPELINE_ORDER:
        here = [r for r in failed_stop if STOP_STAGE[r.stage] == agent_stage]
        if here:
            stopped_stage = agent_stage
            stop_class = "fix" if any(r.fail_class == "fix" for r in here) else "eligibility"
            break

    capped = any(not r.passed and r.on_fail == "cap_refer" for r in results)
    total: float | None = None
    band: str | None = None
    if stopped_stage is None:
        total = round(sum(stage_scores.values()), 2)
        band = band_for(total, ruleset)
        if capped and band == "approve":
            band = "refer"
    elif stop_class == "eligibility":
        band = "reject"

    return CaseEvaluation(
        results=results,
        stage_scores={k: round(v, 2) for k, v in stage_scores.items()},
        total_score=total,
        band=band,
        stopped_stage=stopped_stage,
        stop_class=stop_class,
        capped_to_refer=capped,
        failed_rule_ids=sorted({r.rule_id for r in results if not r.passed}),
    )


def _hard(rule: Rule, case: dict[str, Any], persons: list[dict[str, Any]]) -> list[RuleResult]:
    assert rule.operator is not None
    subjects: list[tuple[str | None, dict[str, Any]]]
    if rule.subject == "case":
        subjects = [(None, case)]
    else:
        subjects = [(p["role"], p) for p in persons if p["role"] in (rule.roles or [])]
    out = []
    for role, facts in subjects:
        value = _get(facts, rule.field, rule.rule_id)
        ok = value is not None and compare(rule.operator, value, rule.threshold)  # unverified fails
        out.append(
            RuleResult(
                rule_id=rule.rule_id, stage=rule.stage, kind="hard", passed=ok,
                points_awarded=0, points_max=0, clause_id=rule.policy_clause, role=role,
                on_fail=rule.on_fail, fail_class=rule.fail_class,
                evidence={"field": rule.field, "value": value, "threshold": rule.threshold},
            )
        )  # fmt: skip
    return out


def _soft(rule: Rule, case: dict[str, Any]) -> RuleResult:
    value = _get(case, rule.field, rule.rule_id)
    if value is None:  # could not be verified: no points
        pts = 0.0
    elif rule.tiers is not None:
        pts = _tier_points(rule.tiers, value)
    else:
        assert rule.operator is not None
        pts = rule.points if compare(rule.operator, value, rule.threshold) else 0.0
    return RuleResult(
        rule_id=rule.rule_id, stage=rule.stage, kind="soft", passed=pts == rule.points,
        points_awarded=pts, points_max=rule.points, clause_id=rule.policy_clause,
        evidence={"field": rule.field, "value": value},
    )  # fmt: skip
