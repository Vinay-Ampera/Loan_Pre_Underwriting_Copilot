"""Score a case: derive facts, run the rules stage by stage, stop early on a hard fail.

Stage groups run in pipeline order (docs/ARCHITECTURE.md): extraction -> kyc -> risk -> policy.
A hard-fail rule with `on_fail: stop` ends the run at the end of its group; later groups are not
run (their facts are never derived), the report is short, and no total is given:
  fix-type          fix_required   (correct the data and resume; not a final reject)
  eligibility-type  recommend_reject, with an indicative score capped below the refer band
"""

from typing import Any

from app.scoring import facts
from app.scoring.evaluate import RuleResult, band_for, evaluate_rule
from app.scoring.facts import Derived
from app.scoring.models import CaseInput, RuleOutcome, ScoreReport
from app.scoring.rules import Rule, RuleSet

# pipeline stage -> the rules-file stages it scores
STAGE_GROUPS: list[tuple[str, tuple[str, ...]]] = [
    ("extraction", ("documents",)),
    ("kyc", ("kyc",)),
    ("risk", ("income", "credit")),
    ("policy", ("policy",)),
]

RECOMMENDATION = {
    "approve": "recommend_approve",
    "refer": "refer",
    "reject": "recommend_reject",
}


def apply_precedent_bonus(
    total: float, band: str, capped: bool, bonus: float, ruleset: RuleSet
) -> tuple[float, str, float]:
    """Stub for the Stage 7 precedent bonus: (total, band, bonus actually applied).

    The bonus is clipped to the rules-file cap and only touches a refer-band case that no
    cap-to-refer rule is holding. Hard rules are never overridden. It is 0 until Stage 4/7
    supply a similarity-checked precedent.
    """
    cap = ruleset.precedent.bonus_max
    applied = max(0.0, min(bonus, cap))
    if applied == 0 or band != "refer" or capped:
        return total, band, 0.0
    new_total = min(round(total + applied, 2), 100.0)
    return new_total, band_for(new_total, ruleset), applied


def _outcome(r: RuleResult) -> RuleOutcome:
    return RuleOutcome(
        rule_id=r.rule_id, stage=r.stage, kind=r.kind,
        passed=r.passed, points_awarded=r.points_awarded, points_max=r.points_max,
        clause_id=r.clause_id, role=r.role, on_fail=r.on_fail, fail_class=r.fail_class,
        evidence=r.evidence,
    )  # fmt: skip


def _derive_group(
    group: str, inp: CaseInput, rs: RuleSet, d: Derived, state: dict[str, Any]
) -> None:
    if group == "extraction":
        facts.documents_facts(inp, rs, d)
    elif group == "kyc":
        facts.kyc_facts(inp, rs, d)
    elif group == "risk":
        state["hints"] = facts.income_facts(inp, rs, d)
        facts.credit_facts(inp, rs, d, state["hints"])
    elif group == "policy":
        facts.policy_facts(inp, rs, d)


def _stage_rules(rs: RuleSet, loan_type: str, stages: tuple[str, ...]) -> list[Rule]:
    return [r for r in rs.rules_for(loan_type) if r.stage in stages]


def score_case(inp: CaseInput, rs: RuleSet, *, precedent_bonus: float = 0.0) -> ScoreReport:
    d = facts.base_facts(inp, rs)
    results: list[RuleResult] = []
    stages_run: list[str] = []
    stopped_stage: str | None = None
    stop_class: str | None = None
    state: dict[str, Any] = {}

    for group, stages in STAGE_GROUPS:
        _derive_group(group, inp, rs, d, state)
        stages_run.append(group)
        here: list[RuleResult] = []
        for rule in _stage_rules(rs, inp.loan_type, stages):
            here.extend(evaluate_rule(rule, inp.loan_type, d.case, d.persons))
        if group == "kyc" and d.case["kyc_docs_complete"] is False:
            # a missing KYC document is reported once, by CM-DOC-01; checks that need it are skipped
            here = [r for r in here if not (r.kind == "hard" and r.evidence.get("value") is None
                                            and r.rule_id != "CM-DOC-01")]  # fmt: skip
        results.extend(here)
        stops = [r for r in here if not r.passed and r.on_fail == "stop"]
        if stops:
            stopped_stage = group
            stop_class = "fix" if any(r.fail_class == "fix" for r in stops) else "eligibility"
            break

    weights = rs.scoring.stage_weights
    stage_scores: dict[str, float] = {s: 0.0 for s in weights}
    for r in results:
        if r.kind == "soft":
            stage_scores[r.stage] += r.points_awarded
    stage_scores = {k: round(v, 2) for k, v in stage_scores.items()}

    capped = any(not r.passed and r.on_fail == "cap_refer" for r in results)
    total: float | None = None
    indicative: float | None = None
    band: str | None = None
    bonus = 0.0
    if stopped_stage is None:
        total = round(sum(stage_scores.values()), 2)
        band = band_for(total, rs)
        if capped and band == "approve":
            band = "refer"
        total, band, bonus = apply_precedent_bonus(total, band, capped, precedent_bonus, rs)
    elif stop_class == "eligibility":
        band = "reject"
        indicative = min(round(sum(stage_scores.values()), 2), rs.scoring.eligibility_score_cap)

    recommendation = "fix_required" if band is None else RECOMMENDATION[band]
    return ScoreReport(
        case_id=inp.case_id,
        loan_type=inp.loan_type,
        rules_version=rs.version,
        rules_checksum=rs.checksum,
        total_score=total,
        indicative_score=indicative,
        band=band,
        recommendation=recommendation,
        stage_scores=stage_scores,
        stage_max={k: float(v) for k, v in weights.items()},
        stopped_stage=stopped_stage,
        stop_class=stop_class,
        capped_to_refer=capped,
        precedent_bonus=bonus,
        failed_rule_ids=sorted({r.rule_id for r in results if not r.passed}),
        stages_run=stages_run,
        results=[_outcome(r) for r in results],
        findings=d.findings,
        case_facts=d.case,
        person_facts=d.persons,
    )
