import pytest

from app.rag.policy_loader import load_all, parse_policy
from app.scoring.evaluate import MissingFactError, evaluate_case
from app.scoring.rules import RuleSet, load_rules

LOANS = ["personal", "home", "education", "business", "vehicle"]


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return load_rules()


def test_stage_points_equal_weights(ruleset: RuleSet) -> None:
    for loan in LOANS:
        assert ruleset.max_points(loan) == {
            k: float(v) for k, v in ruleset.scoring.stage_weights.items()
        }


def test_every_rule_clause_exists_in_policy(ruleset: RuleSet) -> None:
    clauses = {c.clause_id for d in load_all() for c in d.clauses}
    missing = {r.policy_clause for r in ruleset.rules} - clauses
    assert not missing


def test_policy_clause_ids_unique_and_prefix_matches_file() -> None:
    prefix = {"common": "CM", "personal": "PL", "home": "HL", "education": "ED",
              "business": "BL", "vehicle": "VL"}  # fmt: skip
    seen: set[str] = set()
    for doc in load_all():
        assert doc.clauses, doc.path
        for c in doc.clauses:
            assert c.clause_id.startswith(prefix[doc.loan_type] + "-"), c.clause_id
            assert c.clause_id not in seen
            seen.add(c.clause_id)
    assert len(load_all()) == 6


def test_every_loan_has_documents_and_policy(ruleset: RuleSet) -> None:
    for loan in LOANS:
        assert ruleset.required_documents(loan)
    assert {d.loan_type for d in load_all()} == {"common", *LOANS}


def test_parse_rejects_bad_heading(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "x.md"
    f.write_text(
        "---\ndoc_id: x\nloan_type: common\ntitle: t\nversion: '1'\neffective_from: 2026-01-01\n---\n"
        "## nonsense heading\ntext\n"
    )
    with pytest.raises(ValueError, match="bad clause heading"):
        parse_policy(f)


# --- evaluator ----------------------------------------------------------------------------
def _clean_personal() -> tuple[dict[str, object], list[dict[str, object]]]:
    case: dict[str, object] = {
        "kyc_docs_complete": True, "tamper_suspected": False,
        "identity_lookup_match": True, "name_match_score": 98, "address_match_score": 90,
        "kyc_doc_quality": 90, "mandatory_docs_ratio": 1.0, "doc_quality_score": 90,
        "avg_field_confidence": 0.95, "totals_tie_out": True, "foir": 30,
        "income_verified_ratio": 0.98, "income_regularity": 1.0, "net_monthly_income": 60000,
        "total_experience_months": 60, "months_with_current_employer": 40, "cibil_score": 790,
        "cheque_nach_returns_12m": 0, "bureau_dpd_max_12m": 0, "enquiries_6m": 1,
        "tenure_months": 48, "loan_amount": 600000, "loan_purpose_allowed": True,
    }  # fmt: skip
    person: dict[str, object] = {
        "role": "primary", "pan_valid": True, "aadhaar_valid": True, "name_match_score": 98,
        "dob_match": True, "is_resident": True, "age_at_application": 35,
        "age_at_maturity": 39, "cibil_score": 790,
    }  # fmt: skip
    return case, [person]


def test_clean_case_scores_100(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    ev = evaluate_case(ruleset, "personal", case, persons)
    assert ev.total_score == 100 and ev.band == "approve" and ev.stopped_stage is None


def test_fix_stop_has_no_score_or_band(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    persons[0]["pan_valid"] = False
    ev = evaluate_case(ruleset, "personal", case, persons)
    assert (ev.stopped_stage, ev.stop_class) == ("kyc", "fix")
    assert ev.total_score is None and ev.band is None


def test_eligibility_stop_recommends_reject(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    persons[0]["cibil_score"] = 640
    ev = evaluate_case(ruleset, "personal", case, persons)
    assert (ev.stopped_stage, ev.stop_class, ev.band) == ("risk", "eligibility", "reject")


def test_fix_wins_over_eligibility_in_same_stage(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    persons[0]["pan_valid"] = False
    persons[0]["age_at_maturity"] = 60
    ev = evaluate_case(ruleset, "personal", case, persons)
    assert ev.stop_class == "fix"


def test_cibil_650_to_699_is_capped_to_refer(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    persons[0]["cibil_score"] = 680
    case["cibil_score"] = 680
    ev = evaluate_case(ruleset, "personal", case, persons)
    assert ev.capped_to_refer and ev.band == "refer"


def test_tamper_never_passes_silently(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    case["tamper_suspected"] = True
    assert evaluate_case(ruleset, "personal", case, persons).band == "refer"


def test_missing_fact_is_an_error(ruleset: RuleSet) -> None:
    case, persons = _clean_personal()
    del case["foir"]
    with pytest.raises(MissingFactError):
        evaluate_case(ruleset, "personal", case, persons)
