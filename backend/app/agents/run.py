"""Run cases through the pipeline from the command line.

    python -m app.agents.run --split dev                  every dev case, models on
    python -m app.agents.run --case SYN-PL-D01 --no-llm   one case, no model calls (code text)
    python -m app.agents.run --case SYN-PL-D01 --crash-before risk     die mid-run (checkpoint kept)
    python -m app.agents.run --resume SYN-PL-D01          continue that case from its checkpoint
    python -m app.agents.run --split dev --force-429      every primary model answers 429

Each case is compared with its answer key: it must finish (paused for the officer, or stopped for a
correction) and stop at the stage the key expects. The held-out test split needs --allow-test.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from litellm.router import Router
from sqlalchemy import create_engine

from app.agents import store
from app.agents.checkpoint import postgres_saver
from app.agents.graph import Pipeline
from app.agents.runtime import AgentContext, Services
from app.agents.state import PipelineState
from app.agents.submission import Submission, load_case_dir
from app.core.config import REPO_ROOT, get_settings
from app.scoring.rules import load_rules
from app.services.llm import build_router, load_config
from app.services.mock_services import RecordStore

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"


@dataclass
class CaseOutcome:
    case_id: str
    completed: bool = False
    stop_ok: bool = False
    band_ok: bool = False
    score_error: float | None = None
    status: str = ""
    stopped: str | None = None
    band: str | None = None
    unverified: int = 0
    tokens: int = 0
    cost: float = 0.0
    seconds: float = 0.0
    fallbacks: int = 0
    notes: list[str] = field(default_factory=list)


def force_429_router() -> Router:
    """Every role's primary model answers 'rate limited' without a network call."""
    cfg = load_config()
    for spec in cfg["roles"].values():
        cfg["providers"][spec["primary"]]["mock_response"] = "litellm.RateLimitError"
    return build_router(config=cfg)


def compare(state: PipelineState, key: dict[str, Any], out: CaseOutcome) -> None:
    rep = state.get("report") or {}
    out.stopped, out.band = rep.get("stopped_stage"), rep.get("band")
    out.status = state.get("status", "")
    out.completed = bool(rep) and out.status in ("awaiting_confirmation", "stopped")
    out.stop_ok = (out.stopped, rep.get("stop_class")) == (
        key["expected_stop_stage"],
        key["expected_stop_class"],
    )
    out.band_ok = out.band == key["expected_band"]
    exp, got = key["expected_total_score"], rep.get("total_score")
    out.score_error = None if exp is None or got is None else round(abs(got - exp), 2)
    out.unverified = len(rep.get("unverified", []))
    calls = state.get("llm_calls", [])
    out.tokens = sum(c["tokens_in"] + c["tokens_out"] for c in calls)
    out.cost = round(sum(c["cost_usd"] for c in calls), 6)
    out.fallbacks = sum(c["fallback_used"] for c in calls)
    if not out.stop_ok:
        out.notes.append(f"stopped at {out.stopped}/{rep.get('stop_class')}, "
                         f"key says {key['expected_stop_stage']}/{key['expected_stop_class']}")  # fmt: skip
    elif not out.band_ok:
        out.notes.append(f"band {out.band}, key says {key['expected_band']}")


def select_cases(args: argparse.Namespace) -> list[Path]:
    index = json.loads((OUTPUT / "index.json").read_text())
    ids = [
        c["case_id"]
        for c in index
        if (c["case_id"] in args.case if args.case else args.split in ("all", c["split"]))
    ]
    return [OUTPUT / "cases" / i for i in ids][: args.limit]


async def run_one(
    pipe: Pipeline, saver: Any, engine: Any, case_dir: Path, sem: asyncio.Semaphore
) -> CaseOutcome:  # fmt: skip
    sub: Submission = load_case_dir(case_dir)
    key = json.loads((case_dir / "answer_key.json").read_text())
    out = CaseOutcome(sub.case_id)
    async with sem:
        started = time.perf_counter()
        with engine.begin() as conn:
            old = store.find_case(conn, sub.case_id)
            case_uuid = store.create_case(conn, sub, store.ensure_system_user(conn))
        if old is not None:
            await saver.adelete_thread(str(old))
        try:
            state = await pipe.start(sub, case_uuid)
        except Exception as exc:  # noqa: BLE001 - report the failure, keep running the other cases
            out.notes.append(f"run failed: {type(exc).__name__}: {str(exc)[:160]}")
            return out
        out.seconds = round(time.perf_counter() - started, 1)
    compare(state, key, out)
    return out


