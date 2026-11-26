"""The counter-offer box (Stage 12 Part A): other amounts or tenures that would move the band up.

Code only, no model and no database. The case is scored again by `engine.score_case` with only
`loan_amount` and `tenure_months` changed; everything else stays as checked, including the
precedent bonus the real run got (EDGE_CASES E-107). Tenure limits are read from the product's
own tenure rule and the age-at-maturity rule (E-110). The box is shown only when it helps:

  - band reject or refer (`counter_offer.bands`); a refer case held by a cap rule gets none (E-108);
  - points were lost on a rule that reads a fact amount or tenure can move (`moves_fields`);
  - a rescored line really reaches a higher band, at no less than `min_share` of the amount asked.

At most two lines: (a) the same amount over the shortest longer whole-year tenure that moves the
band; (b) the largest smaller amount, in `amount_step` steps, at the longest allowed tenure that
moves it further than (a). A run stopped only by the age-at-maturity rule gets one tenure line and
no band (E-109). An alternate-product line is added only inside a box that already shows a line
(E-111). Wording is "recommended", never "approved"; the box never reaches a prompt or a customer
message (E-112).
"""

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.scoring import facts, finance
from app.scoring.engine import score_case
from app.scoring.models import CaseInput, PersonInput, ScoreReport
from app.scoring.rules import RuleSet

TITLE = "Other amounts or tenures (estimate)"
INTRO = (
    "Worked out in code from this case's checked figures. For you to discuss with the applicant; "
    "it does not change the score or the recommendation."
)
FOOTER = (
    "Rate from the bank's rules file. Your decision is still needed. Not for customer messages."
)
NOT_SCORED = "Not scored"

RANK = {"reject": 0, "refer": 1, "approve": 2}
# rule facts that hold a tenure, and the months in one unit of each
TENURE_UNITS = {"tenure_months": 1, "repayment_years": 12}
ARTICLE = {"education": "an"}
DOC_LABEL = {
    "payslip": "payslips", "bank_statement": "bank statements", "form16": "Form 16",
    "itr": "income tax returns", "pnl_balance_sheet": "profit and loss account and balance sheet",
    "gst_registration": "GST registration", "gst_returns": "GST returns",
    "udyam_certificate": "Udyam certificate", "business_proof": "business proof",
    "sale_agreement": "sale agreement", "title_deed": "title deed",
    "encumbrance_certificate": "encumbrance certificate", "approved_plan": "approved building plan",
    "admission_letter": "admission letter", "fee_structure": "fee structure",
    "marksheet": "marksheet", "dealer_invoice": "dealer invoice",
    "driving_licence": "driving licence", "rc_book": "registration certificate",
    "insurance": "insurance policy",
}  # fmt: skip


class OfferLine(BaseModel):
    kind: Literal["tenure", "amount", "age_tenure", "alternate"]
    loan_type: str
    amount: float | None = None
    tenure_months: int
    rate_pct: float | None = None
    emi: float | None = None
    foir: float | None = None
    band: Literal["approve", "refer"] | None = None  # None: not scored
    scored: bool
    extra_documents: list[str] = Field(default_factory=list)
    text: str
    tags: list[str] = Field(default_factory=list)


class CounterOffer(BaseModel):
    rules_version: str
    lines: list[OfferLine] = Field(min_length=1)


