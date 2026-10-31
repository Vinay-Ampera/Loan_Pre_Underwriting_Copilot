"""Run intake on a file and print the structured output: `python -m app.intake.cli FILE [--llm]`.

Prints extracted fields with confidences, flags, issues and tamper hints. Identifiers are shown
because the data is synthetic; nothing raw is ever sent to a model (masked first).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.intake.masker import Masker
from app.intake.pipeline import IntakeResult, enrich, process_file


async def _run(path: Path, use_llm: bool) -> IntakeResult:
    result = process_file(path.read_bytes(), path.name)
    if use_llm and result.accepted:
        from app.services.llm import build_router

        result = await enrich(result, build_router(), Masker())
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run document intake on one file")
    ap.add_argument("file", type=Path)
    ap.add_argument(
        "--llm", action="store_true", help="fill missing fields with the extraction LLM (masked)"
    )
    ap.add_argument("--json", action="store_true", help="print JSON instead of a summary")
    args = ap.parse_args(argv)

    result = asyncio.run(_run(args.file, args.llm))
    if not result.accepted:
        print(f"REJECTED [{result.upload.reject_code}]: {result.upload.message}")
        return 2
    doc = result.document
    assert doc is not None
    if args.json:
        print(json.dumps(doc.model_dump(mode="json", exclude={"transactions"}), indent=2))
        return 0
    up = doc.upload
    print(
        f"{args.file.name}: {doc.doc_type.value}  quality={doc.quality_score}  avg_conf={doc.avg_confidence}"
    )
    if up and up.warnings:
        print("  warnings:", ", ".join(up.warnings))
    for f in doc.fields:
        mark = " (low)" if f.low_confidence else ""
        print(f"  {f.name:20} {f.value!s:40} {f.confidence:.2f} {f.source}{mark}")
    if doc.transactions:
        print(f"  {len(doc.transactions)} transactions, style {doc.statement_style}")
    for label, items in (("flags", doc.quality_flags), ("issues", [f"{i.code}: {i.message}" for i in doc.issues][:6]),
                         ("tamper", [f"{t.code}: {t.message}" for t in doc.tamper_hints])):  # fmt: skip
        if items:
            print(f"  {label}:", "; ".join(items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
