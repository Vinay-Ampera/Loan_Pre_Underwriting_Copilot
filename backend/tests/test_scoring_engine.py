"""End-to-end scoring from structured inputs: stage order, early stop, caps, aggregation."""

from datetime import date

import pytest

from app.scoring import finance
from app.scoring.engine import apply_precedent_bonus, score_case
from app.scoring.models import (
    CaseInput,
    DocumentInput,
    GstInput,
    LoanRecord,
    StatementAnalytics,
)
from app.scoring.rules import RuleSet, load_rules
from tests.scoring_cases import APP_DATE, income_docs, kyc_docs, person, personal_case


@pytest.fixture(scope="module")
def rs() -> RuleSet:
    return load_rules()


def replace_doc(case: CaseInput, doc_type: str, **fields: object) -> CaseInput:
    docs = [d.model_copy(update={"fields": {**d.fields, **fields}}) if d.doc_type == doc_type else d
            for d in case.documents]  # fmt: skip
    return case.model_copy(update={"documents": docs})


# --- the clean path ---------------------------------------------------------------------------
def test_clean_personal_case_scores_100_and_is_recommended(rs: RuleSet) -> None:
    r = score_case(personal_case(), rs)
    assert (r.total_score, r.band, r.recommendation) == (100.0, "approve", "recommend_approve")
    assert r.stages_run == ["extraction", "kyc", "risk", "policy"]
    assert r.stage_scores == r.stage_max and not r.failed_rule_ids
    assert r.rules_version == rs.version and r.rules_checksum == rs.checksum


def test_every_result_carries_a_rule_id_clause_and_evidence(rs: RuleSet) -> None:
    for res in score_case(personal_case(), rs).results:
        assert res.rule_id and res.clause_id and "field" in res.evidence


def test_foir_is_computed_in_code_from_bureau_loans_and_the_new_emi(rs: RuleSet) -> None:
    loans = [LoanRecord(lender="Apex", emi=9000, remaining_emis=30),
             LoanRecord(lender="Unity", emi=4000, remaining_emis=12)]  # 12 left: excluded (HL-PROD-04)  # fmt: skip
    case = personal_case(persons=[person(loans=loans)])
    r = score_case(case, rs)
    expected = finance.foir_pct(9000, finance.emi(300000, 12.0, 36), 60000)
    assert r.case_facts["foir"] == expected and r.case_facts["existing_emi_total"] == 9000
    assert r.case_facts["dti_pct"] is not None


def test_high_foir_scores_less_and_raises_a_finding(rs: RuleSet) -> None:
    loans = [LoanRecord(lender="Apex", emi=24000, remaining_emis=40)]
    r = score_case(personal_case(persons=[person(loans=loans)]), rs)
    assert r.case_facts["foir"] > 50
    assert r.stage_scores["income"] < 30
    assert "FOIR_OVER_CAP" in {f.code for f in r.findings}


# --- hard fails and early stop ------------------------------------------------------------------
def test_fix_type_stop_is_short_and_has_no_score(rs: RuleSet) -> None:
    case = personal_case(persons=[person().model_copy(update={"pan": "BAD"})])
    docs = [d for d in case.documents if d.doc_type != "pan_card"]
    docs.append(DocumentInput(doc_type="pan_card", fields={"name": "Rekha Sinha", "dob": "1990-05-14", "pan": "ABCPS12"}, quality_score=95))  # fmt: skip
    r = score_case(case.model_copy(update={"documents": docs}), rs)
    assert (r.stopped_stage, r.stop_class, r.recommendation) == ("kyc", "fix", "fix_required")
    assert r.total_score is None and r.band is None and r.indicative_score is None
    assert r.stages_run == ["extraction", "kyc"]  # risk and policy never ran
    assert "foir" not in r.case_facts and "CM-KYC-01" in r.failed_rule_ids


