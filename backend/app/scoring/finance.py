"""Money, age and ratio arithmetic: the only place these are computed (CLAUDE.md constraint)."""

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def age_on(dob: date, on: date) -> int:
    """Completed years on a date."""
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Equated monthly instalment (reducing balance)."""
    if months <= 0:
        raise ValueError("months must be positive")
    if annual_rate_pct == 0:
        return principal / months
    r = annual_rate_pct / 1200
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def foir_pct(existing_emis: float, new_emi: float, monthly_income: float) -> float | None:
    """(existing + new instalments) / net monthly income, in percent, 1 decimal."""
    if monthly_income <= 0:
        return None
    return round((existing_emis + new_emi) / monthly_income * 100, 1)


def dti_pct(total_debt: float, annual_income: float) -> float | None:
    """Total outstanding debt (loan applied for included) over annual income, in percent."""
    if annual_income <= 0:
        return None
    return round(total_debt / annual_income * 100, 1)


def ltv_pct(loan_amount: float, asset_value: float) -> float | None:
    if asset_value <= 0:
        return None
    return round(loan_amount / asset_value * 100, 1)


def ratio(numerator: float, denominator: float, digits: int = 3) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, digits)
