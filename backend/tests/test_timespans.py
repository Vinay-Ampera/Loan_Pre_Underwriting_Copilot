"""Time figures keep their unit (EDGE_CASES E-133): "20 years" never passes for 20 months, and a
chat sentence's time figures must be those of what it cites."""

import pytest

from app.agents.explain import Explanation, Explanations, check_explanations
from app.agents.timespans import known, said, unit_slips
from app.chat.check import ChatAnswer, check_answer
from app.chat.context import FieldRow, Material, build_material, needed_text
from app.rag.schemas import RetrievedClause
from app.scoring.models import RuleOutcome
from app.scoring.rules import load_rules

RS = load_rules()


@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("at least two years old", [24]),
        ("24 months and 30-year term", [24, 360]),
        ("twenty-four months, 5 yrs, 1.5 years", [24, 60, 18]),
        ("the last six months and eighteen months", [6, 18]),
        ("Rs 25,000 a month, monthly credits, 12 payslips", []),
    ],
)
def test_time_figures_are_read_with_their_units(text: str, months: list[int]) -> None:
    assert [s.months for s in said(text)] == months


def test_the_data_states_units_through_its_field_names() -> None:
    source = (
        "BL-INC-12: business vintage months: 20 | tenure months: 96 (needed 60) | "
        'age at maturity: 58 (needed 55) | {"months_with_current_employer":3} | '
        "cheque nach returns 12m: 3"
    )
    got = {(s.number, s.unit) for s in known(source)}
    assert {(20, "months"), (96, "months"), (60, "months"), (58, "years"), (55, "years"),
            (3, "months"), (12, "months")} <= got  # fmt: skip


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        ("The vintage is 20 years.", True),
        ("The limit is 96 years.", True),
        ("The vintage is 20 months.", False),
        ("The business must be two years old.", False),
        ("The business must be 24 months old.", False),  # the same figure
        ("Seven documents arrived over 31 months.", False),  # not a unit slip: the number check's
    ],
)
def test_report_text_is_refused_only_for_a_wrong_unit(text: str, refused: bool) -> None:
    source = "business vintage months: 20 | tenure months: 96 | at least two years old"
    assert bool(unit_slips(text, source)) is refused


def test_an_explanation_with_the_wrong_unit_fails_its_check() -> None:
    source = '[{"key":"BL-INC-12","result":"business vintage months: 20"}]'

    def issues(text: str) -> list[str]:
        out = Explanations(explanations=[Explanation(key="BL-INC-12", text=text)])
        return check_explanations(out, {"BL-INC-12"}, source)

    assert any("wrong unit" in i for i in issues("The business is 20 years old."))
    assert issues("The business is 20 months old.") == []


# --- the chat: against what the sentence cites ------------------------------------------------
def clause(clause_id: str, words: str) -> RetrievedClause:
    return RetrievedClause(clause_id=clause_id, title=clause_id, text=words, source_tag="sample",
                           doc_loan_type="business", doc_version="x", relevance=1.0)  # fmt: skip


def material(rules_version: str = RS.version) -> Material:
    """The case from the real run: a business 20 months old, with a two-year minimum, beside
    another rule that talks about "the last 12 months"."""
    rules = [
        RuleOutcome(rule_id="BL-INC-12", stage="income", kind="soft", passed=False,
                    points_awarded=0, points_max=3, clause_id="BL-STAB-01",
                    evidence={"field": "business_vintage_months", "value": 20}),
        RuleOutcome(rule_id="CM-CRD-11", stage="credit", kind="soft", passed=True,
                    points_awarded=6, points_max=6, clause_id="CM-CRD-02",
                    evidence={"field": "cheque_nach_returns_12m", "value": 0}),
    ]  # fmt: skip
    report = {"versions": {"rules": rules_version}, "facts": {"case": {"tenure_months": 36}}}
    clauses = [
        clause("BL-STAB-01", "The business must be at least two years old."),
        clause("CM-CRD-02", "Returned cheques in the last 12 months are counted."),
    ]
    return build_material(report, rules, [FieldRow("primary", "bank_statement", "months", "12")],
                          clauses, names=[], ruleset=RS)  # fmt: skip


def answer(text: str, kind: str = "rule", cited: str = "BL-INC-12") -> ChatAnswer:
    return ChatAnswer.model_validate({"answerable": True, "sentences": [
        {"text": text, "citations": [{"kind": kind, "id": cited}]}]})  # fmt: skip


@pytest.mark.parametrize(
    "text",
    [
        "The business vintage is 20 months.",
        "The business needs to be at least two years old.",
        "The business needs to be at least 24 months old.",  # refused before: 24 is now there
        "The business needs to be at least 2 years old.",
        "The loan runs for 36 months, or 3 years.",  # the loan's own term, either unit
    ],
)
def test_a_right_time_figure_passes(text: str) -> None:
    assert check_answer(answer(text), material()) == []


@pytest.mark.parametrize(
    "text",
    [
        "The business vintage is 20 years.",
        "The business needs to be at least 12 months old.",  # another rule's figure
        "The business needs to be at least three years old.",  # words are read too
        "The business needs to be at least 24 years old.",
        "The business needs to be at least 36 months old.",  # the loan's tenure, not the business
    ],
)
def test_a_wrong_time_figure_is_refused(text: str) -> None:
    issues = check_answer(answer(text), material())
    assert any("time figures not in what it cites" in i for i in issues), issues


def test_a_figure_counts_when_the_sentence_cites_where_it_comes_from() -> None:
    m = material()
    assert check_answer(answer("No cheque came back in the last 12 months.", "rule", "CM-CRD-11"), m) == []  # fmt: skip
    assert check_answer(answer("It is counted over 12 months.", "clause", "CM-CRD-02"), m) == []
    assert check_answer(answer("The statement covers 12 months.", "field", "bank_statement.months"), m) == []  # fmt: skip


def test_the_chat_is_given_the_threshold_only_from_the_runs_rules_version() -> None:
    entry = material().rules[0]
    assert entry["needed"] == "at least 24 months"
    assert "needed" not in material(rules_version="an-older-one").rules[0]


def test_thresholds_read_as_words_with_units_and_large_amounts_keep_commas() -> None:
    by_id = {r.rule_id: r for r in RS.rules}
    assert needed_text(by_id["BL-INC-12"]) == "at least 24 months"
    assert needed_text(by_id["CM-ELIG-03"]) == "at most 55 years"
    assert needed_text(by_id["PL-INC-11"]) == "at least 25,000"
    assert needed_text(by_id["BL-CRD-10"]) == "at least 700 earns 12; at least 650 earns 8"
