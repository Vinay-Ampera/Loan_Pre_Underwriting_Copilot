"""reportlab renderers for synthetic documents. Each returns PDF bytes.

Every page carries a "SYNTHETIC SPECIMEN" footer. Layouts are invented, not copies of any
real bank's or authority's format.
"""

import io
from collections.abc import Sequence
from datetime import date
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from synthetic.finance import Txn, inr, opening_balance

SS = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=SS["BodyText"], fontSize=9.5, leading=13)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10)
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11, spaceAfter=3)
FOOTER = "SYNTHETIC SPECIMEN - not a real document - generated for software testing"


def _footer(canvas: Canvas, doc: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(doc.pagesize[0] / 2, 8 * mm, f"{FOOTER}   |   page {doc.page}")
    canvas.restoreState()


def build(story: list[Any], *, title: str, creator: str, landscape_mode: bool = False) -> bytes:
    buf = io.BytesIO()
    size = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(
        buf, pagesize=size, title=title, author=creator, creator=creator,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
    )  # fmt: skip
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _p(text: str, style: ParagraphStyle = BODY) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;"), style)


def kv_table(
    rows: Sequence[tuple[str, str]], widths: tuple[float, float] = (55 * mm, 120 * mm)
) -> Table:
    t = Table([[_p(f"<b>{k}</b>", SMALL), _p(v)] for k, v in rows], colWidths=list(widths))
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))  # fmt: skip
    return t


TINY = ParagraphStyle("tiny", parent=BODY, fontSize=7.5, leading=9)


def grid(data: list[list[str]], widths: list[float] | None = None, header: bool = True,
         align_right_from: int = 99, repeat: bool = False,
         right_cols: tuple[int, ...] = ()) -> Table:  # fmt: skip
    cls = LongTable if repeat else Table
    # long cells wrap inside their column instead of running into the next one
    data = [
        [Paragraph(c.replace("&", "&amp;"), TINY) if len(c) > 26 else c for c in row]
        for row in data
    ]
    t = cls(data, colWidths=widths, repeatRows=1 if header and repeat else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]  # fmt: skip
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]  # fmt: skip
    if align_right_from < 99:
        style.append(("ALIGN", (align_right_from, 1), (-1, -1), "RIGHT"))
    for col in right_cols:
        style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------------------
def letter(title: str, issuer: str, fields: Sequence[tuple[str, str]], paragraphs: Sequence[str] = (),
           tables: Sequence[list[list[str]]] = (), subtitle: str = "", creator: str = "DocGen") -> bytes:  # fmt: skip
    story: list[Any] = [_p(f"<b>{issuer}</b>", H2)]
    if subtitle:
        story.append(_p(subtitle, SMALL))
    story += [Spacer(1, 4 * mm), _p(title, H1), Spacer(1, 3 * mm)]
    if fields:
        story += [kv_table(fields), Spacer(1, 4 * mm)]
    for para in paragraphs:
        story += [_p(para), Spacer(1, 2 * mm)]
    for tbl in tables:
        story += [grid(tbl), Spacer(1, 3 * mm)]
    return build(story, title=title, creator=creator)


def id_card(title: str, issuer: str, rows: Sequence[tuple[str, str]], note: str = "") -> bytes:
    story: list[Any] = [
        _p(f"<b>{issuer}</b>", H2),
        _p(title, H1),
        Spacer(1, 3 * mm),
        kv_table(rows),
    ]
    if note:
        story += [Spacer(1, 3 * mm), _p(note, SMALL)]
    return build(story, title=title, creator="IdIssuer")


