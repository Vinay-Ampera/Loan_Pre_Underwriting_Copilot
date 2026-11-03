"""Aggregate outcome rates by group, for the auditor (SECURITY.md D3 and section 8).

Monitoring only: it reports, it changes no rule, score or decision. The route reads the isolated
attributes table through its own read-only connection (`REPORT_DATABASE_URL`, a login that holds
`report_ro`; without it the API's own connection is used, which is fine for a throwaway database
but not for a deployment where `app_rw` is the API's role). No agent, scoring, RAG, intake,
learning, service or API module reads that table or imports this package except to mount the
router, and a test keeps it that way.

Only group-level counts leave this module. A group with fewer than `SMALL_GROUP` cases is reported
as `too_few` with no count and no rate, and no overall total is returned, so a hidden group's size
cannot be worked out by subtraction. Case-level rows are never returned.
"""

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Connection, Engine, create_engine

from app.api.deps import User, auditor_only
from app.core.config import Settings
from app.eval.fairness import SMALL_GROUP, SQL, rates

router = APIRouter(prefix="/auditor", tags=["auditor"])
SPLITS = ("dev", "test")


def build_engine(settings: Settings, default: Engine) -> Engine:
    """The read-only monitoring engine when configured, else the API's own."""
    url = settings.report_sqlalchemy_url()
    return create_engine(url, pool_pre_ping=True) if url else default


def _conn(request: Request) -> Iterator[Connection]:
    engine: Engine = request.app.state.monitor_engine
    with engine.connect() as conn:
        yield conn


def shown(report: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Strip a rates() report down to what the auditor may see."""
    out: dict[str, Any] = {}
    for attr, info in report.items():
        groups = [
            {"group": value, "too_few": True} if g["small"]
            else {"group": value, "n": g["n"], "approve_rate": g["approve_rate"]}
            for value, g in info["groups"].items()
        ]  # fmt: skip
        out[attr] = {"groups": groups, "gap_pp": info["gap_pp"], "flag": info["flag"]}
    return out


@router.get("/fairness")
def group_outcomes(
    split: str = "dev", _: User = Depends(auditor_only), conn: Connection = Depends(_conn)
) -> dict[str, Any]:  # fmt: skip
    split = split if split in SPLITS else "dev"
    rows = [tuple(r) for r in conn.execute(SQL, {"split": split})]
    return {"split": split, "min_group": SMALL_GROUP, "attributes": shown(rates(rows))}
