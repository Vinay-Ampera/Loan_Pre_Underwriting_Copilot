"""The counter-offer box (Stage 12 Part A): pure code, no database, no model."""

from datetime import date
from typing import Any

import pytest

from app.intake.validators import gstin_check_char
from app.notifications.check import check_message
from app.notifications.templates import FOOTER
from app.scoring import counter_offer as co
from app.scoring import finance
from app.scoring.counter_offer import build_counter_offer, inr, inr_short, tenure_limit
from app.scoring.engine import score_case
from app.scoring.models import (
    CaseInput,
    DocumentInput,
    GstInput,
    LoanRecord,
    ScoreReport,
    StatementAnalytics,
)
from app.scoring.rules import RuleSet, load_rules
from tests.scoring_cases import APP_DATE, income_docs, kyc_docs, person, personal_case


@pytest.fixture(scope="module")
def rs() -> RuleSet:
    return load_rules()


def worked_case(*, amount: float = 1_000_000, tenure: int = 36, purpose: str = "car",
                returns: int = 3, income_months: int = 5, dob: date = date(1990, 5, 14),
                cibil: int = 705) -> CaseInput:  # fmt: skip
    """The worked example: personal loan at 12%, verified income ₹60,000 a month, existing EMIs
    ₹10,000. The other stages lose 36 points that amount and tenure cannot move (identity lookup,
    address, KYC photo quality, regularity, experience, CIBIL 705, returns, DPD, enquiries), so 6
    more FOIR points stay in reject and 12 more reach refer."""
    loans = [LoanRecord(lender="Apex", emi=10000, remaining_emis=40, dpd_max_12m=45)]
    p = person(loans=loans, cibil=cibil, dob=dob).model_copy(update={
        "identity_match": False, "total_experience_months": 12, "months_in_current_employment": 6,
        "address": "45, Lake View, Nagpur, Maharashtra 440001"})  # fmt: skip
    assert p.bureau is not None
    p.bureau.enquiry_dates = [date(2026, m, 1) for m in (5, 6, 7, 8, 9)]
    docs = [*kyc_docs(q=50, dob=dob.isoformat()), *income_docs()]
    for d in docs:
        if d.doc_type == "bank_statement":
            d.statement = StatementAnalytics(months=6, income_months=income_months,
                                             credits_total=60000 * income_months,
                                             cheque_returns=returns, detected_emi_monthly=10000)  # fmt: skip
    return personal_case(loan_amount=amount, tenure_months=tenure, persons=[p], documents=docs,
                         purpose=purpose)  # fmt: skip


def box_for(case: CaseInput, rs: RuleSet) -> tuple[ScoreReport, co.CounterOffer | None]:
    score = score_case(case, rs)
    return score, build_counter_offer(case, score, rs)


def rescored(case: CaseInput, rs: RuleSet, amount: float, tenure: int) -> ScoreReport:
    return score_case(case.model_copy(update={"loan_amount": amount, "tenure_months": tenure}), rs)


def assert_within_limits(case: CaseInput, box: co.CounterOffer, rs: RuleSet) -> None:
    """No line passes the product's tenure rule or takes anyone past 55 at maturity (E-110)."""
    for line in box.lines:
        if line.kind not in ("tenure", "amount"):
            continue
        r = rescored(case, rs, line.amount or 0, line.tenure_months)
        assert r.stopped_stage is None
        assert all(p["age_at_maturity"] <= rs.age.max_age_at_maturity for p in r.person_facts)
        field_of = {rule.rule_id: rule.field for rule in rs.rules}
        tenure_rules = [o for o in r.results if field_of[o.rule_id] in co.TENURE_UNITS]
        assert tenure_rules and all(o.passed for o in tenure_rules)


# --- the worked example ---------------------------------------------------------------------
def test_worked_example_numbers_come_from_the_finance_code(rs: RuleSet) -> None:
    case = worked_case()
    score = score_case(case, rs)
    assert (score.total_score, score.band, score.capped_to_refer) == (52.0, "reject", False)
    assert round(score.case_facts["new_emi"]) == 33214 and score.case_facts["foir"] == 72.0
    longer = rescored(case, rs, 1_000_000, 60)
    assert round(longer.case_facts["new_emi"]) == 22244 and longer.case_facts["foir"] == 53.7
    assert longer.total_score == 52.0  # still 0 FOIR points: no line (a)
    seven = rescored(case, rs, 700_000, 60)
    assert round(seven.case_facts["new_emi"]) == 15571 and seven.case_facts["foir"] == 42.6
    assert (seven.total_score, seven.band) == (58.0, "reject")  # 6 points stay in reject
    six_two = rescored(case, rs, 620_000, 60)
    assert round(six_two.case_facts["new_emi"]) == 13792 and six_two.case_facts["foir"] == 39.7
    assert (six_two.total_score, six_two.band) == (64.0, "refer")  # 12 points reach refer


