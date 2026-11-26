"""Run the chat golden set (data/eval/chat_dev.yaml, TESTING.md).

    python -m app.chat.evaluate --split dev --no-llm      the CI gate: no database, no model
    python -m app.chat.evaluate --split dev               with the models (needs the keys)
    python -m app.chat.evaluate --split dev --write-baseline

Each case's material is rebuilt from its structured data: the rules engine, the answer key's
document fields and the policy files. `--no-llm` checks that every expected citation is in the
material the code would give the model, that "what if" and instructions are routed in code, and
that the answer checks accept a grounded answer and refuse planted bad ones. With models it
measures citation validity (must be 100%), expected-citation recall, refusal and "what if"
accuracy and the fixed-text rate on answerable questions.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from app.agents.report import ACTION, code_facts, findings_from, stage_rows, stop_text
from app.agents.results import checks_for
from app.chat import service
from app.chat.check import ChatAnswer, Citation, Sentence, check_answer
from app.chat.context import FieldRow, Material, Names, build_material, mask_question
from app.core.config import REPO_ROOT, get_settings
from app.rag.policy_loader import load_all
from app.rag.schemas import RetrievedClause
from app.scoring.engine import score_case
from app.scoring.models import CaseInput
from app.scoring.replay import CASES_DIR, load_case
from app.scoring.rules import RuleSet, load_rules

GOLDEN = REPO_ROOT / "data" / "eval" / "chat_dev.yaml"
BASELINES = REPO_ROOT / "docs" / "baselines"
SEARCH = 5


def golden(path: Path = GOLDEN) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = yaml.safe_load(path.read_text(encoding="utf-8"))["questions"]
    return items


def _words(value: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", value.lower())}


def policy_clauses(loan_type: str, cited: set[str], question: str) -> list[RetrievedClause]:
    """The cited clauses plus the closest by shared words (a stand-in for the reranked search,
    which needs the database and the local models)."""
    every = [
        RetrievedClause(clause_id=c.clause_id, title=c.title, text=c.text,
                        source_tag=c.source_tag, doc_loan_type=d.loan_type,
                        doc_version=d.version, relevance=1.0)
        for d in load_all() if d.loan_type in ("common", loan_type) for c in d.clauses
    ]  # fmt: skip
    asked = _words(question)
    near = sorted(every, key=lambda c: -len(asked & _words(f"{c.title} {c.text}")))[:SEARCH]
    keep = cited | {c.clause_id for c in near}
    return [c for c in every if c.clause_id in keep]


def case_material(inp: CaseInput, rs: RuleSet, app: dict[str, Any], question: str) -> Material:
    score = score_case(inp, rs)
    findings = findings_from(checks_for(score, ("documents", "kyc", "income", "credit", "policy")))
    cited = {f.clause_id for f in findings if f.clause_id}
    report = {
        "recommendation_text": ACTION[score.recommendation],
        "band": score.band,
        "total_score": score.total_score,
        "stage_scores": [r.model_dump() for r in stage_rows(score)],
        "stop_text": stop_text(score),
        "precedent_bonus": 0,
        "facts": code_facts(score),
        "findings": [f.model_dump() for f in findings],
    }
    fields = [
        FieldRow(d.role, d.doc_type, name, str(value))
        for d in inp.documents
        for name, value in d.fields.items()
        if value is not None
    ]
    people = app["applicants"]
    return build_material(
        report, score.results, fields, policy_clauses(inp.loan_type, cited, question),
        names=[a["full_name"] for a in people], addresses=[a["address"] for a in people],
    )  # fmt: skip


def material_of(item: dict[str, Any], rs: RuleSet) -> Material:
    folder = CASES_DIR / item["case"]
    inp, key = load_case(folder)
    if key["split"] != "dev":
        raise ValueError(f"{item['id']}: {item['case']} is not a dev case")
    app = json.loads((folder / "application.json").read_text())
    return case_material(inp, rs, app, item["question"])


def _known(material: Material) -> dict[str, set[str]]:
    return {"rule": material.rule_ids(), "clause": material.clause_ids(),
            "field": set(material.field_labels())}  # fmt: skip


def _answer(text: str, citations: list[dict[str, str]]) -> ChatAnswer:
    sentence = Sentence(text=text, citations=[Citation.model_validate(c) for c in citations])
    return ChatAnswer(answerable=True, sentences=[sentence])


def planted(good: list[dict[str, str]]) -> dict[str, ChatAnswer]:
    """Bad answers the checks must refuse."""
    plain = "The cited source shows this."
    return {
        "unknown clause": _answer(plain, [{"kind": "clause", "id": "ZZ-NONE-99"}]),
        "unknown rule": _answer(plain, [{"kind": "rule", "id": "CM-NONE-99"}]),
        "unknown field": _answer(plain, [{"kind": "field", "id": "payslip.nothing"}]),
        "invented number": _answer("The figure is 731.77 on this case.", good),
        "approval wording": _answer("This case is approved.", good),
    }


def check_offline(item: dict[str, Any], material: Material) -> list[str]:
    problems = []
    route = service.route(item["question"])
    if item["expect"] == "what_if" and route != "what_if":
        problems.append(f"should be routed to the what-if pointer, got {route}")
    if item["expect"] == "answer" and route is not None:
        problems.append(f"an answerable question was routed to {route}")
    if item["expect"] == "cannot" and route == "what_if":
        problems.append("an out-of-scope question was routed to the what-if pointer")
    if item["expect"] != "answer":
        return problems
    known = _known(material)
    for c in item["citations"]:
        if c["id"] not in known[c["kind"]]:
            problems.append(f"expected {c['kind']} {c['id']} is not in the material")
    if problems:
        return problems
    if issues := check_answer(_answer("The cited source shows this.", item["citations"]), material):
        problems.append(f"a grounded answer was refused: {issues}")
    for name, bad in planted(item["citations"]).items():
        if not check_answer(bad, material):
            problems.append(f"the checks accepted a bad answer ({name})")
    return problems


def offline(items: list[dict[str, Any]], rs: RuleSet) -> list[str]:
    return [f"{i['id']}: {p}" for i in items for p in check_offline(i, material_of(i, rs))]


class _Models:
    def __init__(self, router: Any) -> None:
        self.router = router

    def models(self) -> Any:
        return self.router


async def with_models(
    items: list[dict[str, Any]], rs: RuleSet, router: Any
) -> tuple[dict[str, float], list[str]]:  # fmt: skip
    valid = total = 0
    recall: list[float] = []
    refused: list[bool] = []
    what_if: list[bool] = []
    fixed: list[bool] = []
    lines = []
    for item in items:
        material = material_of(item, rs)
        question = mask_question(item["question"], Names([]))
        routed = service.route(question)
        turn = service.Turn(routed) if routed else await service.answer(
            _Models(router), material, question)  # fmt: skip
        cited = [c for s in turn.answer.sentences for c in s.citations] if turn.answer else []
        known = _known(material)
        total += len(cited)
        valid += sum(c.id in known[c.kind] for c in cited)
        if item["expect"] == "answer":
            wanted = {(c["kind"], c["id"]) for c in item["citations"]}
            recall.append(len(wanted & {(c.kind, c.id) for c in cited}) / len(wanted))
            fixed.append(turn.outcome != "answered")
        elif item["expect"] == "cannot":
            refused.append(turn.outcome in ("fixed_text", "refused"))
        else:
            what_if.append(turn.outcome == "what_if")
        lines.append(f"{item['id']} {item['expect']:8s} -> {turn.outcome}"
                     + (f"  ({turn.issues[0]})" if turn.issues else ""))  # fmt: skip

    def share(values: list[Any]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "questions": float(len(items)),
        "citation_validity": round(valid / total, 4) if total else 1.0,
        "expected_citation_recall": share(recall),
        "refusal_accuracy": share(refused),
        "what_if_accuracy": share(what_if),
        "fixed_text_rate_on_answerable": share(fixed),
    }, lines


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--split", choices=["dev"], default="dev")
    ap.add_argument("--no-llm", action="store_true", help="code checks only (the CI gate)")
    ap.add_argument("--write-baseline", action="store_true")
    args = ap.parse_args()
    rs, items = load_rules(), golden()
    if args.no_llm:
        problems = offline(items, rs)
        for p in problems:
            print(f"FAIL {p}")
        print(f"chat golden set ({args.split}, no model): {len(items)} questions, "
              f"{len(problems)} problem(s)")  # fmt: skip
        return 1 if problems else 0

    from app.services.llm import build_router  # noqa: PLC0415 - only with models

    metrics, lines = asyncio.run(with_models(items, rs, build_router(get_settings())))
    print("\n".join(lines))
    for name, value in metrics.items():
        print(f"  {name:32s} {value:.4f}")
    if args.write_baseline:
        path = BASELINES / "dev-chat.json"
        path.write_text(json.dumps({"rules_version": rs.version, "split": args.split,
                                    "metrics": metrics}, indent=2) + "\n")  # fmt: skip
        print(f"baseline written to {path.relative_to(REPO_ROOT)}")
    floors = json.loads((BASELINES / "thresholds.json").read_text()).get("chat", {})
    failed = [n for n, rule in floors.items() if metrics.get(n, 0.0) < rule.get("min", 0.0)]
    for name in failed:
        print(f"FAIL {name} is below its floor")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
