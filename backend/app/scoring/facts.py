"""Derive the facts the rules read from structured case inputs.

One function per pipeline stage group (`documents`, `kyc`, `risk`, `policy`). Each returns the
case-level facts and, where the rules are per person, the person-level facts. Nothing here
reads a file, calls a service or an LLM; every number is computed in `finance.py` or here.

Aggregation (co-applicants), as the header of `data/rules/rules.yaml` states:
  KYC and document facts   weakest value across persons
  income and credit facts  the "earner" is the primary applicant, or the co-applicant for
                           education; FOIR is combined over every earner
"""

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from app.intake.validators import aadhaar_valid, gstin_valid, pan_valid
from app.scoring import analytics, finance, matching
from app.scoring.models import (
    CaseInput,
    DocumentInput,
    Finding,
    PersonInput,
    Role,
    StatementAnalytics,
)
from app.scoring.rules import DocRequirement, RuleSet

KYC_TYPES = ("pan_card", "aadhaar", "photo")
RESIDENT_WORDS = {"resident", "resident indian", "ri", "indian resident"}


@dataclass
class Derived:
    """Facts built up as the stage groups run."""

    case: dict[str, Any] = field(default_factory=dict)
    persons: list[dict[str, Any]] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    def person(self, role: str) -> dict[str, Any]:
        return next(p for p in self.persons if p["role"] == role)


# --- helpers --------------------------------------------------------------------------------
def earners(inp: CaseInput) -> list[PersonInput]:
    """Whose income funds the loan: the co-applicant for education, every adult otherwise."""
    if inp.loan_type == "education":
        return [p for p in inp.persons if p.role == "co"]
    return [p for p in inp.persons if p.employment_type != "student"]


def _docs(inp: CaseInput, doc_type: str, role: Role | None = None) -> list[DocumentInput]:
    """Documents of a type, with repeats of the same content_key counted once (EDGE_CASES E-03)."""
    seen: set[tuple[str, str, str]] = set()
    out = []
    for d in inp.documents:
        if d.doc_type != doc_type or (role and d.role != role):
            continue
        if d.content_key:
            key = (d.doc_type, d.role, d.content_key)
            if key in seen:
                continue
            seen.add(key)
        out.append(d)
    return out


def _first(inp: CaseInput, doc_type: str, role: Role = "primary") -> DocumentInput | None:
    docs = _docs(inp, doc_type, role)
    return docs[0] if docs else None


def _text(d: DocumentInput | None, name: str) -> str | None:
    v = d.fields.get(name) if d else None
    return None if v in (None, "") else str(v)


def _number(d: DocumentInput | None, name: str) -> float | None:
    v = d.fields.get(name) if d else None
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def _surname(full_name: str) -> str:
    return full_name.split()[-1] if full_name.split() else ""


def months_between(start: date, end: date) -> int:
    """Whole months elapsed from `start` to `end`."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return months - (1 if end.day < start.day else 0)


def _applies(inp: CaseInput, when: dict[str, str] | None, applicant: Role) -> bool:
    """Evaluate a document requirement's `when` filter against the applicant and the case."""
    if not when:
        return True
    person = next((p for p in inp.persons if p.role == applicant), None)
    env = {
        "employment_type": person.employment_type if person else None,
        "vehicle_kind": inp.details.get("vehicle_kind"),
        "vehicle_condition": inp.details.get("vehicle_condition"),
    }
    return all(env.get(k) == v for k, v in when.items())


def base_facts(inp: CaseInput, rs: RuleSet) -> Derived:
    """Facts that exist before any stage runs: the labels rules use in their `when` filters."""
    d = Derived()
    band = ""
    for b in rs.params.home_amount_bands:
        if b.max is None or inp.loan_amount <= b.max:
            band = b.name
            break
    d.case.update(
        amount_band=band,
        vehicle_kind=inp.details.get("vehicle_kind", ""),
        vehicle_condition=inp.details.get("vehicle_condition", ""),
        loan_amount=inp.loan_amount,
        tenure_months=inp.tenure_months,
    )
    for p in inp.persons:
        d.persons.append(
            {
                "role": p.role,
                "age_at_application": finance.age_on(p.dob, inp.application_date),
                "age_at_maturity": finance.age_on(
                    p.dob, finance.add_months(inp.application_date, inp.tenure_months)
                ),
                "is_resident": p.residential_status.strip().lower() in RESIDENT_WORDS,
            }
        )
    return d


