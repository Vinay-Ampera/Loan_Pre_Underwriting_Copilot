from pathlib import Path

import pytest

from app.intake.models import Transaction
from app.intake.pipeline import process_file
from app.scoring import analytics
from app.scoring.rules import RuleSet, StatementParams, load_rules

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def ruleset() -> RuleSet:
    return load_rules()


@pytest.fixture(scope="module")
def sp(ruleset: RuleSet) -> StatementParams:
    return ruleset.params.statement


def tx(day: str, desc: str, credit: float = 0.0, debit: float = 0.0) -> Transaction:
    return Transaction(day=day, desc=desc, credit=credit, debit=debit)


def salary_months(
    n: int, amount: float = 50000.0, desc: str = "NEFT-ASTER-SALARY"
) -> list[Transaction]:
    return [tx(f"2026-{m:02d}-02", desc, credit=amount) for m in range(1, n + 1)]


def test_salary_found_by_keyword(sp: StatementParams) -> None:
    a = analytics.analyse_statement(salary_months(6), sp, "salary")
    assert (a.months, a.income_months, a.credits_total, a.salary_credit) == (
        6,
        6,
        300000.0,
        50000.0,
    )
    assert analytics.regularity(a) == 1.0


def test_salary_found_by_recurring_amount_without_keyword(sp: StatementParams) -> None:
    txns = salary_months(5, desc="NEFT-ACME TECH") + [tx("2026-03-15", "NEFT-FRIEND", credit=30000)]
    a = analytics.analyse_statement(txns, sp, "salary")
    assert a.income_months == 5 and a.credits_total == 250000.0  # the one-off 30,000 is not salary


def test_missing_salary_month_lowers_regularity(sp: StatementParams) -> None:
    txns = [t for t in salary_months(6) if not t.day.startswith("2026-04")]
    txns.append(tx("2026-04-20", "UPI-GROCERY", debit=900))  # April has activity but no salary
    a = analytics.analyse_statement(txns, sp, "salary")
    assert (a.months, a.income_months) == (6, 5)
    assert analytics.regularity(a) == pytest.approx(0.833, abs=0.001)


def test_cheque_and_nach_returns_counted_and_charges_line_ignored(sp: StatementParams) -> None:
    txns = [
        *salary_months(6),
        tx("2026-02-10", "INWARD CHEQUE RETURN - INSUFFICIENT FUNDS"),
        tx("2026-02-10", "RETURN CHARGES + GST", debit=590),
        tx("2026-05-11", "NACH DEBIT RETURN - INSUFFICIENT FUNDS"),
    ]
    a = analytics.analyse_statement(txns, sp, "salary")
    assert (a.cheque_returns, a.nach_returns, a.returns) == (1, 1, 2)
    assert len(a.evidence) == 2 and a.evidence[0].startswith("2026-02-10")


def test_returns_older_than_the_window_are_not_counted(sp: StatementParams) -> None:
    txns = [tx("2025-01-05", "INWARD CHEQUE RETURN - INSUFFICIENT FUNDS"), *salary_months(3)]
    a = analytics.analyse_statement(txns, sp, "salary", months=15)
    assert a.returns == 0


def test_return_credits_are_not_income(sp: StatementParams) -> None:
    txns = [*salary_months(3), tx("2026-02-12", "CHEQUE RETURN REVERSAL", credit=50000)]
    assert analytics.analyse_statement(txns, sp, "salary").credits_total == 150000.0


def test_business_income_is_all_trade_credits(sp: StatementParams) -> None:
    txns = [tx("2026-01-05", "NEFT-CUSTOMER 101 PAYMENT", credit=120000),
            tx("2026-01-19", "NEFT-CUSTOMER 202 PAYMENT", credit=80000),
            tx("2026-03-07", "NEFT-CUSTOMER 303 PAYMENT", credit=150000)]  # fmt: skip
    a = analytics.analyse_statement(txns, sp, "business")
    assert (a.months, a.income_months, a.credits_total) == (3, 2, 350000.0)


def test_credit_to_gst_ratio_annualises_the_window(sp: StatementParams) -> None:
    txns = [tx(f"2026-{m:02d}-05", "NEFT-CUSTOMER PAYMENT", credit=1_000_000) for m in range(1, 7)]
    a = analytics.analyse_statement(txns, sp, "business")
    assert analytics.annualised_credits(a) == 12_000_000
    assert analytics.credit_to_gst_ratio(a, 15_000_000) == 0.8  # at the BL-CRD-13 threshold
    assert analytics.credit_to_gst_ratio(a, 0) is None


def test_recurring_emi_debits_detected(sp: StatementParams) -> None:
    txns = [
        *salary_months(4),
        *(tx(f"2026-0{m}-05", "NACH-APEX CREDIT-EMI", debit=7000) for m in range(1, 5)),
    ]
    assert analytics.analyse_statement(txns, sp, "salary").detected_emi_monthly == 7000


def test_empty_statement_is_zero_not_an_error(sp: StatementParams) -> None:
    a = analytics.analyse_statement([], sp, "salary", months=6)
    assert (a.months, a.income_months, a.credits_total) == (6, 0, 0.0)
    assert analytics.regularity(a) == 0.0


@pytest.mark.parametrize("name", ["statement_digital.pdf", "statement_scanned.pdf"])
def test_real_parsed_statements_digital_and_scanned(name: str, sp: StatementParams) -> None:
    """The analytics run on what Stage 2 really parses, text layer and OCR alike."""
    doc = process_file((FIX / name).read_bytes(), name, max_bytes=10**8).document
    assert doc is not None
    a = analytics.analyse_statement(doc.transactions, sp, "salary")
    assert (a.months, a.income_months, a.salary_credit) == (3, 3, 35000.0)
    assert (a.nach_returns, a.cheque_returns) == (1, 0)
    assert a.detected_emi_monthly == 4000.0
