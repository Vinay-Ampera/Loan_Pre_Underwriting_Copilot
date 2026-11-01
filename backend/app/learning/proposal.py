"""Turn an officer override into a proposed precedent.

Gate 1 was the officer (a written reason, two clicks). This module is gate 2: a rule-based check
in code. A proposal that would approve a case with a failed hard rule is stored as `held`; it never
reaches the admin queue and never enters retrieval. Everything else is stored as `pending` for the
admin (gate 3). The summary text is masked before it goes to a model, and its output is checked.
"""

import json
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.agents.guardrails import ID_PATTERN, check_cites, check_text
from app.agents.report import Report
from app.agents.runtime import AgentContext, Asked, ask
from app.intake.masker import Masker
from app.observability import metrics
from app.scoring.models import ScoreReport

SUMMARY_SYSTEM = (
    "You write a two-sentence note for a bank's precedent store. You are given the recommended "
    "outcome, the officer's final decision, the rule ids that failed and the officer's reason. "
    "State what made the case borderline and why the officer decided differently. Use only the "
    "given facts and ids. Say 'recommended', never 'approved' or 'rejected' for the system. "
    'Do not mention any person. Reply as JSON: {"summary": "..."}.'
)


class PrecedentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=20, max_length=600)


def hard_rule_breach(score: ScoreReport, final_decision: str) -> str | None:
    """Why this override may not become a precedent, or None. Approving over a hard rule is the
    case a precedent must never teach: a hard stop, or a failed hard rule of any kind."""
    if final_decision != "approve":
        return None
    if score.stop_class is not None:
        return f"the case stopped on a hard rule ({score.stopped_stage})"
    failed = sorted({r.rule_id for r in score.results if r.kind == "hard" and not r.passed})
    if failed or score.capped_to_refer:
        return f"hard rules failed: {', '.join(failed) or 'cap to refer'}"
    return None


def code_summary(
    score: ScoreReport, recommendation: str, final_decision: str, masked_reason: str
) -> str:
    rules = ", ".join(score.failed_rule_ids) or "none"
    return (
        f"{score.loan_type.capitalize()} case recommended as {recommendation}; the officer "
        f"decided {final_decision}. Rules involved: {rules}. Reason: {masked_reason.strip()}"
    )[:600]


async def summarise(
    ctx: AgentContext, score: ScoreReport, recommendation: str, final_decision: str, reason: str
) -> tuple[str, Asked[PrecedentSummary]]:
    masker = Masker()
    masked_reason = masker.mask(reason)
    fallback = code_summary(score, recommendation, final_decision, masked_reason)
    known = set(score.failed_rule_ids)
    facts = json.dumps(
        {"loan_type": score.loan_type, "recommended": recommendation,
         "final_decision": final_decision,
         "failed_rules": score.failed_rule_ids, "officer_reason": masked_reason},
        separators=(",", ":"),
    )  # fmt: skip

    def build(issues: list[str]) -> list[dict[str, str]]:
        user = f"<case>\n{masker.mask(facts)}\n</case>"
        if issues:
            user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
                f"- {i}" for i in issues
            )
        return [{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": user}]

    def check(out: PrecedentSummary) -> list[str]:
        return check_text(out.summary) + check_cites(out.summary, known, ID_PATTERN)

    asked = await ask(ctx, "precedent", "decision", build, PrecedentSummary, check, max_tokens=400)
    return (asked.output.summary.strip() if asked.output else fallback), asked


async def propose_precedent(
    ctx: AgentContext, case_uuid: UUID, *, officer_id: UUID | str, score: ScoreReport,
    report: Report, final_decision: str, reason: str,
) -> dict[str, str | None]:  # fmt: skip
    """Write the proposal. Returns {"id", "status", "held_reason"}; one proposal per case."""
    summary, _ = await summarise(ctx, score, report.recommendation, final_decision, reason)
    held = hard_rule_breach(score, final_decision)
    status = "held" if held else "pending"
    with ctx.engine.begin() as conn:
        existing = conn.execute(
            text(
                "SELECT id FROM precedents "
                "WHERE source_case_id = :c AND status IN ('pending','held')"
            ),
            {"c": case_uuid},
        ).first()
        if existing is not None:
            return {"id": str(existing[0]), "status": "exists", "held_reason": None}
        row = _insert(
            conn, case_uuid, officer_id, score, report, final_decision, reason, summary, status
        )
        conn.execute(
            text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, after)
                    VALUES (:u, :a, 'precedent', :e, CAST(:j AS jsonb))"""),
            {"u": officer_id, "a": "precedent_held" if held else "precedent_proposed",
             "e": str(row),
             "j": json.dumps({"case": str(case_uuid), "status": status, "held_reason": held})},
        )  # fmt: skip
    metrics.PRECEDENTS.labels(status).inc()
    return {"id": str(row), "status": status, "held_reason": held}


def _insert(
    conn: Connection, case: UUID, officer: UUID | str, score: ScoreReport, report: Report,
    final: str, reason: str, summary: str, status: str,
) -> UUID:  # fmt: skip
    new_id: UUID = conn.execute(
        text("""INSERT INTO precedents (source_case_id, status, loan_type, rule_ids, original_score,
                    original_recommendation, final_decision, officer_reason, report_summary,
                    proposed_by)
                VALUES (:c, :s, :lt, :rules, :score, :rec, :fin, :why, :sum, :u) RETURNING id"""),
        {"c": case, "s": status, "lt": score.loan_type, "rules": score.failed_rule_ids,
         "score": score.total_score, "rec": report.recommendation, "fin": final,
         "why": reason, "sum": summary, "u": officer},
    ).scalar_one()  # fmt: skip
    return new_id