def test_worked_example_box_is_the_largest_amount_that_reaches_refer(rs: RuleSet) -> None:
    case = worked_case(purpose="home renovation")
    _, box = box_for(case, rs)
    assert box is not None and [line.kind for line in box.lines] == ["amount"]
    line = box.lines[0]
    # ₹6.3L gives FOIR 40.0%, which still earns the 40% tier, so it beats the ₹6.2L of the brief
    assert (line.amount, line.tenure_months, line.band, line.foir) == (630_000, 60, "refer", 40.0)
    assert line.emi == 14014.0 and line.rate_pct == 12.0 and line.scored
    assert line.text == ("Pramaan estimates ₹6.3L over 5 years would be recommended for refer "
                         "(FOIR 40.0%).")  # fmt: skip
    assert line.tags == ["EMI ₹14,014"]
    assert rescored(case, rs, 640_000, 60).band == "reject"  # the next step up does not
    assert_within_limits(case, box, rs)


def test_worked_example_purpose_car_adds_the_vehicle_line(rs: RuleSet) -> None:
    _, box = box_for(worked_case(purpose="car"), rs)
    assert box is not None and [line.kind for line in box.lines] == ["amount", "alternate"]
    alt = box.lines[1]
    assert (alt.loan_type, alt.amount, alt.tenure_months, alt.rate_pct) == (
        "vehicle",
        1_000_000,
        84,
        9.5,
    )
    assert round(alt.emi or 0) == 16344 and alt.foir == 43.9
    assert alt.band is None and not alt.scored and alt.tags == ["Not scored"]
    assert alt.extra_documents == ["dealer invoice"]
    assert alt.text == (
        "The stated purpose fits a vehicle loan: ₹10L over 7 years at 9.5%, EMI ₹16,344, "
        "FOIR 43.9%. A new application, not scored. It would also need: dealer invoice."
    )


def test_line_a_is_the_shortest_longer_whole_year_tenure(rs: RuleSet) -> None:
    case = worked_case(amount=700_000, returns=2, income_months=6)  # 55: 6 FOIR points reach refer
    score, box = box_for(case, rs)
    assert (score.total_score, score.band) == (55.0, "reject")
    assert box is not None and box.lines[0].kind == "tenure"
    line = box.lines[0]
    assert (line.amount, line.tenure_months, line.band, line.foir) == (700_000, 48, "refer", 47.4)
    assert line.text.startswith("Pramaan estimates ₹7L over 4 years would be recommended for refer")
    assert "amount" not in [x.kind for x in box.lines]  # (b) would have to reach approve
    assert_within_limits(case, box, rs)


# --- never shown ----------------------------------------------------------------------------
def test_no_box_on_approve(rs: RuleSet) -> None:
    score, box = box_for(personal_case(), rs)
    assert score.band == "approve" and box is None


def _with_loan(**over: Any) -> CaseInput:
    loans = [LoanRecord(lender="Apex", emi=10000, remaining_emis=40)]
    return personal_case(loan_amount=1_000_000, persons=[person(loans=loans, **over)])


def test_no_box_on_refer_held_by_pl_cibil_02(rs: RuleSet) -> None:
    score, box = box_for(_with_loan(cibil=680), rs)
    assert score.band == "refer" and score.capped_to_refer
    assert "PL-CIBIL-02" in score.failed_rule_ids and "CM-INC-10" in score.failed_rule_ids
    assert box is None


def test_no_box_on_refer_held_by_cm_frd_01(rs: RuleSet) -> None:
    case = _with_loan().model_copy(update={"extra_tamper_hints": ["EDITOR_PRODUCER"]})
    score, box = box_for(case, rs)
    assert score.band == "refer" and "CM-FRD-01" in score.failed_rule_ids and box is None


