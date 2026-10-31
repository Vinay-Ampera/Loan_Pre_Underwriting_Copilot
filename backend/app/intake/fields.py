"""Deterministic field extraction for the document layouts the bank sees (label cell, then value
cell). This is the local, first pass of Extraction (AGENTS.md section 2): it works on raw text,
so matching (name, PAN, DOB) never needs a cloud model, and the LLM pass in `llm_extract` only
fills what is missing. Values are normalised: money -> float, dates -> ISO, ids -> upper case.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime

from rapidfuzz import fuzz

from app.intake.models import DocType, ExtractedField
from app.intake.ocr import Cell

LABEL_MATCH = 88.0


@dataclass(frozen=True)
class Spec:
    name: str
    labels: tuple[str, ...]
    kind: str = (
        "text"  # text | money | date | id | digits | inline_money | before_title | month_title
    )
    multi: bool = False  # value may wrap over several cells (addresses)


S = Spec
_COMMON_STOP = ("SYNTHETIC SPECIMEN",)

SPECS: dict[DocType, tuple[Spec, ...]] = {
    DocType.PAN_CARD: (
        S("name", ("Name",)),
        S("father_name", ("Father's name",)),
        S("dob", ("Date of birth",), "date"),
        S("pan", ("PAN",), "id"),
    ),  # fmt: skip
    DocType.AADHAAR: (
        S("name", ("Name",)),
        S("dob", ("Date of birth",), "date"),
        S("address", ("Address",), multi=True),
        S("aadhaar", ("Aadhaar number",), "digits"),
    ),  # fmt: skip
    DocType.PAYSLIP: (
        S("employer", ("Payslip for",), "before_title"),
        S("month", ("Payslip for",), "month_title"),
        S("employee", ("Employee",)),
        S("emp_id", ("Employee ID",)),
        S("pan", ("PAN",), "id"),
        S("gross", ("Gross earnings",), "money"),
        S("total_deductions", ("Total deductions",), "money"),
        S("net", ("Net pay",), "inline_money"),
    ),  # fmt: skip
    DocType.FORM16: (
        S("employer", ("Employer",)),
        S("tan", ("Employer TAN",), "id"),
        S("employee", ("Employee",)),
        S("pan", ("Employee PAN",), "id"),
        S("ay", ("Assessment year",)),
        S("period", ("Period",)),
        S("gross", ("Gross salary",), "money"),
        S("standard_deduction", ("Less: standard deduction",), "money"),
        S("taxable_income", ("Taxable income",), "money"),
        S("tds", ("Tax deducted at source",), "money"),
    ),  # fmt: skip
    DocType.ITR: (
        S("ay", ("Assessment year",)),
        S("name", ("Name",)),
        S("pan", ("PAN",), "id"),
        S("form", ("Form",)),
        S("gross_total_income", ("Gross total income",), "money"),
        S("deductions", ("Deductions under chapter VI-A",), "money"),
        S("total_taxable_income", ("Total taxable income",), "money"),
        S("ack_no", ("Acknowledgement no.",), "digits"),
    ),  # fmt: skip
    DocType.PNL_BALANCE_SHEET: (
        S("entity", ("Financial statements for the year ended",), "before_title"),
        S("revenue", ("Revenue from operations",), "money"),
        S("cost_of_goods", ("Cost of goods and services",), "money"),
        S("operating_expenses", ("Operating expenses",), "money"),
        S("net_profit", ("Net profit",), "money"),
    ),  # fmt: skip
    DocType.GST_REGISTRATION: (
        S("gstin", ("GSTIN",), "id"),
        S("legal_name", ("Legal name",)),
        S("pan", ("PAN",), "id"),
    ),
    DocType.GST_RETURNS: (
        S("gstin", ("GSTIN",), "id"),
        S("legal_name", ("Legal name",)),
        S("trade_name", ("Trade name",)),
        S("total", ("Total outward taxable value",), "inline_money"),
    ),  # fmt: skip
    DocType.UDYAM_CERTIFICATE: (
        S("udyam", ("Udyam number",), "id"),
        S("enterprise", ("Enterprise",)),
        S("pan", ("PAN",), "id"),
    ),
    DocType.BUSINESS_PROOF: (
        S("business", ("Business",)),
        S("constitution", ("Constitution",)),
        S("activity", ("Activity",)),
        S("registered_on", ("Registered on",), "date"),
        S("promoter", ("Promoter",)),
    ),  # fmt: skip
    DocType.SALE_AGREEMENT: (
        S("seller", ("Seller",)),
        S("buyer", ("Buyer",)),
        S("property", ("Property",), multi=True),
        S("sale_consideration", ("Sale consideration",), "money"),
        S("date", ("Date",), "date"),
    ),  # fmt: skip
    DocType.TITLE_DEED: (
        S("owner", ("Owner",)),
        S("property", ("Property",), multi=True),
        S("survey_no", ("Survey no.",)),
    ),
    DocType.ENCUMBRANCE_CERTIFICATE: (
        S("property", ("Property",), multi=True),
        S("period", ("Period",)),
        S("result", ("Result",)),
    ),  # fmt: skip
    DocType.APPROVED_PLAN: (
        S("property", ("Property",), multi=True),
        S("plan_no", ("Plan no.",)),
        S("status", ("Status",)),
    ),
    DocType.ADMISSION_LETTER: (
        S("student", ("Student",)),
        S("course", ("Course",)),
        S("duration", ("Duration",)),
        S("country", ("Country",)),
    ),  # fmt: skip
    DocType.FEE_STRUCTURE: (
        S("course", ("Course",)),
        S("total_fee", ("Tuition and other fees",), "money"),
    ),
    DocType.MARKSHEET: (
        S("student", ("Student",)),
        S("result", ("Result",)),
        S("percentage", ("Percentage",)),
    ),
    DocType.DEALER_INVOICE: (
        S("customer", ("Customer",)),
        S("model", ("Vehicle",)),
        S("on_road", ("On-road price",), "money"),
    ),
    DocType.DRIVING_LICENCE: (
        S("name", ("Name",)),
        S("dob", ("DOB",), "date"),
        S("licence_no", ("Licence no.",), "id"),
    ),
    DocType.RC_BOOK: (S("make_model", ("Make/model",)), S("registration", ("Registration",), "id")),
    DocType.INSURANCE: (S("insured", ("Insured",)), S("valid_till", ("Valid till",), "date")),
}

_MONEY_RE = re.compile(r"[-+]?\d[\d,.\s]*")
_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d %B %Y",
    "%d.%m.%y",
    "%Y-%m-%d",
)


def norm(text: str) -> str:
    return " ".join(text.lower().replace(":", " ").split())


def parse_money(text: str) -> float | None:
    """'INR 1,23,456.50' -> 123456.5. Tolerates OCR reading a ',' as '.' ('10.600.00')."""
    m = _MONEY_RE.search(text.replace("₹", " ").replace("Rs.", " "))
    if not m:
        return None
    raw = re.sub(r"[\s,]", "", m.group(0).strip().rstrip(".,"))
    if raw.count(".") > 1:  # keep only the last '.' as the decimal point when it has two digits
        head, _, tail = raw.rpartition(".")
        raw = head.replace(".", "") + ("." + tail if len(tail) == 2 else tail)
    try:
        return float(raw)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    t = re.sub(r"(?<=\d)[Oo]|[Oo](?=\d)", "0", text.strip()).replace(
        ":", "/"
    )  # OCR reads 0 as O between digits
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _find_label(
    cells: list[Cell], labels: tuple[str, ...], start: int = 0, prefix: bool = False
) -> int | None:
    for i in range(start, len(cells)):
        text = norm(cells[i].text)
        for label in labels:
            lab = norm(label)
            if prefix:
                if text.startswith(lab) or fuzz.ratio(text[: len(lab)], lab) >= LABEL_MATCH:
                    return i
            elif abs(len(text) - len(lab)) <= 3 and fuzz.ratio(text, lab) >= LABEL_MATCH:
                return i
    return None


def _month_from_title(text: str) -> str | None:
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", text)
    if not m:
        return None
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", fmt).strftime("%Y-%m")
        except ValueError:
            continue
    return None


def _normalise(spec: Spec, raw: str) -> str | float | None:
    raw = raw.strip()
    if spec.kind in ("money", "inline_money"):
        return parse_money(raw)
    if spec.kind == "date":
        d = parse_date(raw)
        return d.isoformat() if d else raw or None
    if spec.kind == "id":
        return re.sub(r"\s+", "", raw).upper() or None
    if spec.kind == "digits":
        return re.sub(r"\D", "", raw) or None
    return raw or None


def extract_fields(doc_type: DocType, cells: list[Cell], page: int = 0) -> list[ExtractedField]:
    """One field per spec found. A spec whose label is absent is simply not returned."""
    specs = SPECS.get(doc_type, ())
    all_labels = tuple(lab for s in specs for lab in s.labels)
    out: list[ExtractedField] = []
    for spec in specs:
        inline = spec.kind in ("inline_money", "before_title", "month_title")
        idx = _find_label(cells, spec.labels, prefix=inline)
        if idx is None:
            continue
        label = cells[idx]
        if spec.kind == "before_title":
            if idx == 0:
                continue
            parts, conf = [cells[idx - 1].text], cells[idx - 1].confidence
        elif spec.kind == "month_title":
            parts, conf = [label.text], label.confidence
        elif spec.kind == "inline_money":
            # value either in the same cell ("Net pay: INR 30,000.00") or in the next one
            tail = label.text.split(":", 1)[-1] if ":" in label.text else ""
            if parse_money(tail) is None and idx + 1 < len(cells):
                nxt = cells[idx + 1]
                parts, conf = [nxt.text], min(label.confidence, nxt.confidence)
            else:
                parts, conf = [tail], label.confidence
        else:
            if idx + 1 >= len(cells):
                continue
            nxt = cells[idx + 1]
            if _find_label([nxt], all_labels) is not None:
                continue  # the value is missing; the next cell is another label
            parts, conf = [nxt.text], min(label.confidence, nxt.confidence)
            if spec.multi:
                j = idx + 2
                while (
                    j < len(cells)
                    and _find_label([cells[j]], all_labels) is None
                    and not cells[j].text.startswith(_COMMON_STOP)
                ):
                    parts.append(cells[j].text)
                    conf = min(conf, cells[j].confidence)
                    j += 1
        raw = " ".join(parts)
        value = _month_from_title(raw) if spec.kind == "month_title" else _normalise(spec, raw)
        if value is None:
            continue
        out.append(
            ExtractedField(name=spec.name, value=value, confidence=round(conf, 3), page=page)
        )
    return out


def payslip_components(cells: list[Cell]) -> tuple[dict[str, float], dict[str, float]]:
    """Earnings and deductions rows, split by the x position of the 'Deductions' header."""
    ded_hdr = _find_label(cells, ("Deductions",))
    start = _find_label(cells, ("Amount (INR)",))
    end = _find_label(cells, ("Gross earnings",))
    if ded_hdr is None or start is None or end is None:
        return {}, {}
    split_x = cells[ded_hdr].x - 15
    earnings: dict[str, float] = {}
    deductions: dict[str, float] = {}
    body = cells[start + 1 : end]
    # skip the second 'Amount (INR)' header cell, then read (label, amount) pairs
    body = [c for c in body if norm(c.text) not in ("amount (inr)", "earnings", "deductions")]
    i = 0
    while i + 1 < len(body):
        label, amount = body[i], parse_money(body[i + 1].text)
        if amount is None:
            i += 1
            continue
        (deductions if label.x >= split_x else earnings)[label.text] = amount
        i += 2
    return earnings, deductions


# Fields downstream stages rely on. A missing one goes to the LLM pass, then to the officer.
REQUIRED: dict[DocType, frozenset[str]] = {
    DocType.PAN_CARD: frozenset({"name", "dob", "pan"}),
    DocType.AADHAAR: frozenset({"name", "dob", "aadhaar", "address"}),
    DocType.PAYSLIP: frozenset({"employer", "month", "employee", "pan", "gross", "net"}),
    DocType.FORM16: frozenset({"employee", "pan", "gross"}),
    DocType.ITR: frozenset({"ay", "name", "pan", "gross_total_income"}),
    DocType.PNL_BALANCE_SHEET: frozenset({"net_profit"}),
    DocType.GST_REGISTRATION: frozenset({"gstin", "legal_name", "pan"}),
    DocType.GST_RETURNS: frozenset({"gstin", "total"}),
    DocType.UDYAM_CERTIFICATE: frozenset({"udyam"}),
    DocType.BUSINESS_PROOF: frozenset({"business"}),
    DocType.SALE_AGREEMENT: frozenset({"seller", "buyer", "property"}),
    DocType.TITLE_DEED: frozenset({"owner", "property"}),
    DocType.ENCUMBRANCE_CERTIFICATE: frozenset({"property"}),
    DocType.APPROVED_PLAN: frozenset({"property"}),
    DocType.ADMISSION_LETTER: frozenset({"student", "course"}),
    DocType.FEE_STRUCTURE: frozenset({"total_fee"}),
    DocType.MARKSHEET: frozenset({"student"}),
    DocType.DEALER_INVOICE: frozenset({"customer", "on_road"}),
    DocType.DRIVING_LICENCE: frozenset({"name", "dob", "licence_no"}),
    DocType.RC_BOOK: frozenset({"registration"}),
    DocType.INSURANCE: frozenset({"insured", "valid_till"}),
    DocType.BANK_STATEMENT: frozenset({"account_no", "credits_total"}),
}

# Field names that hold a person's name or address: registered with the masker before any LLM call.
NAME_FIELDS = frozenset({"name", "employee", "student", "customer", "buyer", "seller", "owner",
                         "insured", "promoter", "holder", "father_name"})  # fmt: skip
ADDRESS_FIELDS = frozenset({"address"})