# --------------------------------------------------------------------------------------
def payslip(c: dict[str, Any]) -> bytes:
    """c: employer, employee, designation, emp_id, pan, doj, month_label, bank_last4, earnings{},
    deductions{}, gross, total_deductions, net (net printed as given, so tampering can break it)."""
    story: list[Any] = [
        _p(f"<b>{c['employer']}</b>", H2),
        _p(f"Payslip for {c['month_label']}", H1),
        kv_table([("Employee", c["employee"]), ("Employee ID", c["emp_id"]),
                  ("Designation", c["designation"]), ("PAN", c["pan"]),
                  ("Date of joining", c["doj"]), ("Bank A/c", f"XXXXXX{c['bank_last4']}"),
                  ("Days paid", str(c.get("days", 30)))]),
        Spacer(1, 4 * mm),
    ]  # fmt: skip
    rows = [["Earnings", "Amount (INR)", "Deductions", "Amount (INR)"]]
    e, d = list(c["earnings"].items()), list(c["deductions"].items())
    for i in range(max(len(e), len(d))):
        left = e[i] if i < len(e) else ("", None)
        right = d[i] if i < len(d) else ("", None)
        rows.append([left[0], "" if left[1] is None else inr(left[1]),
                     right[0], "" if right[1] is None else inr(right[1])])  # fmt: skip
    rows.append(["Gross earnings", inr(c["gross"]), "Total deductions", inr(c["total_deductions"])])
    story += [grid(rows, [50 * mm, 35 * mm, 50 * mm, 35 * mm], right_cols=(1, 3)), Spacer(1, 4 * mm),
              _p(f"<b>Net pay: INR {inr(c['net'])}</b>", H2),
              _p("This is a computer generated payslip.", SMALL)]  # fmt: skip
    return build(story, title=f"Payslip {c['month_label']}", creator="Payroll System v4.2")


# --------------------------------------------------------------------------------------
def bank_statement(style: str, c: dict[str, Any], txns: list[Txn]) -> bytes:
    """style: heritage | horizon | imperial | citadel. c: bank, holder, account_no, address,
    period_from, period_to, ifsc."""
    ob = opening_balance(txns)
    story: list[Any] = []
    if style == "heritage":
        story += [_p(f"<b>{c['bank']}</b>", H1), _p("Statement of Account", H2),
                  kv_table([("Account holder", c["holder"]), ("Account no.", c["account_no"]),
                            ("Address", c["address"]), ("IFSC", c["ifsc"]),
                            ("Period", f"{c['period_from']:%d-%b-%Y} to {c['period_to']:%d-%b-%Y}"),
                            ("Opening balance", inr(ob))]), Spacer(1, 4 * mm)]  # fmt: skip
        rows = [["Txn Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"]]
        rows += [[f"{t.day:%d-%b-%Y}", t.desc, t.ref, inr(t.debit) if t.debit else "",
                  inr(t.credit) if t.credit else "", inr(t.balance)] for t in txns]  # fmt: skip
        story.append(
            grid(
                rows,
                [22 * mm, 64 * mm, 30 * mm, 20 * mm, 20 * mm, 24 * mm],
                repeat=True,
                align_right_from=3,
            )
        )
    elif style == "horizon":
        story += [_p(f"<b>{c['bank']}</b>   <font size=8>Account Statement</font>", H1),
                  grid([["Account Holder", c["holder"], "Account No", c["account_no"]],
                        ["Address", c["address"], "IFSC", c["ifsc"]],
                        ["From", f"{c['period_from']:%d/%m/%Y}", "To", f"{c['period_to']:%d/%m/%Y}"]],
                       [28 * mm, 70 * mm, 24 * mm, 55 * mm], header=False), Spacer(1, 4 * mm)]  # fmt: skip
        rows = [
            [
                "Date",
                "Narration",
                "Chq./Ref.No.",
                "Value Dt",
                "Withdrawal Amt.",
                "Deposit Amt.",
                "Closing Balance",
            ]
        ]
        rows += [[f"{t.day:%d/%m/%y}", t.desc, t.ref, f"{t.day:%d/%m/%y}",
                  inr(t.debit, "western") if t.debit else "", inr(t.credit, "western") if t.credit else "",
                  inr(t.balance, "western")] for t in txns]  # fmt: skip
        story.append(
            grid(
                rows,
                [16 * mm, 56 * mm, 25 * mm, 16 * mm, 22 * mm, 22 * mm, 26 * mm],
                repeat=True,
                align_right_from=4,
            )
        )
    else:  # imperial and citadel (citadel is later turned into an image-only scan)
        title = c["bank"] if style == "imperial" else f"{c['bank']} - Passbook Statement"
        story += [_p(f"<b>{title}</b>", H1),
                  _p(f"Account: {c['account_no']} | {c['holder']} | {c['address']}", SMALL),
                  _p(f"Statement period {c['period_from']:%d.%m.%Y} - {c['period_to']:%d.%m.%Y}", SMALL),
                  Spacer(1, 3 * mm)]  # fmt: skip
        rows = [
            [
                "S No.",
                "Transaction Date",
                "Transaction Remarks",
                "Withdrawal (INR)",
                "Deposit (INR)",
                "Balance (INR)",
            ]
        ]
        rows.append(["", f"{c['period_from']:%d.%m.%Y}", "OPENING BALANCE", "", "", inr(ob)])
        rows += [[str(i), f"{t.day:%d.%m.%Y}", f"{t.desc} / {t.ref}", inr(t.debit) if t.debit else "",
                  inr(t.credit) if t.credit else "", inr(t.balance)] for i, t in enumerate(txns, 1)]  # fmt: skip
        story.append(
            grid(
                rows,
                [12 * mm, 24 * mm, 78 * mm, 24 * mm, 24 * mm, 24 * mm],
                repeat=True,
                align_right_from=3,
            )
        )
    return build(story, title=f"Statement {c['account_no']}", creator=f"{c['bank']} eStatement")