# --- wording --------------------------------------------------------------------------------
def _grouped(n: int) -> str:
    """Indian digit grouping: 1234567 -> 12,34,567."""
    s = str(abs(n))
    head, tail = s[:-3], s[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ("-" if n < 0 else "") + ",".join([*parts, tail])


def inr(amount: float) -> str:
    return f"₹{_grouped(round(amount))}"


def inr_short(amount: float) -> str:
    """₹6.3L, ₹1.25Cr; below a lakh in full."""
    for size, unit in ((10_000_000, "Cr"), (100_000, "L")):
        if amount >= size:
            return f"₹{f'{amount / size:.2f}'.rstrip('0').rstrip('.')}{unit}"
    return inr(amount)


def tenure_words(months: int) -> str:
    if months % 12:
        return f"{months} months"
    years = months // 12
    return f"{years} year{'s' if years != 1 else ''}"


# --- limits ---------------------------------------------------------------------------------
def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _moratorium(inp: CaseInput) -> int:
    return int(inp.details.get("moratorium_months", 0)) if inp.loan_type == "education" else 0


def tenure_limit(rs: RuleSet, loan_type: str, case: dict[str, Any] | None) -> int | None:
    """Longest tenure, in repayment months, that the product's tenure rule allows. With the case's
    facts only the rule that applies to it counts (the vehicle kind); without them, the longest."""
    limits: list[int] = []
    for r in rs.rules_for(loan_type):
        unit = TENURE_UNITS.get(r.field)
        value = _number(r.threshold)
        if r.kind != "soft" or r.operator != "lte" or unit is None or value is None:
            continue
        if case is not None and r.when and any(case.get(k) != v for k, v in r.when.items()):
            continue
        limits.append(int(value * unit))
    if not limits:
        return None if case is None else tenure_limit(rs, loan_type, None)
    return min(limits) if case is not None else max(limits)


def age_cap_months(persons: list[PersonInput], inp: CaseInput, cap: int, upper: int) -> int:
    """The longest tenure up to `upper` that keeps every person at `cap` or under at maturity."""
    for months in range(upper, 0, -1):
        end = finance.add_months(inp.application_date, months)
        if all(finance.age_on(p.dob, end) <= cap for p in persons):
            return months
    return 0


def _case_limit(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> int:
    product = tenure_limit(rs, inp.loan_type, score.case_facts)
    upper = (product + _moratorium(inp)) if product is not None else inp.tenure_months
    return age_cap_months(inp.persons, inp, rs.age.max_age_at_maturity, upper)


# --- rescoring ------------------------------------------------------------------------------
def _rescore(inp: CaseInput, rs: RuleSet, amount: float, tenure: int, bonus: float) -> ScoreReport:
    changed = inp.model_copy(update={"loan_amount": amount, "tenure_months": tenure})
    return score_case(changed, rs, precedent_bonus=bonus)


def _rank(r: ScoreReport) -> int:
    return -1 if r.stopped_stage is not None or r.band is None else RANK[r.band]


def _moves(score: ScoreReport, rs: RuleSet) -> bool:
    field_of = {r.rule_id: r.field for r in rs.rules}
    return any(
        o.kind == "soft"
        and o.points_awarded < o.points_max
        and field_of.get(o.rule_id) in rs.counter_offer.moves_fields
        for o in score.results
    )


def _scored_line(
    kind: Literal["tenure", "amount"], inp: CaseInput, rs: RuleSet, amount: float, tenure: int,
    r: ScoreReport,
) -> OfferLine:  # fmt: skip
    emi = float(r.case_facts["new_emi"])
    foir = r.case_facts.get("foir")
    words = tenure_words(tenure) + (" including the moratorium" if _moratorium(inp) else "")
    ratio = f" (FOIR {foir:.1f}%)" if foir is not None else ""
    text = (f"Pramaan estimates {inr_short(amount)} over {words} would be recommended "
            f"for {r.band}{ratio}.")  # fmt: skip
    return OfferLine(
        kind=kind, loan_type=inp.loan_type, amount=amount, tenure_months=tenure,
        rate_pct=rs.pricing.rate_pct[inp.loan_type], emi=round(emi, 2), foir=foir,
        band=r.band, scored=True, text=text, tags=[f"EMI {inr(emi)}"],
    )  # fmt: skip


def _amount_and_tenure_lines(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> list[OfferLine]:
    co = rs.counter_offer
    bonus = score.precedent_bonus  # the bonus the real run got, unchanged (E-107)
    now = RANK[score.band or "reject"]
    limit = _case_limit(inp, score, rs)
    base = _moratorium(inp)
    whole = list(range(base + co.tenure_step_months, limit + 1, co.tenure_step_months))
    lines: list[OfferLine] = []

    reached = now
    for months in (t for t in whole if t > inp.tenure_months):  # (a) same amount, longer
        r = _rescore(inp, rs, inp.loan_amount, months, bonus)
        if _rank(r) > now:
            lines.append(_scored_line("tenure", inp, rs, inp.loan_amount, months, r))
            reached = _rank(r)
            break

    if reached < RANK["approve"]:  # (b) the largest smaller amount at the longest tenure
        allowed = [*whole, *([inp.tenure_months] if inp.tenure_months <= limit else [])]
        if allowed:
            months = max(allowed)
            step = co.amount_step
            floor = co.min_share * inp.loan_amount
            amount = (math.ceil(inp.loan_amount / step) - 1) * step
            while amount >= floor and amount > 0:
                r = _rescore(inp, rs, amount, months, bonus)
                if _rank(r) > reached:
                    lines.append(_scored_line("amount", inp, rs, amount, months, r))
                    break
                amount -= step
    return lines


# --- the age stop ---------------------------------------------------------------------------
def _age_line(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> OfferLine | None:
    """Stopped only by age at maturity: the longest tenure that keeps everyone within the cap.
    Income was never checked, so there is no rescoring and no band (E-109)."""
    if score.stop_class != "eligibility":
        return None
    field_of = {r.rule_id: r.field for r in rs.rules}
    failed = {field_of.get(o.rule_id) for o in score.results if o.kind == "hard" and not o.passed}
    if failed != {"age_at_maturity"}:
        return None
    product = tenure_limit(rs, inp.loan_type, score.case_facts)
    base = _moratorium(inp)
    upper = inp.tenure_months - 1
    if product is not None:
        upper = min(upper, product + base)
    cap = rs.age.max_age_at_maturity
    months = age_cap_months(inp.persons, inp, cap, upper)
    if months - base < rs.counter_offer.min_tenure_months:
        return None
    return OfferLine(
        kind="age_tenure", loan_type=inp.loan_type, tenure_months=months, scored=False,
        text=(f"A tenure of up to {months} months keeps every applicant at {cap} or under at "
              "maturity. Not scored: the assessment stopped before income was checked."),
    )  # fmt: skip


# --- the alternate product ------------------------------------------------------------------
def _mentions(text: str, keywords: list[str]) -> bool:
    for k in keywords:
        pattern = r"(?<!\w)" + re.escape(k.strip()).replace(r"\ ", " ").replace(" ", r"\s+")
        if re.search(pattern + r"(?!\w)", text, re.I):
            return True
    return False


def _extra_documents(inp: CaseInput, rs: RuleSet, target: str, employment: str) -> list[str]:
    """What a new application for `target` asks for that this loan does not (by type)."""
    own_roles = {p.role: p.employment_type for p in inp.persons}
    own = {r.type for r in facts.applicable_requirements(rs, inp.loan_type, own_roles, inp.details)}
    roles = {"primary": employment}
    if target == "education":  # the student applies; the earner is the co-applicant
        roles = {"primary": "student", "co": employment}
    out: list[str] = []
    for req in facts.applicable_requirements(rs, target, roles, {}):  # type: ignore[arg-type]
        if req.kyc or req.type in own:
            continue
        label = " or ".join(DOC_LABEL.get(t, t.replace("_", " ")) for t in req.any_of or [req.type])
        if label not in out:
            out.append(label)
    return out


def _alternate_line(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> OfferLine | None:
    co = rs.counter_offer
    hits = [lt for lt, alt in co.alternate_products.items()
            if lt != inp.loan_type and _mentions(inp.purpose, alt.keywords)]  # fmt: skip
    if len(hits) != 1:
        return None
    target = hits[0]
    earners = facts.earners(inp)
    if not earners or earners[0].employment_type not in co.alternate_products[target].employment:
        return None
    income = score.case_facts.get("net_monthly_income")
    case_foir = score.case_facts.get("foir")
    upper = tenure_limit(rs, target, None)
    if not income or case_foir is None or upper is None:
        return None
    reach = age_cap_months(inp.persons, inp, rs.age.max_age_at_maturity, upper)
    months = reach // co.tenure_step_months * co.tenure_step_months
    if months < co.min_tenure_months:
        return None
    rate = rs.pricing.rate_pct[target]
    emi = finance.emi(inp.loan_amount, rate, months)
    foir = finance.foir_pct(float(score.case_facts.get("existing_emi_total") or 0), emi, income)
    if foir is None or foir >= case_foir:
        return None
    extra = _extra_documents(inp, rs, target, earners[0].employment_type)
    need = f" It would also need: {', '.join(extra)}." if extra else ""
    text = (
        f"The stated purpose fits {ARTICLE.get(target, 'a')} {target} loan: "
        f"{inr_short(inp.loan_amount)} over {tenure_words(months)} at {rate:g}%, EMI {inr(emi)}, "
        f"FOIR {foir:.1f}%. A new application, not scored.{need}"
    )
    return OfferLine(
        kind="alternate", loan_type=target, amount=inp.loan_amount, tenure_months=months,
        rate_pct=rate, emi=round(emi, 2), foir=foir, scored=False, extra_documents=extra,
        text=text, tags=[NOT_SCORED],
    )  # fmt: skip


# --- the box --------------------------------------------------------------------------------
def build_counter_offer(inp: CaseInput, score: ScoreReport, rs: RuleSet) -> CounterOffer | None:
    """The box for this run's report, or None when it would not help."""
    if score.stopped_stage is not None:
        age = _age_line(inp, score, rs)
        return CounterOffer(rules_version=rs.version, lines=[age]) if age else None
    if score.band not in rs.counter_offer.bands:
        return None
    if score.band == "refer" and score.capped_to_refer:
        return None  # no amount or tenure clears a cap rule (E-108)
    if not _moves(score, rs):
        return None
    lines = _amount_and_tenure_lines(inp, score, rs)
    if not lines:
        return None
    alternate = _alternate_line(inp, score, rs)
    if alternate:
        lines.append(alternate)
    return CounterOffer(rules_version=rs.version, lines=lines)