def test_missing_kyc_document_is_reported_once(rs: RuleSet) -> None:
    case = personal_case()
    case = case.model_copy(
        update={"documents": [d for d in case.documents if d.doc_type != "aadhaar"]}
    )
    r = score_case(case, rs)
    hard_fails = [x.rule_id for x in r.results if x.kind == "hard" and not x.passed]
    assert r.stop_class == "fix" and hard_fails == ["CM-DOC-01"]


def test_name_mismatch_is_a_fix_type_stop(rs: RuleSet) -> None:
    r = score_case(replace_doc(personal_case(), "pan_card", name="Mahesh Kumar"), rs)
    assert (r.stopped_stage, r.stop_class) == ("kyc", "fix") and "CM-KYC-03" in r.failed_rule_ids


def test_dob_mismatch_is_a_fix_type_stop(rs: RuleSet) -> None:
    r = score_case(replace_doc(personal_case(), "aadhaar", dob="1989-05-14"), rs)
    assert r.stop_class == "fix" and "CM-KYC-04" in r.failed_rule_ids


def test_invalid_aadhaar_checksum_is_a_fix_type_stop(rs: RuleSet) -> None:
    r = score_case(replace_doc(personal_case(), "aadhaar", aadhaar="234567890125"), rs)
    assert r.stop_class == "fix" and "CM-KYC-02" in r.failed_rule_ids


def test_age_over_cap_at_maturity_recommends_reject_with_capped_score(rs: RuleSet) -> None:
    old = person(dob=date(1973, 1, 1))  # 52 now, 55+ before a 60-month loan ends
    docs = [*kyc_docs(dob="1973-01-01"), *income_docs()]
    r = score_case(personal_case(persons=[old], documents=docs, tenure_months=60), rs)
    assert (r.stopped_stage, r.stop_class, r.band) == ("kyc", "eligibility", "reject")
    assert r.recommendation == "recommend_reject" and r.total_score is None
    assert r.indicative_score is not None and r.indicative_score <= rs.scoring.eligibility_score_cap
    assert "CM-ELIG-03" in r.failed_rule_ids


def test_under_21_and_non_resident_are_eligibility_stops(rs: RuleSet) -> None:
    young = personal_case(persons=[person(dob=date(2007, 1, 1))], documents=[*kyc_docs(dob="2007-01-01"), *income_docs()])  # fmt: skip
    assert "CM-ELIG-02" in score_case(young, rs).failed_rule_ids
    nri = personal_case(persons=[person().model_copy(update={"residential_status": "NRI"})])
    r = score_case(nri, rs)
    assert r.stop_class == "eligibility" and "CM-ELIG-01" in r.failed_rule_ids


def test_cibil_below_floor_stops_at_risk_and_policy_never_runs(rs: RuleSet) -> None:
    r = score_case(personal_case(persons=[person(cibil=640)]), rs)
    assert (r.stopped_stage, r.stop_class, r.band) == ("risk", "eligibility", "reject")
    assert r.stages_run == ["extraction", "kyc", "risk"]
    assert "PL-CIBIL-01" in r.failed_rule_ids


def test_no_bureau_record_is_a_reject_not_a_crash(rs: RuleSet) -> None:
    r = score_case(personal_case(persons=[person(cibil=None)]), rs)
    assert r.band == "reject" and "PL-CIBIL-01" in r.failed_rule_ids


def test_cibil_650_to_699_is_never_a_silent_pass(rs: RuleSet) -> None:
    r = score_case(personal_case(persons=[person(cibil=680)]), rs)
    assert r.stopped_stage is None and r.capped_to_refer and r.band == "refer"
    assert r.total_score is not None and r.total_score >= 85  # would have been approve


def test_fix_wins_over_eligibility_in_the_same_stage(rs: RuleSet) -> None:
    old = person(dob=date(1973, 1, 1))
    docs = [*kyc_docs(dob="1973-01-01", name="Mahesh Kumar"), *income_docs()]
    r = score_case(personal_case(persons=[old], documents=docs, tenure_months=60), rs)
    assert r.stop_class == "fix"