def test_no_box_on_refer_held_by_bl_crd_20(rs: RuleSet) -> None:
    first14 = "08PPIPM4603I9Z"
    gstin = first14 + gstin_check_char(first14)
    owner = person("primary", emp="self_employed", income=300000)
    common: dict[str, Any] = dict(quality_score=95, avg_confidence=0.96, tie_out_ok=True)
    itr = [DocumentInput(doc_type="itr", fields={"ay": f"{2026 - i}-{27 - i}", "gross_total_income": 3_600_000, "name": "Rekha Sinha"}, **common) for i in range(2)]  # fmt: skip
    docs = [*kyc_docs(), *itr,
            DocumentInput(doc_type="business_proof", fields={"registered_on": "20-Jun-2019"}, **common),
            DocumentInput(doc_type="gst_registration", fields={"gstin": gstin, "pan": "PPIPM4603I"}, **common),
            DocumentInput(doc_type="gst_returns", units=12, **common),
            DocumentInput(doc_type="pnl_balance_sheet", fields={"net_profit": 3_600_000}, **common),
            DocumentInput(doc_type="bank_statement", units=12, statement=StatementAnalytics(
                months=12, income_months=12, credits_total=26_000_000, cheque_returns=3), **common)]  # fmt: skip
    case = CaseInput(case_id="T-BL-1", loan_type="business", application_date=APP_DATE,
                     loan_amount=10_000_000, tenure_months=60, purpose="working capital",
                     persons=[owner], documents=docs, details={},
                     gst=GstInput(gstin=gstin, pan="PPIPM4603I", turnover_12m=29_000_000))  # fmt: skip
    score, box = box_for(case, rs)
    assert score.band == "refer" and "BL-CRD-20" in score.failed_rule_ids
    assert "BL-POL-12" in score.failed_rule_ids  # a movable loss exists, and still no box
    assert box is None


def test_a_capped_reject_case_gets_lines_to_refer_only(rs: RuleSet) -> None:
    score, box = box_for(worked_case(cibil=680), rs)
    assert score.band == "reject" and score.capped_to_refer
    assert box is not None
    assert {line.band for line in box.lines if line.scored} == {"refer"}  # never aims at approve


@pytest.mark.parametrize(
    ("label", "case"),
    [
        ("fix-type stop", personal_case(documents=[*kyc_docs(name="Mahesh Kumar"), *income_docs()])),
        ("CIBIL floor", personal_case(persons=[person(cibil=600)])),
        ("residency", personal_case(persons=[person().model_copy(update={"residential_status": "NRI"})])),
        ("minimum age", personal_case(persons=[person(dob=date(2007, 1, 1))],
                                      documents=[*kyc_docs(dob="2007-01-01"), *income_docs()])),
    ],
)  # fmt: skip
def test_no_box_on_a_stop_other_than_age(rs: RuleSet, label: str, case: CaseInput) -> None:
    score, box = box_for(case, rs)
    assert score.stopped_stage is not None, label
    assert box is None, label


def test_no_box_when_only_unmovable_rules_lost_points(rs: RuleSet) -> None:
    score, box = box_for(worked_case(amount=300_000), rs)  # FOIR fine; points lost elsewhere
    assert score.band == "refer" and "CM-INC-10" not in score.failed_rule_ids
    assert box is None


def test_no_box_when_only_an_amount_under_half_would_help(rs: RuleSet) -> None:
    score, box = box_for(worked_case(amount=2_000_000, tenure=60), rs)
    assert score.band == "reject"
    assert rescored(worked_case(amount=2_000_000, tenure=60), rs, 630_000, 60).band == "refer"
    assert box is None  # ₹6.3L is under 50% of ₹20L, and 60 months is already the limit


# --- tenure limits --------------------------------------------------------------------------
def test_tenure_limits_are_read_from_the_rules(rs: RuleSet) -> None:
    assert tenure_limit(rs, "personal", {}) == 60
    assert tenure_limit(rs, "home", {}) == 360
    assert tenure_limit(rs, "business", {}) == 84
    assert tenure_limit(rs, "education", {}) == 180  # ED-POL-10: 15 repayment years
    assert tenure_limit(rs, "vehicle", {"vehicle_kind": "new_car"}) == 84
    assert tenure_limit(rs, "vehicle", {"vehicle_kind": "used_car"}) == 60
    assert tenure_limit(rs, "vehicle", {"vehicle_kind": "two_wheeler"}) == 60
    assert tenure_limit(rs, "vehicle", None) == 84  # alternate product: the longest


