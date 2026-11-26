"""The report: stage scores, findings with rule ids and clause links, citations, a rejection
reason, and the co-applicant sections. Everything numeric is copied from the `ScoreReport`; the
narrative (`summary`, `rejection_reason`) is the only model-written text and is optional.
Wording is "recommended"; the officer confirms every case.
"""

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.results import RuleCheck
from app.rag.schemas import ClauseRef, PrecedentMatch, RetrievedClause
from app.scoring.counter_offer import CounterOffer
from app.scoring.models import ScoreReport

ACTION = {
    "recommend_approve": "Recommended: approve",
    "refer": "Recommended: refer for manual review",
    "recommend_reject": "Recommended: reject",
    "fix_required": "Stopped: correction needed before this case can be scored",
}
AWAITING = "Awaiting your confirmation."
STAGE_LABEL = {"kyc": "KYC", "documents": "Documents", "income": "Income and FOIR",
               "credit": "Credit and behaviour", "policy": "Policy fit"}  # fmt: skip
# the scoring stage -> the pipeline stage that has to run for it to be scored
RAN_BY = {
    "documents": "extraction",
    "kyc": "kyc",
    "income": "risk",
    "credit": "risk",
    "policy": "policy",
}
STAGE_ORDER = ["extraction", "kyc", "risk", "policy"]


class StageScoreRow(BaseModel):
    stage: str
    label: str
    score: float | None
    max: float
    ran: bool


class BreakdownStage(BaseModel):
    stage: str
    label: str
    max: float
    earned: float
    lost: float
    level_after: float  # where the running total stands after this step


class ScoreBreakdown(BaseModel):
    """The numbers the score chart and the PDF's "Points lost" column draw (Stage 12 Part D).
    Display only: every figure is read from the stored stage scores, nothing is scored here."""

    start: float
    stages: list[BreakdownStage]
    bonus: float
    final: float
    band: str
    approve_min: float
    refer_min: float
    cap_rule_ids: list[str]  # rules that hold the case at refer; empty when none does


class ReportFinding(BaseModel):
    stage: str
    rule_id: str | None
    clause_id: str | None
    role: str | None = None
    severity: Literal["hard_fail", "cap", "points_lost", "note"]
    message: str
    explanation: str | None = None
    points_lost: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)
    source: Literal["rules", "agent", "intake"] = "rules"


class Report(BaseModel):
    case_id: str
    loan_type: str
    status: Literal["awaiting_confirmation", "stopped"]
    recommendation: str
    recommendation_text: str
    band: str | None
    total_score: float | None
    indicative_score: float | None
    stage_scores: list[StageScoreRow]
    stopped_stage: str | None
    stop_class: str | None
    stop_text: str | None
    findings: list[ReportFinding]
    sections: dict[str, list[int]]  # primary | co | case -> indexes into `findings`
    citations: list[ClauseRef]
    precedents: list[PrecedentMatch] = Field(default_factory=list)
    precedent_bonus: float = 0.0  # points added by an approved precedent (capped, refer band only)
    rejection_reason: str | None
    summary: str
    summary_source: Literal["model", "code"]
    flags: list[dict[str, Any]]
    unverified: list[dict[str, str]]
    applicants: list[dict[str, str]]
    documents: list[dict[str, Any]] = Field(default_factory=list)
    versions: dict[str, Any]
    awaiting: str = AWAITING
    # identity fields of the form that were read from the PAN and Aadhaar cards, per person
    # (Stage 10, Part B). A match against those same cards is not an independent check.
    identity_from_documents: dict[str, list[str]] = Field(default_factory=dict)
    # other amounts or tenures worked out in code (Stage 12 Part A); None when it would not help.
    # Added after the summary is written: never in a prompt, the summary or a customer message.
    counter_offer: CounterOffer | None = None
    # how the score was reached (Stage 12 Part D); None when a stage did not run
    score_breakdown: ScoreBreakdown | None = None


def points_lost(row: StageScoreRow) -> float | None:
    """What a stage lost; None for a stage that did not run."""
    return None if row.score is None else round(row.max - row.score, 2)


def cap_rules(findings: Iterable[tuple[str | None, str | None]]) -> list[str]:
    """The rule ids that cap the band, from (severity, rule id) pairs."""
    return sorted({rule_id for severity, rule_id in findings if severity == "cap" and rule_id})


def score_breakdown(
    rows: list[StageScoreRow], *, total: float | None, band: str | None, bonus: float,
    cap_rule_ids: list[str], bands: Mapping[Any, float],
) -> ScoreBreakdown | None:  # fmt: skip
    """Only for a scored case in which every stage ran; a stopped case has no chart (E-120)."""
    if total is None or band is None or not rows or any(r.score is None for r in rows):
        return None
    start = round(sum(r.max for r in rows), 2)
    level = start
    stages = []
    for r in rows:
        lost = points_lost(r) or 0.0
        level = round(level - lost, 2)
        stages.append(BreakdownStage(stage=r.stage, label=r.label, max=r.max,
                                     earned=round(r.max - lost, 2), lost=lost, level_after=level))  # fmt: skip
    return ScoreBreakdown(
        start=start, stages=stages, bonus=bonus, final=total, band=band,
        approve_min=bands["approve_min"], refer_min=bands["refer_min"], cap_rule_ids=cap_rule_ids,
    )  # fmt: skip


