"""Bank-statement analytics: income credits, salary detection, returned cheques and NACH debits.

Input is the transaction list the Extraction stage parsed; output feeds the Income and Credit
scorers. Everything is deterministic and every count carries the rows it came from.
"""

import re
import statistics
from collections import defaultdict
from datetime import date
from typing import Literal

from app.intake.models import Transaction
from app.intake.statement import is_return_entry
from app.scoring.finance import ratio
from app.scoring.matching import parse_date
from app.scoring.models import StatementAnalytics
from app.scoring.rules import StatementParams

_NOT_INCOME = re.compile(r"REVERSAL|REFUND|RETURN|INTEREST|CASHBACK|SELF TRANSFER|OWN ACCOUNT")
_EMI_DEBIT = re.compile(r"\bEMI\b|LOAN REPAY|ECS-LOAN")


def _month(day: str) -> str:
    return day[:7]


def _is_income_candidate(t: Transaction, params: StatementParams) -> bool:
    return t.credit >= params.min_income_credit and not _NOT_INCOME.search(t.desc.upper())


def _recurring_amount_credits(
    credits: list[Transaction], params: StatementParams
) -> list[Transaction]:
    """Credits whose amount repeats (within the tolerance) in at least N different months."""
    out: list[Transaction] = []
    tol = params.recurring_amount_tolerance_pct / 100
    for t in credits:
        months = {
            _month(o.day) for o in credits if abs(o.credit - t.credit) <= tol * max(t.credit, 1)
        }
        if len(months) >= params.recurring_min_months:
            out.append(t)
    return out


def salary_credits(txns: list[Transaction], params: StatementParams) -> list[Transaction]:
    """Credits that look like a salary: a payroll keyword, or the same amount month after month."""
    candidates = [t for t in txns if _is_income_candidate(t, params)]
    keyword = [t for t in candidates if any(k in t.desc.upper() for k in params.salary_keywords)]
    rest = [t for t in candidates if t not in keyword]
    return sorted([*keyword, *_recurring_amount_credits(rest, params)], key=lambda t: t.day)


def months_covered(txns: list[Transaction]) -> int:
    days = sorted(t.day for t in txns)
    if not days:
        return 0
    a, b = parse_date(days[0]), parse_date(days[-1])
    if a is None or b is None:
        return len({_month(d) for d in days})
    return (b.year - a.year) * 12 + (b.month - a.month) + 1


def analyse_statement(
    txns: list[Transaction],
    params: StatementParams,
    income_kind: Literal["salary", "business"],
    *,
    return_window_months: int = 12,
    months: int | None = None,
) -> StatementAnalytics:
    """`months` overrides the span derived from the transactions (use the statement header)."""
    if not txns:
        return StatementAnalytics(months=months or 0, income_months=0, credits_total=0.0)
    span = months if months is not None else months_covered(txns)

    if income_kind == "salary":
        income = salary_credits(txns, params)
    else:
        income = [t for t in txns if _is_income_candidate(t, params)]
    income_months = {_month(t.day) for t in income}

    last = parse_date(max(t.day for t in txns))
    cheque = nach = 0
    evidence: list[str] = []
    for t in txns:
        if not is_return_entry(t.desc):
            continue
        d = parse_date(t.day)
        if (
            last
            and d
            and (last.year - d.year) * 12 + (last.month - d.month) >= return_window_months
        ):
            continue
        if "CHEQUE" in t.desc.upper():
            cheque += 1
        else:
            nach += 1
        if len(evidence) < 5:
            evidence.append(f"{t.day} {t.desc[:48]}")

    emi_by_month: dict[str, float] = defaultdict(float)
    for t in txns:
        if t.debit and _EMI_DEBIT.search(t.desc.upper()) and not is_return_entry(t.desc):
            emi_by_month[_month(t.day)] += t.debit
    salary_amounts = [t.credit for t in income] if income_kind == "salary" else []
    return StatementAnalytics(
        months=span,
        income_months=len(income_months),
        credits_total=round(sum(t.credit for t in income), 2),
        cheque_returns=cheque,
        nach_returns=nach,
        salary_credit=round(statistics.median(salary_amounts), 2) if salary_amounts else None,
        detected_emi_monthly=round(sum(emi_by_month.values()) / max(span, 1), 2),
        evidence=evidence,
    )


def regularity(a: StatementAnalytics) -> float | None:
    """Share of statement months that carried an income credit (1.0 = every month)."""
    return ratio(a.income_months, a.months)


def annualised_credits(a: StatementAnalytics) -> float | None:
    """Income credits scaled to 12 months."""
    return round(a.credits_total * 12 / a.months, 2) if a.months else None


def credit_to_gst_ratio(a: StatementAnalytics, gst_turnover_12m: float) -> float | None:
    """Business: bank credits (annualised) over GST turnover. Below the rule threshold = refer."""
    credits = annualised_credits(a)
    return None if credits is None else ratio(credits, gst_turnover_12m)


def latest_day(txns: list[Transaction]) -> date | None:
    return parse_date(max((t.day for t in txns), default=""))