def test_age_55_at_maturity_caps_the_tenure(rs: RuleSet) -> None:
    case = worked_case(amount=800_000, dob=date(1973, 11, 1))  # 55 until 2029-11-01: 36 months
    _, box = box_for(case, rs)
    assert box is not None
    assert all(line.tenure_months <= 36 for line in box.lines)
    assert (box.lines[0].kind, box.lines[0].amount, box.lines[0].band) == (
        "amount",
        420_000,
        "refer",
    )
    assert_within_limits(case, box, rs)


def education_case() -> CaseInput:
    """A parent co-applicant who reaches 56 in January 2040 (E-35): at most 158 months."""
    student = person("primary", emp="student", income=None, cibil=None, dob=date(2005, 3, 1), name="Asha Sinha")  # fmt: skip
    parent = person("co", income=40000, dob=date(1984, 1, 1),
                    loans=[LoanRecord(lender="Apex", emi=10000, remaining_emis=40)])  # fmt: skip
    parent = parent.model_copy(update={"identity_match": False})
    docs = [*kyc_docs("primary", name="Asha Sinha", dob="2005-03-01"), *kyc_docs("co", dob="1984-01-01"), *income_docs("co", 40000)]  # fmt: skip
    docs += [DocumentInput(doc_type="admission_letter", fields={"student": "Asha Sinha", "country": "India"}),
             DocumentInput(doc_type="fee_structure", fields={"total_fee": 900000}),
             DocumentInput(doc_type="marksheet", fields={"student": "Asha Sinha"})]  # fmt: skip
    details = {"moratorium_months": 36, "total_fee": 900000, "country": "India", "margin_amount": 60000, "collateral_offered": True}  # fmt: skip
    return CaseInput(case_id="T-ED-1", loan_type="education", application_date=APP_DATE,
                     loan_amount=840000, tenure_months=144, purpose="higher education",
                     persons=[student, parent], documents=docs, details=details)  # fmt: skip


def test_education_includes_the_moratorium_and_the_parent_age_cap(rs: RuleSet) -> None:
    case = education_case()
    score, box = box_for(case, rs)
    assert score.band == "refer" and not score.capped_to_refer
    assert box is not None and [line.kind for line in box.lines] == ["amount"]
    line = box.lines[0]
    assert line.tenure_months == 156  # 36 moratorium + 10 whole repayment years, under 158
    assert (line.tenure_months - 36) % 12 == 0
    assert (line.amount, line.band) == (770_000, "approve")
    assert "including the moratorium" in line.text
    end = finance.add_months(APP_DATE, line.tenure_months)
    assert all(finance.age_on(p.dob, end) <= 55 for p in case.persons)
    assert_within_limits(case, box, rs)