def with_breakdown(report: dict[str, Any], bands: Mapping[Any, float]) -> dict[str, Any]:
    """A report stored before the chart existed gets its breakdown on read, from its own stage
    scores and through the same function. Only the fields the chart draws are read, and the
    stored row is not changed."""
    if "score_breakdown" in report:
        return report
    built = None
    if report.get("total_score") is not None:
        built = score_breakdown(
            [StageScoreRow.model_validate(r) for r in report.get("stage_scores") or []],
            total=report["total_score"], band=report.get("band"),
            bonus=report.get("precedent_bonus") or 0.0,
            cap_rule_ids=cap_rules((f.get("severity"), f.get("rule_id"))
                                   for f in report.get("findings") or []),
            bands=bands,
        )  # fmt: skip
    return {**report, "score_breakdown": built.model_dump(mode="json") if built else None}


FROM_DOCUMENT_NOTE = "from document, not an independent check"
# which identity rules compare a form field with the card it may have been read from
_RULE_FIELD = {"CM-KYC-03": "full_name", "CM-KYC-11": "full_name", "CM-KYC-04": "dob",
               "CM-KYC-12": "address"}  # fmt: skip


def mark_from_documents(report: "Report", marks: dict[str, list[str]]) -> None:
    """Say, on the report, which form values came from the cards. Scoring is not touched: the
    other documents are still compared with the form, and a match against the source card is only
    labelled so the officer does not read it as proof."""
    marks = {role: sorted(fields) for role, fields in marks.items() if fields}
    report.identity_from_documents = marks
    for f in report.findings:
        fields = marks.get(f.role or "", [])
        wanted = _RULE_FIELD.get(f.rule_id or "")
        if f.rule_id == "CM-KYC-10" and fields or (wanted and wanted in fields):
            f.evidence = {**f.evidence, "source_note": FROM_DOCUMENT_NOTE}


def stage_rows(score: ScoreReport) -> list[StageScoreRow]:
    ran = set(score.stages_run)
    return [
        StageScoreRow(stage=s, label=STAGE_LABEL[s], max=score.stage_max[s],
                      ran=RAN_BY[s] in ran,
                      score=score.stage_scores[s] if RAN_BY[s] in ran else None)
        for s in STAGE_LABEL
    ]  # fmt: skip


def findings_from(checks: list[RuleCheck]) -> list[ReportFinding]:
    out: list[ReportFinding] = []
    for c in checks:
        if c.clean:
            continue
        sev = ("hard_fail" if c.on_fail == "stop" else "cap") if c.kind == "hard" else "points_lost"
        out.append(ReportFinding(
            stage=c.stage, rule_id=c.rule_id, clause_id=c.clause_id, role=c.role, severity=sev,
            message=c.message, explanation=c.explanation, points_lost=round(c.points_max - c.points, 2),
            evidence=c.evidence,
        ))  # fmt: skip
    return out


def stop_text(score: ScoreReport) -> str | None:
    if score.stopped_stage is None:
        return None
    label = {"extraction": "Documents", "kyc": "KYC", "risk": "Income and credit"}.get(
        score.stopped_stage, score.stopped_stage
    )
    later = [s for s in STAGE_ORDER if s not in score.stages_run]
    rest = f" The remaining stages were not run ({', '.join(later)})." if later else ""
    kind = ("a correction is needed; resume the case after fixing it" if score.stop_class == "fix"
            else "the case does not meet an eligibility rule")  # fmt: skip
    return f"Stopped at {label}: {kind}.{rest}"


def group_sections(findings: list[ReportFinding]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {"primary": [], "co": [], "case": []}
    for i, f in enumerate(findings):
        out[f.role if f.role in ("primary", "co") else "case"].append(i)
    return out


def code_summary(score: ScoreReport, findings: list[ReportFinding]) -> str:
    action = ACTION[score.recommendation]
    hard = [f for f in findings if f.severity == "hard_fail"]
    if score.stopped_stage:
        ids = ", ".join(sorted({f.rule_id for f in hard if f.rule_id}))
        return f"{action}. {stop_text(score)} Rules that stopped it: {ids}. {AWAITING}"
    cap = (
        " It is held at refer because of a rule that caps the band."
        if score.capped_to_refer
        else ""
    )
    return (f"{action}. Total score {score.total_score:g} of 100 ({score.band} band).{cap} "
            f"{len(findings)} item(s) need your attention. {AWAITING}")  # fmt: skip


def code_rejection_reason(
    score: ScoreReport, findings: list[ReportFinding], clauses: dict[str, RetrievedClause]
) -> str | None:
    """Plain-language reason, one line per cause, each with its rule and clause (RBI expects a
    written reason). Used when the model's text is missing or failed the guardrails."""
    if score.recommendation != "recommend_reject":
        return None
    causes = [f for f in findings if f.severity == "hard_fail"] or sorted(
        (f for f in findings if f.severity == "points_lost"), key=lambda f: -f.points_lost
    )[:4]
    lines = []
    for f in causes:
        c = clauses.get(f.clause_id or "")
        what = c.title if c else (f.message or "a policy requirement")
        lines.append(f"{what} (rule {f.rule_id}, clause {f.clause_id})")
    return ("We recommend not proceeding with this application for these reasons: "
            + "; ".join(lines) + ".")  # fmt: skip


def citations_for(
    findings: list[ReportFinding], clauses: dict[str, RetrievedClause], extra: list[ClauseRef]
) -> list[ClauseRef]:
    seen: dict[str, ClauseRef] = {c.clause_id: c for c in extra}
    for f in findings:
        if f.clause_id and f.clause_id in clauses and f.clause_id not in seen:
            c = clauses[f.clause_id]
            seen[f.clause_id] = ClauseRef(clause_id=c.clause_id, text=c.text, relevance=1.0)
    return list(seen.values())
