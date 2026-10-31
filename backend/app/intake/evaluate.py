"""Stage 2 evaluation on the synthetic set: `python -m app.intake.evaluate --split dev`.

Measures what docs/TESTING.md asks of the Parser layer:
  field accuracy per document type (against `truth` in each answer key), classifier accuracy,
  upload checks (accepted / rejected as expected), masking leaks, tamper-hint recall and
  false-alarm rate, measured quality by photo level (calibration of the design targets).
Never tune on `--split test`; it is refused unless --allow-test is given.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import REPO_ROOT
from app.intake.duplicates import CaseDocuments, Verdict
from app.intake.fields import parse_date
from app.intake.masker import Masker, find_leaks
from app.intake.pipeline import process_file, register_known

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"
SPECIAL_EXPECTED = {
    "blurry_reject.jpg": "blurry", "cropped_reject.jpg": "cropped", "borderline_blur_accept.jpg": None,
    "password_protected_1.pdf": "password_protected", "password_protected_2.pdf": "password_protected",
    "password_protected_3.pdf": "password_protected",
}  # fmt: skip


def truth_field(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


# The invoice prints "<make> <model>"; the answer key keeps only the model, so containing it is a match.
CONTAINS = {("dealer_invoice", "model")}


def same(got: Any, want: Any, contains: bool = False) -> bool:
    if got is None:
        return False
    if contains:
        return str(want).lower() in str(got).lower()
    if isinstance(want, int | float) and not isinstance(want, bool):
        try:
            return abs(float(got) - float(want)) < 0.01
        except (TypeError, ValueError):
            return False
    gd, wd = parse_date(str(got)), parse_date(str(want))
    if gd and wd and re.search(r"\d", str(want)) and len(str(want)) >= 8:
        return gd == wd
    clean = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower().replace(" ", "")  # noqa: E731
    return clean(got) == clean(want)


@dataclass
class DocOutcome:
    case_id: str
    doc_type: str
    fmt: str
    level: str
    accepted: bool
    predicted_type: str = ""
    fields_ok: int = 0
    fields_total: int = 0
    wrong: list[str] = field(default_factory=list)
    leaks: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)
    quality: float | None = None
    blur: float | None = None
    ocr_conf: float | None = None
    reject_code: str | None = None
    sha: str = ""
    dup_doc: Any = field(
        default=None, repr=False
    )  # the extracted document, for the duplicate check


def run_doc(args: tuple[str, dict[str, Any], str]) -> DocOutcome:
    case_id, doc, base = args
    path = Path(base) / doc["file"]
    out = DocOutcome(case_id, doc["doc_type"], doc["format"], doc["quality"], False)
    res = process_file(path.read_bytes(), path.name)
    out.reject_code, out.accepted = res.upload.reject_code, res.accepted
    out.blur = res.upload.blur_score
    if res.document is None:
        return out
    d = res.document
    out.predicted_type, out.quality = d.doc_type.value, d.quality_score
    out.ocr_conf = d.meta.get("ocr_confidence")
    out.hints = [h.code for h in d.tamper_hints]
    out.sha, out.dup_doc = res.sha256, d
    masker = Masker()
    register_known(masker, d)
    out.leaks = find_leaks(masker.mask(res.raw_text))
    if doc["doc_type"] == "photo":
        return out
    got = {f.name: f.value for f in d.fields}
    for key, want in doc["truth"].items():
        name = truth_field(key)
        out.fields_total += 1
        if same(got.get(name), want, (doc["doc_type"], name) in CONTAINS):
            out.fields_ok += 1
        else:
            out.wrong.append(f"{name}: got {got.get(name)!r} want {want!r}")
    return out


def load_cases(
    split: str, limit: int | None, formats: set[str] | None
) -> list[tuple[str, dict[str, Any], str]]:
    jobs = []
    index = json.loads((OUTPUT / "index.json").read_text())
    ids = [c["case_id"] for c in index if split == "all" or c["split"] == split]
    for cid in ids[:limit]:
        base = OUTPUT / "cases" / cid
        key = json.loads((base / "answer_key.json").read_text())
        for doc in key["documents"]:
            if formats is None or doc["format"] in formats:
                jobs.append((cid, doc, str(base)))
    return jobs


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:5.1f}% ({a}/{b})" if b else "n/a"


def report(
    outcomes: list[DocOutcome], tamper_cases: set[str], broken_totals: set[str], verbose: bool
) -> dict[str, float]:
    by_type: dict[str, list[DocOutcome]] = defaultdict(list)
    for o in outcomes:
        by_type[o.doc_type].append(o)
    print("\nFIELD ACCURACY by document type")
    ok_all = tot_all = 0
    for t, rows in sorted(by_type.items()):
        ok, tot = sum(r.fields_ok for r in rows), sum(r.fields_total for r in rows)
        ok_all, tot_all = ok_all + ok, tot_all + tot
        print(f"  {t:24} {pct(ok, tot)}  docs={len(rows)}")
    print(f"  {'ALL':24} {pct(ok_all, tot_all)}")
    print("\nFIELD ACCURACY by format / quality")
    by_fmt: dict[tuple[str, str], list[DocOutcome]] = defaultdict(list)
    for o in outcomes:
        if o.doc_type != "photo":
            by_fmt[(o.fmt, o.level)].append(o)
    for k, rows in sorted(by_fmt.items()):
        ok, tot = sum(r.fields_ok for r in rows), sum(r.fields_total for r in rows)
        qs = [r.quality for r in rows if r.quality is not None]
        bs = [r.blur for r in rows if r.blur is not None]
        oc = [r.ocr_conf for r in rows if r.ocr_conf is not None]
        print(f"  {k[0]:12} {k[1]:8} {pct(ok, tot)}  quality={sum(qs) / len(qs):5.1f}"
              + (f"  blur={sum(bs) / len(bs):6.1f} ocr_conf={sum(oc) / len(oc):.3f}" if oc else ""))  # fmt: skip
    acc = [o for o in outcomes if o.accepted]
    cls_ok = sum(o.predicted_type == o.doc_type for o in acc)
    print(
        f"\nUPLOAD accepted: {pct(len(acc), len(outcomes))}   CLASSIFIER: {pct(cls_ok, len(acc))}"
    )
    leaks = [o for o in outcomes if o.leaks]
    print(f"MASKING docs with a raw PAN/Aadhaar/GSTIN/email left after masking: {len(leaks)}")
    t_docs = [o for o in outcomes if o.case_id in tamper_cases]
    hit_cases = {o.case_id for o in t_docs if o.hints}
    # cases built with broken totals must raise NET_PAY_MISMATCH; they are not false alarms
    clean = [
        o for o in outcomes if o.case_id not in tamper_cases and o.case_id not in broken_totals
    ]
    false_alarm = [o for o in clean if o.hints]
    print(f"TAMPER cases flagged by >=1 hint: {pct(len(hit_cases), len(tamper_cases & {o.case_id for o in outcomes}))}"
          f"   clean docs with a hint: {pct(len(false_alarm), len(clean))}")  # fmt: skip
    if false_alarm:
        print(
            "  false alarms by hint:",
            dict(sorted(_count(h for o in false_alarm for h in o.hints).items())),
        )
    if verbose:
        for o in outcomes:
            for w in o.wrong:
                print(f"  WRONG {o.case_id} {o.doc_type} {o.fmt}/{o.level}: {w}")
    return {
        "field_accuracy": ok_all / tot_all if tot_all else 0.0,
        "classifier": cls_ok / len(acc) if acc else 0.0,
    }


def _count(items: Any) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for i in items:
        out[i] += 1
    return out


def check_special() -> int:
    from app.intake.upload import check_upload

    bad = 0
    print("\nSPECIAL upload fixtures")
    for name, expected in SPECIAL_EXPECTED.items():
        p = OUTPUT / "special" / name
        r = check_upload(p.read_bytes(), name, 10 * 1024 * 1024)
        good = r.reject_code == expected and (expected is not None or r.accepted and r.warnings)
        bad += not good
        print(
            f"  {'ok ' if good else 'BAD'} {name:28} -> {r.reject_code or 'accepted'} {r.warnings}"
        )
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument(
        "--allow-test", action="store_true", help="the held-out split is for the final report only"
    )
    ap.add_argument("--limit", type=int, help="first N cases")
    ap.add_argument("--formats", help="comma list: digital_pdf,photo,scanned_pdf")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)
    if a.split != "dev" and not a.allow_test:
        print("refusing: never tune on the test split (use --allow-test for the final report)")
        return 2
    os.environ.setdefault(
        "OMP_NUM_THREADS", "2"
    )  # one OCR per worker; avoid thread oversubscription
    jobs = load_cases(a.split, a.limit, set(a.formats.split(",")) if a.formats else None)
    print(f"{len(jobs)} documents, split={a.split}")
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        outcomes = list(pool.map(run_doc, jobs, chunksize=4))
    index = json.loads((OUTPUT / "index.json").read_text())
    tamper_cases = {c["case_id"] for c in index if c["scenario"] == "tamper"}
    broken = {
        c["case_id"] for c in index
        if json.loads((OUTPUT / "cases" / c["case_id"] / "answer_key.json").read_text())["facts"].get("totals_tie_out") is False
    }  # fmt: skip
    metrics = report(outcomes, tamper_cases, broken, a.verbose)
    registries: dict[str, CaseDocuments] = {}
    false_dups = []
    for o in outcomes:
        if o.accepted and o.dup_doc is not None:
            dec = registries.setdefault(o.case_id, CaseDocuments()).add(
                o.doc_type, o.sha, o.dup_doc
            )
            if dec.verdict is not Verdict.NEW:
                false_dups.append(f"{o.case_id} {o.doc_type}: {dec.message}")
    print(f"\nDUPLICATES wrongly flagged among genuine documents: {len(false_dups)}")
    for line in false_dups[:10]:
        print("  ", line)
    bad_special = check_special()
    print(
        f"\nfield accuracy {metrics['field_accuracy']:.3f}  classifier {metrics['classifier']:.3f}"
    )
    return 1 if bad_special else 0


if __name__ == "__main__":
    sys.exit(main())
