"""Fairness report is monitoring only: it computes gaps and no pipeline module can read the table."""

from pathlib import Path

from app.core.config import REPO_ROOT
from app.eval.fairness import rates

ROWS = (
    [("M", "<30", "tier1", "recommend_approve")] * 6
    + [("F", "<30", "tier1", "refer")] * 6
    + [("F", "45+", "tier3", "recommend_approve")] * 2
)


def test_gap_is_computed_over_groups_with_enough_cases() -> None:
    out = rates(ROWS)  # type: ignore[arg-type]
    assert out["gender"]["gap_pp"] == 75.0 and out["gender"]["flag"] is True
    assert out["age_band"]["groups"]["45+"]["small"] is True
    assert out["city_tier"]["gap_pp"] == 100.0 or out["city_tier"]["gap_pp"] is None


def test_no_pipeline_code_reads_the_fairness_table() -> None:
    for pkg in ("agents", "scoring", "rag", "intake", "learning", "services", "api"):
        for f in (REPO_ROOT / "backend" / "app" / pkg).rglob("*.py"):
            assert "fairness" not in Path(f).read_text().lower(), f
