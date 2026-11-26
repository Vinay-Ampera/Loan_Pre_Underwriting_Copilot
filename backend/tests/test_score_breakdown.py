"""The score breakdown behind the chart and the PDF column (Stage 12 Part D, E-120): display only,
read from the engine's own stage scores."""

import pytest

from app.agents.report import (
    ScoreBreakdown,
    StageScoreRow,
    cap_rules,
    points_lost,
    score_breakdown,
    stage_rows,
)
from app.scoring.engine import score_case
from app.scoring.models import ScoreReport
from app.scoring.replay import CASES_DIR, load_case
from app.scoring.rules import load_rules

RS = load_rules()
BANDS = RS.scoring.bands


def dev_scores() -> list[ScoreReport]:
    cases = [load_case(d) for d in sorted(CASES_DIR.iterdir()) if d.is_dir()]
    return [score_case(inp, RS) for inp, key in cases if key["split"] == "dev"]


def built(score: ScoreReport, cap: list[str] | None = None) -> ScoreBreakdown | None:
    return score_breakdown(stage_rows(score), total=score.total_score, band=score.band,
                           bonus=score.precedent_bonus, cap_rule_ids=cap or [], bands=BANDS)  # fmt: skip


def test_every_scored_dev_case_adds_up_to_its_score_and_a_stopped_one_has_none() -> None:
    scores = dev_scores()
    assert len(scores) == 60
    scored = stopped = 0
    for s in scores:
        got = built(s)
        if s.stopped_stage is not None:
            assert got is None, s.case_id
            stopped += 1
            continue
        assert got is not None and got.start == 100, s.case_id
        lost = sum(st.lost for st in got.stages)
        assert round(got.start - lost + got.bonus, 2) == got.final == s.total_score, s.case_id
        assert got.stages[-1].level_after == pytest.approx(got.final - got.bonus), s.case_id
        # the PDF column is the same function over the same rows
        assert [points_lost(r) for r in stage_rows(s)] == [st.lost for st in got.stages]
        assert all(st.earned + st.lost == pytest.approx(st.max) for st in got.stages)
        scored += 1
    assert scored and stopped  # both kinds are in the split


def row(stage: str, score: float | None, mx: float) -> StageScoreRow:
    return StageScoreRow(stage=stage, label=stage, score=score, max=mx, ran=score is not None)


def test_a_capped_case_carries_the_cap_and_its_rules() -> None:
    rows = [row("kyc", 20, 20), row("income", 70, 80)]
    ids = cap_rules([("cap", "CM-FRD-01"), ("points_lost", "PL-POL-10"), ("cap", "BL-CRD-20"),
                     ("cap", None), ("cap", "CM-FRD-01")])  # fmt: skip
    got = score_breakdown(rows, total=90, band="refer", bonus=0, cap_rule_ids=ids, bands=BANDS)
    assert got is not None and got.cap_rule_ids == ["BL-CRD-20", "CM-FRD-01"]
    assert (got.final, got.band, got.approve_min, got.refer_min) == (90, "refer", 85, 60)


def test_a_precedent_bonus_is_its_own_step_up() -> None:
    rows = [row("kyc", 18, 20), row("income", 56, 80)]
    got = score_breakdown(rows, total=77, band="refer", bonus=3, cap_rule_ids=[], bands=BANDS)
    assert got is not None and got.bonus == 3
    assert [s.level_after for s in got.stages] == [98, 74]  # then +3 to the final 77


def test_no_chart_without_a_total_or_with_a_stage_that_did_not_run() -> None:
    rows = [row("kyc", 20, 20), row("income", None, 80)]
    assert score_breakdown(rows, total=None, band="reject", bonus=0, cap_rule_ids=[], bands=BANDS) is None  # fmt: skip
    assert (
        score_breakdown(rows, total=20, band="reject", bonus=0, cap_rule_ids=[], bands=BANDS)
        is None
    )
    assert (
        score_breakdown([], total=0, band="reject", bonus=0, cap_rule_ids=[], bands=BANDS) is None
    )
    assert points_lost(rows[1]) is None