# --- documents --------------------------------------------------------------------------------
def test_missing_payslips_lower_the_documents_score(rs: RuleSet) -> None:
    full = score_case(personal_case(), rs)
    two = score_case(personal_case(documents=[*kyc_docs(), *income_docs(slips=2)]), rs)
    assert full.case_facts["mandatory_docs_ratio"] == 1.0
    assert two.case_facts["mandatory_docs_ratio"] == round(8 / 9, 4)
    assert two.stage_scores["documents"] < full.stage_scores["documents"]


def test_duplicates_do_not_fill_a_missing_slot(rs: RuleSet) -> None:
    docs = [*kyc_docs(), *income_docs(slips=1)]
    slip = next(d for d in docs if d.doc_type == "payslip")
    docs += [slip.model_copy(), slip.model_copy()]  # the same payslip uploaded three times
    r = score_case(personal_case(documents=docs), rs)
    assert r.case_facts["mandatory_docs_ratio"] == round(7 / 9, 4)  # 1 payslip + 6 statement months


def test_payslip_that_does_not_tie_out_is_left_out_of_income(rs: RuleSet) -> None:
    docs = [*kyc_docs(), *income_docs()]
    first = next(d for d in docs if d.doc_type == "payslip")
    first.fields["net"] = 61000
    first.tie_out_ok = False
    r = score_case(personal_case(documents=docs), rs)
    assert r.case_facts["net_monthly_income"] == 60000 and r.case_facts["totals_tie_out"] is False


# --- income verification and tamper -------------------------------------------------------------
def test_payslip_above_bank_credits_is_held_down_and_flags_tamper(rs: RuleSet) -> None:
    docs = [*kyc_docs(), *income_docs(net=80000)]
    stmt = next(d for d in docs if d.doc_type == "bank_statement")
    stmt.statement = StatementAnalytics(months=6, income_months=6, credits_total=60000 * 6)
    r = score_case(personal_case(documents=docs), rs)
    assert r.case_facts["net_monthly_income"] == 60000  # the lower, bank-supported figure
    assert (
        r.case_facts["tamper_suspected"] and r.band == "refer" and "CM-FRD-01" in r.failed_rule_ids
    )


def test_a_single_weak_tamper_hint_does_not_flag_but_two_do(rs: RuleSet) -> None:
    one = personal_case(extra_tamper_hints=["ROUND_SALARY"])
    two = personal_case(extra_tamper_hints=["ROUND_SALARY", "ROUND_SALARY"])
    assert score_case(one, rs).case_facts["tamper_suspected"] is False
    assert score_case(two, rs).case_facts["tamper_suspected"] is True


def test_a_strong_hint_from_intake_caps_to_refer(rs: RuleSet) -> None:
    r = score_case(personal_case(extra_tamper_hints=["EDITOR_PRODUCER"]), rs)
    assert r.band == "refer" and r.capped_to_refer and r.total_score == 100.0


def test_irregular_income_and_returns_come_from_the_statement(rs: RuleSet) -> None:
    docs = [*kyc_docs(), *income_docs()]
    stmt = next(d for d in docs if d.doc_type == "bank_statement")
    stmt.statement = StatementAnalytics(months=6, income_months=3, credits_total=180000, cheque_returns=2)  # fmt: skip
    r = score_case(personal_case(documents=docs), rs)
    assert r.case_facts["income_regularity"] == 0.5 and r.case_facts["cheque_nach_returns_12m"] == 2


