"""Replay synthetic cases through the scoring engine and compare with the answer keys.

    python -m app.scoring.replay --split dev [--case SYN-HL-D01] [--verbose]

No document is opened. A case is rebuilt from its structured data: the application form, the field
values each document carries (the answer key's `truth`), and the mock identity, bureau and GST
records. Four quantities are *measured* by Stage 2 on real documents and cannot be read from
fields, so the key supplies them: document quality, field confidence, totals tie-out and income
regularity (months with an income credit). Everything else is derived from raw inputs by the
engine, independently of how the generator computed the key.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from app.scoring.engine import score_case
from app.scoring.models import (
    BureauInput,
    CaseInput,
    DocumentInput,
    GstInput,
    LoanRecord,
    PersonInput,
    ScoreReport,
    StatementAnalytics,
)
from app.scoring.rules import RuleSet, load_rules
from app.services.mock_services import BureauService, GstService, IdentityService, RecordStore

CASES_DIR = REPO_ROOT / "data" / "synthetic" / "output" / "cases"
KYC = {"pan_card", "aadhaar", "photo"}


def _field_name(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


def _document(
    d: dict[str, Any], measured: dict[str, Any], details: dict[str, Any], first_income_doc: bool
) -> DocumentInput:
    fields = {_field_name(k): v for k, v in d["truth"].items()}
    kind = d["doc_type"]
    if kind == "dealer_invoice":  # the invoice line reads "<make> <model>"
        fields["model"] = f"{details.get('make', '')} {fields['model']}".strip()
    statement = None
    if kind == "bank_statement":
        months = int(d["truth"]["months"])
        statement = StatementAnalytics(
            months=months,
            income_months=round(float(measured["income_regularity"]) * months),
            credits_total=float(d["truth"]["credits_total"]),
            cheque_returns=int(d["truth"].get("returns", 0)),
        )
    in_kyc = kind in KYC
    # Stage 2 raises a PDF-metadata hint on every tampered income document (its eval guarantees one)
    hints = ["EDITOR_PRODUCER"] if measured["tamper_suspected"] and first_income_doc else []
    return DocumentInput(
        doc_type=kind,
        role=d["role"],
        units=d["units"],
        fields=fields,
        statement=statement,
        quality_score=measured["kyc_doc_quality"] if in_kyc else measured["doc_quality_score"],
        avg_confidence=measured["avg_field_confidence"],
        tie_out_ok=measured["totals_tie_out"] or not first_income_doc,
        tamper_hints=hints,
    )


def load_case(case_dir: Path, store: RecordStore | None = None) -> tuple[CaseInput, dict[str, Any]]:
    """(scoring input, answer key) for one generated case."""
    app = json.loads((case_dir / "application.json").read_text())
    key = json.loads((case_dir / "answer_key.json").read_text())
    store = store or RecordStore()
    identity, bureau, gst = IdentityService(store), BureauService(store), GstService(store)
    details = app["loan_details"]
    measured = key["facts"]

    docs: list[DocumentInput] = []
    seen_income = False
    for d in key["documents"]:
        income = d["doc_type"] not in KYC
        docs.append(_document(d, measured, details, income and not seen_income))
        seen_income |= income

    aadhaar_by_role = {
        x.role: str(x.fields["aadhaar"])
        for x in docs
        if x.doc_type == "aadhaar" and x.fields.get("aadhaar")
    }
    app_date = date.fromisoformat(app["application_date"])
    persons = []
    for a in app["applicants"]:
        dob = date.fromisoformat(a["dob"])
        rec = bureau.report(a["pan"])
        persons.append(
            PersonInput(
                role=a["role"],
                full_name=a["full_name"],
                dob=dob,
                pan=a["pan"],
                address=a["address"],
                employment_type=a["employment_type"],
                residential_status=a["residential_status"],
                declared_monthly_income=a.get("declared_monthly_income"),
                months_in_current_employment=a.get("months_in_current_employment"),
                total_experience_months=a.get("total_experience_months"),
                identity_match=identity.verify(
                    a["pan"], a["full_name"], dob, aadhaar_by_role.get(a["role"])
                ),
                bureau=BureauInput(
                    cibil_score=rec.cibil_score,
                    active_loans=[LoanRecord(**x) for x in rec.active_loans],
                    enquiry_dates=[date.fromisoformat(e["date"]) for e in rec.enquiries],
                )
                if rec
                else None,
            )
        )

    reg = next((x for x in docs if x.doc_type == "gst_registration"), None)
    record = gst.lookup(str(reg.fields.get("gstin"))) if reg else None
    return CaseInput(
        case_id=app["case_id"],
        loan_type=app["loan_type"],
        application_date=app_date,
        loan_amount=app["loan_amount"],
        tenure_months=app["tenure_months"],
        purpose=app["purpose"],
        persons=persons,
        documents=docs,
        details=details,
        gst=GstInput(gstin=record.gstin, pan=record.pan, turnover_12m=record.turnover_12m)
        if record
        else None,
    ), key


@dataclass
class Comparison:
    case_id: str
    band_ok: bool
    stop_ok: bool
    score_ok: bool
    stages_ok: bool
    failed_ok: bool
    notes: list[str] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        return self.band_ok and self.stop_ok and self.score_ok and self.stages_ok and self.failed_ok


def compare(report: ScoreReport, key: dict[str, Any]) -> Comparison:
    exp_total = key["expected_total_score"]
    c = Comparison(
        case_id=key["case_id"],
        band_ok=report.band == key["expected_band"],
        stop_ok=(report.stopped_stage, report.stop_class)
        == (key["expected_stop_stage"], key["expected_stop_class"]),
        score_ok=(report.total_score is None and exp_total is None)
        or (
            report.total_score is not None
            and exp_total is not None
            and abs(report.total_score - exp_total) < 0.01
        ),
        stages_ok=report.stopped_stage is not None  # a stopped run has partial stage scores
        or all(abs(report.stage_scores[k] - v) < 0.01 for k, v in key["stage_scores"].items()),
        failed_ok=report.failed_rule_ids == sorted(key["failed_rule_ids"]),
    )
    if not c.exact:
        c.notes.append(
            f"got band={report.band} stop={report.stopped_stage}/{report.stop_class} "
            f"total={report.total_score} failed={report.failed_rule_ids} | "
            f"want band={key['expected_band']} stop={key['expected_stop_stage']}/"
            f"{key['expected_stop_class']} total={exp_total} "
            f"failed={sorted(key['failed_rule_ids'])}"
        )
    return c


def replay(
    split: str, only: str | None = None, rs: RuleSet | None = None, cases_dir: Path = CASES_DIR
) -> list[Comparison]:
    rs = rs or load_rules()
    store = RecordStore(cases_dir.parent / "records")
    out = []
    for d in sorted(cases_dir.iterdir()):
        if only and d.name != only:
            continue
        key_split = json.loads((d / "answer_key.json").read_text())["split"]
        if split != "all" and key_split != split:
            continue
        inp, key = load_case(d, store)
        out.append(compare(score_case(inp, rs), key))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--case")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--min-band-agreement", type=float, default=0.95)
    args = ap.parse_args()
    if args.split == "test":
        print("note: the held-out test split is for the final evaluation, never for tuning")
    rows = replay(args.split, args.case)
    n = len(rows)
    for label, ok in [
        ("band", sum(r.band_ok for r in rows)),
        ("stop stage and class", sum(r.stop_ok for r in rows)),
        ("total score", sum(r.score_ok for r in rows)),
        ("stage scores", sum(r.stages_ok for r in rows)),
        ("failed rule ids", sum(r.failed_ok for r in rows)),
        ("everything", sum(r.exact for r in rows)),
    ]:
        print(f"{label:22s} {ok}/{n}  ({ok / n:.1%})")
    for r in rows:
        if not r.exact and (args.verbose or not r.band_ok):
            print(f"  {r.case_id}: {' '.join(r.notes)}")
    return 0 if sum(r.band_ok for r in rows) / n >= args.min_band_agreement else 1


if __name__ == "__main__":
    sys.exit(main())