# --- documents ------------------------------------------------------------------------------
def applicable_requirements(
    rs: RuleSet, loan_type: str, employment: dict[Role, str], details: dict[str, Any]
) -> list[DocRequirement]:
    """The checklist: required documents that apply to this case's people and loan details.
    `employment` maps each role present on the application to its employment type."""
    env_case = {
        "vehicle_kind": details.get("vehicle_kind"),
        "vehicle_condition": details.get("vehicle_condition"),
    }
    out = []
    for req in rs.required_documents(loan_type):
        env = {"employment_type": employment.get(req.applicant), **env_case}
        if all(env.get(k) == v for k, v in (req.when or {}).items()):
            out.append(req)
    return out


def document_shortfalls(inp: CaseInput, rs: RuleSet) -> list[dict[str, Any]]:
    """Checklist items the uploads do not cover yet: [{type, applicant, needed, have, kyc}]."""
    employment = {p.role: p.employment_type for p in inp.persons}
    out: list[dict[str, Any]] = []
    for req in applicable_requirements(rs, inp.loan_type, employment, inp.details):
        roles: list[Role] = ["primary", "co"] if req.kyc else [req.applicant]
        for role in roles:
            if role == "co" and not any(p.role == "co" for p in inp.persons):
                continue
            if req.any_of:
                have = sum(x.units for t in req.any_of for x in _docs(inp, t))
            else:
                have = sum(x.units for x in _docs(inp, req.type, role))
            if have < req.min_count:
                out.append({"type": req.type if not req.any_of else "/".join(req.any_of),
                            "applicant": role, "needed": req.min_count, "have": have,
                            "kyc": req.kyc})  # fmt: skip
    return out


def documents_facts(inp: CaseInput, rs: RuleSet, d: Derived) -> None:
    required = have = 0
    for req in rs.required_documents(inp.loan_type):
        if req.kyc or not _applies(inp, req.when, req.applicant):
            continue
        if req.any_of:
            got = sum(x.units for t in req.any_of for x in _docs(inp, t))
        else:
            got = sum(x.units for x in _docs(inp, req.type, req.applicant))
        required += req.min_count
        have += min(got, req.min_count)
    d.case["mandatory_docs_ratio"] = round(have / required, 4) if required else 1.0

    kyc_q = [
        x.quality_score
        for x in inp.documents
        if x.doc_type in KYC_TYPES and x.quality_score is not None
    ]
    other_q = [
        x.quality_score
        for x in inp.documents
        if x.doc_type not in KYC_TYPES and x.quality_score is not None
    ]
    conf = [x.avg_confidence for x in inp.documents if x.avg_confidence is not None]
    d.case["kyc_doc_quality"] = min(kyc_q) if kyc_q else None
    d.case["doc_quality_score"] = min(other_q) if other_q else None
    d.case["avg_field_confidence"] = round(statistics.fmean(conf), 4) if conf else None
    d.case["totals_tie_out"] = not any(x.tie_out_ok is False for x in inp.documents)


# --- KYC ------------------------------------------------------------------------------------
def _kyc_person(inp: CaseInput, p: PersonInput, d: Derived) -> tuple[int | None, int | None]:
    pan_doc = _first(inp, "pan_card", p.role)
    aad_doc = _first(inp, "aadhaar", p.role)
    pf = d.person(p.role)

    pan = _text(pan_doc, "pan") or p.pan
    pf["pan_valid"] = pan_valid(pan.strip().upper(), _surname(p.full_name)) if pan else None
    aad = _text(aad_doc, "aadhaar")
    pf["aadhaar_valid"] = aadhaar_valid("".join(ch for ch in aad if ch.isdigit())) if aad else None

    named = [
        _text(pan_doc, "name"),
        _text(aad_doc, "name"),
        *(_text(x, "employee") for x in _docs(inp, "payslip", p.role)),
        *(_text(x, "name") for x in _docs(inp, "itr", p.role)),
        *(_text(x, "name") for x in _docs(inp, "driving_licence", p.role)),
    ]
    name_score = matching.min_score(matching.name_match(p.full_name, n) for n in named)
    pf["name_match_score"] = name_score
    pf["dob_match"] = matching.dob_match(
        p.dob,
        [
            _text(pan_doc, "dob"),
            _text(aad_doc, "dob"),
            *(_text(x, "dob") for x in _docs(inp, "driving_licence", p.role)),
        ],
    )
    addr_score = matching.address_match(p.address, _text(aad_doc, "address"))

    if name_score is not None and 85 <= name_score < 100:
        d.findings.append(
            Finding(
                code="NAME_VARIANT",
                role=p.role,
                rule_id="CM-KYC-11",
                message=f"Name differs slightly across documents (match {name_score})",
            )
        )
    for x in _docs(inp, "payslip", p.role):
        same = matching.pan_match(_text(x, "pan"), pan)
        if same is False:
            d.findings.append(
                Finding(
                    code="PAN_MISMATCH_INCOME_DOC",
                    role=p.role,
                    rule_id="CM-KYC-01",
                    message="PAN on an income document differs from the PAN card",
                )
            )
            break
    return name_score, addr_score


