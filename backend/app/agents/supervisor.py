"""Supervisor: opens the case, reads the application, builds the required-document checklist from
the rules file and briefs the officer. It does not choose the route (the graph is fixed) and it
decides nothing about the case. Missing documents are filled in after Extraction classifies the
uploads (`CasePlan.missing`)."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.explain import invented_numbers
from app.agents.guardrails import check_text
from app.agents.runtime import AgentContext, ask, prompt_text
from app.agents.state import LLMCallRecord
from app.agents.submission import Submission
from app.intake.masker import Masker
from app.scoring.facts import applicable_requirements


class ChecklistItem(BaseModel):
    type: str
    applicant: str
    needed: int
    kyc: bool = False


class CasePlan(BaseModel):
    case_id: str
    loan_type: str
    applicants: list[dict[str, str]]
    checklist: list[ChecklistItem]
    missing: list[dict[str, Any]] = Field(default_factory=list)  # filled after extraction
    notes: str
    notes_source: str = "code"  # model | code
    prompt_version: int = 0
    model: str | None = None
    unverified: bool = False


class Briefing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=1, max_length=600)


def build_checklist(ctx: AgentContext, sub: Submission) -> list[ChecklistItem]:
    employment = {a["role"]: a["employment_type"] for a in sub.application["applicants"]}
    details = sub.application.get("loan_details", {})
    items: list[ChecklistItem] = []
    for req in applicable_requirements(ctx.ruleset, sub.loan_type, employment, details):
        roles = [r for r in ("primary", "co") if r in employment] if req.kyc else [req.applicant]
        for role in roles:
            if role not in employment:
                continue
            name = "/".join(req.any_of) if req.any_of else req.type
            items.append(
                ChecklistItem(type=name, applicant=role, needed=req.min_count, kyc=req.kyc)
            )
    return items


def code_notes(sub: Submission, checklist: list[ChecklistItem]) -> str:
    people = len(sub.application["applicants"])
    kinds = sorted({c.type for c in checklist})
    return (f"{sub.loan_type.capitalize()} loan with {people} applicant(s). "
            f"Required document types: {', '.join(kinds)}.")  # fmt: skip


async def run_supervisor(
    ctx: AgentContext, sub: Submission
) -> tuple[CasePlan, list[LLMCallRecord]]:
    checklist = build_checklist(ctx, sub)
    applicants = [{"role": a["role"], "employment_type": a["employment_type"]}
                  for a in sub.application["applicants"]]  # fmt: skip
    body, version = prompt_text("supervisor")
    block = (f"loan_type: {sub.loan_type}\napplicants: {len(applicants)}\n"
             f"required_documents: {', '.join(sorted({c.type for c in checklist}))}")  # fmt: skip
    masker = Masker()

    def build(issues: list[str]) -> list[dict[str, str]]:
        user = f"<case>\n{block}\n</case>"
        if issues:
            user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
                f"- {i}" for i in issues
            )
        return [{"role": "system", "content": body}, {"role": "user", "content": masker.mask(user)}]

    def check(out: Briefing) -> list[str]:
        issues = check_text(out.notes, allow_numbers=False)
        if bad := invented_numbers(out.notes, block):
            issues.append(f"numbers not in the data ({', '.join(bad)})")
        return issues

    asked = await ask(ctx, "supervisor", "supervisor", build, Briefing, check, max_tokens=1200)
    notes = asked.output.notes if asked.output else code_notes(sub, checklist)
    plan = CasePlan(
        case_id=sub.case_id, loan_type=sub.loan_type, applicants=applicants, checklist=checklist,
        notes=notes, notes_source="model" if asked.output else "code", prompt_version=version,
        model=asked.model, unverified=asked.unverified,
    )  # fmt: skip
    return plan, asked.calls
