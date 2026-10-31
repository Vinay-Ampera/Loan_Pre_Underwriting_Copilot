"""Risk agent (runs beside Policy). FOIR, DTI, LTV, income checks, bank-statement behaviour,
bureau and tamper hints. Every number comes from the scoring engine and is recomputed here from
its parts; the model only explains flags and weak results. Output: `RiskResult`
(Income and FOIR 30 points, Credit and behaviour 25)."""

from typing import Any

from pydantic import BaseModel, Field

from app.agents.explain import explain
from app.agents.results import RuleCheck, checks_for, hard_fail, stage_points
from app.agents.runtime import AgentContext, prompt_text
from app.agents.state import LLMCallRecord
from app.intake import tamper
from app.intake.models import Transaction
from app.scoring import finance
from app.scoring.facts import earners, statement_for
from app.scoring.models import CaseInput, PersonInput, Role, ScoreReport
from app.scoring.rules import RuleSet

STAGES = ("income", "credit")
METRIC_KEYS = ("foir", "new_emi", "existing_emi_total", "dti_pct", "net_monthly_income",
               "income_verified_ratio", "income_regularity", "cibil_score",
               "cheque_nach_returns_12m", "bureau_dpd_max_12m", "enquiries_6m",
               "bank_credit_to_gst_ratio", "ltv_percent", "annual_turnover")  # fmt: skip


class RiskFlag(BaseModel):
    code: str
    message: str
    severity: str = "concern"  # info | concern
    rule_id: str | None = None
    role: str | None = None
    evidence: list[str] = Field(default_factory=list)  # statement rows or hint codes behind it
    explanation: str | None = None

    @property
    def key(self) -> str:
        return f"flag:{self.code}:{self.role or 'case'}"


class RiskResult(BaseModel):
    metrics: dict[str, float | None]
    per_person: list[dict[str, Any]]
    flags: list[RiskFlag]
    checks: list[RuleCheck]
    income_score: float
    behaviour_score: float
    income_max: float
    behaviour_max: float
    hard_fail: bool
    fail_class: str | None
    recomputed: dict[str, bool] = Field(default_factory=dict)
    unverified: bool = False
    llm_skipped: bool = False
    model: str | None = None
    prompt_version: int = 0
    retries: int = 0
    fallback_used: bool = False
    issues: list[str] = Field(default_factory=list)