def kyc_facts(inp: CaseInput, rs: RuleSet, d: Derived) -> None:
    names: list[int | None] = []
    addrs: list[int | None] = []
    complete = True
    for p in inp.persons:
        n, a = _kyc_person(inp, p, d)
        names.append(n)
        addrs.append(a)
        complete &= all(_docs(inp, t, p.role) for t in KYC_TYPES)
    d.case["kyc_docs_complete"] = complete
    d.case["identity_lookup_match"] = all(p.identity_match is True for p in inp.persons)
    d.case["name_match_score"] = matching.min_score(names)
    d.case["address_match_score"] = matching.min_score(addrs)


# --- income and credit ("risk") --------------------------------------------------------------
def _merge(statements: Iterable[StatementAnalytics]) -> StatementAnalytics | None:
    items = list(statements)
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    return StatementAnalytics(
        months=max(s.months for s in items),
        income_months=max(s.income_months for s in items),
        credits_total=round(sum(s.credits_total for s in items), 2),
        cheque_returns=sum(s.cheque_returns for s in items),
        nach_returns=sum(s.nach_returns for s in items),
        salary_credit=max((s.salary_credit or 0 for s in items), default=0) or None,
        detected_emi_monthly=sum(s.detected_emi_monthly for s in items),
        evidence=[e for s in items for e in s.evidence][:5],
    )


def statement_for(inp: CaseInput, role: Role) -> StatementAnalytics | None:
    return _merge(x.statement for x in _docs(inp, "bank_statement", role) if x.statement)


def _bank_monthly(st: StatementAnalytics | None) -> float | None:
    """Average income credit over the months that had one."""
    if st is None or st.income_months == 0:
        return None
    return st.credits_total / st.income_months


def _documented_income(inp: CaseInput, p: PersonInput) -> float | None:
    """Monthly income the documents show, before the bank cross-check."""
    if p.employment_type == "salaried":
        slips = _docs(inp, "payslip", p.role)
        # a payslip whose totals do not tie out cannot be trusted; use it only if all are like that
        usable = [x for x in slips if x.tie_out_ok is not False] or slips
        vals = [v for x in usable if (v := _number(x, "net")) is not None]
        return statistics.fmean(vals) if vals else None
    itrs = [x for x in _docs(inp, "itr", p.role) if _number(x, "gross_total_income") is not None]
    if itrs:
        latest = max(itrs, key=lambda x: str(x.fields.get("ay") or ""))
        return (_number(latest, "gross_total_income") or 0) / 12
    pnl = _first(inp, "pnl_balance_sheet", p.role)
    profit = _number(pnl, "net_profit")
    return profit / 12 if profit is not None else None


def _verified_income(
    inp: CaseInput, rs: RuleSet, p: PersonInput, d: Derived
) -> tuple[float | None, list[str]]:
    """Documented income, held down to what the bank statement supports. Returns (income, hints)."""
    shown = _documented_income(inp, p)
    bank = _bank_monthly(statement_for(inp, p.role))
    if shown is None:
        return (bank if p.employment_type == "salaried" else None), []
    if bank is None:
        return shown, []
    tol = rs.params.statement.salary_cross_check_tolerance_pct / 100
    if shown > bank * (1 + tol):
        d.findings.append(
            Finding(
                code="INCOME_EXCEEDS_BANK_CREDITS",
                role=p.role,
                rule_id="CM-FRD-01",
                message=(
                    f"Documented income {shown:,.0f} a month is above bank credits "
                    f"{bank:,.0f}; the lower figure is used"
                ),
            )
        )
        return bank, ["INCOME_EXCEEDS_BANK_CREDITS"]
    return shown, []


