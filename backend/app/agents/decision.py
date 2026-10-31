"""Decision agent: totals come from the scoring engine (never from the model); the model writes
the summary and, for a reject recommendation, the plain-language reason. Code builds everything
else and writes fallback text when the model fails its checks twice."""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.agents.explain import invented_numbers
from app.agents.guardrails import ID_PATTERN, check_cites, check_text
from app.agents.kyc import KycResult
from app.agents.report import (
    ACTION,
    AWAITING,
    Report,
    ReportFinding,
    citations_for,
    code_rejection_reason,
    code_summary,
    findings_from,
    group_sections,
    stage_rows,
    stop_text,
)
from app.agents.results import checks_for
from app.agents.risk import RiskResult
from app.agents.runtime import AgentContext, Asked, ask, prompt_text
from app.agents.state import Flag
from app.intake.masker import Masker
from app.rag.retrieve import PolicyRetriever
from app.rag.schemas import PolicyResult, RetrievedClause
from app.scoring.models import ScoreReport

MAX_FINDINGS_TO_MODEL = 12
SEVERITY_ORDER = {"hard_fail": 0, "cap": 1, "points_lost": 2, "note": 3}
_CAUSAL = re.compile(r"\b(because|due to|since|as a result)\b", re.I)


class Narrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1500)
    rejection_reason: str | None = Field(default=None, max_length=1500)


def version_info(conn: Connection, loan_type: str) -> dict[str, str]:
    rows = conn.execute(
        text(
            "SELECT loan_type, version FROM policy_documents WHERE active AND loan_type = ANY(:t)"
        ),
        {"t": ["common", loan_type]},
    ).all()
    return {r[0]: str(r[1]) for r in rows}


def _note_findings(flags: list[Flag]) -> list[ReportFinding]:
    return [
        ReportFinding(stage=f.stage, rule_id=f.rule_id, clause_id=None, role=f.role,
                      severity="note", message=f"{f.code}: {f.message}", source="intake")
        for f in flags
    ]  # fmt: skip


def collect_findings(
    score: ScoreReport, kyc: KycResult | None, risk: RiskResult | None,
    policy: PolicyResult | None, flags: list[Flag],
) -> list[ReportFinding]:  # fmt: skip
    """Rule findings (with the agents' explanations attached), then notes for the officer."""
    findings = findings_from(checks_for(score, ("documents",)))
    if kyc:
        findings += findings_from(kyc.checks)
    elif "kyc" in score.stages_run:
        findings += findings_from(checks_for(score, ("kyc",)))
    if risk:
        findings += findings_from(risk.checks)
    elif "risk" in score.stages_run:
        findings += findings_from(checks_for(score, ("income", "credit")))
    if "policy" in score.stages_run:
        by_rule = {f.rule_id: f.statement for f in (policy.fit_findings if policy else [])}
        for f in findings_from(checks_for(score, ("policy",))):
            f.explanation = by_rule.get(f.rule_id)
            findings.append(f)
    if risk:
        findings += [
            ReportFinding(stage="risk", rule_id=f.rule_id, clause_id=None, role=f.role, severity="note",
                          message=f"{f.code}: {f.message}", explanation=f.explanation, source="agent")
            for f in risk.flags
        ]  # fmt: skip
    findings += _note_findings(flags)
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    return findings


def _model_input(score: ScoreReport, findings: list[ReportFinding],
                 clauses: dict[str, RetrievedClause], stop: str | None) -> dict[str, Any]:  # fmt: skip
    top = [f for f in findings if f.severity != "note"][:MAX_FINDINGS_TO_MODEL]
    return {
        "recommendation": ACTION[score.recommendation],
        "band": score.band,
        "total_score": score.total_score,
        "indicative_score": score.indicative_score,
        "stage_scores": {
            k: f"{score.stage_scores[k]:g}/{score.stage_max[k]:g}"
            for k in score.stage_max
            if k in score.stage_scores
        },  # fmt: skip
        "stopped": stop,
        "findings": [
            {
                "rule_id": f.rule_id,
                "clause_id": f.clause_id,
                "severity": f.severity,
                "result": f.message,
            }
            for f in top
        ],  # fmt: skip
        "clauses": [{"clause_id": c.clause_id, "title": c.title} for c in clauses.values()],
        "needs_rejection_reason": score.recommendation == "recommend_reject",
    }


