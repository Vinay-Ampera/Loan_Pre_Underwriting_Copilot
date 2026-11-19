"""Part D measurement: `python -m app.intake.evaluate_bundles --split dev`.

For every synthetic case, one bundle PDF is built from the case's documents (primary person's,
then the co-applicant's), photographs and scanned pages included (a photograph becomes one
image-only page, as a scanner would make it). The bundle is checked and read like an upload, split
by `intake.bundle.propose`, and compared with what was put in:

  page label accuracy   pages whose proposed type equals the true type
  documents exact       documents whose first and last page and type were all proposed correctly
  bundles refused       a page too blurry or cropped for the bundle checks (named in the message)

The passport-style applicant photograph is left out: it has no title, so a page like it joins
the document before it and the officer moves it (EDGE_CASES E-62). Never tune on `--split test`.
"""

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf

from app.core.config import REPO_ROOT
from app.intake import bundle, upload
from app.intake.reader import read_document

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"
SKIP_TYPES = {"photo"}
PAGE_WIDTH = 595.0


@dataclass
class Outcome:
    case_id: str
    mode: str
    refused: str = ""
    pages: int = 0
    pages_ok: int = 0
    docs: int = 0
    docs_exact: int = 0
    wrong: str = ""


def _as_pdf(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        return data
    with pymupdf.open(stream=data) as img:  # a photograph becomes one image-only page
        w, h = img[0].rect.width, img[0].rect.height
    out = pymupdf.open()
    page = out.new_page(width=PAGE_WIDTH, height=PAGE_WIDTH * h / w)
    page.insert_image(page.rect, stream=data)
    pdf = out.tobytes()
    out.close()
    return bytes(pdf)


def build_bundle(
    case_dir: Path, key: dict[str, Any], mode: str
) -> tuple[bytes, list[str], list[tuple[int, int, str]]]:
    """(bundle bytes, true type of every page, true (first, last, type) of every document)."""
    out = pymupdf.open()
    truth_pages: list[str] = []
    truth_docs: list[tuple[int, int, str]] = []
    docs = sorted(key["documents"], key=lambda d: (d["role"] != "primary", d["file"]))
    for d in docs:
        if d["doc_type"] in SKIP_TYPES:
            continue
        if mode == "digital" and d["format"] != "digital_pdf":
            continue
        with pymupdf.open(stream=_as_pdf(case_dir / d["file"]), filetype="pdf") as src:
            first = len(truth_pages) + 1
            out.insert_pdf(src)
            truth_pages += [d["doc_type"]] * src.page_count
            truth_docs.append((first, len(truth_pages), d["doc_type"]))
    pdf = out.tobytes() if len(out) else b""
    out.close()
    return bytes(pdf), truth_pages, truth_docs


def run_case(job: tuple[str, str]) -> Outcome:
    case_id, mode = job
    base = OUTPUT / "cases" / case_id
    key = json.loads((base / "answer_key.json").read_text())
    data, truth_pages, truth_docs = build_bundle(base, key, mode)
    o = Outcome(case_id, mode)
    if len(truth_docs) < bundle.MIN_PAGES:
        o.refused = "fewer than two documents in this mode"
        return o
    chk = upload.check_upload(data, "bundle.pdf", 10**9, bundle_pages=10**4)
    if not chk.accepted:
        o.refused = f"{chk.reject_code}: {chk.message}"
        return o
    segments = bundle.propose(read_document(data, chk).pages)
    ok, total = bundle.page_accuracy(truth_pages, segments)
    o.pages, o.pages_ok = total, ok
    got = {(s.page_from, s.page_to, s.doc_type) for s in segments}
    o.docs, o.docs_exact = len(truth_docs), sum(t in got for t in truth_docs)
    if o.docs_exact < o.docs:
        miss = [t for t in truth_docs if t not in got]
        o.wrong = f"missed {miss[:3]} proposed {sorted(got)[:4]}"
    return o


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--mode", default="all", choices=["digital", "all"],
                    help="digital = text-layer PDFs only; all = photographs and scans too")  # fmt: skip
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verbose", "-v", action="store_true")
    a = ap.parse_args(argv)
    if a.split != "dev" and not a.allow_test:
        print("refusing: never tune on the test split (use --allow-test for the final report)")
        return 2
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    index = json.loads((OUTPUT / "index.json").read_text())
    ids = [c["case_id"] for c in index if a.split == "all" or c["split"] == a.split][: a.limit]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        outcomes = list(pool.map(run_case, [(i, a.mode) for i in ids], chunksize=2))
    done = [o for o in outcomes if not o.refused]
    refused = [o for o in outcomes if o.refused]
    pages, pages_ok = sum(o.pages for o in done), sum(o.pages_ok for o in done)
    docs, exact = sum(o.docs for o in done), sum(o.docs_exact for o in done)
    print(f"bundles built {len(outcomes)} (mode={a.mode}, split={a.split}); refused {len(refused)}")
    for o in refused[: 10 if not a.verbose else None]:
        print(f"  refused {o.case_id}: {o.refused}")
    print(f"page label accuracy   {100 * pages_ok / max(pages, 1):5.1f}% ({pages_ok}/{pages})")
    print(f"documents exact       {100 * exact / max(docs, 1):5.1f}% ({exact}/{docs})")
    for o in done:
        if o.wrong:
            print(f"  {o.case_id}: {o.wrong}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