# --- the age stop ---------------------------------------------------------------------------
def test_age_stop_gets_a_tenure_line_only_and_no_rescoring(
    rs: RuleSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = worked_case(tenure=60, dob=date(1973, 1, 1))
    score = score_case(case, rs)
    assert (score.stopped_stage, score.stop_class) == ("kyc", "eligibility")

    def no_rescoring(*_: object, **__: object) -> ScoreReport:
        raise AssertionError("an age stop is never rescored")

    monkeypatch.setattr(co, "score_case", no_rescoring)
    box = build_counter_offer(case, score, rs)
    assert box is not None and len(box.lines) == 1
    line = box.lines[0]
    assert (line.kind, line.band, line.scored, line.amount, line.emi) == (
        "age_tenure",
        None,
        False,
        None,
        None,
    )
    assert line.tenure_months == 26  # 2028-12-20: still 55; a month more is 56
    assert line.text == ("A tenure of up to 26 months keeps every applicant at 55 or under at "
                         "maturity. Not scored: the assessment stopped before income was checked.")  # fmt: skip


def test_age_stop_with_under_12_months_left_gets_no_line(rs: RuleSet) -> None:
    score, box = box_for(worked_case(tenure=36, dob=date(1971, 9, 1)), rs)  # 10 months left
    assert score.stop_class == "eligibility" and box is None


def test_age_stop_with_another_failure_gets_no_box(rs: RuleSet) -> None:
    old = worked_case(tenure=60, dob=date(1973, 1, 1))
    nri = old.model_copy(update={"persons": [old.persons[0].model_copy(update={"residential_status": "NRI"})]})  # fmt: skip
    score, box = box_for(nri, rs)
    assert {"CM-ELIG-01", "CM-ELIG-03"} <= set(score.failed_rule_ids) and box is None


# --- the alternate product ------------------------------------------------------------------
def test_two_products_in_the_purpose_means_no_alternate_line(rs: RuleSet) -> None:
    _, box = box_for(worked_case(purpose="car for my shop"), rs)
    assert box is not None and "alternate" not in [line.kind for line in box.lines]


def test_business_alternate_needs_a_self_employed_earner(rs: RuleSet) -> None:
    _, box = box_for(worked_case(purpose="working capital"), rs)  # salaried applicant
    assert box is not None and "alternate" not in [line.kind for line in box.lines]


def test_alternate_line_is_dropped_when_its_foir_is_not_better(rs: RuleSet) -> None:
    case = worked_case(purpose="car")
    score = score_case(case, rs)
    lower = score.model_copy(update={"case_facts": {**score.case_facts, "foir": 43.9}})
    box = build_counter_offer(case, lower, rs)
    assert box is not None and "alternate" not in [line.kind for line in box.lines]


def test_alternate_line_never_appears_on_its_own(rs: RuleSet) -> None:
    _, box = box_for(worked_case(amount=300_000, purpose="car"), rs)  # nothing else to show
    assert box is None


def test_keywords_match_whole_words_only(rs: RuleSet) -> None:
    for purpose in ("career course", "carpet shopkeeping", "scar treatment"):
        _, box = box_for(worked_case(purpose=purpose), rs)
        assert box is not None and "alternate" not in [line.kind for line in box.lines], purpose


# --- other checks ---------------------------------------------------------------------------
def test_the_run_precedent_bonus_is_passed_through_unchanged(
    rs: RuleSet, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = worked_case()
    score = score_case(case, rs).model_copy(update={"precedent_bonus": 3.0})
    seen: list[float] = []

    def recording(inp: CaseInput, ruleset: RuleSet, *, precedent_bonus: float = 0.0) -> ScoreReport:
        seen.append(precedent_bonus)
        return score_case(inp, ruleset, precedent_bonus=precedent_bonus)

    monkeypatch.setattr(co, "score_case", recording)
    build_counter_offer(case, score, rs)
    assert seen and set(seen) == {3.0}


def test_the_same_input_gives_the_same_box(rs: RuleSet) -> None:
    case = worked_case()
    a, b = box_for(case, rs)[1], box_for(case, rs)[1]
    assert a is not None and a.model_dump() == (b.model_dump() if b else None)
    assert a.rules_version == rs.version


def test_the_customer_message_check_blocks_every_line_kind(rs: RuleSet) -> None:
    lines = {
        "amount": box_for(worked_case(), rs)[1],
        "tenure": box_for(worked_case(amount=700_000, returns=2, income_months=6), rs)[1],
        "age_tenure": box_for(worked_case(tenure=60, dob=date(1973, 1, 1)), rs)[1],
    }
    texts = {kind: next(x.text for x in box.lines if x.kind == kind)
             for kind, box in lines.items() if box is not None}  # fmt: skip
    alt = lines["amount"]
    assert alt is not None
    texts["alternate"] = next(x.text for x in alt.lines if x.kind == "alternate")
    assert set(texts) == {"amount", "tenure", "age_tenure", "alternate"}
    for kind, text in texts.items():
        reasons = check_message("A note from your bank", text, final_text=f"{text}\n{FOOTER}")
        assert "Mentions a score, a band or a rule" in reasons, kind
        if kind != "age_tenure":
            assert "Contains an amount of money" in reasons, kind
        if kind in ("amount", "tenure"):
            assert "Mentions a result of the assessment" in reasons, kind


def test_money_wording(rs: RuleSet) -> None:
    assert inr(13791.56) == "₹13,792" and inr(1234567) == "₹12,34,567"
    assert inr_short(630_000) == "₹6.3L" and inr_short(1_000_000) == "₹10L"
    assert inr_short(12_500_000) == "₹1.25Cr" and inr_short(85_000) == "₹85,000"
    assert co.tenure_words(60) == "5 years" and co.tenure_words(12) == "1 year"
    assert co.tenure_words(26) == "26 months"


def test_rules_file_block_is_validated(rs: RuleSet) -> None:
    assert rs.counter_offer.bands == ["reject", "refer"] and rs.counter_offer.min_share == 0.5
    data = rs.model_dump(exclude={"checksum"})
    data["counter_offer"]["moves_fields"] = ["foir", "not_a_fact"]
    with pytest.raises(ValueError, match="not read by any rule"):
        RuleSet.model_validate(data)
