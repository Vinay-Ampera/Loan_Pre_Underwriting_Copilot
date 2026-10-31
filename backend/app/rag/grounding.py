"""Self-RAG style grounding check, in code.

A finding is grounded when every clause it cites was retrieved for this case, comes from the
common policy or the case's own loan type, is on the active policy version, and (for search hits)
scored above the relevance threshold; and when its `quote` really appears in a cited clause.
A failed check is retried once by the agent, then the result is marked unverified.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.rag.schemas import FitFindingLLM, RetrievedClause
from app.scoring.rules import RuleSet


@dataclass(frozen=True)
class GroundingIssue:
    code: str  # not_retrieved | wrong_loan_type | inactive_version | low_relevance | no_citation
    #            | unsupported_quote | unknown_rule
    detail: str
    clause_id: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


@dataclass
class GroundingReport:
    issues: list[GroundingIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def check_grounding(
    findings: Iterable[FitFindingLLM],
    retrieved: list[RetrievedClause],
    loan_type: str,
    ruleset: RuleSet,
    min_relevance: float,
) -> GroundingReport:
    by_id = {c.clause_id: c for c in retrieved}
    case_rules = {r.rule_id for r in ruleset.rules_for(loan_type)}
    report = GroundingReport()
    for f in findings:
        label = f.rule_id or f.statement[:40]
        if not f.clause_ids:
            report.issues.append(
                GroundingIssue("no_citation", f"finding {label!r} cites no clause")
            )
        if f.rule_id is not None and f.rule_id not in case_rules:
            report.issues.append(
                GroundingIssue("unknown_rule", f"{f.rule_id} is not a rule for {loan_type}")
            )
        cited: list[RetrievedClause] = []
        for cid in f.clause_ids:
            c = by_id.get(cid)
            if c is None:
                report.issues.append(
                    GroundingIssue("not_retrieved", f"{cid} was not in the retrieved text", cid)
                )
                continue
            cited.append(c)
            if c.doc_loan_type not in ("common", loan_type):
                report.issues.append(
                    GroundingIssue("wrong_loan_type", f"{cid} is a {c.doc_loan_type} clause", cid)
                )
            if not c.active:
                report.issues.append(
                    GroundingIssue("inactive_version", f"{cid} is not active", cid)
                )
            if c.via == "search" and c.relevance < min_relevance:
                report.issues.append(
                    GroundingIssue("low_relevance", f"{cid} scored {c.relevance:.2f}", cid)
                )
        quote = _norm(f.quote)
        if cited and quote and not any(quote in _norm(c.text) for c in cited):
            report.issues.append(
                GroundingIssue("unsupported_quote", f"quote not found in {f.clause_ids}")
            )
    return report
