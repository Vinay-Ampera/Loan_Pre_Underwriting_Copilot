"""Bank statement parsers (FR-10) for the four synthetic styles:

  heritage   SBI-like        Txn Date | Description | Ref | Debit | Credit | Balance       (digital)
  horizon    HDFC-like       Date | Narration | Ref | Value Dt | Withdrawal | Deposit | Closing (digital)
  imperial   ICICI-like      S No. | Date | Remarks / Ref | Withdrawal | Deposit | Balance  (digital)
  citadel    imperial layout printed as an image-only scan, read through OCR

Digital styles read the pdfplumber tables; the scan is rebuilt from OCR cell positions. Debit
versus credit comes from the column; the running balance is then re-checked in `checks`.
"""

import re
from dataclasses import dataclass

from app.intake.fields import parse_date, parse_money
from app.intake.models import ExtractedField, Transaction
from app.intake.ocr import Cell
from app.intake.reader import ReadDocument

_MONEY_CELL = re.compile(r"^-?\d[\d,\s]*[.,]\s?\d{2}$")
_DATE_CELL = re.compile(r"^\d{1,2}[./-](?:\d{1,2}|[A-Za-z]{3})[./-]\d{2,4}$")


@dataclass
class ParsedStatement:
    style: str
    transactions: list[Transaction]
    fields: list[ExtractedField]
    opening_balance: float | None
    confidence: float  # 1.0 for the digital text layer, mean OCR confidence for a scan


def detect_style(text: str) -> str:
    t = text.lower()
    if "passbook statement" in t:
        return "citadel"
    if "txn date" in t:
        return "heritage"
    if "withdrawal amt" in t or "narration" in t:
        return "horizon"
    return "imperial"


def _is_return(desc: str) -> bool:
    d = desc.upper()
    return "RETURN" in d and ("CHEQUE" in d or "NACH" in d) and "CHARGES" not in d


_REF_TAIL = re.compile(r"\s*/\s*([A-Z]\d{6,})\s*$")


def _split_desc_ref(raw: str) -> tuple[str, str]:
    m = _REF_TAIL.search(raw)
    if m:
        return raw[: m.start()].strip(), m.group(1)
    return raw.strip(), ""


# --- digital: pdfplumber tables ---------------------------------------------------------------
def _digital_rows(tables: list[list[list[str]]]) -> list[Transaction]:
    """Position-based: the last three columns are debit, credit, balance in all three styles.
    (Header text is unreliable: pdfplumber splits a header word across a column edge.)"""
    txns: list[Transaction] = []
    for table in tables:
        for row in table:
            if len(row) < 5:
                continue
            c_date = next((i for i in (0, 1) if parse_date(row[i]) is not None), None)
            if c_date is None:
                continue
            bal = parse_money(row[-1])
            if bal is None:
                continue
            desc, ref = _split_desc_ref(row[c_date + 1])
            if len(row) - 3 - (c_date + 1) >= 2 and row[c_date + 2]:  # separate reference column
                ref = row[c_date + 2]
            day = parse_date(row[c_date])
            assert day is not None
            txns.append(Transaction(
                day=day.isoformat(), desc=desc, ref=ref,
                debit=parse_money(row[-3]) or 0.0, credit=parse_money(row[-2]) or 0.0,
                balance=bal))  # fmt: skip
    return [t for t in txns if "opening balance" not in t.desc.lower()]