# --- co-applicants ----------------------------------------------------------------------------
def home_case(**over: object) -> CaseInput:
    young = date(1996, 1, 1)
    primary, co = person("primary", income=70000, dob=young), person("co", income=30000, dob=young)
    docs = [*kyc_docs("primary", dob="1996-01-01"), *kyc_docs("co", dob="1996-01-01"), *income_docs("primary", 70000), *income_docs("co", 30000)]  # fmt: skip
    for d in docs:
        if d.doc_type == "payslip":
            d.fields["employee"] = "Rekha Sinha"
    extra = [
        DocumentInput(doc_type="form16", fields={"gross": 1200000}),
        DocumentInput(doc_type="sale_agreement", fields={"buyer": "Rekha Sinha", "seller": "Sunil Mehta"}),
        DocumentInput(doc_type="title_deed", fields={"owner": "Sunil Mehta"}),
        DocumentInput(doc_type="encumbrance_certificate", fields={"result": "NIL encumbrances"}),
        DocumentInput(doc_type="approved_plan", fields={"status": "Approved"}),
    ]  # fmt: skip
    base = dict(case_id="T-HL-1", loan_type="home", application_date=APP_DATE, loan_amount=3_400_000, tenure_months=240,
                purpose="purchase of residential property", persons=[primary, co],
                documents=[*docs, *extra], details={"property_value": 4_250_000})  # fmt: skip
    base.update(over)
    return CaseInput(**base)  # type: ignore[arg-type]


def test_home_foir_is_combined_across_both_earners(rs: RuleSet) -> None:
    loans = [LoanRecord(lender="Apex", emi=8000, remaining_emis=30)]
    case = home_case()
    case.persons[0] = person("primary", income=70000, loans=loans, dob=date(1996, 1, 1))
    r = score_case(case, rs)
    new_emi = finance.emi(3_400_000, 8.75, 240)
    assert r.case_facts["net_monthly_income"] == 100000
    assert r.case_facts["foir"] == finance.foir_pct(8000, new_emi, 100000)
    assert r.case_facts["ltv_percent"] == 80.0 and r.case_facts["amount_band"] == "upto_75l"
    assert r.total_score == 100.0 and len([p for p in r.person_facts if p["role"] == "co"]) == 1


def test_kyc_is_checked_for_each_person_separately(rs: RuleSet) -> None:
    case = home_case()
    case.documents = [replace_name(d) for d in case.documents]
    r = score_case(case, rs)
    bad = [x for x in r.results if x.rule_id == "CM-KYC-03" and not x.passed]
    assert [x.role for x in bad] == ["co"] and r.stop_class == "fix"


def replace_name(d: DocumentInput) -> DocumentInput:
    if d.role == "co" and d.doc_type == "pan_card":
        return d.model_copy(update={"fields": {**d.fields, "name": "Mahesh Kumar"}})
    return d


def test_co_applicant_age_cap_is_enforced_at_maturity(rs: RuleSet) -> None:
    case = home_case()
    case.persons[1] = person("co", income=30000, dob=date(1974, 1, 1))
    case.documents = [d if d.role != "co" else d.model_copy(update={"fields": {**d.fields, **({"dob": "1974-01-01"} if "dob" in d.fields else {})}}) for d in case.documents]  # fmt: skip
    r = score_case(case, rs)
    co = r.person_facts[1]
    assert co["age_at_maturity"] > 55
    assert any(x.rule_id == "CM-ELIG-03" and x.role == "co" and not x.passed for x in r.results)
    assert r.stop_class == "eligibility"


