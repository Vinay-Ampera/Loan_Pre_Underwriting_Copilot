"""Quality 'levers' that decide how good or bad a synthetic case is, and a search that finds a
lever setting whose total score equals a target exactly.

A lever level maps to nominal facts. The builder then makes documents that realise those facts
and recomputes the real facts from what it built; generation fails loudly if the two disagree.
"""

import random
from dataclasses import asdict, dataclass, fields
from typing import Any

from app.scoring.evaluate import evaluate_case
from app.scoring.rules import RuleSet

NOMINAL_CIBIL = {"personal": [790, 725, 670], "business": [760, 675]}
DEFAULT_CIBIL = [790, 725]


@dataclass
class Levers:
    name: int = 0  # 0 exact, 1 spelling variant
    addr: int = 0  # 0 close, 1 loose, 2 weak
    lookup: int = 0  # 1 = identity record missing
    kycq: int = 0  # KYC document quality: 0 good, 1 mild, 2 poor
    drop: int = 0  # units of mandatory documents left out
    docq: int = 0  # income-document quality (also drives extraction confidence)
    tie: int = 0  # 1 = totals do not tie out
    foir: int = 0  # 0 about 30, 1 about 45, 2 about 60
    incratio: int = 0  # verified / declared income: 0.98, 0.8, 0.6
    reg: int = 0  # income regularity: all months, one missing, half missing
    minincome: int = 0  # 1 = below the product's income floor
    stab: int = 0  # stability shortfall
    cibil: int = 0
    returns: int = 0  # cheque / NACH returns in 12 months
    dpd: int = 0
    enq: int = 0
    gst: int = 0  # business: bank credits to GST sales
    pol1: int = 0
    pol2: int = 0
    pol3: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class Context:
    loan_type: str
    employment_type: str  # of the earner
    has_co: bool
    vehicle_kind: str = ""
    vehicle_condition: str = ""
    units_total: int = 0  # mandatory non-KYC document units (for the completeness ratio)
    max_drop: int = 0


def level_counts(ctx: Context) -> dict[str, int]:
    loan = ctx.loan_type
    n = {f.name: 3 for f in fields(Levers)}
    n.update(name=2, lookup=2, tie=2, minincome=2, stab=2, gst=2, pol1=2, pol2=2, pol3=2)
    n["drop"] = ctx.max_drop + 1
    n["returns"] = 4
    n["cibil"] = len(NOMINAL_CIBIL.get(loan, DEFAULT_CIBIL))
    if loan == "personal":
        n["stab"] = 3
    if loan != "business":
        n["gst"] = 1
    else:
        n["enq"] = 1
    if loan == "education":
        n["minincome"] = 1  # co-applicant income verification follows incratio instead
        n["pol1"] = 1  # repayment is always within 15 years once the age cap holds
    return n


def compatible(ctx: Context, lv: Levers) -> bool:
    # low income fixes the loan size, so "amount above the cap" / "turnover share too high" cannot hold
    if ctx.loan_type == "personal" and lv.minincome and lv.pol2:
        return False
    return not (ctx.loan_type == "business" and lv.minincome and lv.pol3)


