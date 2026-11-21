"""Model-judged evaluation of the stored reports (Stage 11). It replaces the RAGAS and DeepEval
suites the first plan named (user decision, 2026-11-21): no new packages, the project's own judge
model role, masked text only.

    python -m app.agents.run --split dev                first, run the cases with the models on
    python -m app.eval.judge --split dev                then the judge grades the stored reports
    python -m app.eval.judge --split dev --write-baseline
    python -m app.eval.judge --split test --allow-test  the final run only

For each case of the split whose latest report has a model-written summary, the judge model (a
different family from the Decision writer; the AI control page refuses the same one) grades, 0 to 1:

  faithfulness       is the summary supported by the report's own result, stage scores, findings
                     and cited clauses
  citation_support   is each Policy finding's statement supported by the text of the clause it
                     cites (at most MAX_CITATIONS per case)

Names from the report and every identifier pattern are masked before anything is sent. A summary
written by code needs no judge and is counted as skipped. Floors, when set, are the `judge` block
of docs/baselines/thresholds.json. Cost: about one call per case plus one per checked citation.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, text

from app.agents import evals
from app.agents.runtime import AgentContext, Services
from app.core.config import REPO_ROOT
from app.intake.masker import Masker
from app.scoring.rules import load_rules
from app.services import ai_config

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"
BASELINES = REPO_ROOT / "docs" / "baselines"
THRESHOLDS = BASELINES / "thresholds.json"
MAX_CITATIONS = 3
MAX_FINDINGS = 30


@dataclass
class Judged:
    case: str
    faithfulness: float | None = None
    citations: list[float] = field(default_factory=list)
    skipped: str | None = None
    calls: int = 0


def _masker(report: dict[str, Any]) -> Masker:
    m = Masker()
    for a in report.get("applicants") or []:
        m.add_known("NAME", str(a.get("name") or ""))
    return m


def evidence_of(report: dict[str, Any]) -> str:
    """What the summary may rest on: the report's own result, scores, findings and clauses."""
    clauses = {c["clause_id"]: c.get("text", "")[:500] for c in report.get("citations") or []}
    data = {
        "recommendation": report.get("recommendation_text"),
        "band": report.get("band"),
        "total_score": report.get("total_score"),
        "stage_scores": [
            {"stage": s["label"], "score": s["score"], "max": s["max"]}
            for s in report.get("stage_scores") or [] if s.get("ran")
        ],
        "stopped": report.get("stop_text"),
        "findings": [
            {"rule_id": f.get("rule_id"), "clause_id": f.get("clause_id"),
             "severity": f.get("severity"), "result": f.get("message")}
            for f in (report.get("findings") or []) if f.get("severity") != "note"
        ][:MAX_FINDINGS],
        "clauses": [{"clause_id": k, "text": v} for k, v in clauses.items()],
    }  # fmt: skip
    return json.dumps(data, separators=(",", ":"), default=str)


def policy_claims(report: dict[str, Any]) -> list[tuple[str, str]]:
    """(statement, cited clause text) for the Policy findings that cite a clause in the report."""
    clauses = {c["clause_id"]: c.get("text", "") for c in report.get("citations") or []}
    out = []
    for f in report.get("findings") or []:
        statement, cid = f.get("explanation"), f.get("clause_id")
        if f.get("stage") == "policy" and statement and cid in clauses:
            out.append((str(statement), clauses[cid]))
    return out[:MAX_CITATIONS]


async def judge_report(ctx: AgentContext, case: str, report: dict[str, Any]) -> Judged:
    out = Judged(case)
    if report.get("summary_source") != "model":
        out.skipped = "summary written by code"
        return out
    masker = _masker(report)
    verdict, calls = await evals.judge_claim(
        ctx, "eval", masker.mask(report["summary"]), masker.mask(evidence_of(report))
    )
    out.faithfulness, out.calls = verdict.value, len(calls)
    for statement, clause in policy_claims(report):
        verdict, calls = await evals.judge_claim(
            ctx, "eval", masker.mask(statement), masker.mask(clause)
        )
        out.calls += len(calls)
        if verdict.value is not None:
            out.citations.append(verdict.value)
    return out


