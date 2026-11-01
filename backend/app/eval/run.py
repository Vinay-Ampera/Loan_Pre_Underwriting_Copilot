"""Evaluate the code-side behaviour on a split and gate on thresholds.

    python -m app.eval.run --split dev                      print metrics, check the thresholds
    python -m app.eval.run --split dev --write-baseline     store the metrics as the baseline
    python -m app.eval.run --split dev --pipeline --no-llm  also run the agent pipeline (needs DB)

The default (code) metrics need no database and no model: every case is rebuilt from its
structured data and scored by the rules engine, so this is what GitHub Actions runs on a PR. The
model-judged suites (RAGAS, DeepEval) are in `app.eval.judge` and run locally with your keys.

A run fails (exit 1) when a metric is below its floor in `docs/baselines/thresholds.json` or has
dropped more than `max_drop` below the stored baseline. The held-out test split needs --allow-test.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from app.scoring.engine import score_case
from app.scoring.replay import CASES_DIR, compare, load_case
from app.scoring.rules import RuleSet, load_rules
from app.services.mock_services import RecordStore

BASELINES = REPO_ROOT / "docs" / "baselines"
THRESHOLDS = BASELINES / "thresholds.json"


def code_metrics(split: str, rs: RuleSet, cases_dir: Path = CASES_DIR) -> dict[str, float]:
    """Band, stop, score and rule agreement with the answer keys, plus hard-rule integrity with
    the largest allowed precedent bonus applied to every case."""
    store = RecordStore(cases_dir.parent / "records")
    rows, errors, hard, broken, lifted = [], [], 0, 0, 0
    for d in sorted(cases_dir.iterdir()):
        key_split = json.loads((d / "answer_key.json").read_text())["split"]
        if split != "all" and key_split != split:
            continue
        inp, key = load_case(d, store)
        base = score_case(inp, rs)
        rows.append(compare(base, key))
        if key["expected_total_score"] is not None and base.total_score is not None:
            errors.append(abs(base.total_score - key["expected_total_score"]))
        boosted = score_case(inp, rs, precedent_bonus=rs.precedent.bonus_max)
        if base.stopped_stage is not None or base.capped_to_refer:
            hard += 1  # a hard stop or a cap-to-refer rule: a precedent must change nothing
            same = (boosted.band, boosted.total_score, boosted.stopped_stage) == (
                base.band, base.total_score, base.stopped_stage,
            )  # fmt: skip
            if not same or boosted.precedent_bonus != 0 or boosted.band == "approve":
                broken += 1
        elif boosted.band != base.band:
            lifted += 1  # informational: the label a bonus would move (OI-3 tuning)
    n = len(rows) or 1
    return {
        "cases": float(len(rows)),
        "band_accuracy": sum(r.band_ok for r in rows) / n,
        "stop_accuracy": sum(r.stop_ok for r in rows) / n,
        "total_score_exact": sum(r.score_ok for r in rows) / n,
        "stage_scores_exact": sum(r.stages_ok for r in rows) / n,
        "failed_rules_exact": sum(r.failed_ok for r in rows) / n,
        "mean_score_error": round(sum(errors) / len(errors), 4) if errors else 0.0,
        "hard_rule_integrity": 1.0 - (broken / hard if hard else 0.0),
        "bonus_lifts_label": float(lifted),
    }


def check(
    metrics: dict[str, float], thresholds: dict[str, Any], baseline: dict[str, float] | None
) -> list[str]:
    """Every way the metrics fall short. `min` is a floor, `max` a ceiling (errors), `max_drop`
    the largest allowed fall below the stored baseline."""
    problems = []
    for name, rule in thresholds.get("metrics", {}).items():
        if name not in metrics:
            problems.append(f"{name}: not measured")
            continue
        value = metrics[name]
        if "min" in rule and value < rule["min"]:
            problems.append(f"{name} {value:.4f} is below the floor {rule['min']}")
        if "max" in rule and value > rule["max"]:
            problems.append(f"{name} {value:.4f} is above the ceiling {rule['max']}")
        drop = baseline[name] - value if baseline and name in baseline else 0.0
        if "max_drop" in rule and drop > rule["max_drop"]:
            problems.append(f"{name} fell {drop:.4f} from the baseline")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--thresholds", type=Path, default=THRESHOLDS)
    args = ap.parse_args()
    if args.split != "dev" and not args.allow_test:
        print("the held-out test split is for the final evaluation; pass --allow-test")
        return 2
    rs = load_rules()
    metrics = code_metrics(args.split, rs)
    print(f"rules {rs.version}   split {args.split}")
    for name, value in metrics.items():
        print(f"  {name:22s} {value:.4f}")
    path = BASELINES / f"{args.split}-code.json"
    if args.write_baseline:
        BASELINES.mkdir(exist_ok=True)
        path.write_text(json.dumps({"rules_version": rs.version, "split": args.split,
                                    "metrics": metrics}, indent=2) + "\n")  # fmt: skip
        print(f"baseline written to {path.relative_to(REPO_ROOT)}")
        return 0
    baseline = json.loads(path.read_text())["metrics"] if path.exists() else None
    thresholds = json.loads(args.thresholds.read_text()) if args.thresholds.exists() else {}
    problems = check(metrics, thresholds, baseline)
    for p in problems:
        print(f"FAIL {p}")
    if not thresholds:
        print("no thresholds file: nothing was gated")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