def test_education_income_and_cibil_come_from_the_co_applicant(rs: RuleSet) -> None:
    student = person(
        "primary", emp="student", income=None, cibil=None, dob=date(2005, 3, 1), name="Asha Sinha"
    )
    co = person("co", income=90000, cibil=760)
    docs = [*kyc_docs("primary", name="Asha Sinha", dob="2005-03-01"), *kyc_docs("co"), *income_docs("co", 90000)]  # fmt: skip
    docs += [DocumentInput(doc_type="admission_letter", fields={"student": "Asha Sinha", "country": "India"}),
             DocumentInput(doc_type="fee_structure", fields={"total_fee": 900000}),
             DocumentInput(doc_type="marksheet", fields={"student": "Asha Sinha"})]  # fmt: skip
    details = {"moratorium_months": 36, "total_fee": 900000, "country": "India", "margin_amount": 60000, "collateral_offered": True}  # fmt: skip
    case = CaseInput(case_id="T-ED-1", loan_type="education", application_date=APP_DATE, loan_amount=840000,
                     tenure_months=144, purpose="higher education", persons=[student, co], documents=docs, details=details)  # fmt: skip
    r = score_case(case, rs)
    assert r.stopped_stage is None, r.failed_rule_ids
    assert r.case_facts["net_monthly_income"] == 90000 and r.case_facts["cibil_score"] == 760
    assert r.case_facts["repayment_years"] == 9.0 and r.case_facts["collateral_ok"] is True
    # the new instalment is spread over the repayment period, not the moratorium
    assert r.case_facts["new_emi"] == round(finance.emi(840000, 9.5, 108), 2)
    assert r.case_facts["margin_ok"] is True and r.case_facts["margin_required"] == 45000


def test_education_margin_and_collateral_shortfalls(rs: RuleSet) -> None:
    base = test_education_income_and_cibil_come_from_the_co_applicant  # noqa: F841
    student = person(
        "primary", emp="student", income=None, cibil=None, dob=date(2005, 3, 1), name="Asha Sinha"
    )
    docs = [*kyc_docs("primary", name="Asha Sinha", dob="2005-03-01"), *kyc_docs("co"), *income_docs("co", 90000)]  # fmt: skip
    docs += [DocumentInput(doc_type="admission_letter", fields={"student": "Asha Sinha", "country": "Canada"}),
             DocumentInput(doc_type="fee_structure", fields={"total_fee": 900000}),
             DocumentInput(doc_type="marksheet", fields={"student": "Asha Sinha"})]  # fmt: skip
    details = {"moratorium_months": 36, "total_fee": 900000, "country": "Canada", "margin_amount": 60000, "collateral_offered": False}  # fmt: skip
    case = CaseInput(case_id="T-ED-2", loan_type="education", application_date=APP_DATE, loan_amount=840000,
                     tenure_months=144, purpose="higher education", persons=[student, person("co", income=90000)],
                     documents=docs, details=details)  # fmt: skip
    r = score_case(case, rs)
    assert r.case_facts["margin_required"] == 135000  # 15% abroad
    assert not r.case_facts["margin_ok"] and not r.case_facts["collateral_ok"]
    assert {"ED-POL-11", "ED-POL-12"} <= set(r.failed_rule_ids)


# --- other loan types ---------------------------------------------------------------------------
def test_business_credit_to_gst_ratio_and_gstin_check(rs: RuleSet) -> None:
    from app.intake.validators import gstin_check_char

    first14 = "08PPIPM4603I9Z"
    gstin = first14 + gstin_check_char(first14)
    owner = person("primary", emp="self_employed", income=300000)
    common = dict(quality_score=95, avg_confidence=0.96, tie_out_ok=True)
    itr = [DocumentInput(doc_type="itr", fields={"ay": f"{2026 - i}-{27 - i}", "gross_total_income": 3_600_000, "name": "Rekha Sinha"}, **common) for i in range(2)]  # fmt: skip
    docs = [*kyc_docs(), *itr,
            DocumentInput(doc_type="business_proof", fields={"registered_on": "20-Jun-2019"}, **common),
            DocumentInput(doc_type="gst_registration", fields={"gstin": gstin, "pan": "PPIPM4603I"}, **common),
            DocumentInput(doc_type="gst_returns", units=12, **common),
            DocumentInput(doc_type="pnl_balance_sheet", fields={"net_profit": 3_600_000}, **common),
            DocumentInput(doc_type="bank_statement", units=12, statement=StatementAnalytics(
                months=12, income_months=12, credits_total=26_000_000), **common)]  # fmt: skip
    case = CaseInput(case_id="T-BL-1", loan_type="business", application_date=APP_DATE, loan_amount=3_900_000,
                     tenure_months=60, purpose="working capital", persons=[owner], documents=docs,
                     details={}, gst=GstInput(gstin=gstin, pan="PPIPM4603I", turnover_12m=29_000_000))  # fmt: skip
    r = score_case(case, rs)
    assert r.case_facts["bank_credit_to_gst_ratio"] == round(26_000_000 / 29_000_000, 3)
    assert r.case_facts["gst_or_udyam_valid"] is True and r.case_facts["loan_to_turnover"] == round(3_900_000 / 29_000_000, 3)  # fmt: skip
    assert r.case_facts["business_vintage_months"] == 88
    wrong = case.model_copy(
        update={"gst": GstInput(gstin=gstin, pan="ABCDE1234F", turnover_12m=29_000_000)}
    )
    assert score_case(wrong, rs).case_facts["gst_or_udyam_valid"] is False


