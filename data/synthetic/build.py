"""Build one synthetic case: people, money, documents, mock records and the answer key.

Order of work: pick context and levers -> size the loan and incomes -> make people ->
make documents -> compute the REAL facts from what was built -> evaluate with the rules file.
For score cases the evaluated total must equal the target, otherwise the caller retries.
"""

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from rapidfuzz import fuzz

from app.intake.validators import aadhaar_valid, gstin_valid, pan_valid
from app.scoring.evaluate import evaluate_case
from app.scoring.rules import RuleSet
from app.services.mock_services import aadhaar_hash
from synthetic import render, variants
from synthetic.finance import (
    RATES,
    StatementProfile,
    add_months,
    build_statement,
    emi,
    principal_from_emi,
)  # fmt: skip
from synthetic.levers import (
    DEFAULT_CIBIL,
    NOMINAL_CIBIL,
    Context,
    Levers,
    find_levers,
)  # fmt: skip
from synthetic.people import (
    BUSINESS_KINDS,
    CITIES,
    CONSTITUTIONS,
    DEALERS,
    INSTITUTIONS_ABROAD,
    INSTITUTIONS_IN,
    SURNAMES,
    VEHICLES,
    IdFactory,
    Person,
    age_on,
    make_gstin,
    make_person,
    make_udyam,
)  # fmt: skip
from synthetic.scenarios import Scenario

APP_DATE = date(2026, 10, 20)
STMT_END = date(2026, 9, 1)  # first day of the last statement month
LENDERS = ["Finserv Capital", "Unity Finance", "Apex Credit", "Greenfield Finance"]
BANK_STYLES = {
    "heritage": ("State Heritage Bank", "SHB"), "horizon": ("HorizonFirst Bank", "HFB"),
    "imperial": ("Imperial Trust Bank", "ITB"), "citadel": ("Citadel Cooperative Bank", "CCB"),
}  # fmt: skip
SEMANTIC_FLAGS = {
    "CM-KYC-01": "invalid_pan", "CM-KYC-02": "invalid_aadhaar", "CM-KYC-03": "name_mismatch",
    "CM-KYC-04": "dob_mismatch", "CM-DOC-01": "missing_kyc_document", "CM-ELIG-01": "non_resident",
    "CM-ELIG-02": "below_minimum_age", "ED-ELIG-01": "below_minimum_age",
    "ED-ELIG-02": "below_minimum_age", "CM-ELIG-03": "age_over_cap_at_maturity",
    "PL-CIBIL-01": "cibil_below_floor", "HL-CIBIL-01": "cibil_below_floor",
    "ED-CIBIL-01": "cibil_below_floor", "BL-CIBIL-01": "cibil_below_floor",
    "VL-CIBIL-01": "cibil_below_floor", "PL-CIBIL-02": "cibil_refer_window",
    "CM-FRD-01": "tamper_suspected", "BL-CRD-20": "cheque_returns_refer",
}  # fmt: skip


class GenerationError(RuntimeError):
    """The realised facts did not reproduce the intended score; caller may retry."""


@dataclass
class Doc:
    role: str
    doc_type: str
    name: str  # file name without directory
    data: bytes
    fmt: str  # digital_pdf | scanned_pdf | photo
    units: int = 1
    quality: str = "digital"
    truth: dict[str, Any] = field(default_factory=dict)
    blur: float | None = None


@dataclass
class Shown:
    """What the identity documents print (can differ from the truth in fix scenarios)."""

    pan: str
    aadhaar: str
    pan_name: str
    aadhaar_name: str
    pan_dob: date
    aadhaar_dob: date
    aadhaar_address: str


@dataclass
class BuiltCase:
    sc: Scenario
    application: dict[str, Any]
    docs: list[Doc]
    answer_key: dict[str, Any]
    identity: list[dict[str, Any]]
    bureau: list[dict[str, Any]]
    gst: list[dict[str, Any]]
    udyam: list[dict[str, Any]]
    fairness: list[dict[str, Any]]


def name_score(a: str, b: str) -> int:
    return round(fuzz.token_sort_ratio(a.casefold(), b.casefold()))


def perturb(rng: random.Random, text: str, lo: int, hi: int) -> str:
    """Character edits until the reference matcher scores the result within [lo, hi]."""
    for _ in range(400):
        out = list(text)
        for _ in range(60):
            if name_score(text, "".join(out)) <= hi:
                break
            i = rng.randrange(len(out))
            op = rng.choice(["ins", "del", "sub"])
            if op == "ins":
                out.insert(i, rng.choice("aeiouyhr"))
            elif op == "del" and len(out) > 4:
                del out[i]
            else:
                out[i] = rng.choice("aeioulnrst")
            if lo <= name_score(text, "".join(out)) <= hi:
                return "".join(out)
    raise GenerationError(f"cannot perturb {text!r} into [{lo}, {hi}]")


def round_to(x: float, base: int) -> int:
    return int(round(x / base) * base)


def month_label(y: int, m: int) -> str:
    return date(y, m, 1).strftime("%B %Y")


