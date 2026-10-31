"""Smoke test the router: `python -m app.services.llm_smoke [--break-primary]`.

Calls every role once with a trivial synthetic prompt. With --break-primary it corrupts each
primary provider key so the call must succeed through a fallback.
"""

import argparse
import asyncio

from pydantic import BaseModel

from app.services.llm import build_router, complete, load_config


class Pong(BaseModel):
    answer: str


async def run(break_primary: bool) -> int:
    cfg = load_config()
    failures = 0
    for role, spec in cfg["roles"].items():
        override = None
        if break_primary:
            override = {cfg["providers"][spec["primary"]]["key"]: "invalid-key"}
        router = build_router(config=cfg, override_keys=override)
        try:
            res = await complete(
                router,
                role,
                [{"role": "user", "content": 'Return JSON {"answer": "pong"} and nothing else.'}],
                Pong,
                max_tokens=1500,
            )
            print(f"OK   {role:<11} -> {res.model}  tokens={res.tokens_in}/{res.tokens_out}")
        except Exception as exc:  # smoke script: report any provider failure by type
            failures += 1
            print(f"FAIL {role:<11} {type(exc).__name__}: {str(exc)[:140]}")
    return failures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--break-primary", action="store_true")
    args = ap.parse_args()
    raise SystemExit(1 if asyncio.run(run(args.break_primary)) else 0)


if __name__ == "__main__":
    main()
