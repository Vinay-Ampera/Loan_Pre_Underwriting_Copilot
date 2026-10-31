"""Money helpers and bank-statement transaction generation (data generation only)."""

import random
from dataclasses import dataclass
from datetime import date, timedelta

RATES = {"personal": 12.0, "home": 8.75, "education": 9.5, "business": 12.5, "vehicle": 9.5}


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 1200
    return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)


def principal_from_emi(payment: float, annual_rate_pct: float, months: int) -> float:
    r = annual_rate_pct / 1200
    return payment * ((1 + r) ** months - 1) / (r * (1 + r) ** months)


def inr(amount: float, style: str = "indian", decimals: int = 2) -> str:
    """Indian lakh/crore grouping (1,23,456.00) or western grouping (123,456.00)."""
    sign = "-" if amount < 0 else ""
    whole, _, frac = f"{abs(amount):.{decimals}f}".partition(".")
    if style == "indian" and len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join([*parts, tail])
    elif style != "indian":
        whole = f"{int(whole):,}"
    return sign + whole + (f".{frac}" if decimals else "")


def add_months(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    y, m = divmod(total, 12)
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m])  # fmt: skip
    return date(y, m + 1, day)


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


@dataclass
class Txn:
    day: date
    desc: str
    ref: str
    debit: float = 0.0
    credit: float = 0.0
    balance: float = 0.0
    tag: str = ""  # salary | emi | return | business_credit | other  (ground truth, not printed)


@dataclass
class StatementProfile:
    months: int
    end_month: date  # first day of the last month in the statement
    income_per_month: float  # salary net, or average business credits
    kind: str  # salary | business
    employer: str = ""
    skip_income_months: int = 0  # months with no income credit
    existing_emis: list[tuple[str, float]] | None = None
    new_emi_hint: float = 0.0  # a rent-like fixed debit, keeps balances realistic
    returns: int = 0  # cheque / NACH returns across the window
    broken_balance: bool = False  # inject one running-balance error (totals do not tie)


def build_statement(rng: random.Random, p: StatementProfile) -> list[Txn]:
    first = add_months(p.end_month, -(p.months - 1))
    skip = set(rng.sample(range(p.months), p.skip_income_months)) if p.skip_income_months else set()
    return_months = [rng.randrange(p.months) for _ in range(p.returns)]
    txns: list[Txn] = []
    for i in range(p.months):
        ms = add_months(first, i)
        if i not in skip:
            if p.kind == "salary":
                txns.append(Txn(ms + timedelta(days=rng.randint(0, 3)),
                                f"NEFT-{p.employer.upper()[:22]}-SALARY", f"N{rng.randint(10**9, 10**10 - 1)}",
                                credit=p.income_per_month, tag="salary"))  # fmt: skip
            else:
                n = rng.randint(3, 6)
                cuts = sorted(rng.random() for _ in range(n))
                weights = [b - a for a, b in zip([0.0, *cuts[:-1]], cuts, strict=True)] or [1.0]
                total = p.income_per_month * rng.uniform(0.95, 1.05)
                for w in weights:
                    txns.append(Txn(ms + timedelta(days=rng.randint(1, 26)),
                                    f"NEFT-CUSTOMER {rng.randint(100, 999)} PAYMENT",
                                    f"N{rng.randint(10**9, 10**10 - 1)}",
                                    credit=round(total * w / sum(weights), 2), tag="business_credit"))  # fmt: skip
        for lender, amount in p.existing_emis or []:
            txns.append(Txn(ms + timedelta(days=rng.randint(4, 7)), f"NACH-{lender.upper()}-EMI",
                            f"E{rng.randint(10**8, 10**9 - 1)}", debit=amount, tag="emi"))  # fmt: skip
        spend = p.income_per_month * rng.uniform(0.28, 0.4)
        for _ in range(rng.randint(6, 10)):
            kind = rng.choice(["UPI", "UPI", "UPI", "POS", "ATM-WDL", "BILLPAY"])
            who = rng.choice(["GROCERY MART", "FUEL STATION", "ONLINE STORE", "ELECTRICITY BOARD",
                              "MOBILE RECHARGE", "RESTAURANT", "PHARMACY", "METRO CARD"])  # fmt: skip
            txns.append(Txn(ms + timedelta(days=rng.randint(2, 27)), f"{kind}-{who}",
                            f"R{rng.randint(10**8, 10**9 - 1)}",
                            debit=round(spend / 8 * rng.uniform(0.4, 1.6), 2), tag="other"))  # fmt: skip
        if p.new_emi_hint:
            txns.append(Txn(ms + timedelta(days=rng.randint(1, 5)), "NEFT-HOUSE RENT",
                            f"N{rng.randint(10**9, 10**10 - 1)}", debit=p.new_emi_hint, tag="other"))  # fmt: skip
    for m in return_months:
        d = add_months(first, m) + timedelta(days=rng.randint(8, 20))
        kind = rng.choice(["INWARD CHEQUE RETURN", "NACH DEBIT RETURN"])
        txns.append(
            Txn(
                d, f"{kind} - INSUFFICIENT FUNDS", f"X{rng.randint(10**8, 10**9 - 1)}", tag="return"
            )
        )
        txns.append(Txn(d, "RETURN CHARGES + GST", f"X{rng.randint(10**8, 10**9 - 1)}", debit=590.0, tag="return"))  # fmt: skip
    txns.sort(key=lambda t: t.day)

    # opening balance high enough that the account never goes negative
    running, low = 0.0, 0.0
    for t in txns:
        running += t.credit - t.debit
        low = min(low, running)
    opening = round(max(-low + rng.uniform(2000, 15000), 3000.0), 2)
    bal = opening
    for t in txns:
        bal = round(bal + t.credit - t.debit, 2)
        t.balance = bal
    if p.broken_balance and len(txns) > 6:
        txns[len(txns) // 2].balance = round(
            txns[len(txns) // 2].balance + rng.choice([1000, -700, 2500]), 2
        )
    return txns


def opening_balance(txns: list[Txn]) -> float:
    t = txns[0]
    return round(t.balance - t.credit + t.debit, 2)