def cross_document_hints(
    persons: list[PersonInput],
    payslip_nets: dict[Role, list[float]],
    txns_by_role: dict[Role, list[Transaction]],
) -> list[str]:
    """Hints that need two documents at once (EDGE_CASES E-12): does the payslip's net pay appear
    as a recurring bank credit, and are there large credits of unclear source? Salaried only."""
    out: list[str] = []
    for p in persons:
        nets, txns = sorted(payslip_nets.get(p.role, [])), txns_by_role.get(p.role, [])
        if p.employment_type != "salaried" or not nets or not txns:
            continue
        net = nets[len(nets) // 2]
        if h := tamper.salary_credit_hint(net, txns):
            out.append(h.code)
        out += [h.code for h in tamper.odd_credit_hints(txns, net)]
    return sorted(set(out))


def recompute(inp: CaseInput, rs: RuleSet, facts: dict[str, Any]) -> dict[str, bool]:
    """FOIR, DTI, LTV and the new instalment rebuilt from their parts with `finance.py`, then
    compared with what the engine reported. A difference means a bug, not a model error."""
    repay = inp.tenure_months - (
        int(inp.details.get("moratorium_months", 0)) if inp.loan_type == "education" else 0
    )
    new_emi = finance.emi(inp.loan_amount, rs.pricing.rate_pct[inp.loan_type], repay)
    existing = sum(
        loan.emi
        for p in inp.persons if p.bureau
        for loan in p.bureau.active_loans
        if loan.remaining_emis > rs.params.existing_loan_min_remaining_emis
    )  # fmt: skip
    income = facts.get("net_monthly_income")
    foir = finance.foir_pct(existing, new_emi, income) if income else None

    def same(a: float | None, b: float | None) -> bool:
        return a is None and b is None or (a is not None and b is not None and abs(a - b) <= 0.05)

    out = {"new_emi": same(round(new_emi, 2), facts.get("new_emi")),
           "existing_emi": same(round(existing, 2), facts.get("existing_emi_total")),
           "foir": same(foir, facts.get("foir"))}  # fmt: skip
    if facts.get("dti_pct") is not None and income:
        outstanding = sum(
            loan.emi * loan.remaining_emis
            for p in inp.persons if p.bureau
            for loan in p.bureau.active_loans
        )  # fmt: skip
        out["dti"] = same(
            finance.dti_pct(inp.loan_amount + outstanding, income * 12), facts["dti_pct"]
        )
    return out


def _flags(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    for p in earners(inp):
        st = statement_for(inp, p.role)
        if st is None:
            continue
        if st.returns:
            flags.append(RiskFlag(
                code="RETURNED_PAYMENTS", role=p.role, rule_id="BL-CRD-20" if inp.loan_type == "business" else None,
                message=f"{st.returns} returned cheque or NACH debit(s) in the statement",
                evidence=st.evidence,
            ))  # fmt: skip
        if st.months and st.income_months < st.months:
            flags.append(RiskFlag(
                code="IRREGULAR_INCOME", role=p.role, severity="info",
                message=f"Income credit in {st.income_months} of {st.months} statement months",
                evidence=[f"{st.income_months}/{st.months} months"],
            ))  # fmt: skip
    for f in score.findings:
        if f.code in ("TAMPER_SUSPECTED", "INCOME_EXCEEDS_BANK_CREDITS", "FOIR_OVER_CAP"):
            hints = (
                f.message.split(": ", 1)[1].split(", ")
                if f.code == "TAMPER_SUSPECTED"
                else [f.code]
            )
            flags.append(RiskFlag(code=f.code, message=f.message, rule_id=f.rule_id, role=f.role,
                                  evidence=hints))  # fmt: skip
    return flags


def _per_person(inp: CaseInput, rs: RuleSet) -> list[dict[str, Any]]:
    out = []
    for p in inp.persons:
        st = statement_for(inp, p.role)
        out.append({
            "role": p.role, "earner": p in earners(inp),
            "cibil_score": p.bureau.cibil_score if p.bureau else None,
            "active_loans": len(p.bureau.active_loans) if p.bureau else 0,
            "statement_months": st.months if st else None,
            "income_months": st.income_months if st else None,
            "returns": st.returns if st else None,
        })  # fmt: skip
    return out


async def run_risk_agent(
    ctx: AgentContext, inp: CaseInput, score: ScoreReport
) -> tuple[RiskResult, list[LLMCallRecord]]:
    rs = ctx.ruleset
    checks = checks_for(score, STAGES)
    fail, klass = hard_fail(checks)
    facts = score.case_facts
    metrics = {k: facts.get(k) for k in METRIC_KEYS if isinstance(facts.get(k), int | float | None)}
    flags = [f for f in _flags(inp, score, rs) if f.evidence]  # a flag without evidence is dropped
    inc, inc_max = stage_points(score, ("income",))
    beh, beh_max = stage_points(score, ("credit",))

    need = [c for c in checks if not c.clean]
    items = [
        {"key": c.key, "rule_id": c.rule_id, "result": c.message, "points": f"{c.points:g}/{c.points_max:g}"}
        for c in need
    ] + [{"key": f.key, "flag": f.code, "result": f.message, "evidence": f.evidence} for f in flags]  # fmt: skip
    texts, asked = await explain(ctx, "risk", "risk", items, "items")
    for c in need:
        c.explanation = texts.get(c.key)
    for f in flags:
        f.explanation = texts.get(f.key)
    return (
        RiskResult(
            metrics=metrics,
            per_person=_per_person(inp, rs),
            flags=flags,
            checks=checks,
            income_score=inc,
            behaviour_score=beh,
            income_max=inc_max,
            behaviour_max=beh_max,
            hard_fail=fail,
            fail_class=klass,
            recomputed=recompute(inp, rs, facts),
            unverified=asked.unverified,
            llm_skipped=asked.skipped or not items,
            model=asked.model,
            prompt_version=prompt_text("risk")[1],
            retries=asked.retries,
            fallback_used=asked.fallback_used,
            issues=asked.issues,
        ),
        asked.calls,
    )