class CaseBuilder:
    def __init__(self, sc: Scenario, ids: IdFactory, rng: random.Random, ruleset: RuleSet) -> None:
        self.sc, self.ids, self.rng, self.rs = sc, ids, rng, ruleset
        self.loan = sc.loan_type
        self.docs: list[Doc] = []
        self.persons: dict[str, Person] = {}
        self.shown: dict[str, Shown] = {}
        self.income: dict[str, float] = {}  # verified monthly net income by role (earners)
        self.declared: dict[str, float] = {}
        self.loans: dict[str, list[dict[str, Any]]] = {}  # existing loans by role
        self.facts: dict[str, Any] = {}
        self.form_extra: dict[str, Any] = {}
        self.regularity: list[float] = []
        self.statement_months: dict[str, int] = {}

    # ------------------------------------------------------------------ context + levers
    def choose_context(self) -> Context:
        rng, loan = self.rng, self.loan
        emp = (
            "self_employed"
            if loan == "business"
            else rng.choice(["salaried", "salaried", "self_employed"])
        )
        if loan == "personal":
            emp = "salaried"
        kind = cond = ""
        if loan == "vehicle":
            kind = rng.choice(["new_car", "new_car", "used_car", "two_wheeler", "two_wheeler"])
            cond = (
                "used"
                if kind == "used_car"
                else ("used" if kind == "two_wheeler" and rng.random() < 0.3 else "new")
            )
        ctx = Context(loan, emp, self.sc.co_applicant, kind, cond)
        units, pool = self.required_units(ctx)
        ctx.units_total, ctx.max_drop = units, min(3, sum(u for _, _, u in pool))
        self.pool = pool
        return ctx

    def req_applies(self, ctx: Context, when: dict[str, str] | None, who: str) -> bool:
        if not when:
            return True
        env = {"employment_type": ctx.employment_type, "vehicle_kind": ctx.vehicle_kind,
               "vehicle_condition": ctx.vehicle_condition}  # fmt: skip
        if who == "co" and self.loan == "education":
            env["employment_type"] = self.co_employment
        return all(env.get(k) == v for k, v in when.items())

    def required_units(self, ctx: Context) -> tuple[int, list[tuple[str, str, int]]]:
        """(total mandatory non-KYC units, droppable pool of (doc_type, role, spare units))."""
        if self.loan == "education":
            self.co_employment = ctx.employment_type
        total = 0
        pool: list[tuple[str, str, int]] = []
        for r in self.rs.required_documents(self.loan):
            if r.kyc or not self.req_applies(ctx, r.when, r.applicant):
                continue
            total += r.min_count
            spare = {"bank_statement": 3, "payslip": 2, "itr": r.min_count - 1, "gst_returns": 3,
                     "encumbrance_certificate": 1, "approved_plan": 1, "fee_structure": 1,
                     "marksheet": 1}.get(r.type, 0)  # fmt: skip
            if spare > 0:
                pool.append((r.type, r.applicant, spare))
        return total, pool

    def allocate_drops(self, k: int) -> dict[tuple[str, str], int]:
        drops: dict[tuple[str, str], int] = {}
        pool = [[t, r, n] for t, r, n in self.pool]
        for _ in range(k):
            live = [p for p in pool if p[2] > 0]
            p = self.rng.choice(live)
            p[2] -= 1
            drops[(p[0], p[1])] = drops.get((p[0], p[1]), 0) + 1
        return drops

    # ------------------------------------------------------------------ sizing
    def size(self, ctx: Context, lv: Levers) -> dict[str, Any]:
        rng, loan = self.rng, self.loan
        rate = RATES[loan]
        f = [rng.uniform(26, 34), rng.uniform(43, 48), rng.uniform(55, 68)][lv.foir] / 100
        out: dict[str, Any] = {}
        floor = 30000.0

        def derive(emi_new: float) -> tuple[float, float]:
            existing = emi_new * rng.uniform(0.15, 0.6)
            income = (emi_new + existing) / f
            if income < floor:
                existing = max(f * floor - emi_new, 0.0)
                income = max((emi_new + existing) / f, floor)
            return float(round_to(income, 500)), float(round_to(existing, 100))

        def fixed_income(lo: int, hi: int, tenure: int) -> tuple[float, float, float]:
            income = float(rng.randrange(lo, hi, 500))
            obligations = f * income
            existing = float(round_to(obligations * rng.uniform(0.15, 0.5), 100))
            emi_new = obligations - existing
            return income, existing, principal_from_emi(emi_new, rate, tenure)

        if loan == "personal":
            tenure = 72 if lv.pol1 else rng.choice([24, 36, 48, 60])
            if lv.minincome:
                income, existing, p = fixed_income(19000, 24500, tenure)
                principal = max(round_to(p, 5000), 30000)
            else:
                principal = (rng.randrange(2600000, 3200000, 50000) if lv.pol2
                             else rng.randrange(100000, 1500000, 10000))  # fmt: skip
                income, existing = derive(emi(principal, rate, tenure))
            out.update(principal=principal, tenure=tenure)
        elif loan == "home":
            tenure = 372 if lv.pol1 else rng.choice([120, 180, 240, 300])
            if lv.minincome:
                income, existing, p = fixed_income(19000, 24500, tenure)
                principal = max(round_to(p, 10000), 200000)
            else:
                principal = rng.randrange(1000000, 9500000, 50000)
                income, existing = derive(emi(principal, rate, tenure))
            band = (
                "upto_30l"
                if principal <= 3_000_000
                else "upto_75l"
                if principal <= 7_500_000
                else "above_75l"
            )
            limit = {"upto_30l": 90, "upto_75l": 80, "above_75l": 75}[band]
            ltv = limit + rng.randint(3, 8) if lv.pol2 else limit - rng.randint(5, 15)
            prop_value = round_to(principal / (ltv / 100), 10000)
            out.update(principal=principal, tenure=tenure, band=band, property_value=prop_value,
                       ltv=round(principal / prop_value * 100, 1))  # fmt: skip
        elif loan == "vehicle":
            kind_, cond = ctx.vehicle_kind, ctx.vehicle_condition
            tenure = (rng.choice({"new_car": [36, 48, 60, 72, 84], "used_car": [24, 36, 48, 60],
                                  "two_wheeler": [12, 24, 36, 48, 60]}[kind_])
                      if not lv.pol1 else {"new_car": 96, "used_car": 72, "two_wheeler": 72}[kind_])  # fmt: skip
            limit = 85 if cond == "new" else 80
            ltv = limit + rng.randint(3, 8) if lv.pol2 else limit - rng.randint(8, 20)
            price = {"new_car": (600000, 2000000), "used_car": (300000, 1000000),
                     "two_wheeler": (70000, 300000)}[kind_]  # fmt: skip
            if lv.minincome:
                income, existing, p = fixed_income(19000, 24500, tenure)
                principal = max(round_to(p, 5000), 40000)
                on_road = round_to(principal / (ltv / 100), 5000)
            else:
                on_road = round_to(rng.uniform(*price), 5000)
                principal = round_to(on_road * ltv / 100, 5000)
                income, existing = derive(emi(principal, rate, tenure))
            out.update(principal=principal, tenure=tenure, on_road=on_road,
                       ltv=round(principal / on_road * 100, 1))  # fmt: skip
        elif loan == "business":
            tenure = 96 if lv.pol1 else rng.choice([36, 48, 60, 72, 84])
            if lv.minincome:
                turnover = float(rng.randrange(2800000, 3400000, 50000))
                income = float(round_to(turnover * rng.uniform(0.10, 0.18) / 12, 500))
                obligations = f * income
                existing = float(round_to(obligations * rng.uniform(0.15, 0.5), 100))
                principal = max(
                    round_to(principal_from_emi(obligations - existing, rate, tenure), 10000),
                    100000,
                )
            else:
                turnover = float(rng.randrange(4200000, 40000000, 100000))
                r = rng.uniform(0.33, 0.45) if lv.pol3 else rng.uniform(0.08, 0.26)
                principal = round_to(turnover * r, 10000)
                income, existing = derive(emi(principal, rate, tenure))
            out.update(principal=principal, tenure=tenure, turnover=turnover,
                       loan_to_turnover=round(principal / turnover, 3))  # fmt: skip
        else:  # education
            course_years = rng.choice([2, 3, 4])
            abroad = rng.random() < 0.35
            self.abroad = abroad
            need_big = lv.pol2 == 1  # collateral missing only matters above 7.5 lakh
            need_margin = lv.pol3 == 1  # margin shortfall only matters above 4 lakh
            if need_big:
                principal = rng.randrange(850000, 2500000, 50000)
            elif need_margin:
                principal = rng.randrange(450000, 2000000, 50000)
            else:
                principal = rng.randrange(200000, 2500000, 50000)
            margin_pct = 0.15 if abroad else 0.05
            total_fee = (
                float(round_to(principal / (1 - margin_pct), 10000))
                if principal > 400000
                else float(principal)
            )
            req_margin = round(total_fee * margin_pct) if total_fee > 400000 else 0
            margin = (
                round(req_margin * 0.4)
                if lv.pol3 and req_margin
                else req_margin + round_to(total_fee * 0.01, 1000)
            )
            principal = int(total_fee - margin)
            moratorium = course_years * 12 + 12
            repay_cap = 55 - self.co_age_hint - course_years - 1 - 1
            repay_years = rng.randint(5, max(5, min(10, repay_cap)))
            tenure = moratorium + repay_years * 12
            income, existing = derive(emi(principal, rate, repay_years * 12))
            out.update(principal=principal, tenure=tenure, course_years=course_years, moratorium=moratorium,
                       repay_years=repay_years, total_fee=total_fee, margin=margin, req_margin=req_margin,
                       collateral_needed=principal > 750000)  # fmt: skip
        out.update(income=income, existing=existing, f=f)
        return out

    # ------------------------------------------------------------------ people
    def age_for(self, tenure_months: int, role: str, low: int, high: int) -> int:
        """An age whose age at maturity stays <= 55 (unless the scenario wants a breach)."""
        years = -(-tenure_months // 12)
        top = min(high, 55 - years - 1)
        return self.rng.randint(low, max(low, top))

    def make_people(self, ctx: Context, sz: dict[str, Any]) -> None:
        rng, loan, kind = self.rng, self.loan, self.sc.kind
        tenure = sz["tenure"]
        surname = rng.choice(SURNAMES)
        city = rng.choice(CITIES)
        mk = lambda role, age, emp, **kw: make_person(rng, self.ids, role, age, emp, APP_DATE, **kw)  # noqa: E731
        if loan == "education":
            student_age = 17 if kind == "elig_age_under" else rng.randint(19, 23)
            co_age = self.co_age
            primary = mk("primary", student_age, "student", surname=surname, city=city)
            co = mk("co", co_age, ctx.employment_type, surname=surname, city=city,
                    gender=rng.choice(["M", "F"]))  # fmt: skip
            self.persons = {"primary": primary, "co": co}
            return
        if kind == "elig_age_under":
            age = 19
        elif kind == "elig_age_over" and not (loan == "home" and ctx.has_co):
            age = 55 - -(-tenure // 12) + rng.randint(2, 3)
        else:
            age = self.age_for(tenure, "primary", 24, 50)
        primary = mk("primary", age, ctx.employment_type, surname=surname, city=city)
        self.persons = {"primary": primary}
        if ctx.has_co:
            co_age = (
                (55 - -(-tenure // 12) + 3)
                if kind == "elig_age_over"
                else self.age_for(tenure, "co", 26, 52)
            )
            self.persons["co"] = mk("co", co_age, "salaried", city=city)
            self.persons["co"].extra["relationship"] = rng.choice(["spouse", "parent", "sibling"])

    # ------------------------------------------------------------------ identity documents
    def identity_variants(self, lv: Levers) -> None:
        rng, kind = self.rng, self.sc.kind
        for role, p in self.persons.items():
            s = Shown(p.pan, p.aadhaar, p.full_name, p.full_name, p.dob, p.dob, p.address)
            if role == "primary":
                if lv.name:
                    s.aadhaar_name = perturb(rng, p.full_name, 86, 94)
                if lv.addr == 1:
                    s.aadhaar_address = perturb(rng, p.address, 62, 82)
                elif lv.addr == 2:
                    for _ in range(50):
                        other = f"{rng.randint(1, 480)}, {rng.choice(['Canal Road', 'Orchard Lane', 'Mill Street'])}, {p.city}"
                        if name_score(p.address, other) < 55:
                            s.aadhaar_address = other
                            break
                    else:
                        raise GenerationError("address variant")
                if kind == "fix_pan_invalid":
                    s.pan = p.pan[:4] + str(rng.randint(0, 9)) + p.pan[5:]
                elif kind == "fix_aadhaar_invalid":
                    s.aadhaar = p.aadhaar[:-1] + str((int(p.aadhaar[-1]) + 1) % 10)
                elif kind == "fix_name_mismatch":
                    other = f"{rng.choice(['Mahesh', 'Sunil', 'Kamala', 'Rajeev'])} {rng.choice(SURNAMES)}"
                    s.pan_name = other
                elif kind == "fix_dob_mismatch":
                    s.aadhaar_dob = date(p.dob.year - 1, p.dob.month, p.dob.day)
            self.shown[role] = s

    def kyc_docs(self, lv: Levers) -> None:
        rng = self.rng
        missing: tuple[str, str] | None = None
        if self.sc.kind == "fix_kyc_missing":
            role = rng.choice(list(self.persons))
            missing = (role, rng.choice(["pan_card", "aadhaar", "photo"]))
        self.facts["missing_kyc"] = missing
        for role, p in self.persons.items():
            s = self.shown[role]
            level = ["good" if rng.random() < 0.3 else "digital", "mild", "poor"][lv.kycq]
            pan_pdf = render.id_card("Permanent Account Number Card", "Income Tax Department (specimen)",
                                     [("Name", s.pan_name), ("Father's name", p.father_first + " " + p.surname),
                                      ("Date of birth", f"{s.pan_dob:%d/%m/%Y}"), ("PAN", s.pan)])  # fmt: skip
            aad_pdf = render.id_card("Aadhaar", "Unique Identification Authority (specimen)",
                                     [("Name", s.aadhaar_name), ("Date of birth", f"{s.aadhaar_dob:%d/%m/%Y}"),
                                      ("Address", s.aadhaar_address), ("Aadhaar number", f"{s.aadhaar[:4]} {s.aadhaar[4:8]} {s.aadhaar[8:]}")],
                                     note="Aadhaar is proof of identity, not of citizenship.")  # fmt: skip
            for doc_type, pdf, truth in (
                ("pan_card", pan_pdf, {"name": s.pan_name, "dob": str(s.pan_dob), "pan": s.pan}),
                ("aadhaar", aad_pdf, {"name": s.aadhaar_name, "dob": str(s.aadhaar_dob),
                                      "aadhaar": s.aadhaar, "address": s.aadhaar_address}),
            ):  # fmt: skip
                if missing == (role, doc_type):
                    continue
                self.add_visual(role, doc_type, doc_type, pdf, level, truth)
            if missing != (role, "photo"):
                self.docs.append(Doc(role, "photo", "photo.jpg", variants.avatar_jpg(rng, p.first.upper()), "photo",
                                     quality="good", truth={"name": p.full_name}))  # fmt: skip

    def add_visual(self, role: str, doc_type: str, stem: str, pdf: bytes, level: str,
                   truth: dict[str, Any], units: int = 1) -> None:  # fmt: skip
        """Single-page document: digital PDF, or a phone photo when `level` is good/mild/poor."""
        if level == "digital":
            self.docs.append(
                Doc(role, doc_type, f"{stem}.pdf", pdf, "digital_pdf", units, level, truth)
            )
        else:
            jpg, blur = variants.photo_variant(pdf, level, self.rng)
            self.docs.append(
                Doc(role, doc_type, f"{stem}.jpg", jpg, "photo", units, level, truth, blur)
            )

    # ------------------------------------------------------------------ income documents
    def income_docs(
        self, ctx: Context, lv: Levers, sz: dict[str, Any], drops: dict[tuple[str, str], int]
    ) -> None:
        rng, loan = self.rng, self.loan
        earners = ["co"] if loan == "education" else list(self.persons)
        total_income = sz["income"]
        shares = {r: 1.0 for r in earners}
        if len(earners) == 2:
            shares = {"primary": (s := rng.uniform(0.6, 0.75)), "co": 1 - s}
        existing_total = sz["existing"]
        for role in earners:
            p = self.persons[role]
            emp = p.employment_type
            net = (
                float(round_to(total_income * shares[role], 100))
                if loan != "business"
                else total_income
            )
            self.income[role] = net
            first = role == earners[0]
            self.loans[role] = self.make_loans(role, existing_total if first else 0.0, lv)
            tamper = self.sc.kind == "tamper" and first
            ratio = [0.98, 0.8, 0.6][lv.incratio]
            # a tampered income document inflates what the applicant declares and shows
            self.declared[role] = float(round_to(net / ratio, 100)) * (1.35 if tamper else 1.0)
            my_drops = drops if first else {}
            drop_role = "co" if loan == "education" else "primary"
            window = (12 if loan == "business" else 6) - my_drops.get(
                ("bank_statement", drop_role), 0
            )
            self.statement_months[role] = window
            skip = [0, 1, -(-window // 2)][lv.reg]
            level = ["digital", "mild", "poor"][lv.docq]
            if emp == "salaried":
                self.salaried_docs(role, p, net, my_drops, level, lv, tamper, ctx)
            else:
                self.self_employed_docs(role, p, net, sz, my_drops, lv, tamper, ctx)
            self.statement(role, p, net, window, skip, lv, sz, level)

    def make_loans(self, role: str, existing: float, lv: Levers) -> list[dict[str, Any]]:
        rng = self.rng
        if existing <= 0:
            return []
        n = 2 if existing > 6000 and rng.random() < 0.5 else 1
        parts = [existing] if n == 1 else [existing * 0.6, existing * 0.4]
        loans = []
        for i, amt in enumerate(parts):
            loans.append({"lender": LENDERS[(i + rng.randrange(2)) % len(LENDERS)], "emi": float(round_to(amt, 100)),
                          "remaining_emis": rng.randint(13, 60),
                          "dpd_max_12m": [0, 20, 60][lv.dpd] if i == 0 else 0})  # fmt: skip
        return loans

    def salaried_docs(self, role: str, p: Person, net: float, drops: dict[tuple[str, str], int], level: str,
                      lv: Levers, tamper: bool, ctx: Context) -> None:  # fmt: skip
        rng, loan = self.rng, self.loan
        months_emp = self.employment_months
        doj = add_months(APP_DATE, -months_emp)
        # gross from net: PF 12% of basic (basic = 45% of gross), PT 200, TDS absorbs rounding
        gross = round_to((net + 200) / (1 - 0.054 - rng.uniform(0.04, 0.08)), 100)
        basic = round_to(gross * 0.45, 100)
        pf = round(basic * 0.12)
        tds = gross - pf - 200 - int(net)
        earnings = {"Basic": basic, "HRA": round_to(basic * 0.4, 100)}
        earnings["Special allowance"] = gross - sum(earnings.values())
        n_pay = 3 - drops.get(("payslip", "co" if loan == "education" else "primary"), 0)
        months = [(2026, m) for m in (7, 8, 9)][-n_pay:]
        for idx, (y, m) in enumerate(months):
            g = gross + (round(gross * 0.35) if tamper else 0)
            ded = {"Provident fund": pf, "Professional tax": 200, "Income tax (TDS)": tds}
            printed_net = g - sum(ded.values())
            if lv.tie and idx == 0 and role == ("co" if loan == "education" else "primary"):
                printed_net += 1000  # totals do not tie
            ctx_p = dict(employer=p.employer, employee=p.full_name, designation=p.designation,
                         emp_id=f"E{rng.randint(1000, 9999)}", pan=p.pan, doj=f"{doj:%d-%b-%Y}",
                         month_label=month_label(y, m), bank_last4=p.aadhaar[-4:], earnings=earnings if not tamper else
                         {**earnings, "Special allowance": earnings["Special allowance"] + round(gross * 0.35)},
                         deductions=ded, gross=g, total_deductions=sum(ded.values()), net=printed_net)  # fmt: skip
            pdf = render.payslip(ctx_p)
            if tamper:
                pdf = variants.tamper_metadata(pdf, rng, datetime(y, m, 28))
            lvl = level if level != "digital" else ("good" if rng.random() < 0.25 else "digital")
            self.add_visual(role, "payslip", f"payslip_{y}-{m:02d}", pdf, lvl,
                            {"employee": p.full_name, "employer": p.employer, "month": f"{y}-{m:02d}", "gross": g,
                             "net": printed_net, "pan": p.pan}, units=1)  # fmt: skip
        want_f16 = loan == "home" or (loan == "personal" and rng.random() < 0.5)
        if want_f16 and (role == "primary" or loan == "education"):
            annual = gross * 12 * (1.35 if tamper else 1.0)
            lines = {"Gross salary": annual, "Less: standard deduction": 75000.0,
                     "Taxable income": annual - 75000.0, "Tax deducted at source": float(tds * 12)}  # fmt: skip
            pdf = render.form16(
                dict(
                    employer=p.employer,
                    tan="BLRB12345C",
                    name=p.full_name,
                    pan=p.pan,
                    ay="2026-27",
                    period="01-Apr-2025 to 31-Mar-2026",
                    lines=lines,
                )
            )
            if tamper:
                pdf = variants.tamper_metadata(pdf, rng, datetime(2026, 5, 20))
            self.docs.append(
                Doc(
                    role,
                    "form16",
                    "form16.pdf",
                    pdf,
                    "digital_pdf",
                    1,
                    "digital",
                    {"gross": annual, "pan": p.pan},
                )
            )

    def self_employed_docs(self, role: str, p: Person, net: float, sz: dict[str, Any],
                           drops: dict[tuple[str, str], int], lv: Levers, tamper: bool, ctx: Context) -> None:  # fmt: skip
        rng, loan = self.rng, self.loan
        years = {"home": 3, "business": 2, "vehicle": 1, "education": 2}.get(loan, 1)
        years -= drops.get(("itr", "co" if loan == "education" else "primary"), 0)
        annual = net * 12
        entity = (
            self.business_name
            if loan == "business"
            else f"{p.surname} {rng.choice(BUSINESS_KINDS)[0]}"
        )
        p.employer = entity
        for i in range(max(years, 1)):
            ay = f"{2026 - i}-{(27 - i) % 100:02d}"
            income = annual * (1.0, 0.92, 0.85)[i] * (1.35 if tamper else 1.0)
            lines = {"Gross receipts": income / 0.15, "Net profit": income, "Gross total income": income,
                     "Deductions under chapter VI-A": 150000.0,
                     "Total taxable income": max(income - 150000, 0.0), "Tax paid": round(income * 0.08)}  # fmt: skip
            pdf = render.itr(
                dict(
                    ay=ay,
                    name=p.full_name,
                    pan=p.pan,
                    form="ITR-3",
                    filed=date(2026 - i, 7, 20),
                    ack=f"{rng.randint(10**11, 10**12 - 1)}",
                    lines=lines,
                )
            )
            if tamper and i == 0:
                pdf = variants.tamper_metadata(pdf, rng, datetime(2026, 7, 25))
            self.docs.append(Doc(role, "itr", f"itr_{ay}.pdf", pdf, "digital_pdf", 1, "digital",
                                 {"ay": ay, "pan": p.pan, "gross_total_income": income}))  # fmt: skip
        if loan in ("home", "business"):
            profit = annual * (1.35 if tamper else 1.0)
            revenue = sz.get("turnover", profit / 0.15)
            assets = {
                "Fixed assets": revenue * 0.2,
                "Inventory": revenue * 0.1,
                "Receivables": revenue * 0.08,
                "Cash and bank": revenue * 0.05,
            }
            loans_bs, payables = revenue * 0.12, revenue * 0.06
            pdf = render.pnl_balance_sheet(dict(
                entity=entity, year_end=date(2026, 3, 31),
                pnl={"Revenue from operations": revenue, "Cost of goods and services": revenue - profit - revenue * 0.1,
                     "Operating expenses": revenue * 0.1, "Net profit": profit},
                bs={**{f"Asset: {k}": v for k, v in assets.items()}, "Liability: Term loans": loans_bs,
                    "Liability: Payables": payables, "Capital and reserves": sum(assets.values()) - loans_bs - payables}))  # fmt: skip
            if tamper:
                pdf = variants.tamper_metadata(pdf, rng, datetime(2026, 7, 25))
            self.docs.append(Doc(role, "pnl_balance_sheet", "pnl_balance_sheet.pdf", pdf, "digital_pdf", 1, "digital",
                                 {"net_profit": profit}))  # fmt: skip

    def statement(self, role: str, p: Person, net: float, window: int, skip: int, lv: Levers,
                  sz: dict[str, Any], level: str) -> None:  # fmt: skip
        rng, loan = self.rng, self.loan
        salaried = p.employment_type == "salaried"
        earner_first = role == (list(self.income)[0])
        returns = lv.returns if earner_first else 0
        if loan == "business":
            ratio = [rng.uniform(0.86, 0.98), rng.uniform(0.6, 0.75)][lv.gst]
            # credits over the window annualise to ratio x turnover, however many months are shown
            per_month = ratio * sz["turnover"] / 12 * window / max(window - skip, 1)
        else:
            per_month = net if salaried else net * 1.25
        prof = StatementProfile(
            months=window, end_month=STMT_END, income_per_month=per_month,
            kind="salary" if salaried else "business", employer=p.employer, skip_income_months=skip,
            existing_emis=[(x["lender"], x["emi"]) for x in self.loans.get(role, [])], returns=returns,
            broken_balance=bool(lv.tie and not salaried and earner_first),
        )  # fmt: skip
        txns = build_statement(rng, prof)
        style = "citadel" if level != "digital" else rng.choice(["heritage", "horizon", "imperial"])
        bank, code = BANK_STYLES[style]
        first = add_months(STMT_END, -(window - 1))
        acct = f"{rng.randint(10**9, 10**10 - 1)}"
        pdf = render.bank_statement(style, dict(bank=bank, holder=p.full_name, account_no=acct, address=p.address,
                                                period_from=first, period_to=date(2026, 9, 30),
                                                ifsc=f"{code}0{rng.randint(10000, 99999)}"), txns)  # fmt: skip
        fmt, quality = "digital_pdf", "digital"
        if style == "citadel":
            pdf, fmt, quality = variants.scanned_pdf(pdf, rng), "scanned_pdf", level
        credits = [t for t in txns if t.tag in ("salary", "business_credit")]
        self.docs.append(Doc(role, "bank_statement", "bank_statement.pdf", pdf, fmt, window, quality,
                             {"style": style, "months": window, "account_no": acct, "returns": returns,
                              "credits_total": round(sum(t.credit for t in credits), 2)}))  # fmt: skip
        if loan == "business":
            self.facts["credits_annualised"] = sum(t.credit for t in credits) * 12 / window
        self.regularity.append((window - skip) / window)

    # ------------------------------------------------------------------ loan-specific documents
    def loan_docs(
        self, ctx: Context, lv: Levers, sz: dict[str, Any], drops: dict[tuple[str, str], int]
    ) -> dict[str, Any]:
        rng, loan = self.rng, self.loan
        p = self.persons["primary"]
        extra: dict[str, Any] = {}
        if loan == "home":
            seller = f"{rng.choice(['Mahesh', 'Sunil', 'Kamala', 'Rajeev'])} {rng.choice(SURNAMES)}"
            addr = f"Plot {rng.randint(1, 90)}, {rng.choice(['Lakeside Layout', 'Garden Enclave', 'Hilltop Colony'])}, {p.city}"
            owner = p.full_name
            deed_owner = seller if lv.pol3 else seller  # title deed always names the seller
            agreement_buyer = owner if not lv.pol3 else perturb(rng, owner, 20, 55)
            extra = dict(
                property_value=sz["property_value"],
                property_address=addr,
                seller_or_builder=seller,
                owner_name=owner,
            )
            self.simple("sale_agreement", "Agreement for Sale", "Registered Sub-Registrar (specimen)",
                        [("Seller", seller), ("Buyer", agreement_buyer), ("Property", addr),
                         ("Sale consideration", f"INR {int(sz['property_value']):,}"), ("Date", "05-Oct-2026")], truth={"buyer": agreement_buyer, "seller": seller})  # fmt: skip
            self.simple("title_deed", "Title Deed", "Registered Sub-Registrar (specimen)",
                        [("Owner", deed_owner), ("Property", addr), ("Survey no.", str(rng.randint(10, 999)))], truth={"owner": deed_owner})  # fmt: skip
            if not drops.get(("encumbrance_certificate", "primary")):
                self.simple("encumbrance_certificate", "Encumbrance Certificate", "Registration Department (specimen)",
                            [("Property", addr), ("Period", "2006 to 2026"), ("Result", "NIL encumbrances")])  # fmt: skip
            if not drops.get(("approved_plan", "primary")):
                self.simple("approved_plan", "Approved Building Plan", "Municipal Authority (specimen)",
                            [("Property", addr), ("Plan no.", f"BP/{rng.randint(1000, 9999)}/2025"), ("Status", "Approved")])  # fmt: skip
        elif loan == "education":
            c = self.persons["primary"]
            inst, country = (
                rng.choice(INSTITUTIONS_ABROAD)
                if self.abroad
                else (rng.choice(INSTITUTIONS_IN), "India")
            )
            course = rng.choice(
                ["B.Tech Computer Science", "MBA", "M.Sc Data Science", "B.Sc Nursing"]
            )
            extra = dict(course=course, institution=inst, country=country, course_duration_months=sz["course_years"] * 12,
                         total_fee=sz["total_fee"], moratorium_months=sz["moratorium"], margin_amount=sz["margin"],
                         collateral_offered=(not lv.pol2) and sz["collateral_needed"])  # fmt: skip
            self.simple("admission_letter", "Letter of Admission", inst,
                        [("Student", c.full_name), ("Course", course), ("Duration", f"{sz['course_years']} years"), ("Country", country)],
                        truth={"student": c.full_name, "course": course})  # fmt: skip
            if not drops.get(("fee_structure", "primary")):
                self.simple("fee_structure", "Fee Structure", inst, [("Course", course)],
                            tables=[[["Item", "Amount (INR)"], ["Tuition and other fees", f"{int(sz['total_fee']):,}"]]],
                            truth={"total_fee": sz["total_fee"]})  # fmt: skip
            if not drops.get(("marksheet", "primary")):
                self.simple("marksheet", "Statement of Marks", "State Secondary Board (specimen)",
                            [("Student", c.full_name), ("Result", "Pass"), ("Percentage", f"{rng.randint(62, 94)}%")])  # fmt: skip
        elif loan == "vehicle":
            kind, cond = ctx.vehicle_kind, ctx.vehicle_condition
            make, model = rng.choice(VEHICLES[kind])
            dealer = rng.choice(DEALERS)
            inv_model = (
                model
                if not lv.pol3
                else rng.choice([m for _, m in VEHICLES[kind] if m != model] or ["Edge 2.0"])
            )
            extra = dict(make=make, model=model, vehicle_condition=cond, vehicle_kind=kind,
                         on_road_price=sz["on_road"], dealer=dealer)  # fmt: skip
            self.simple("dealer_invoice", "Proforma Invoice", dealer,
                        [("Customer", p.full_name), ("Vehicle", f"{make} {inv_model}"),
                         ("On-road price", f"INR {int(sz['on_road']):,}")], truth={"model": inv_model, "on_road": sz["on_road"]})  # fmt: skip
            if kind == "two_wheeler":
                self.simple("driving_licence", "Driving Licence", "Transport Department (specimen)",
                            [("Name", p.full_name), ("DOB", f"{p.dob:%d/%m/%Y}"), ("Licence no.", f"DL{rng.randint(10**12, 10**13 - 1)}")])  # fmt: skip
            if cond == "used":
                self.simple("rc_book", "Registration Certificate", "Transport Department (specimen)",
                            [("Make/model", f"{make} {model}"), ("Registration", f"KA{rng.randint(10, 60)}AB{rng.randint(1000, 9999)}")])  # fmt: skip
                self.simple("insurance", "Motor Insurance Policy", "Invented Insurance Co (specimen)",
                            [("Insured", p.full_name), ("Valid till", "31-Mar-2027")])  # fmt: skip
        elif loan == "business":
            extra = self.business_docs(lv, sz, drops)
        return extra

    def simple(
        self,
        doc_type: str,
        title: str,
        issuer: str,
        fields: list[tuple[str, str]],
        tables: list[list[list[str]]] | None = None,
        truth: dict[str, Any] | None = None,
        role: str = "primary",
    ) -> None:
        pdf = render.letter(title, issuer, fields, tables=tables or [])
        self.docs.append(
            Doc(
                role,
                doc_type,
                f"{doc_type}.pdf",
                pdf,
                "digital_pdf",
                1,
                "digital",
                truth or dict(fields),
            )
        )

    def business_docs(
        self, lv: Levers, sz: dict[str, Any], drops: dict[tuple[str, str], int]
    ) -> dict[str, Any]:
        rng = self.rng
        p = self.persons["primary"]
        sc = next(c for c in CITIES if c[0] == p.city)
        kind_name, activity = self.business_kind
        constitution = self.constitution
        holder = {"Proprietorship": "P", "Partnership": "F", "Private Limited": "C"}[constitution]
        biz_pan = (
            p.pan if constitution == "Proprietorship" else self.ids.pan(self.business_name, holder)
        )
        gstin = make_gstin(rng, sc[1], biz_pan)
        if lv.pol2:  # embedded PAN does not belong to the business
            wrong = self.ids.pan(p.surname)
            gstin = make_gstin(rng, sc[1], wrong)
        udyam = make_udyam(rng, sc[1])
        vintage = self.vintage_months
        reg_on = add_months(APP_DATE, -vintage)
        self.simple("business_proof", "Shop and Establishment Certificate" if constitution == "Proprietorship" else "Certificate of Constitution",
                    "Local Authority (specimen)", [("Business", self.business_name), ("Constitution", constitution),
                                                     ("Activity", activity), ("Registered on", f"{reg_on:%d-%b-%Y}"), ("Promoter", p.full_name)])  # fmt: skip
        self.simple("gst_registration", "GST Registration Certificate", "GST Authority (specimen)",
                    [("GSTIN", gstin), ("Legal name", self.business_name), ("PAN", biz_pan),
                     ("Date of registration", f"{reg_on:%d-%b-%Y}")], truth={"gstin": gstin, "pan": biz_pan, "legal_name": self.business_name})  # fmt: skip
        self.simple("udyam_certificate", "Udyam Registration Certificate", "Ministry of MSME (specimen)",
                    [("Udyam number", udyam), ("Enterprise", self.business_name), ("PAN", biz_pan), ("Date", f"{reg_on:%d-%b-%Y}")],
                    truth={"udyam": udyam})  # fmt: skip
        months_n = 12 - drops.get(("gst_returns", "primary"), 0)
        weights = [rng.uniform(0.8, 1.2) for _ in range(months_n)]
        sales = [sz["turnover"] * w / sum(weights) * (months_n / 12) for w in weights]
        # keep the 12-month total equal to turnover even when months are missing
        first = add_months(STMT_END, -(months_n - 1))
        rows = [{"period": f"{add_months(first, i):%b %Y}", "sales": s, "tax": s * 0.18,
                 "filed": add_months(first, i + 1) + timedelta(days=19)} for i, s in enumerate(sales)]  # fmt: skip
        pdf = render.gst_returns(dict(gstin=gstin, legal_name=self.business_name, trade_name=self.business_name,
                                      months=rows, total=sum(sales)))  # fmt: skip
        self.docs.append(Doc("primary", "gst_returns", "gst_returns.pdf", pdf, "digital_pdf", months_n, "digital",
                             {"gstin": gstin, "total": sum(sales)}))  # fmt: skip
        self.gst_record = {"gstin": gstin, "legal_name": self.business_name, "pan": biz_pan,
                           "turnover_12m": sz["turnover"], "filings": [{"period": r["period"], "sales": round(r["sales"], 2)} for r in rows]}  # fmt: skip
        self.udyam_record = {
            "udyam_no": udyam,
            "legal_name": self.business_name,
            "pan": biz_pan,
            "registered_on": str(reg_on),
        }
        return dict(business_name=self.business_name, constitution=constitution, gstin=gstin, udyam_number=udyam,
                    vintage_months=vintage, annual_turnover=sz["turnover"])  # fmt: skip

    # ------------------------------------------------------------------ main
    def build(self, ctx: Context, lv: Levers) -> BuiltCase:
        rng, loan, kind = self.rng, self.loan, self.sc.kind
        drops = self.allocate_drops(lv.drop)
        # pre-draw values that sizing and documents share
        self.co_age = rng.randint(36, 40)
        self.co_age_hint = self.co_age
        if kind == "elig_age_over" and loan == "education":
            self.co_age = 50
            self.co_age_hint = 36  # repayment cap is ignored for this breach case
        self.employment_months = rng.randint(26, 140) if lv.stab == 0 else rng.randint(4, 20)
        self.total_experience = 0
        if loan == "personal":
            # PL-INC-12 wants >= 24 months experience, PL-INC-13 >= 12 months with this employer
            self.employment_months = [rng.randint(14, 100), rng.randint(3, 10), rng.randint(3, 8)][
                lv.stab
            ]
            exp = [rng.randint(30, 180), rng.randint(30, 180), rng.randint(8, 20)][lv.stab]
            self.total_experience = max(exp, self.employment_months)
        if loan == "business":
            self.business_kind = rng.choice(BUSINESS_KINDS)
            self.constitution = rng.choice(CONSTITUTIONS)
            self.vintage_months = rng.randint(36, 120) if lv.stab == 0 else rng.randint(12, 20)
        sz = self.size(ctx, lv)
        self.make_people(ctx, sz)
        if loan == "business":
            prom = self.persons["primary"]
            self.business_name = f"{prom.surname} {self.business_kind[0]} {'Pvt Ltd' if self.constitution == 'Private Limited' else ''}".strip()
            prom.employer = self.business_name
        self.identity_variants(lv)
        self.kyc_docs(lv)
        self.income_docs(ctx, lv, sz, drops)
        extra = self.loan_docs(ctx, lv, sz, drops)
        return self.finish(ctx, lv, sz, drops, extra)

    # ------------------------------------------------------------------ facts + answer key
    def finish(
        self,
        ctx: Context,
        lv: Levers,
        sz: dict[str, Any],
        drops: dict[tuple[str, str], int],
        extra: dict[str, Any],
    ) -> BuiltCase:
        rng, loan, kind = self.rng, self.loan, self.sc.kind
        persons_facts: list[dict[str, Any]] = []
        bureau: list[dict[str, Any]] = []
        identity: list[dict[str, Any]] = []
        earners = list(self.income)
        maturity = add_months(APP_DATE, sz["tenure"])
        cibil_by_role: dict[str, int] = {}
        for role, p in self.persons.items():
            s = self.shown[role]
            if role in earners:
                if kind == "elig_cibil_low":
                    base = {"business": (600, 640), "personal": (600, 640)}.get(loan, (640, 690))
                    score = rng.randint(*base) if role == earners[0] else 760
                elif role == earners[0]:
                    tiers = NOMINAL_CIBIL.get(loan, DEFAULT_CIBIL)
                    score = {
                        790: rng.randint(750, 830),
                        725: rng.randint(702, 745),
                        670: rng.randint(655, 695),
                        760: rng.randint(702, 800),
                        675: rng.randint(655, 695),
                    }[tiers[lv.cibil]]
                else:
                    score = rng.randint(740, 800)
                cibil_by_role[role] = score
                enq_n = [1, 3, 6][lv.enq] if role == earners[0] else 1
                bureau.append({"pan": p.pan, "cibil_score": score,
                               "active_loans": self.loans.get(role, []),
                               "enquiries": [{"date": str(APP_DATE - timedelta(days=rng.randint(5, 170))), "lender": rng.choice(LENDERS)}
                                             for _ in range(enq_n)]})  # fmt: skip
            if not (lv.lookup and role == "primary"):
                identity.append({"pan": p.pan, "name": p.full_name, "dob": str(p.dob),
                                 "aadhaar_hash": aadhaar_hash(p.aadhaar), "address": p.address})  # fmt: skip
            nm = min(name_score(p.full_name, s.pan_name), name_score(p.full_name, s.aadhaar_name))
            pf: dict[str, Any] = {
                "role": role, "pan_valid": pan_valid(s.pan, p.surname), "aadhaar_valid": aadhaar_valid(s.aadhaar),
                "name_match_score": nm, "dob_match": s.pan_dob == s.aadhaar_dob == p.dob,
                "is_resident": not (kind == "elig_nonresident" and role == "primary"),
                "age_at_application": age_on(p.dob, APP_DATE), "age_at_maturity": age_on(p.dob, maturity),
            }  # fmt: skip
            if role in cibil_by_role:
                pf["cibil_score"] = cibil_by_role[role]
            persons_facts.append(pf)

        k_missing = self.facts.pop("missing_kyc", None)
        total_income = sum(self.income.values())
        existing_total = sum(x["emi"] for ls in self.loans.values() for x in ls)
        emi_new = emi(
            sz["principal"],
            RATES[loan],
            (sz["repay_years"] * 12) if loan == "education" else sz["tenure"],
        )
        foir = round((existing_total + emi_new) / total_income * 100, 1)
        declared_total = sum(self.declared.values())
        verified_total = total_income
        units_have = self.count_units(ctx)
        q = [95, 72, 55][lv.docq]
        case: dict[str, Any] = {
            "kyc_docs_complete": k_missing is None,
            "tamper_suspected": kind == "tamper",
            "identity_lookup_match": lv.lookup == 0,
            "name_match_score": min(p["name_match_score"] for p in persons_facts),
            "address_match_score": min(name_score(self.persons[r].address, self.shown[r].aadhaar_address) for r in self.persons),
            "kyc_doc_quality": [95, 72, 55][lv.kycq],
            "mandatory_docs_ratio": round(units_have / ctx.units_total, 4),
            "doc_quality_score": q, "avg_field_confidence": [0.96, 0.82, 0.70][lv.docq],
            "totals_tie_out": lv.tie == 0, "foir": foir,
            "income_verified_ratio": round(verified_total / declared_total, 3),
            "income_regularity": round(min(self.regularity), 3),
            "cibil_score": cibil_by_role[earners[0]],
            "cheque_nach_returns_12m": lv.returns,
            "bureau_dpd_max_12m": max((x["dpd_max_12m"] for ls in self.loans.values() for x in ls), default=0),
            "enquiries_6m": len(bureau[0]["enquiries"]),
            "amount_band": sz.get("band", ""), "vehicle_kind": ctx.vehicle_kind, "vehicle_condition": ctx.vehicle_condition,
            "net_monthly_income": total_income,
        }  # fmt: skip
        if loan == "personal":
            case.update(total_experience_months=self.total_experience, months_with_current_employer=self.employment_months,
                        tenure_months=sz["tenure"], loan_amount=sz["principal"], loan_purpose_allowed=lv.pol3 == 0)  # fmt: skip
        elif loan == "home":
            case.update(stability_months=self.employment_months, tenure_months=sz["tenure"], ltv_percent=sz["ltv"],
                        property_docs_valid=lv.pol3 == 0)  # fmt: skip
        elif loan == "vehicle":
            case.update(stability_months=self.employment_months, tenure_months=sz["tenure"], ltv_percent=sz["ltv"],
                        vehicle_docs_valid=lv.pol3 == 0)  # fmt: skip
        elif loan == "education":
            case.update(coapp_income_verified=case["income_verified_ratio"] >= 0.75, stability_months=self.employment_months,
                        repayment_years=sz["repay_years"], collateral_ok=lv.pol2 == 0 or not sz["collateral_needed"],
                        margin_ok=lv.pol3 == 0 or sz["req_margin"] == 0)  # fmt: skip
        else:
            case.update(annual_turnover=sz["turnover"], business_vintage_months=self.vintage_months,
                        bank_credit_to_gst_ratio=round(self.facts["credits_annualised"] / sz["turnover"], 3), tenure_months=sz["tenure"],
                        gst_or_udyam_valid=gstin_valid(extra["gstin"], self.gst_record["pan"]),
                        loan_to_turnover=sz["loan_to_turnover"])  # fmt: skip
        ev = evaluate_case(self.rs, loan, case, persons_facts)
        if self.sc.kind == "score" and ev.total_score != self.sc.target:
            raise GenerationError(
                f"{self.sc.case_id}: got {ev.total_score}, wanted {self.sc.target}"
            )
        if self.sc.kind.startswith(("fix_", "elig_")) and ev.stopped_stage is None:
            raise GenerationError(f"{self.sc.case_id}: {self.sc.kind} did not stop")
        if self.sc.kind == "tamper" and not ev.capped_to_refer:
            raise GenerationError("tamper not flagged")
        return self.pack(ctx, lv, sz, extra, case, persons_facts, ev, bureau, identity, units_have)

    def count_units(self, ctx: Context) -> int:
        have = 0
        for r in self.rs.required_documents(self.loan):
            if r.kyc or not self.req_applies(ctx, r.when, r.applicant):
                continue
            role = r.applicant
            n = sum(d.units for d in self.docs if d.doc_type == r.type and d.role == role)
            if r.any_of:
                n = sum(d.units for d in self.docs if d.doc_type in r.any_of)
            have += min(n, r.min_count)
        return have

    def pack(self, ctx: Context, lv: Levers, sz: dict[str, Any], extra: dict[str, Any], case: dict[str, Any],
             persons_facts: list[dict[str, Any]], ev: Any, bureau: list[dict[str, Any]],
             identity: list[dict[str, Any]], units_have: int) -> BuiltCase:  # fmt: skip
        loan = self.loan
        applicants = []
        for role, p in self.persons.items():
            s = self.shown[role]
            a = {"role": role, "full_name": p.full_name, "dob": str(p.dob), "pan": s.pan,
                 "aadhaar_last4": s.aadhaar[-4:], "address": p.address, "phone": p.phone,
                 "employment_type": p.employment_type, "employer_or_business": p.employer or None,
                 "declared_monthly_income": round(self.declared[role]) if role in self.declared else None,
                 "relationship_to_primary": None if role == "primary" else p.extra.get("relationship", "parent"),
                 "residential_status": "NRI" if (self.sc.kind == "elig_nonresident" and role == "primary") else "resident"}  # fmt: skip
            if role in self.income:
                a["months_in_current_employment"] = self.employment_months
                if loan == "personal":
                    a["total_experience_months"] = self.total_experience
            applicants.append(a)
        purpose = "stock market investment" if (loan == "personal" and lv.pol3) else {
            "personal": "home renovation", "home": "purchase of residential property", "education": "higher education",
            "business": "working capital and expansion", "vehicle": "vehicle purchase"}[loan]  # fmt: skip
        application = {
            "case_id": self.sc.case_id, "loan_type": loan, "application_date": str(APP_DATE),
            "loan_amount": sz["principal"], "tenure_months": sz["tenure"], "purpose": purpose,
            "applicants": applicants, "loan_details": extra,
        }  # fmt: skip
        flags = sorted(
            {SEMANTIC_FLAGS[r] for r in ev.failed_rule_ids if r in SEMANTIC_FLAGS}
            | self.soft_flags(case, lv)
        )
        docs_truth = [{"file": f"documents/{d.role}/{d.name}", "doc_type": d.doc_type, "role": d.role, "format": d.fmt,
                       "units": d.units, "quality": d.quality, "blur_score": d.blur, "truth": d.truth} for d in self.docs]  # fmt: skip
        key = {
            "case_id": self.sc.case_id, "split": self.sc.split, "loan_type": loan, "scenario": self.sc.kind,
            "target_score": self.sc.target if self.sc.target is not None else ev.total_score,
            "expected_total_score": ev.total_score, "expected_band": ev.band,
            "expected_stop_stage": ev.stopped_stage, "expected_stop_class": ev.stop_class,
            "expected_flags": flags, "failed_rule_ids": ev.failed_rule_ids, "capped_to_refer": ev.capped_to_refer,
            "stage_scores": ev.stage_scores, "rules_version": self.rs.version, "levers": lv.as_dict(),
            "facts": case, "persons": persons_facts, "documents": docs_truth,
            "rule_results": [{"rule_id": r.rule_id, "stage": r.stage, "kind": r.kind, "passed": r.passed, "role": r.role,
                              "points_awarded": r.points_awarded, "points_max": r.points_max, "evidence": r.evidence} for r in ev.results],
            "units": {"required": ctx.units_total, "present": units_have},
        }  # fmt: skip
        fairness = [{"case_id": self.sc.case_id, "applicant_role": role, "gender": p.gender,
                     "age_band": "<30" if age_on(p.dob, APP_DATE) < 30 else "30-44" if age_on(p.dob, APP_DATE) < 45 else "45+",
                     "city_tier": f"tier{p.tier}"} for role, p in self.persons.items()]  # fmt: skip
        return BuiltCase(self.sc, application, self.docs, key, identity, bureau,
                         [self.gst_record] if loan == "business" else [],
                         [self.udyam_record] if loan == "business" else [], fairness)  # fmt: skip

    def soft_flags(self, case: dict[str, Any], lv: Levers) -> set[str]:
        f: set[str] = set()
        if case["foir"] > 50:
            f.add("foir_over_cap")
        elif case["foir"] > 40:
            f.add("high_foir")
        if case["mandatory_docs_ratio"] < 1:
            f.add("missing_documents")
        if not case["totals_tie_out"]:
            f.add("totals_mismatch")
        if case["doc_quality_score"] < 80 or case["kyc_doc_quality"] < 80:
            f.add("low_document_quality")
        if case["income_regularity"] < 0.9:
            f.add("irregular_income")
        if case["cheque_nach_returns_12m"] > 0:
            f.add("cheque_nach_returns")
        if case["bureau_dpd_max_12m"] > 0:
            f.add("past_due_history")
        if case["income_verified_ratio"] < 0.9:
            f.add("income_mismatch")
        if not case["identity_lookup_match"]:
            f.add("identity_lookup_miss")
        if case["address_match_score"] < 85:
            f.add("address_mismatch")
        return f


def build_case(
    sc: Scenario, ids: IdFactory, seed: int, ruleset: RuleSet, attempts: int = 12
) -> BuiltCase:
    last: Exception | None = None
    for attempt in range(attempts):
        rng = random.Random(f"{seed}-{sc.case_id}-{attempt}")
        b = CaseBuilder(sc, ids, rng, ruleset)
        ctx = b.choose_context()
        if sc.kind == "score":
            assert sc.target is not None
            lv = find_levers(rng, ruleset, ctx, sc.target)
        else:
            lv = Levers(tie=0)
        try:
            return b.build(ctx, lv)
        except GenerationError as exc:
            last = exc
    raise GenerationError(f"{sc.case_id}: gave up after {attempts} attempts: {last}")