def nominal(ctx: Context, lv: Levers) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Facts if every lever were realised exactly at its nominal value."""
    loan = ctx.loan_type
    ratio = (ctx.units_total - lv.drop) / ctx.units_total
    doc_q, conf = [(95, 0.96), (72, 0.82), (55, 0.70)][lv.docq]
    case: dict[str, Any] = {
        "kyc_docs_complete": True, "tamper_suspected": False,
        "identity_lookup_match": lv.lookup == 0,
        "name_match_score": [100, 90][lv.name], "address_match_score": [92, 72, 50][lv.addr],
        "kyc_doc_quality": [95, 72, 55][lv.kycq],
        "mandatory_docs_ratio": ratio, "doc_quality_score": doc_q, "avg_field_confidence": conf,
        "totals_tie_out": lv.tie == 0,
        "foir": [30, 45, 60][lv.foir], "income_verified_ratio": [0.98, 0.8, 0.6][lv.incratio],
        "income_regularity": [1.0, 0.83, 0.5][lv.reg],
        "cibil_score": NOMINAL_CIBIL.get(loan, DEFAULT_CIBIL)[lv.cibil],
        "cheque_nach_returns_12m": lv.returns, "bureau_dpd_max_12m": [0, 20, 60][lv.dpd],
        "enquiries_6m": [1, 3, 6][lv.enq],
        "amount_band": "upto_75l", "vehicle_kind": ctx.vehicle_kind,
        "vehicle_condition": ctx.vehicle_condition,
    }  # fmt: skip
    short = lv.stab
    if loan == "personal":
        case.update(net_monthly_income=22000 if lv.minincome else 60000,
                    total_experience_months=18 if short == 2 else 60,
                    months_with_current_employer=8 if short >= 1 else 40,
                    tenure_months=72 if lv.pol1 else 48, loan_amount=2800000 if lv.pol2 else 600000,
                    loan_purpose_allowed=lv.pol3 == 0)  # fmt: skip
    elif loan == "home":
        case.update(net_monthly_income=22000 if lv.minincome else 90000,
                    stability_months=14 if short else 48, tenure_months=372 if lv.pol1 else 240,
                    ltv_percent=95 if lv.pol2 else 70, property_docs_valid=lv.pol3 == 0)  # fmt: skip
    elif loan == "vehicle":
        case.update(net_monthly_income=22000 if lv.minincome else 60000,
                    stability_months=14 if short else 48, tenure_months=96 if lv.pol1 else 48,
                    ltv_percent=95 if lv.pol2 else 70, vehicle_docs_valid=lv.pol3 == 0)  # fmt: skip
    elif loan == "education":
        case.update(coapp_income_verified=lv.incratio < 2, stability_months=14 if short else 48,
                    repayment_years=8, collateral_ok=lv.pol2 == 0, margin_ok=lv.pol3 == 0)  # fmt: skip
    else:  # business
        case.update(annual_turnover=3200000 if lv.minincome else 8000000,
                    business_vintage_months=15 if short else 60,
                    bank_credit_to_gst_ratio=[0.92, 0.7][lv.gst],
                    tenure_months=96 if lv.pol1 else 60, gst_or_udyam_valid=lv.pol2 == 0,
                    loan_to_turnover=0.4 if lv.pol3 else 0.2)  # fmt: skip
    cibil = case["cibil_score"]
    person = {
        "role": "co" if loan == "education" else "primary", "pan_valid": True, "aadhaar_valid": True,
        "name_match_score": 100, "dob_match": True, "is_resident": True, "age_at_application": 35,
        "age_at_maturity": 40, "cibil_score": cibil,
    }  # fmt: skip
    persons = [person]
    if loan == "education":
        persons.append(
            {**person, "role": "primary", "age_at_application": 20, "age_at_maturity": 30}
        )
    return case, persons


def total_for(ruleset: RuleSet, ctx: Context, lv: Levers) -> tuple[float | None, bool]:
    case, persons = nominal(ctx, lv)
    ev = evaluate_case(ruleset, ctx.loan_type, case, persons)
    return ev.total_score, ev.capped_to_refer


def find_levers(rng: random.Random, ruleset: RuleSet, ctx: Context, target: float) -> Levers:
    counts = level_counts(ctx)
    p_bad = min(max((100 - target) / 55, 0.03), 0.85)
    for _ in range(200_000):
        lv = Levers()
        for f in fields(Levers):
            n = counts[f.name]
            if n > 1 and rng.random() < p_bad:
                setattr(lv, f.name, rng.randrange(1, n))
        if not compatible(ctx, lv):
            continue
        total, capped = total_for(ruleset, ctx, lv)
        if total == target and not (capped and target >= 85):
            return lv
    raise RuntimeError(f"no lever combination reaches {target} for {ctx.loan_type}")