def check_narrative(
    out: Narrative, score: ScoreReport, known_ids: set[str], source: str
) -> list[str]:
    issues = check_text(
        out.summary
    )  # may state the code's score; invented numbers are caught below
    if "recommend" not in out.summary.lower():
        issues.append("the summary must use the word 'recommended'")
    if bad := invented_numbers(out.summary, source):
        issues.append(f"summary has numbers not in the data ({', '.join(bad)})")
    issues += check_cites(out.summary, known_ids, ID_PATTERN)
    reason = out.rejection_reason
    if score.recommendation == "recommend_reject":
        if not reason:
            issues.append("a reject recommendation needs a rejection_reason")
        else:
            issues += check_text(reason)
            issues += check_cites(reason, known_ids, ID_PATTERN)
            if not set(ID_PATTERN.findall(reason)) & known_ids:
                issues.append("the rejection_reason must cite a rule id and a clause id")
            if bad := invented_numbers(reason, source):
                issues.append(f"reason has numbers not in the data ({', '.join(bad)})")
    return issues


def needs_judge(summary: str, labels: list[str]) -> bool:
    """Code cannot tell whether a causal claim rests on a finding: no id and no stage named."""
    named = ID_PATTERN.search(summary) or any(lab.lower() in summary.lower() for lab in labels)
    return bool(_CAUSAL.search(summary)) and not named


async def run_decision(
    ctx: AgentContext, conn: Connection, score: ScoreReport, *, kyc: KycResult | None,
    risk: RiskResult | None, policy: PolicyResult | None, flags: list[Flag],
    applicants: list[dict[str, str]], documents: list[dict[str, Any]],
    models: dict[str, str | None], prompts: dict[str, int], unverified: list[dict[str, str]],
) -> tuple[Report, Asked[Narrative], dict[str, Any]]:  # fmt: skip
    findings = collect_findings(score, kyc, risk, policy, flags)
    ids = sorted({f.clause_id for f in findings if f.clause_id})
    retr = ctx.retriever_factory(conn) if ctx.retriever_factory else PolicyRetriever(conn)
    clauses = {c.clause_id: c for c in retr.by_ids(ids, score.loan_type)}
    stop = stop_text(score)
    data = _model_input(score, findings, clauses, stop)
    source = json.dumps(data, separators=(",", ":"), default=str)
    known = {f.rule_id for f in findings if f.rule_id} | set(clauses)
    body, version = prompt_text("decision")
    masker = Masker()

    def build(issues: list[str]) -> list[dict[str, str]]:
        user = f"<report>\n{masker.mask(source)}\n</report>"
        if issues:
            user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
                f"- {i}" for i in issues
            )
        return [{"role": "system", "content": body}, {"role": "user", "content": user}]

    asked = await ask(ctx, "decision", "decision", build, Narrative,
                      lambda o: check_narrative(o, score, known, source), max_tokens=2500)  # fmt: skip
    if asked.output:
        summary, reason, origin = (
            asked.output.summary.strip(),
            asked.output.rejection_reason,
            "model",
        )
        if AWAITING.lower() not in summary.lower():
            summary = f"{summary} {AWAITING}"
        if score.recommendation != "recommend_reject":
            reason = None
    else:
        summary, origin = code_summary(score, findings), "code"
        reason = code_rejection_reason(score, findings, clauses)

    policy_clauses = list(policy.clauses) if policy else []
    report = Report(
        case_id=score.case_id, loan_type=score.loan_type,
        status="stopped" if score.recommendation == "fix_required" else "awaiting_confirmation",
        recommendation=score.recommendation, recommendation_text=ACTION[score.recommendation],
        band=score.band, total_score=score.total_score, indicative_score=score.indicative_score,
        stage_scores=stage_rows(score), stopped_stage=score.stopped_stage, stop_class=score.stop_class,
        stop_text=stop, findings=findings, sections=group_sections(findings),
        citations=citations_for(findings, clauses, policy_clauses),
        precedents=list(policy.precedent_matches) if policy else [],
        rejection_reason=reason, summary=summary, summary_source=origin,
        flags=[f.model_dump() for f in flags], unverified=unverified, applicants=applicants,
        documents=documents,
        versions={"rules": score.rules_version, "rules_checksum": score.rules_checksum,
                  "policy": version_info(conn, score.loan_type), "prompts": {**prompts, "decision": version},
                  "models": models},
    )  # fmt: skip
    meta = {"needs_judge": asked.output is not None and needs_judge(
        summary, [r.label for r in report.stage_scores]), "known_ids": sorted(known), "version": version}  # fmt: skip
    return report, asked, meta
