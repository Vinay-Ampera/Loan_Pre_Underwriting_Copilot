"""Code validators (FR-8): ID formats and checksums, totals, dates, running balances.

Pure functions. Nothing here calls a model; the Extraction agent runs these after the LLM and
they decide the final confidence of a field and which issues the officer sees.
"""

from datetime import date

from app.intake.fields import norm, parse_date
from app.intake.models import DocType, ExtractedField, Transaction, ValidationIssue
from app.intake.validators import aadhaar_valid, gstin_valid, pan_valid, udyam_valid

LOW_CONFIDENCE = 0.80  # fields under this are flagged to the officer, never guessed
INVALID_CAP = 0.40  # a field that fails its format check cannot be more confident than this
MONEY_TOLERANCE = 1.0  # rupees; printed totals are rounded
BALANCE_TOLERANCE = 0.02


def _val(fields: list[ExtractedField], name: str) -> str | float | int | None:
    return next((f.value for f in fields if f.name == name), None)


def _num(fields: list[ExtractedField], name: str) -> float | None:
    v = _val(fields, name)
    return float(v) if isinstance(v, int | float) else None


def surname_of(name: str) -> str | None:
    parts = name.split()
    return parts[-1] if parts else None


def check_ids(doc_type: DocType, fields: list[ExtractedField]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    pan, name = _val(fields, "pan"), _val(fields, "name") or _val(fields, "employee")
    if isinstance(pan, str) and not pan_valid(
        pan, surname_of(str(name)) if doc_type is DocType.PAN_CARD and name else None
    ):
        issues.append(
            ValidationIssue(code="PAN_FORMAT", message="PAN is not a valid PAN", field="pan")
        )
    aad = _val(fields, "aadhaar")
    if isinstance(aad, str) and not aadhaar_valid(aad):
        issues.append(
            ValidationIssue(
                code="AADHAAR_CHECKSUM",
                message="Aadhaar number fails its checksum",
                field="aadhaar",
            )
        )
    gst = _val(fields, "gstin")
    if isinstance(gst, str) and not gstin_valid(gst, pan if isinstance(pan, str) else None):
        issues.append(
            ValidationIssue(
                code="GSTIN_INVALID", message="GSTIN fails its checksum or PAN link", field="gstin"
            )
        )
    udy = _val(fields, "udyam")
    if isinstance(udy, str) and not udyam_valid(udy):
        issues.append(
            ValidationIssue(
                code="UDYAM_FORMAT", message="Udyam number format is wrong", field="udyam"
            )
        )
    return issues


def check_dates(fields: list[ExtractedField], as_of: date) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    dob = parse_date(str(_val(fields, "dob") or ""))
    if dob is not None and not (date(1900, 1, 1) < dob < as_of):
        issues.append(
            ValidationIssue(
                code="DOB_IMPLAUSIBLE", message="Date of birth is not plausible", field="dob"
            )
        )
    for name in ("registered_on", "date"):
        d = parse_date(str(_val(fields, name) or ""))
        if d is not None and d > as_of:
            issues.append(
                ValidationIssue(
                    code="DATE_IN_FUTURE", message=f"{name} is in the future", field=name
                )
            )
    return issues


def check_totals(doc_type: DocType, fields: list[ExtractedField],
                 earnings: dict[str, float] | None = None, deductions: dict[str, float] | None = None,
                 monthly_sales: list[float] | None = None) -> list[ValidationIssue]:  # fmt: skip
    issues: list[ValidationIssue] = []

    def tie(code: str, message: str, a: float | None, b: float | None, field: str) -> None:
        if a is not None and b is not None and abs(a - b) > MONEY_TOLERANCE:
            issues.append(ValidationIssue(code=code, message=message, field=field))

    if doc_type is DocType.PAYSLIP:
        gross, ded, net = (
            _num(fields, "gross"),
            _num(fields, "total_deductions"),
            _num(fields, "net"),
        )
        tie(
            "NET_PAY_MISMATCH",
            "Net pay is not gross minus deductions",
            None if gross is None or ded is None else gross - ded,
            net,
            "net",
        )
        if earnings:
            tie(
                "GROSS_SUM_MISMATCH",
                "Earnings lines do not add up to gross",
                sum(earnings.values()),
                gross,
                "gross",
            )
        if deductions:
            tie(
                "DEDUCTION_SUM_MISMATCH",
                "Deduction lines do not add up to total deductions",
                sum(deductions.values()),
                ded,
                "total_deductions",
            )
    elif doc_type is DocType.FORM16:
        g, sd, ti = (
            _num(fields, "gross"),
            _num(fields, "standard_deduction"),
            _num(fields, "taxable_income"),
        )
        tie(
            "TAXABLE_MISMATCH",
            "Taxable income is not gross minus standard deduction",
            None if g is None or sd is None else g - sd,
            ti,
            "taxable_income",
        )
    elif doc_type is DocType.ITR:
        g, d, ti = (
            _num(fields, "gross_total_income"),
            _num(fields, "deductions"),
            _num(fields, "total_taxable_income"),
        )
        tie(
            "TAXABLE_MISMATCH",
            "Taxable income is not gross income minus deductions",
            None if g is None or d is None else g - d,
            ti,
            "total_taxable_income",
        )
    elif doc_type is DocType.PNL_BALANCE_SHEET:
        r, c, o, n = (
            _num(fields, k)
            for k in ("revenue", "cost_of_goods", "operating_expenses", "net_profit")
        )
        if r is not None and c is not None and o is not None:
            tie(
                "PROFIT_MISMATCH",
                "Net profit is not revenue minus costs",
                r - c - o,
                n,
                "net_profit",
            )
    elif doc_type is DocType.GST_RETURNS and monthly_sales:
        tie(
            "TOTAL_MISMATCH",
            "Monthly sales do not add up to the stated total",
            sum(monthly_sales),
            _num(fields, "total"),
            "total",
        )
    return issues


def check_balances(txns: list[Transaction], opening: float | None) -> list[ValidationIssue]:
    """Each row's balance must equal the previous balance plus credit minus debit."""
    issues: list[ValidationIssue] = []
    prev = opening
    for i, t in enumerate(txns):
        if prev is not None and abs(prev + t.credit - t.debit - t.balance) > BALANCE_TOLERANCE:
            issues.append(
                ValidationIssue(
                    code="BALANCE_BREAK",
                    message=f"Running balance does not tie at row {i + 1} ({t.day})",
                )
            )
        prev = t.balance
    return issues


def apply_confidence_rules(
    fields: list[ExtractedField], issues: list[ValidationIssue]
) -> list[ExtractedField]:
    """Cap the confidence of any field a validator rejected; flag everything under LOW_CONFIDENCE."""
    bad = {i.field for i in issues if i.field}
    out = []
    for f in fields:
        conf = min(f.confidence, INVALID_CAP) if f.name in bad else f.confidence
        out.append(
            f.model_copy(update={"confidence": conf, "low_confidence": conf < LOW_CONFIDENCE})
        )
    return out


def present_in_source(value: str | float | int | None, source_text: str) -> bool:
    """Guard against invented values: the value (digits or words) must occur in the document text."""
    if value is None:
        return False
    if isinstance(value, int | float):
        digits = f"{value:.2f}".replace(".", "")
        flat = "".join(ch for ch in source_text if ch.isdigit())
        return digits in flat or str(int(value)) in flat
    return norm(str(value)) in norm(source_text) or str(value).replace(
        " ", ""
    ) in source_text.replace(" ", "")