def latest_reports(engine: Engine, case_ids: list[str]) -> dict[str, dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT DISTINCT ON (c.id) c.form_data->>'external_id' AS ext, r.report_json
                    FROM cases c JOIN reports r ON r.case_id = c.id
                    WHERE c.form_data->>'external_id' = ANY(CAST(:ids AS text[]))
                    ORDER BY c.id, r.version DESC"""),
            {"ids": case_ids},
        ).all()  # fmt: skip
    return {r.ext: dict(r.report_json) for r in rows}


def summarise(rows: list[Judged]) -> dict[str, float]:
    faith = [r.faithfulness for r in rows if r.faithfulness is not None]
    cites = [v for r in rows for v in r.citations]
    return {
        "cases_judged": float(len(faith)),
        "cases_skipped": float(sum(r.skipped is not None for r in rows)),
        "faithfulness": round(sum(faith) / len(faith), 4) if faith else 0.0,
        "citations_judged": float(len(cites)),
        "citation_support": round(sum(cites) / len(cites), 4) if cites else 0.0,
        "judge_calls": float(sum(r.calls for r in rows)),
    }


def floors(metrics: dict[str, float], thresholds: dict[str, Any]) -> list[str]:
    return [f"{name} {metrics[name]:.4f} is below the floor {rule['min']}"
            for name, rule in thresholds.get("judge", {}).items()
            if name in metrics and metrics[name] < rule.get("min", 0)]  # fmt: skip


def split_ids(split: str, only: list[str] | None, limit: int | None) -> list[str]:
    index = json.loads((OUTPUT / "index.json").read_text())
    ids = [c["case_id"] for c in index
           if (c["case_id"] in only if only else split in ("all", c["split"]))]  # fmt: skip
    return ids[:limit]


async def run(ctx: AgentContext, engine: Engine, ids: list[str]) -> tuple[list[Judged], int]:
    reports = latest_reports(engine, ids)
    rows = [await judge_report(ctx, case, reports[case]) for case in ids if case in reports]
    return rows, len(ids) - len(reports)


def main() -> int:
    from app.core.config import get_settings  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--case", action="append", help="one case id (repeatable)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--thresholds", type=Path, default=THRESHOLDS)
    args = ap.parse_args()
    if args.split != "dev" and not args.allow_test:
        print("the held-out test split is for the final evaluation; pass --allow-test")
        return 2
    settings = get_settings()
    if not settings.llm_enabled:
        print("the models are off (LLM_ENABLED=false): the judge needs them")
        return 2
    engine = create_engine(settings.sqlalchemy_url())
    snapshot = ai_config.refresh(engine, settings)  # the judge model the admin chose, if any
    ctx = AgentContext(ruleset=load_rules(), engine=engine, router=snapshot.router(),
                       services=Services.from_store())  # fmt: skip
    try:
        rows, missing = asyncio.run(run(ctx, engine, split_ids(args.split, args.case, args.limit)))
    finally:
        engine.dispose()
    for r in rows:
        cites = ", ".join(f"{v:.2f}" for v in r.citations) or "none"
        faith = (
            "skipped"
            if r.skipped
            else ("no answer" if r.faithfulness is None else f"{r.faithfulness:.2f}")
        )
        print(f"  {r.case:14s} faithfulness {faith:10s} citations {cites}")
    if missing:
        run_first = f"python -m app.agents.run --split {args.split}"
        print(f"{missing} case(s) have no report yet: run {run_first}")
    metrics = summarise(rows)
    print(f"split {args.split}")
    for name, value in metrics.items():
        print(f"  {name:18s} {value:.4f}")
    if args.write_baseline:
        path = BASELINES / f"{args.split}-judge.json"
        path.write_text(json.dumps({"split": args.split, "metrics": metrics}, indent=2) + "\n")
        print(f"baseline written to {path.relative_to(REPO_ROOT)}")
        return 0
    thresholds = json.loads(args.thresholds.read_text()) if args.thresholds.exists() else {}
    problems = floors(metrics, thresholds)
    for p in problems:
        print(f"FAIL {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
