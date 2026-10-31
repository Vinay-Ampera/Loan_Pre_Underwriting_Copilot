"""Every operator, every hard rule, tier points, and 'a threshold change needs no code change'."""

import re
from typing import Any

import pytest
import yaml

from app.core.config import REPO_ROOT
from app.scoring.evaluate import compare, evaluate_case, evaluate_rule
from app.scoring.rules import Rule, RuleSet, load_rules

RULES_FILE = REPO_ROOT / "data" / "rules" / "rules.yaml"
RS = load_rules()
HARD = [r for r in RS.rules if r.kind == "hard"]
SOFT_TIERED = [r for r in RS.rules if r.kind == "soft" and r.tiers]


# --- operators -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("op", "value", "threshold", "expected"),
    [
        ("gte", 5, 5, True), ("gte", 4, 5, False),
        ("lte", 5, 5, True), ("lte", 6, 5, False),
        ("gt", 6, 5, True), ("gt", 5, 5, False),
        ("lt", 4, 5, True), ("lt", 5, 5, False),
        ("eq", True, True, True), ("eq", False, True, False), ("eq", "a", "a", True),
        ("ne", 4, 5, True), ("ne", 5, 5, False),
        ("in", "a", ["a", "b"], True), ("in", "c", ["a", "b"], False),
    ],
)  # fmt: skip
def test_operator(op: Any, value: Any, threshold: Any, expected: bool) -> None:
    assert compare(op, value, threshold) is expected


# --- derive a passing and a failing value from the rule itself --------------------------------
def passing(op: str, thr: Any) -> Any:
    return {"gte": thr, "lte": thr, "eq": thr, "gt": thr + 1 if isinstance(thr, int | float) else thr,
            "lt": thr - 1 if isinstance(thr, int | float) else thr, "in": thr[0] if op == "in" else thr,
            "ne": not thr if isinstance(thr, bool) else "other"}[op]  # fmt: skip


def failing(op: str, thr: Any) -> Any:
    if isinstance(thr, bool):
        return not thr
    return {"gte": thr - 1, "lte": thr + 1, "eq": f"{thr}x" if isinstance(thr, str) else thr + 1,
            "gt": thr, "lt": thr, "ne": thr, "in": "zzz"}[op]  # fmt: skip


def run(rule: Rule, value: Any) -> list[Any]:
    loan = rule.loan_types[0]
    roles = rule.roles or ["primary"]
    persons = [{"role": r, rule.field: value} for r in roles]
    return evaluate_rule(rule, loan, {rule.field: value}, persons)


@pytest.mark.parametrize("rule", HARD, ids=lambda r: r.rule_id)
def test_every_hard_rule_passes_and_fails_on_its_threshold(rule: Rule) -> None:
    assert rule.operator is not None
    ok = run(rule, passing(rule.operator, rule.threshold))
    bad = run(rule, failing(rule.operator, rule.threshold))
    assert ok and all(r.passed for r in ok), f"{rule.rule_id} should pass at its threshold"
    assert bad and all(not r.passed for r in bad), f"{rule.rule_id} should fail beyond it"
    for r in bad:
        assert (r.on_fail, r.fail_class) == (rule.on_fail, rule.fail_class)
        assert r.clause_id == rule.policy_clause and r.evidence["field"] == rule.field


@pytest.mark.parametrize("rule", HARD, ids=lambda r: r.rule_id)
def test_hard_rule_with_unverified_value_fails(rule: Rule) -> None:
    assert all(not r.passed for r in run(rule, None))


def test_hard_rules_cover_both_fail_classes_and_the_cap() -> None:
    assert {(r.on_fail, r.fail_class) for r in HARD} == {("stop", "fix"), ("stop", "eligibility"), ("cap_refer", None)}  # fmt: skip


def test_each_hard_rule_applies_to_every_listed_role() -> None:
    rule = next(r for r in HARD if r.rule_id == "CM-KYC-01")
    persons = [{"role": "primary", "pan_valid": True}, {"role": "co", "pan_valid": False}]
    out = evaluate_rule(rule, "home", {}, persons)
    assert [(r.role, r.passed) for r in out] == [("primary", True), ("co", False)]


def test_hard_rule_limited_to_the_co_applicant_ignores_the_primary() -> None:
    rule = next(r for r in HARD if r.rule_id == "ED-CIBIL-01")
    persons = [{"role": "primary", "cibil_score": 300}, {"role": "co", "cibil_score": 760}]
    out = evaluate_rule(rule, "education", {}, persons)
    assert [(r.role, r.passed) for r in out] == [("co", True)]


