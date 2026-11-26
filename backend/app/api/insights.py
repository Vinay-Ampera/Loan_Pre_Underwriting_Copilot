"""Insights routes (Stage 12 Part B). Read-only, counted by SQL, no model (SECURITY.md 4j).

- `GET /admin/insights`: the full page, with case references and officer ids for links.
- `GET /auditor/insights`: the same numbers with no case id, case reference or link (E-115).
- `GET /me/insights`: the calling officer's own numbers for Home; never another officer's.

`start` and `end` are instants (the browser sends its own midnight), `end` exclusive; cases
**created** in that window are counted.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Connection

from app.api.deps import User, admin_only, auditor_only, get_conn, officer_only
from app.reporting import insights
from app.scoring.rules import RuleSet

router = APIRouter(tags=["insights"])
LoanType = Literal["personal", "home", "education", "business", "vehicle"]


def _aware(v: datetime | None) -> datetime | None:
    return v if v is None or v.tzinfo else v.replace(tzinfo=UTC)


def _scope(
    start: Annotated[datetime | None, Query(description="cases created at or after")] = None,
    end: Annotated[datetime | None, Query(description="cases created before")] = None,
    loan_type: LoanType | None = None,
) -> insights.Scope:
    start, end = _aware(start), _aware(end)
    if start and end and end <= start:
        raise HTTPException(422, "The end of the period must be after its start.")
    return insights.Scope(start=start, end=end, loan_type=loan_type)


def _page(request: Request, conn: Connection, scope: insights.Scope) -> dict[str, Any]:
    rs: RuleSet = request.app.state.ruleset
    return insights.build(conn, scope, rs)


@router.get("/admin/insights")
def admin_insights(
    request: Request, scope: insights.Scope = Depends(_scope),
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    return _page(request, conn, scope)


@router.get("/auditor/insights")
def auditor_insights(
    request: Request, scope: insights.Scope = Depends(_scope),
    _: User = Depends(auditor_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    return insights.strip_refs(_page(request, conn, scope))


@router.get("/me/insights")
def my_insights(
    request: Request, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    settings = request.app.state.settings
    own = insights.officer_own(conn, user.id, settings.sla_timezone)
    return {**own, "sla_working_days": settings.sla_working_days}