def print_summary(rows: list[CaseOutcome]) -> int:
    n = len(rows) or 1
    done, stop, band = (
        sum(r.completed for r in rows),
        sum(r.stop_ok for r in rows),
        sum(r.band_ok for r in rows),
    )
    errs = [r.score_error for r in rows if r.score_error is not None]
    print(f"\ncompleted or stopped cleanly   {done}/{len(rows)}")
    print(f"stop stage and class as keyed  {stop}/{len(rows)}")
    print(f"band as keyed                  {band}/{len(rows)}  ({band / n:.1%})")
    if errs:
        print(
            f"mean score error               {sum(errs) / len(errs):.2f} points over {len(errs)} scored cases"
        )
    print(f"unverified stage outputs       {sum(r.unverified for r in rows)}")
    print(f"tokens {sum(r.tokens for r in rows)}   cost ${sum(r.cost for r in rows):.4f}   "
          f"fallback calls {sum(r.fallbacks for r in rows)}   seconds/case {sum(r.seconds for r in rows) / n:.1f}")  # fmt: skip
    for r in rows:
        if r.notes:
            print(f"  {r.case_id}: {'; '.join(r.notes)}")
    return 0 if done == len(rows) and stop == len(rows) else 1


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    url = settings.sqlalchemy_url()
    engine = create_engine(url, pool_size=8, max_overflow=8)
    router: Router | None = None
    if not args.no_llm:
        router = force_429_router() if args.force_429 else build_router()
    ctx = AgentContext(
        ruleset=load_rules(),
        engine=engine,
        router=router,
        crash_before=args.crash_before,
        intake_slots=asyncio.Semaphore(args.intake_slots),
        intake_cache=OUTPUT / ".intake_cache" if args.cache else None,
        services=Services.from_store(RecordStore(OUTPUT / "records")),
    )
    async with postgres_saver(url) as saver:
        pipe = Pipeline(ctx, saver)
        if args.resume:
            with engine.connect() as conn:
                case_uuid = store.find_case(conn, args.resume)
            if case_uuid is None:
                print(f"no case {args.resume} in the database")
                return 2
            state = await pipe.resume(case_uuid)
            rep = state.get("report", {})
            print(f"{args.resume}: {state.get('status')} | {rep.get('recommendation_text')} | "
                  f"total {rep.get('total_score')}")  # fmt: skip
            return 0
        cases = select_cases(args)
        sem = asyncio.Semaphore(args.concurrency)
        rows = await asyncio.gather(*(run_one(pipe, saver, engine, c, sem) for c in cases))
    if args.out:
        Path(args.out).write_text(json.dumps([r.__dict__ for r in rows], indent=1))
    return print_summary(list(rows))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--case", nargs="+", metavar="ID")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument(
        "--no-llm", action="store_true", help="skip every model call; code writes the text"
    )
    ap.add_argument(
        "--force-429",
        action="store_true",
        help="primary models answer 429; fallbacks must carry the run",
    )
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument(
        "--intake-slots", type=int, default=3, help="files read at once (OCR is CPU-heavy)"
    )
    ap.add_argument(
        "--cache", action="store_true", help="reuse intake results between runs (dev only)"
    )
    ap.add_argument(
        "--crash-before", help="exit the process hard as this stage starts (resume test)"
    )
    ap.add_argument("--resume", metavar="CASE_ID")
    ap.add_argument("--out", help="write per-case results as JSON")
    ap.add_argument("--allow-test", action="store_true")
    args = ap.parse_args()
    if args.split in ("test", "all") and not args.case and not args.allow_test:
        print("the held-out test split is for the final evaluation; pass --allow-test to run it")
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
