"""Tamper hints (FR-9). A hint is evidence for the officer and the Risk agent, never a verdict:
`CM-FRD-01` in the rules file decides what a hint is worth. Pure functions.
"""

import re
from collections.abc import Iterable
from datetime import datetime

from app.intake.models import DocType, ExtractedField, TamperHint, Transaction

EDITOR_TOOLS = ("ilovepdf", "sejda", "acrobat", "pdfescape", "smallpdf", "photoshop", "canva",
                "foxit", "nitro", "pdf-xchange", "pdfsam", "gimp", "libreoffice", "word")  # fmt: skip
PF_RATIO = (0.10, 0.13)  # provident fund as a share of basic pay
ROUND_STEP = 5000  # a gross salary that is an exact multiple of this is suspiciously tidy


def _pdf_date(raw: str | None) -> datetime | None:
    m = re.match(r"D:(\d{14})", raw or "")
    return datetime.strptime(m.group(1), "%Y%m%d%H%M%S") if m else None


def metadata_hints(meta: dict[str, str]) -> list[TamperHint]:
    hints: list[TamperHint] = []
    producer = f"{meta.get('producer', '')} {meta.get('creator', '')}".lower()
    tool = next((t for t in EDITOR_TOOLS if t in producer), None)
    if tool:
        hints.append(
            TamperHint(
                code="EDITOR_PRODUCER", message=f"PDF was last written by an editing tool ({tool})"
            )
        )
    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    if created and modified and (modified - created).days >= 1:
        hints.append(
            TamperHint(
                code="MODIFIED_AFTER_CREATION",
                message=f"PDF modified {(modified - created).days} days after it was created",
            )
        )
    return hints


def _num(fields: Iterable[ExtractedField], name: str) -> float | None:
    v = next((f.value for f in fields if f.name == name), None)
    return float(v) if isinstance(v, int | float) else None


def salary_hints(
    fields: list[ExtractedField], earnings: dict[str, float], deductions: dict[str, float]
) -> list[TamperHint]:
    hints: list[TamperHint] = []
    gross, net, ded = _num(fields, "gross"), _num(fields, "net"), _num(fields, "total_deductions")
    if gross is not None and gross >= ROUND_STEP and gross % ROUND_STEP == 0:
        hints.append(
            TamperHint(code="ROUND_SALARY", message="Gross salary is an exact round number")
        )
    if None not in (gross, net, ded) and abs(gross - ded - net) > 1:  # type: ignore[operator]
        hints.append(
            TamperHint(code="NET_PAY_MISMATCH", message="Net pay is not gross minus deductions")
        )
    basic = next((v for k, v in earnings.items() if k.lower().startswith("basic")), None)
    pf = next(
        (
            v
            for k, v in deductions.items()
            if "provident" in k.lower() or k.lower() in ("pf", "epf")
        ),
        None,
    )
    if basic and pf is not None and not PF_RATIO[0] <= pf / basic <= PF_RATIO[1]:
        hints.append(
            TamperHint(
                code="PF_OUT_OF_LINE", message="Provident fund is out of line with basic pay"
            )
        )
    return hints


def document_hints(doc_type: DocType, meta: dict[str, str], fields: list[ExtractedField],
                   earnings: dict[str, float], deductions: dict[str, float]) -> list[TamperHint]:  # fmt: skip
    hints = metadata_hints(meta)
    if doc_type is DocType.PAYSLIP:
        hints += salary_hints(fields, earnings, deductions)
    return hints


# --- cross-document hints: used when a case has both the payslip and the statement ----------------
def salary_credit_hint(
    payslip_net: float, txns: list[Transaction], tolerance: float = 0.02
) -> TamperHint | None:
    """The payslip's net pay should appear as a recurring bank credit."""
    matches = [
        t for t in txns if t.credit and abs(t.credit - payslip_net) <= tolerance * payslip_net
    ]
    months = {t.day[:7] for t in matches}
    if len(months) >= 2:
        return None
    return TamperHint(
        code="NO_MATCHING_CREDIT",
        message="Payslip net pay has no recurring matching credit in the bank statement",
    )


def odd_credit_hints(txns: list[Transaction], salary: float) -> list[TamperHint]:
    """Large credits that are neither the salary nor a business receipt, on a salaried account."""
    odd = [t for t in txns if t.credit >= 0.5 * salary and abs(t.credit - salary) > 0.02 * salary
           and not t.desc.upper().startswith(("NEFT-CUSTOMER", "NEFT-SALARY"))
           and "SALARY" not in t.desc.upper()]  # fmt: skip
    return [
        TamperHint(code="ODD_CREDIT", message=f"Large credit of unclear source on {t.day}")
        for t in odd
    ]
