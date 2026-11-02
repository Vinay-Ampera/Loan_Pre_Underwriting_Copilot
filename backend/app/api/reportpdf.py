"""PDF export of the report, built on the server from the stored report JSON (reportlab).

The PDF carries the same wording as the screen: "Recommended", never "approved", and the officer's
decision only once it exists. Identifiers are not in the report JSON, so none are printed.
"""

from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BAND_COLOUR = {"approve": "#1E7F4F", "refer": "#9A6200", "reject": "#B03A36"}
DECISION_WORD = {"approve": "approve", "refer": "refer", "reject": "reject"}
SEVERITY = {
    "hard_fail": "Hard fail",
    "cap": "Caps the band",
    "points_lost": "Points lost",
    "note": "Note",
}


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _score(v: float | None, mx: float) -> str:
    return "not run" if v is None else f"{v:g} / {mx:g}"


def build_report_pdf(case_no: str, report: dict[str, Any], officer: dict[str, Any] | None) -> bytes:
    base = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=base["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle(
        "small", parent=body, fontSize=8, leading=10.5, textColor=colors.HexColor("#52606D")
    )
    h1 = ParagraphStyle("h1", parent=base["Heading1"], fontSize=16, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{case_no} pre-underwriting report", author="Pramaan")  # fmt: skip
    out: list[Any] = [_p(f"{case_no} - {report['loan_type'].capitalize()} loan", h1)]
    out.append(
        _p(
            report["recommendation_text"] + ". " + (report.get("awaiting") if not officer else ""),
            body,
        )
    )
    if report.get("stop_text"):
        out.append(_p(report["stop_text"], body))

    score = report.get("total_score")
    band = report.get("band")
    headline = (
        f"Score {score:g} of 100 ({band} band)" if score is not None else "Score not computed"
    )
    out += [Spacer(1, 4), _p(headline, ParagraphStyle("hl", parent=body, fontSize=11,
            textColor=colors.HexColor(BAND_COLOUR.get(band or "", "#52606D"))))]  # fmt: skip

    rows = [["Stage", "Score"]] + [
        [r["label"], _score(r["score"], r["max"])] for r in report["stage_scores"]
    ]
    t = Table(rows, colWidths=[90 * mm, 40 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF0F3")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9DEE3")),
                           ("ALIGN", (1, 0), (1, -1), "RIGHT")]))  # fmt: skip
    out += [_p("Stage scores", h2), t, _p("Summary", h2), _p(report["summary"], body)]

    if report.get("rejection_reason"):
        out += [_p("Reason", h2), _p(report["rejection_reason"], body)]

    out.append(_p("Findings", h2))
    if not report["findings"]:
        out.append(_p("No findings.", body))
    for f in report["findings"]:
        ids = ", ".join(x for x in (f.get("rule_id"), f.get("clause_id")) if x)
        out.append(_p(f"{SEVERITY.get(f['severity'], f['severity'])}: {f['message']}", body))
        extra = f.get("explanation")
        out.append(_p(f"{ids}" + (f" - {extra}" if extra else ""), small))
        out.append(Spacer(1, 3))

    if report.get("citations"):
        out.append(_p("Policy citations", h2))
        for c in report["citations"]:
            out += [_p(c["clause_id"], ParagraphStyle("cid", parent=body, fontName="Courier", fontSize=9)),
                    _p(c["text"], small), Spacer(1, 3)]  # fmt: skip

    if report.get("unverified"):
        out.append(_p("Could not be verified automatically. Please check manually.", h2))
        for u in report["unverified"]:
            out.append(_p(f"{u['stage']}: {u['reason']}", body))

    out.append(_p("Officer decision", h2))
    if officer:
        word = DECISION_WORD.get(officer["final_decision"], officer["final_decision"])
        verb = (
            "confirmed the recommendation"
            if officer["action"] == "confirm"
            else f"overrode the recommendation to {word}"
        )
        when = (
            officer["at"].strftime("%Y-%m-%d %H:%M")
            if isinstance(officer["at"], datetime)
            else officer["at"]
        )
        out.append(_p(f"{officer['officer']} {verb} on {when}.", body))
        if officer.get("reason"):
            out.append(_p(f"Reason: {officer['reason']}", body))
    else:
        out.append(_p("Not confirmed yet. A loan officer confirms every case.", body))

    v = report.get("versions", {})
    out += [
        Spacer(1, 8),
        _p(f"Rules version {v.get('rules', '-')}. Synthetic data; recommendation only.", small),
    ]
    doc.build(out)
    return buf.getvalue()