# --- scanned: OCR cells -----------------------------------------------------------------------
def _scan_rows(doc: ReadDocument) -> tuple[list[Transaction], float | None]:
    """Rebuild rows from OCR cell positions. A row is anchored on its date cell. Debit or credit is
    decided from the running balance (OCR garbles the column headers), falling back to which of
    the two amount columns the number sits in."""
    rows: list[tuple[str, str, str, list[Cell]]] = []  # (iso day, desc, ref, money cells by x)
    opening: float | None = None
    for page in doc.pages:
        cells = page.cells
        anchors = [c for c in cells if _DATE_CELL.match(c.text.strip())]
        if not anchors:
            continue
        pitch = _median_gap([a.y for a in anchors]) or 30.0
        for a in anchors:
            band = [c for c in cells if c is not a and abs(c.y - a.y) <= 0.7 * pitch
                    and min(abs(c.y - o.y) for o in anchors) == abs(c.y - a.y)]  # fmt: skip
            money = sorted((c for c in band if _MONEY_CELL.match(c.text.strip()) and c.x > a.x),
                           key=lambda c: c.x)  # fmt: skip
            text = sorted(
                (c for c in band if c not in money and c.x > a.x),
                key=lambda c: (round(c.y / 8), c.x),
            )
            desc, ref = _split_desc_ref(" ".join(c.text for c in text))
            day = parse_date(a.text)
            if day is None or not money:
                continue
            if "opening balance" in desc.lower():
                opening = parse_money(money[-1].text)
                continue
            rows.append((day.isoformat(), desc, ref, money))
    amount_xs = sorted(m[-2].x for *_, m in rows if len(m) >= 2)
    split_x = (
        (amount_xs[0] + amount_xs[-1]) / 2
        if amount_xs and amount_xs[-1] - amount_xs[0] > 100
        else None
    )
    txns: list[Transaction] = []
    prev = opening
    for iso_day, desc, ref, money in rows:
        bal = parse_money(money[-1].text) or 0.0
        debit = credit = 0.0
        if len(money) >= 2:
            amount = parse_money(money[-2].text) or 0.0
            if prev is not None and abs(prev - amount - bal) < 0.02:
                debit = amount
            elif (
                prev is not None
                and abs(prev + amount - bal) < 0.02
                or split_x is not None
                and money[-2].x > split_x
            ):
                credit = amount
            else:
                debit = amount
        txns.append(
            Transaction(day=iso_day, desc=desc, ref=ref, debit=debit, credit=credit, balance=bal)
        )
        prev = bal
    return txns, opening


def _median_gap(ys: list[float]) -> float | None:
    ys = sorted(ys)
    gaps = [b - a for a, b in zip(ys, ys[1:], strict=False) if b - a > 2]
    return sorted(gaps)[len(gaps) // 2] if gaps else None


# --- header + summary -------------------------------------------------------------------------
def _header_fields(lines: list[str], style: str) -> dict[str, str]:
    out: dict[str, str] = {}
    text = "\n".join(lines)
    for key, pattern in (
        ("account_no", r"(?:Account\s*No\.?|Account)\s*[:\n ]\s*(\d{9,18})"),
        ("ifsc", r"IFSC\s*\n?\s*([A-Z0-9]{8,11})"),
    ):
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            out[key] = m.group(1).upper()
    m = re.search(r"Account Holder\s*\n(.+)", text, flags=re.IGNORECASE) or re.search(
        r"Account holder\s*\n(.+)", text
    )
    if m:
        out["holder"] = m.group(1).strip()
    m = re.search(r"Account:\s*\d+\s*\|\s*([^|]+)\|", text)
    if m:
        out["holder"] = m.group(1).strip()
    m = re.search(r"Opening balance\s*\n\s*([\d,.]+)", text, flags=re.IGNORECASE)
    if m:
        out["opening_balance"] = m.group(1)
    return out


def parse_statement(doc: ReadDocument) -> ParsedStatement:
    style = detect_style(doc.text)
    opening: float | None = None
    if doc.is_ocr:
        txns, opening = _scan_rows(doc)
        conf = doc.ocr_confidence or 0.0
    else:
        txns = _digital_rows(doc.tables)
        conf = 0.99
    head = _header_fields(doc.lines, style)
    if opening is None and "opening_balance" in head:
        opening = parse_money(head["opening_balance"])
    if opening is None and txns:  # imperial digital prints it as a row with an empty amount
        opening = None
    fields: list[ExtractedField] = []

    def add(name: str, value: str | float | int | None, c: float = conf) -> None:
        if value not in (None, ""):
            fields.append(ExtractedField(name=name, value=value, confidence=round(min(c, 1.0), 3)))

    add("account_no", head.get("account_no"))
    add("holder", head.get("holder"))
    add("ifsc", head.get("ifsc"))
    add("style", style, 0.95)
    if txns:
        add("credits_total", round(sum(t.credit for t in txns), 2))
        add("debits_total", round(sum(t.debit for t in txns), 2))
        add("months", len({t.day[:7] for t in txns}))
        add("returns", sum(_is_return(t.desc) for t in txns))
        add("closing_balance", txns[-1].balance)
        add("transaction_count", len(txns))
    return ParsedStatement(style, txns, fields, opening, conf)
