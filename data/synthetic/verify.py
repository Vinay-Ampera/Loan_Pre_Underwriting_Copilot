"""Stage 1 exit-criteria check: `python -m synthetic.verify [--out DIR]`. Exit code 1 on failure.

1. 100 cases, 60 dev / 40 test, with the loan-type split from PRD section 11
2. every case has application, answer key and every file its manifest lists; the document set is
   complete unless the answer key says documents were deliberately left out
3. score targets cover 30, 40, 55, 67, 85, 98 and 100
4. every generated PAN and Aadhaar passes the validators, except those deliberately corrupted
   in fix_pan_invalid / fix_aadhaar_invalid cases, which must be exactly the ones that fail
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.intake.validators import aadhaar_valid, gstin_valid, pan_valid, udyam_valid
from app.scoring.rules import load_rules
from app.services.mock_services import aadhaar_hash
from synthetic.generate import OUTPUT

TARGETS = {30, 40, 55, 67, 85, 98, 100}
EXPECTED_SPLIT = {
    ("personal", "dev"): 13, ("personal", "test"): 9, ("home", "dev"): 13, ("home", "test"): 9,
    ("vehicle", "dev"): 13, ("vehicle", "test"): 9, ("business", "dev"): 13, ("business", "test"): 9,
    ("education", "dev"): 8, ("education", "test"): 4,
}  # fmt: skip


def load(out: Path) -> list[tuple[Path, dict[str, Any], dict[str, Any]]]:
    rows = []
    for d in sorted((out / "cases").iterdir()):
        rows.append((d, json.loads((d / "application.json").read_text()),
                     json.loads((d / "answer_key.json").read_text())))  # fmt: skip
    return rows


def check(out: Path) -> list[str]:
    problems: list[str] = []
    rows = load(out)
    ruleset = load_rules()

    # 1. counts
    counts: dict[tuple[str, str], int] = {}
    for _, _, key in rows:
        k = (key["loan_type"], key["split"])
        counts[k] = counts.get(k, 0) + 1
    if len(rows) != 100:
        problems.append(f"expected 100 cases, found {len(rows)}")
    if counts != EXPECTED_SPLIT:
        problems.append(f"loan/split counts differ from PRD: {counts}")

    index = {r["case_id"]: r for r in json.loads((out / "index.json").read_text())}
    identity_hashes = {
        r["pan"]: r["aadhaar_hash"]
        for r in json.loads((out / "records" / "identity.json").read_text())
    }

    achieved: set[float] = set()
    for d, app, key in rows:
        cid = key["case_id"]
        # 2. answer key row + files
        if cid not in index:
            problems.append(f"{cid}: missing from index.json")
        for doc in key["documents"]:
            if not (d / doc["file"]).is_file():
                problems.append(f"{cid}: manifest file missing on disk: {doc['file']}")
        intentional_gap = (
            key["facts"]["mandatory_docs_ratio"] < 1 or not key["facts"]["kyc_docs_complete"]
        )
        if not intentional_gap:
            have = {(x["doc_type"], x["role"]): 0 for x in key["documents"]}
            for x in key["documents"]:
                have[(x["doc_type"], x["role"])] += x["units"]
            for r in ruleset.required_documents(key["loan_type"]):
                applicants = ["primary", "co"] if r.kyc else [r.applicant]
                for role in applicants:
                    if role == "co" and "co" not in {a["role"] for a in app["applicants"]}:
                        continue
                    employment = next(
                        a["employment_type"] for a in app["applicants"] if a["role"] == role
                    )
                    ld = app["loan_details"]
                    env = {"employment_type": employment, "vehicle_kind": ld.get("vehicle_kind"),
                           "vehicle_condition": ld.get("vehicle_condition")}  # fmt: skip
                    if r.when and any(env.get(k) != v for k, v in r.when.items()):
                        continue
                    types = r.any_of or [r.type]
                    got = sum(v for (t, rl), v in have.items() if t in types and rl == role)
                    if got < r.min_count:
                        problems.append(f"{cid}: {role} has {got}/{r.min_count} of {r.type}")
        if key["expected_total_score"] is not None and key["scenario"] == "score":
            achieved.add(key["expected_total_score"])
        if key["scenario"] == "score" and key["expected_total_score"] != key["target_score"]:
            problems.append(
                f"{cid}: score {key['expected_total_score']} != target {key['target_score']}"
            )

        # 4. PAN / Aadhaar validators
        bad_pan_expected = key["scenario"] == "fix_pan_invalid"
        bad_aadhaar_expected = key["scenario"] == "fix_aadhaar_invalid"
        for a in app["applicants"]:
            surname = a["full_name"].split()[-1]
            ok = pan_valid(a["pan"], surname)
            if ok == (bad_pan_expected and a["role"] == "primary"):
                problems.append(
                    f"{cid}: {a['role']} PAN validity {ok} contradicts scenario {key['scenario']}"
                )
        for doc in key["documents"]:
            if doc["doc_type"] == "aadhaar":
                ok = aadhaar_valid(doc["truth"]["aadhaar"])
                if ok == (bad_aadhaar_expected and doc["role"] == "primary"):
                    problems.append(
                        f"{cid}: {doc['role']} Aadhaar validity {ok} contradicts scenario"
                    )
                # an Aadhaar that was left uncorrupted must hash to the identity record
                pan = next(a["pan"] for a in app["applicants"] if a["role"] == doc["role"])
                if (
                    ok
                    and pan in identity_hashes
                    and identity_hashes[pan] != aadhaar_hash(doc["truth"]["aadhaar"])
                ):
                    problems.append(f"{cid}: Aadhaar does not match its identity record")
        if key["loan_type"] == "business":
            ld = app["loan_details"]
            if not udyam_valid(ld["udyam_number"]):
                problems.append(f"{cid}: bad Udyam format")
            gst = next(x for x in key["documents"] if x["doc_type"] == "gst_registration")["truth"]
            if gstin_valid(gst["gstin"], gst["pan"]) != key["facts"]["gst_or_udyam_valid"]:
                problems.append(f"{cid}: GSTIN validity disagrees with the answer key")

    # 3. score spread
    missing = TARGETS - achieved
    if missing:
        problems.append(f"score targets not covered: {sorted(missing)}")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, default=OUTPUT)
    args = ap.parse_args()
    problems = check(args.out)
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for p in problems[:40]:
            print("  -", p)
        sys.exit(1)
    rows = load(args.out)
    spread = sorted({k["expected_total_score"] for _, _, k in rows if k["scenario"] == "score"})
    print(f"OK: {len(rows)} cases; score spread {spread}")


if __name__ == "__main__":
    main()
