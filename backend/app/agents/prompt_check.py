"""Try a prompt on a small fixed synthetic sample before it is published (AI control).

The same schemas and guardrails the real agents use judge the reply: it must parse as the agent's
schema, pass `check_text` (no protected attributes, no "approved", no instruction-like text) and
the agent's own consistency checks (known keys only, no invented numbers, quotes copied from the
cited clause, clause ids that were given). One call, no retry: a prompt that needs the retry to
pass is a worse prompt. The sample holds no real data (nothing to mask), and `complete` still
refuses anything that looks like a raw identifier.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.agents.decision import Narrative
from app.agents.explain import Explanations, check_explanations, invented_numbers
from app.agents.guardrails import check_text
from app.agents.supervisor import Briefing
from app.chat.check import ChatAnswer, check_answer
from app.chat.context import FieldRow, build_material
from app.intake.llm_extract import LLMFields
from app.rag.schemas import PolicyLLMOutput, RetrievedClause
from app.scoring.models import RuleOutcome
from app.services.llm import LLMOutputError, complete

_KYC_ITEMS = [
    {"key": "CM-KYC-01", "check": "PAN format", "result": "passed", "detail": "PAN is in the right format"},
    {"key": "CM-KYC-03", "check": "Name on PAN and Aadhaar", "result": "failed",
     "detail": "The two names differ by more than the allowed tolerance"},
]  # fmt: skip
_RISK_ITEMS = [
    {"key": "CM-INC-02", "measure": "FOIR", "value": "38 percent", "limit": "50 percent", "result": "within the limit"},
    {"key": "CM-CRD-01", "measure": "Credit score", "value": "716", "limit": "700", "result": "meets the minimum"},
]  # fmt: skip
_CLAUSES = ("[HL-ELIG-03] Credit score: A credit score of 700 or above is required for a home loan.\n"
            "[CM-CNDT-02] Key facts: A key fact statement is given before sanction.")  # fmt: skip
_RESULTS = [{"rule_id": "HL-ELIG-03", "clause_id": "HL-ELIG-03", "passed": False, "points": "0/10",
             "evidence": {"credit_score": 655, "minimum": 700}}]  # fmt: skip
_REPORT = {"recommendation": "refer", "band": "refer", "total_score": 72, "stopped_stage": None,
           "stage_scores": {"kyc": 20, "documents": 12, "income": 20, "credit": 15, "policy": 5},
           "findings": [{"rule_id": "CM-INC-02", "text": "FOIR is 41 percent, within the limit of 50."}]}  # fmt: skip


@dataclass
class Sample:
    user: str
    schema: type[BaseModel]
    check: Callable[[Any], list[str]]


def _explain(items: list[dict[str, Any]], tag: str) -> Sample:
    source = json.dumps(items, separators=(",", ":"))
    keys = {i["key"] for i in items}
    return Sample(
        f"<{tag}>\n{source}\n</{tag}>", Explanations, lambda o: check_explanations(o, keys, source)
    )


def _briefing() -> Sample:
    block = ("loan_type: personal\napplicants: 1\n"
             "required_documents: aadhaar, bank_statement, pan_card, payslip")  # fmt: skip

    def check(o: Briefing) -> list[str]:
        out = check_text(o.notes, allow_numbers=False)
        if bad := invented_numbers(o.notes, block):
            out.append(f"numbers not in the data ({', '.join(bad)})")
        return out

    return Sample(f"<case>\n{block}\n</case>", Briefing, check)


def _narrative() -> Sample:
    source = json.dumps(_REPORT, separators=(",", ":"))

    def check(o: Narrative) -> list[str]:
        out = check_text(o.summary, allow_numbers=False)
        if "recommend" not in o.summary.lower():
            out.append("the summary does not use the word 'recommended'")
        if o.rejection_reason:
            out.append(
                "a rejection reason was written for a case that is not recommended for rejection"
            )
        if bad := invented_numbers(o.summary, source):
            out.append(f"numbers not in the data ({', '.join(bad)})")
        return out

    return Sample(f"<report>\n{source}\n</report>", Narrative, check)


def _policy() -> Sample:
    def check(o: Any) -> list[str]:
        out: list[str] = []
        known = {"HL-ELIG-03", "CM-CNDT-02"}
        for f in o.fit_findings:
            out += check_text(f.statement)
            if unknown := sorted(set(f.clause_ids) - known):
                out.append(f"cites {', '.join(unknown)}, which was not given")
            cited = " ".join(
                line
                for line in _CLAUSES.splitlines()
                if any(f"[{c}]" in line for c in f.clause_ids)
            )
            if f.quote.lower() not in cited.lower():
                out.append("a quote is not copied from a cited clause")
        if not o.fit_findings:
            out.append("no finding was written for the failed rule")
        return out

    results = json.dumps(_RESULTS, separators=(",", ":"))
    return Sample(
        f"<clauses>\n{_CLAUSES}\n</clauses>\n<results>\n{results}\n</results>",
        PolicyLLMOutput,
        check,
    )


def _extraction() -> Sample:
    wanted = ["employer", "net_pay"]
    text = (
        "PAYSLIP FOR <MONTH_1>\nEmployer: Orchid Textiles Ltd\nNet pay: 35,000\nEmployee: <NAME_1>"
    )

    def check(o: LLMFields) -> list[str]:
        return [f"{f.name} was not in the wanted list" for f in o.fields if f.name not in wanted]

    return Sample(f"document_type: payslip\nwanted: {', '.join(wanted)}\n<document>\n{text}\n</document>",
                  LLMFields, check)  # fmt: skip


def _case_question() -> Sample:
    report = {"recommendation_text": "Recommended: refer for manual review", "band": "refer",
              "total_score": 72, "facts": {"case": {"foir": 41.0, "net_monthly_income": 60000}},
              "stage_scores": [{"label": "Income and FOIR", "score": 18, "max": 30}]}  # fmt: skip
    rules = [RuleOutcome(rule_id="CM-INC-10", stage="income", kind="soft", passed=False,
                         points_awarded=6, points_max=12, clause_id="CM-INC-10",
                         evidence={"field": "foir", "value": 41.0})]  # fmt: skip
    clause = RetrievedClause(clause_id="CM-INC-10", title="Fixed obligations", source_tag="sample",
                             text="FOIR of 40 percent or under earns full points.",
                             doc_loan_type="common", doc_version="sample", relevance=1.0)  # fmt: skip
    material = build_material(report, rules, [FieldRow("primary", "payslip", "employer",
                              "Orchid Textiles Ltd")], [clause], names=[])  # fmt: skip

    def check(o: ChatAnswer) -> list[str]:
        out = check_answer(o, material)
        if not o.answerable:
            out.append("the sample question can be answered, but the reply said it cannot")
        return out

    return Sample(f"<case>\n{material.block()}\n</case>\n<question>\nWhy did Income and FOIR "
                  "lose points?\n</question>", ChatAnswer, check)  # fmt: skip


def sample_for(name: str) -> Sample:
    return {
        "supervisor": _briefing, "kyc": lambda: _explain(_KYC_ITEMS, "checks"),
        "risk": lambda: _explain(_RISK_ITEMS, "items"), "decision": _narrative,
        "policy": _policy, "extraction": _extraction, "case_assistant": _case_question,
    }[name]()  # fmt: skip


async def try_prompt(router: Any, name: str, system: str) -> dict[str, Any]:
    """Run one sample through the real model for this prompt's role. Never raises."""
    sample = sample_for(name)
    started = time.perf_counter()
    try:
        res = await complete(router, name, [{"role": "system", "content": system},
                                            {"role": "user", "content": sample.user}], sample.schema,
                             max_tokens=2500)  # fmt: skip
    except LLMOutputError:
        return {"ok": False, "issues": ["The reply was not valid JSON for the expected shape."],
                "model": None, "latency_ms": round((time.perf_counter() - started) * 1000), "preview": ""}  # fmt: skip
    except Exception as exc:  # noqa: BLE001 - a provider outage is a failed test, not a crash
        return {"ok": False, "issues": [f"The model could not be reached ({type(exc).__name__})."],
                "model": None, "latency_ms": round((time.perf_counter() - started) * 1000), "preview": ""}  # fmt: skip
    issues = sample.check(res.output)
    return {"ok": not issues, "issues": issues, "model": res.model, "latency_ms": res.latency_ms,
            "preview": res.output.model_dump_json()[:600]}  # fmt: skip