def income_facts(inp: CaseInput, rs: RuleSet, d: Derived) -> list[str]:
    """Fills the income-stage facts. Returns cross-document tamper hint codes."""
    hints: list[str] = []
    people = earners(inp)
    incomes: dict[Role, float] = {}
    for p in people:
        value, h = _verified_income(inp, rs, p, d)
        hints += h
        if value is not None:
            incomes[p.role] = value
    total_income = sum(incomes.values())
    declared = sum(p.declared_monthly_income or 0 for p in people)

    existing = sum(
        loan.emi
        for p in inp.persons
        if p.bureau
        for loan in p.bureau.active_loans
        if loan.remaining_emis > rs.params.existing_loan_min_remaining_emis
    )
    repay_months = inp.tenure_months
    if inp.loan_type == "education":
        repay_months -= int(inp.details.get("moratorium_months", 0))
    new_emi = finance.emi(inp.loan_amount, rs.pricing.rate_pct[inp.loan_type], repay_months)

    foir = finance.foir_pct(existing, new_emi, total_income)
    outstanding = sum(
        loan.emi * loan.remaining_emis
        for p in inp.persons
        if p.bureau
        for loan in p.bureau.active_loans
    )
    d.case.update(
        net_monthly_income=round(total_income, 2),
        foir=foir,
        new_emi=round(new_emi, 2),
        existing_emi_total=round(existing, 2),
        dti_pct=finance.dti_pct(inp.loan_amount + outstanding, total_income * 12),
        income_verified_ratio=min(finance.ratio(total_income, declared) or 0.0, 1.0)
        if declared
        else None,
    )
    if foir is not None and foir > rs.params.foir_cap_pct:
        d.findings.append(
            Finding(
                code="FOIR_OVER_CAP",
                rule_id="CM-INC-10",
                message=f"FOIR {foir}% is above the {rs.params.foir_cap_pct:g}% cap",
            )
        )

    regs = [analytics.regularity(s) for p in people if (s := statement_for(inp, p.role))]
    d.case["income_regularity"] = min((r for r in regs if r is not None), default=None)

    lead = people[0] if people else None
    d.case["stability_months"] = lead.months_in_current_employment if lead else None
    d.case["total_experience_months"] = lead.total_experience_months if lead else None
    d.case["months_with_current_employer"] = lead.months_in_current_employment if lead else None
    d.case["coapp_income_verified"] = bool(
        d.case["income_verified_ratio"] is not None
        and d.case["income_verified_ratio"] >= rs.params.coapp_verified_min_ratio
    )
    if inp.loan_type == "business":
        gst_turnover = inp.gst.turnover_12m if inp.gst else inp.details.get("annual_turnover")
        d.case["annual_turnover"] = float(gst_turnover) if gst_turnover is not None else None
        reg = matching.parse_date(_text(_first(inp, "business_proof"), "registered_on"))
        if reg:
            d.case["business_vintage_months"] = months_between(reg, inp.application_date)
        else:
            d.case["business_vintage_months"] = inp.details.get("vintage_months")
    return hints


def credit_facts(inp: CaseInput, rs: RuleSet, d: Derived, cross_hints: list[str]) -> None:
    people = earners(inp)
    for p in inp.persons:
        d.person(p.role)["cibil_score"] = p.bureau.cibil_score if p.bureau else None
    lead = people[0] if people else None
    d.case["cibil_score"] = lead.bureau.cibil_score if lead and lead.bureau else None

    statements = [s for p in people if (s := statement_for(inp, p.role))]
    d.case["cheque_nach_returns_12m"] = sum(s.returns for s in statements)
    d.case["bureau_dpd_max_12m"] = max(
        (loan.dpd_max_12m for p in inp.persons if p.bureau for loan in p.bureau.active_loans),
        default=0,
    )
    window = rs.params.enquiry_window_days
    d.case["enquiries_6m"] = (
        sum(0 <= (inp.application_date - e).days <= window for e in lead.bureau.enquiry_dates)
        if lead and lead.bureau
        else 0
    )

    hints = [
        *cross_hints,
        *inp.extra_tamper_hints,
        *(h for x in inp.documents for h in x.tamper_hints),
    ]
    weak = set(rs.params.tamper.weak_codes)
    strong = [h for h in hints if h not in weak]
    # weak hints count once per kind: a round salary repeated on every payslip is one hint
    d.case["tamper_suspected"] = bool(strong) or (
        len(set(hints)) >= rs.params.tamper.weak_hints_needed
    )
    if d.case["tamper_suspected"]:
        d.findings.append(
            Finding(
                code="TAMPER_SUSPECTED",
                rule_id="CM-FRD-01",
                message="Tamper hints: " + ", ".join(sorted(set(hints))),
            )
        )

    if inp.loan_type == "business":
        lead_stmt = statement_for(inp, "primary")
        turnover = d.case.get("annual_turnover")
        d.case["bank_credit_to_gst_ratio"] = (
            analytics.credit_to_gst_ratio(lead_stmt, turnover) if lead_stmt and turnover else None
        )