# --------------------------------------------------------------------------------------
def itr(c: dict[str, Any]) -> bytes:
    rows = [["Particulars", "Amount (INR)"]]
    rows += [[k, inr(v)] for k, v in c["lines"].items()]
    story: list[Any] = [
        _p("<b>Income Tax Return Acknowledgement (ITR-V)</b>", H1),
        kv_table([("Assessment year", c["ay"]), ("Name", c["name"]), ("PAN", c["pan"]),
                  ("Form", c["form"]), ("Filing date", f"{c['filed']:%d-%b-%Y}"),
                  ("Acknowledgement no.", c["ack"])]),
        Spacer(1, 4 * mm), grid(rows, [110 * mm, 50 * mm], align_right_from=1),
        Spacer(1, 3 * mm), _p("Return filed electronically. Synthetic summary.", SMALL),
    ]  # fmt: skip
    return build(story, title=f"ITR-V {c['ay']}", creator="ITR Portal")


def form16(c: dict[str, Any]) -> bytes:
    rows = [["Part B particulars", "Amount (INR)"]] + [[k, inr(v)] for k, v in c["lines"].items()]
    story: list[Any] = [
        _p("<b>FORM 16 - Certificate under section 203</b>", H1),
        kv_table([("Employer", c["employer"]), ("Employer TAN", c["tan"]),
                  ("Employee", c["name"]), ("Employee PAN", c["pan"]),
                  ("Assessment year", c["ay"]), ("Period", c["period"])]),
        Spacer(1, 4 * mm), grid(rows, [110 * mm, 50 * mm], align_right_from=1),
    ]  # fmt: skip
    return build(story, title=f"Form 16 {c['ay']}", creator="Payroll System v4.2")


def pnl_balance_sheet(c: dict[str, Any]) -> bytes:
    pl = [["Profit and loss", "Amount (INR)"]] + [[k, inr(v)] for k, v in c["pnl"].items()]
    bs = [["Balance sheet", "Amount (INR)"]] + [[k, inr(v)] for k, v in c["bs"].items()]
    story: list[Any] = [_p(f"<b>{c['entity']}</b>", H2),
                        _p(f"Financial statements for the year ended {c['year_end']:%d %B %Y}", H1),
                        grid(pl, [110 * mm, 50 * mm], align_right_from=1), Spacer(1, 6 * mm),
                        grid(bs, [110 * mm, 50 * mm], align_right_from=1),
                        Spacer(1, 3 * mm), _p("Prepared by an invented chartered accountant firm. Synthetic.", SMALL)]  # fmt: skip
    return build(story, title="Financial statements", creator="Ledger Pro")


def gst_returns(c: dict[str, Any]) -> bytes:
    rows = [["Tax period", "Outward taxable value (INR)", "Tax payable (INR)", "Filed on"]]
    rows += [
        [m["period"], inr(m["sales"]), inr(m["tax"]), f"{m['filed']:%d-%b-%Y}"] for m in c["months"]
    ]
    story: list[Any] = [
        _p("<b>GSTR-3B summary - 12 months</b>", H1),
        kv_table([("GSTIN", c["gstin"]), ("Legal name", c["legal_name"]), ("Trade name", c["trade_name"])]),
        Spacer(1, 4 * mm), grid(rows, [38 * mm, 55 * mm, 40 * mm, 30 * mm], align_right_from=1),
        Spacer(1, 3 * mm), _p(f"Total outward taxable value: INR {inr(c['total'])}", BODY),
    ]  # fmt: skip
    return build(story, title="GSTR-3B summary", creator="GST Portal")


def page_break() -> PageBreak:
    return PageBreak()


def fmt_date(d: date) -> str:
    return f"{d:%d-%b-%Y}"
