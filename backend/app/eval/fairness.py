"""Fairness report: recommended-approve rate by gender, age band and city tier. Monitoring only.

    python -m app.eval.fairness [--split dev] [--out docs/baselines/fairness-dev.json]

Reads `fairness_attributes` (isolated from the pipeline: `app_rw` has no access and no agent,
scoring or RAG module may name it) and joins it to the recommendations the pipeline produced. It
reports gaps; it changes no rule, score or decision. A gap is a prompt to look at the data and the
rules, not proof of bias: the synthetic cases are small groups.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings

ATTRIBUTES = ("gender", "age_band", "city_tier")
SMALL_GROUP = 5  # fewer cases than this: shown, flagged as too small to read anything from
GAP_FLAG_PP = 20.0  # percentage points between the highest and lowest group rate

SQL = text(
    """SELECT f.gender, f.age_band, f.city_tier, c.recommendation
       FROM fairness_attributes f
       JOIN test_cases t ON t.case_id = f.case_id
       JOIN cases c ON c.form_data->>'external_id' = f.case_id
       WHERE f.applicant_role = 'primary' AND t.split = :split
             AND c.recommendation IS NOT NULL AND c.status <> 'stopped'"""
)


def rates(rows: list[tuple[str | None, str | None, str | None, str]]) -> dict[str, dict]:  # type: ignore[type-arg]
    """{attribute: {"groups": {value: {n, approve_rate}}, "gap_pp": float | None, "flag": bool}}.
    Stopped cases have no recommendation and are left out by the query."""
    out: dict[str, dict] = {}  # type: ignore[type-arg]
    for i, attr in enumerate(ATTRIBUTES):
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            value = row[i]
            if value is None:
                continue
            counts[value][0] += 1
            counts[value][1] += row[3] == "recommend_approve"
        groups = {
            v: {"n": n, "approve_rate": round(a / n, 4), "small": n < SMALL_GROUP}
            for v, (n, a) in sorted(counts.items())
        }
        usable = [g["approve_rate"] for g in groups.values() if not g["small"]]
        gap = round((max(usable) - min(usable)) * 100, 1) if len(usable) >= 2 else None
        out[attr] = {"groups": groups, "gap_pp": gap, "flag": gap is not None and gap > GAP_FLAG_PP}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(SQL, {"split": args.split})]
    report = rates(rows)
    print(f"split {args.split}: {len(rows)} scored primary applicants (monitoring only)")
    for attr, info in report.items():
        gap = "n/a" if info["gap_pp"] is None else f"{info['gap_pp']} pp"
        print(f"\n{attr}   gap {gap}{'   REVIEW' if info['flag'] else ''}")
        for value, g in info["groups"].items():
            note = "  (too few cases)" if g["small"] else ""
            print(f"  {value:10s} n={g['n']:3d}  recommended-approve {g['approve_rate']:.0%}{note}")
    if args.out:
        args.out.write_text(json.dumps({"split": args.split, **report}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