# --- policy fit -----------------------------------------------------------------------------
def _party_ok(rs: RuleSet, a: str | None, b: str | None) -> bool:
    score = matching.name_match(a, b)
    return score is not None and score >= rs.params.party_match_min


def _property_docs_valid(inp: CaseInput, rs: RuleSet) -> bool:
    sale, deed = _first(inp, "sale_agreement"), _first(inp, "title_deed")
    if sale is None or deed is None:
        return False
    buyer_ok = _party_ok(rs, _text(sale, "buyer"), inp.persons[0].full_name)
    owner_ok = _party_ok(rs, _text(deed, "owner"), _text(sale, "seller"))
    ec = _first(inp, "encumbrance_certificate")
    clear = ec is None or "nil" in (_text(ec, "result") or "").casefold()
    return buyer_ok and owner_ok and clear


def _vehicle_docs_valid(inp: CaseInput, rs: RuleSet) -> bool:
    inv = _first(inp, "dealer_invoice")
    if inv is None:
        return False
    make, model = str(inp.details.get("make", "")), str(inp.details.get("model", ""))
    invoice_model = _text(inv, "model") or ""
    model_ok = (
        round(fuzz.token_sort_ratio(f"{make} {model}".casefold(), invoice_model.casefold()))
        >= rs.params.party_match_min
    )
    price, listed = _number(inv, "on_road"), inp.details.get("on_road_price")
    price_ok = (
        price is not None
        and listed
        and abs(price - float(listed)) <= float(listed) * rs.params.price_tolerance_pct / 100
    )
    ok = model_ok and bool(price_ok)
    if inp.details.get("vehicle_condition") == "used":
        rc, ins = _first(inp, "rc_book"), _first(inp, "insurance")
        valid_till = matching.parse_date(_text(ins, "valid_till"))
        ok &= (
            rc is not None
            and ins is not None
            and bool(valid_till and valid_till >= inp.application_date)
        )
    if inp.details.get("vehicle_kind") == "two_wheeler":
        lic = _first(inp, "driving_licence")
        ok &= lic is not None and _party_ok(rs, _text(lic, "name"), inp.persons[0].full_name)
    return bool(ok)


def policy_facts(inp: CaseInput, rs: RuleSet, d: Derived) -> None:
    p = rs.params
    purpose = inp.purpose.casefold()
    d.case["loan_purpose_allowed"] = not any(w in purpose for w in p.disallowed_purposes)

    if inp.loan_type == "home":
        d.case["ltv_percent"] = finance.ltv_pct(
            inp.loan_amount, float(inp.details.get("property_value") or 0)
        )
        d.case["property_docs_valid"] = _property_docs_valid(inp, rs)
    if inp.loan_type == "vehicle":
        price = _number(_first(inp, "dealer_invoice"), "on_road") or float(
            inp.details.get("on_road_price") or 0
        )
        d.case["ltv_percent"] = finance.ltv_pct(inp.loan_amount, price)
        d.case["vehicle_docs_valid"] = _vehicle_docs_valid(inp, rs)
    if inp.loan_type == "education":
        e = p.education
        moratorium = int(inp.details.get("moratorium_months", 0))
        d.case["repayment_years"] = round((inp.tenure_months - moratorium) / 12, 2)
        d.case["collateral_ok"] = not (
            inp.loan_amount > e.collateral_required_above
            and not inp.details.get("collateral_offered")
        )
        fee = _number(_first(inp, "fee_structure"), "total_fee") or float(
            inp.details.get("total_fee") or 0
        )
        country = _text(_first(inp, "admission_letter"), "country") or str(
            inp.details.get("country", "India")
        )
        pct = e.margin_pct_india if country.strip().casefold() == "india" else e.margin_pct_abroad
        required = round(fee * pct / 100) if fee > e.margin_free_fee_up_to else 0
        d.case["margin_required"] = required
        d.case["margin_ok"] = float(inp.details.get("margin_amount") or 0) >= required
    if inp.loan_type == "business":
        reg = _first(inp, "gst_registration")
        gstin = _text(reg, "gstin") or (inp.gst.gstin if inp.gst else None)
        pan = _text(reg, "pan") or (inp.gst.pan if inp.gst else None)
        record_ok = inp.gst is None or (pan is None or inp.gst.pan == pan)
        d.case["gst_or_udyam_valid"] = bool(gstin and gstin_valid(gstin, pan) and record_ok)
        turnover = d.case.get("annual_turnover")
        d.case["loan_to_turnover"] = finance.ratio(inp.loan_amount, turnover) if turnover else None
