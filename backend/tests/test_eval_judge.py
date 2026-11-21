"""The judge runner (Stage 11, replaces RAGAS and DeepEval): grades stored reports, masked."""

import asyncio

import pytest
from sqlalchemy import Engine

from app.agents.submission import load_case_dir
from app.eval import judge
from app.intake.masker import find_leaks
from tests.test_pipeline import OUTPUT, ScriptedRouter, engine, make_ctx, one_shot  # noqa: F401


def test_the_evidence_holds_the_result_and_the_clauses_and_names_are_masked() -> None:
    report = {
        "recommendation_text": "Recommended: refer", "band": "refer", "total_score": 72,
        "stage_scores": [{"label": "KYC", "score": 18, "max": 20, "ran": True},
                         {"label": "Policy fit", "score": None, "max": 10, "ran": False}],
        "findings": [{"rule_id": "PL-FOIR-01", "clause_id": "PL-INC-02", "severity": "points_lost",
                      "message": "FOIR 52% above 50%", "stage": "risk"},
                     {"rule_id": None, "clause_id": None, "severity": "note", "message": "fyi"},
                     {"rule_id": "PL-POL-01", "clause_id": "PL-ELIG-01", "severity": "points_lost",
                      "message": "x", "stage": "policy", "explanation": "Asha Rao fits the age rule."}],
        "citations": [{"clause_id": "PL-ELIG-01", "text": "Applicants aged 21 to 55.", "relevance": 0.9}],
        "applicants": [{"role": "primary", "name": "Asha Rao"}],
    }  # fmt: skip
    ev = judge.evidence_of(report)
    assert "PL-FOIR-01" in ev and "Applicants aged 21 to 55." in ev and "fyi" not in ev
    assert "Policy fit" not in ev  # a stage that did not run is not evidence
    claims = judge.policy_claims(report)
    assert claims == [("Asha Rao fits the age rule.", "Applicants aged 21 to 55.")]
    assert "Asha" not in judge._masker(report).mask(claims[0][0])


@pytest.mark.db
def test_a_model_summary_is_graded_a_code_summary_skipped_and_nothing_raw_is_sent(
    engine: Engine,  # noqa: F811
) -> None:
    one_shot(engine, "SYN-PL-D02", ScriptedRouter("good"))  # summary written by the model
    one_shot(engine, "SYN-PL-D03")  # models off: written by code
    router = ScriptedRouter("good")
    rows, missing = asyncio.run(
        judge.run(make_ctx(engine, router), engine, ["SYN-PL-D02", "SYN-PL-D03", "SYN-PL-D04"])
    )
    by = {r.case: r for r in rows}
    assert missing == 1  # D04 was never run
    assert by["SYN-PL-D02"].faithfulness == 0.9 and by["SYN-PL-D02"].calls >= 1
    assert by["SYN-PL-D03"].skipped == "summary written by code" and by["SYN-PL-D03"].calls == 0
    m = judge.summarise(rows)
    assert m["cases_judged"] == 1 and m["cases_skipped"] == 1 and m["faithfulness"] == 0.9
    names = [
        a["full_name"]
        for a in load_case_dir(OUTPUT / "cases" / "SYN-PL-D02").application["applicants"]
    ]
    sent = [m["content"] for msgs in router.seen for m in msgs]
    assert sent and all(not find_leaks(t) and not any(n in t for n in names) for t in sent)
    assert judge.floors(m, {"judge": {"faithfulness": {"min": 0.95}}}) == [
        "faithfulness 0.9000 is below the floor 0.95"
    ]