# --- soft rules: tiers ------------------------------------------------------------------------
@pytest.mark.parametrize("rule", SOFT_TIERED, ids=lambda r: r.rule_id)
def test_each_tier_awards_its_points(rule: Rule) -> None:
    assert rule.tiers
    loan = rule.loan_types[0]
    when = rule.when or {}
    for tier in rule.tiers:
        v = passing(tier.operator, tier.threshold)
        # a value at this tier's threshold may also satisfy an earlier, better tier: take the first match
        expect = next(t.points for t in rule.tiers if compare(t.operator, v, t.threshold))
        (res,) = evaluate_rule(rule, loan, {rule.field: v, **when}, [])
        assert res.points_awarded == expect
    worst = failing(rule.tiers[-1].operator, rule.tiers[-1].threshold)
    (res,) = evaluate_rule(rule, loan, {rule.field: worst, **when}, [])
    assert res.points_awarded == 0 and not res.passed


def test_when_filter_selects_one_of_the_alternatives() -> None:
    rules = {r.rule_id: r for r in RS.rules if r.group == "HL-POL-11"}
    case = {"amount_band": "upto_75l", "ltv_percent": 85}
    hits = [r for rule in rules.values() for r in evaluate_rule(rule, "home", case, [])]
    assert [r.rule_id for r in hits] == ["HL-POL-11B"] and hits[0].points_awarded == 0


# --- thresholds live in the rules file --------------------------------------------------------
def _facts() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case: dict[str, Any] = {}
    for r in RS.rules_for("personal"):
        if r.kind == "soft":
            op, thr = (
                (r.tiers[0].operator, r.tiers[0].threshold)
                if r.tiers
                else (r.operator, r.threshold)
            )
            case[r.field] = passing(str(op), thr)
        else:
            case.setdefault(r.field, passing(str(r.operator), r.threshold))
    persons = [{"role": "primary", **{r.field: passing(str(r.operator), r.threshold) for r in HARD if "personal" in r.loan_types}}]  # fmt: skip
    return case, persons


def _with_rule_change(tmp_path: Any, edit: Any) -> RuleSet:
    data = yaml.safe_load(RULES_FILE.read_text())
    edit(data)
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return load_rules(path)


def test_changing_a_hard_threshold_changes_behaviour_without_code(tmp_path: Any) -> None:
    case, persons = _facts()
    persons[0]["cibil_score"] = 660
    assert (
        evaluate_case(RS, "personal", case, persons).stopped_stage is None
    )  # 660 clears the 650 floor

    def raise_floor(d: dict[str, Any]) -> None:
        next(r for r in d["rules"] if r["rule_id"] == "PL-CIBIL-01")["threshold"] = 680

    stricter = _with_rule_change(tmp_path, raise_floor)
    ev = evaluate_case(stricter, "personal", case, persons)
    assert (ev.stopped_stage, ev.stop_class, ev.band) == ("risk", "eligibility", "reject")
    assert stricter.checksum != RS.checksum


def test_changing_a_tier_changes_the_score_without_code(tmp_path: Any) -> None:
    case, persons = _facts()
    case["foir"] = 45
    base = evaluate_case(RS, "personal", case, persons).stage_scores["income"]

    def tighten(d: dict[str, Any]) -> None:
        rule = next(r for r in d["rules"] if r["rule_id"] == "CM-INC-10")
        rule["tiers"][1]["threshold"] = 44  # was 50: 45 no longer earns the second tier

    after = evaluate_case(
        _with_rule_change(tmp_path, tighten), "personal", case, persons
    ).stage_scores["income"]
    assert base - after == 6


def test_bands_come_from_the_rules_file(tmp_path: Any) -> None:
    case, persons = _facts()
    case["tamper_suspected"] = False
    assert evaluate_case(RS, "personal", case, persons).band == "approve"

    def raise_bar(d: dict[str, Any]) -> None:
        d["scoring"]["bands"]["approve_min"] = 101

    assert (
        evaluate_case(_with_rule_change(tmp_path, raise_bar), "personal", case, persons).band
        == "refer"
    )


def test_rules_file_rejects_a_bad_rule_id_and_unknown_fields(tmp_path: Any) -> None:
    def bad_id(d: dict[str, Any]) -> None:
        d["rules"][0]["rule_id"] = "nonsense"

    with pytest.raises(ValueError, match="bad rule_id"):
        _with_rule_change(tmp_path, bad_id)

    def extra_key(d: dict[str, Any]) -> None:
        d["params"]["surprise"] = 1

    with pytest.raises(ValueError):
        _with_rule_change(tmp_path, extra_key)


def test_checksum_is_the_sha256_of_the_file() -> None:
    import hashlib

    assert RS.checksum == hashlib.sha256(RULES_FILE.read_bytes()).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", RS.checksum)
