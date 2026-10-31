"""Policy agent: retrieve the clauses that apply, explain the rule results, prove the claims.

Order of work: retrieve (search + rule-linked clauses) -> find precedents (refer band only) ->
one LLM call that writes fit findings -> code grounding check -> retry once with the issues ->
otherwise mark `unverified` and hand the officer code-written findings. The score is the policy
stage score from `app.scoring`; the model never touches numbers.
"""

import json
from pathlib import Path
from typing import Any

from litellm.router import Router
from sqlalchemy import Connection

from app.intake.masker import Masker
from app.rag.config import load_rag_config
from app.rag.grounding import GroundingIssue, GroundingReport, check_grounding
from app.rag.precedents import find_precedents
from app.rag.retrieve import PolicyRetriever, merge
from app.rag.schemas import (
    ClauseRef,
    FitFinding,
    FitFindingLLM,
    PolicyLLMOutput,
    PolicyResult,
    RetrievedClause,
)
from app.scoring.models import CaseInput, RuleOutcome, ScoreReport
from app.scoring.rules import RuleSet
from app.services.llm import LLMOutputError, complete

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "policy.md"
PROMPT_VERSION = 1

# plain-English topics for the RBI conduct clauses every loan type is checked against
CONDUCT_QUERIES = [
    "written reason for rejection given to the applicant",
    "key fact statement before sanction",
    "foreclosure and prepayment charges",
    "credit bureau data retention",
]


def _field_words(field: str) -> str:
    return field.replace("_", " ")


def build_queries(inp: CaseInput, score: ScoreReport, ruleset: RuleSet) -> list[str]:
    """Search queries from the case's rule results and loan type. No personal data."""
    rules = {r.rule_id: r for r in ruleset.rules}
    queries: list[str] = []
    for out in score.results:
        if out.passed and out.points_awarded >= out.points_max:
            continue
        rule = rules.get(out.rule_id)
        if rule is not None:
            queries.append(f"{inp.loan_type} loan {_field_words(rule.field)} requirement")
    if inp.loan_type == "education":
        queries.append("education loan moratorium and co-applicant")
    queries.extend(CONDUCT_QUERIES if score.band in ("reject", "refer") else CONDUCT_QUERIES[1:3])
    return list(dict.fromkeys(queries))


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v for k, v in evidence.items()
        if isinstance(v, bool | int | float) or (isinstance(v, str) and len(v) <= 40)
    }  # fmt: skip


def _result_lines(results: list[RuleOutcome]) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": r.rule_id, "clause_id": r.clause_id, "passed": r.passed,
            "points": f"{r.points_awarded:g}/{r.points_max:g}",
            "evidence": _compact_evidence(r.evidence),
        }
        for r in results
    ]  # fmt: skip


def build_messages(
    clauses: list[RetrievedClause], results: list[RuleOutcome], masker: Masker,
    issues: GroundingReport | None = None,
) -> list[dict[str, str]]:  # fmt: skip
    clause_block = "\n".join(f"[{c.clause_id}] {c.title}: {c.text}" for c in clauses)
    result_block = json.dumps(_result_lines(results), separators=(",", ":"))
    user = f"<clauses>\n{clause_block}\n</clauses>\n<results>\n{result_block}\n</results>"
    if issues is not None and not issues.ok:
        user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
            f"- {i}" for i in issues.issues
        )
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return [
        {"role": "system", "content": masker.mask(system)},
        {"role": "user", "content": masker.mask(user)},
    ]


def code_findings(results: list[RuleOutcome], retrieved: list[RetrievedClause]) -> list[FitFinding]:
    """Findings written by code from the rule results; each cites the rule's own clause."""
    by_id = {c.clause_id: c for c in retrieved}
    out: list[FitFinding] = []
    for r in results:
        clause = by_id.get(r.clause_id)
        if clause is None or (r.passed and r.points_awarded >= r.points_max):
            continue
        verdict = "failed" if not r.passed and r.points_awarded == 0 else "earned partial points"
        out.append(
            FitFinding(
                rule_id=r.rule_id, clause_ids=[r.clause_id], assessment="concern",
                statement=(
                    f"Rule {r.rule_id} {verdict} ({r.points_awarded:g} of {r.points_max:g} points)."
                ),
                quote=clause.text[:120], source="code",
            )
        )  # fmt: skip
    return out


async def run_policy_agent(
    conn: Connection,
    router: Router,
    inp: CaseInput,
    score: ScoreReport,
    ruleset: RuleSet,
    *,
    retriever: PolicyRetriever | None = None,
) -> PolicyResult:
    cfg = load_rag_config()
    retriever = retriever or PolicyRetriever(conn)
    searched = [retriever.search(q, inp.loan_type) for q in build_queries(inp, score, ruleset)]
    linked = retriever.by_ids([r.clause_id for r in score.results], inp.loan_type)
    retrieved = merge(*searched, linked)

    hard_failed = score.stop_class is not None
    precedents = find_precedents(
        conn, loan_type=inp.loan_type, band=score.band, rule_ids=score.failed_rule_ids,
        hard_failed=hard_failed, ruleset=ruleset,
    )  # fmt: skip

    policy_score = score.stage_scores.get("policy") if "policy" in score.stages_run else None
    prompt_clauses = [c for c in retrieved if c.relevance >= cfg.min_relevance]
    masker = Masker()
    findings: list[FitFindingLLM] = []
    report = GroundingReport()
    model, tokens_in, tokens_out = None, 0, 0
    for attempt in range(2):  # one retry
        messages = build_messages(
            prompt_clauses, score.results, masker, report if attempt else None
        )
        try:
            res = await complete(router, "policy", messages, PolicyLLMOutput, max_tokens=2500)
        except LLMOutputError as exc:
            report = GroundingReport([GroundingIssue("bad_output", str(exc))])
            continue
        except Exception as exc:  # provider outage after fallbacks: do not fail the case
            report = GroundingReport([GroundingIssue("llm_error", type(exc).__name__)])
            break
        model, tokens_in, tokens_out = (
            res.model,
            tokens_in + res.tokens_in,
            tokens_out + res.tokens_out,
        )
        findings = res.output.fit_findings
        report = check_grounding(findings, retrieved, inp.loan_type, ruleset, cfg.min_relevance)
        if report.ok:
            break

    verified = report.ok and bool(findings or not score.results)
    fit = (
        [FitFinding(**f.model_dump(), source="model") for f in findings]
        if verified
        else code_findings(score.results, retrieved)
    )
    return PolicyResult(
        clauses=[ClauseRef(clause_id=c.clause_id, text=c.text, relevance=round(c.relevance, 4))
                 for c in retrieved],
        precedent_matches=precedents,
        fit_findings=fit,
        score=policy_score,
        unverified=not verified,
        grounding_issues=[str(i) for i in report.issues],
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )  # fmt: skip