def test_disallowed_purpose_fails_the_policy_rule(rs: RuleSet) -> None:
    r = score_case(personal_case(purpose="stock market investment"), rs)
    assert "PL-POL-12" in r.failed_rule_ids and r.stage_scores["policy"] == 7.0


def test_vehicle_invoice_must_match_the_application(rs: RuleSet) -> None:
    owner = person("primary", emp="self_employed", income=100000)
    common = dict(quality_score=95, avg_confidence=0.96, tie_out_ok=True)
    itr = DocumentInput(
        doc_type="itr", fields={"ay": "2026-27", "gross_total_income": 1_200_000}, **common
    )
    stmt = DocumentInput(doc_type="bank_statement", units=6, statement=StatementAnalytics(months=6, income_months=6, credits_total=900_000), **common)  # fmt: skip
    details = {"make": "Veloce", "model": "Sprint 1.2", "vehicle_kind": "new_car", "vehicle_condition": "new", "on_road_price": 1_000_000}  # fmt: skip

    def case(invoice_model: str, price: float) -> CaseInput:
        inv = DocumentInput(doc_type="dealer_invoice", fields={"model": invoice_model, "on_road": price}, **common)  # fmt: skip
        return CaseInput(case_id="T-VL-1", loan_type="vehicle", application_date=APP_DATE, loan_amount=800_000,
                         tenure_months=48, purpose="vehicle purchase", persons=[owner],
                         documents=[*kyc_docs(), itr, stmt, inv], details=details)  # fmt: skip

    ok = score_case(case("Veloce Sprint 1.2", 1_000_000), rs)
    assert ok.case_facts["vehicle_docs_valid"] is True and ok.case_facts["ltv_percent"] == 80.0
    assert (
        score_case(case("Veloce Edge 2.0", 1_000_000), rs).case_facts["vehicle_docs_valid"] is False
    )
    assert (
        score_case(case("Veloce Sprint 1.2", 1_100_000), rs).case_facts["vehicle_docs_valid"]
        is False
    )


# --- precedent bonus stub ---------------------------------------------------------------------
def test_precedent_bonus_is_zero_by_default(rs: RuleSet) -> None:
    assert score_case(personal_case(persons=[person(cibil=680)]), rs).precedent_bonus == 0.0


def test_precedent_bonus_is_capped_and_never_overrides_a_cap_or_a_band(rs: RuleSet) -> None:
    cap = rs.precedent.bonus_max
    assert apply_precedent_bonus(70.0, "refer", False, 99, rs) == (70.0 + cap, "refer", cap)
    assert apply_precedent_bonus(83.0, "refer", False, 99, rs)[1] == "approve"  # 83 + cap >= 85
    assert apply_precedent_bonus(83.0, "refer", True, 99, rs) == (
        83.0,
        "refer",
        0.0,
    )  # held by a cap rule
    assert apply_precedent_bonus(50.0, "reject", False, 99, rs) == (50.0, "reject", 0.0)
    assert apply_precedent_bonus(95.0, "approve", False, 99, rs) == (95.0, "approve", 0.0)
    assert apply_precedent_bonus(70.0, "refer", False, -3, rs)[2] == 0.0
