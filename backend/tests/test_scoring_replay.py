"""Stage 3 exit criterion: replay the dev answer keys through the engine, no documents opened."""

import json

import pytest

from app.scoring.engine import score_case
from app.scoring.replay import CASES_DIR, load_case, replay
from app.scoring.rules import load_rules
from app.services.mock_services import RecordStore

pytestmark = pytest.mark.skipif(
    not CASES_DIR.exists(), reason="run `python -m synthetic.generate` first"
)

AGREED_BAND_SHARE = 0.95  # agreed share of dev cases whose band must be reproduced
AGREED_EXACT_SHARE = 0.90  # ...and whose score, stop and failed rules must be reproduced too


@pytest.fixture(scope="module")
def rows() -> list:  # type: ignore[type-arg]
    return replay("dev")


def test_dev_split_has_sixty_cases(rows: list) -> None:  # type: ignore[type-arg]
    assert len(rows) == 60


def test_band_reproduced_for_the_agreed_share(rows: list) -> None:  # type: ignore[type-arg]
    share = sum(r.band_ok for r in rows) / len(rows)
    assert share >= AGREED_BAND_SHARE, [r.notes for r in rows if not r.band_ok]


def test_stop_stage_and_class_reproduced_for_every_case(rows: list) -> None:  # type: ignore[type-arg]
    assert all(r.stop_ok for r in rows), [r.notes for r in rows if not r.stop_ok]


def test_score_stop_and_failed_rules_reproduced_for_the_agreed_share(rows: list) -> None:  # type: ignore[type-arg]
    share = sum(r.exact for r in rows) / len(rows)
    assert share >= AGREED_EXACT_SHARE, [r.notes for r in rows if not r.exact]


def test_tampered_payslips_are_caught_from_the_numbers_alone() -> None:
    """Remove the metadata hint intake would raise: payslip net vs bank credits still gives it away."""
    rs, store = load_rules(), RecordStore(CASES_DIR.parent / "records")
    checked = 0
    for d in sorted(CASES_DIR.iterdir()):
        key = json.loads((d / "answer_key.json").read_text())
        if key["split"] != "dev" or key["scenario"] != "tamper":
            continue
        inp, _ = load_case(d, store)
        if not any(d.doc_type == "payslip" for d in inp.documents):
            continue  # self-employed: income documents are ITRs; intake's metadata hints cover those
        for doc in inp.documents:
            doc.tamper_hints = []
        report = score_case(inp, rs)
        assert report.case_facts["tamper_suspected"], d.name
        assert report.band == "refer", d.name
        checked += 1
    assert checked >= 1


def test_test_split_is_not_touched_by_the_default_replay() -> None:
    assert all(r.case_id.split("-")[-1].startswith("D") for r in replay("dev"))
