"""The only material the chat model gets, built in code and masked (AGENTS.md section 8,
SECURITY.md 4i): the report's result, rule results and code-derived facts, the extracted document
fields, and policy clauses in the versions the run used. Nothing else: no raw page text, no other
case, no precedent, no counter-offer box.

Names and addresses become tokens, identity numbers are hidden by field name before the masker's
pattern pass, and `complete` still refuses any prompt that holds a raw identifier.
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.agents.guardrails import ID_PATTERN
from app.agents.report import STAGE_LABEL
from app.agents.results import message_for
from app.intake.fields import ADDRESS_FIELDS, NAME_FIELDS
from app.intake.masker import Masker
from app.rag.retrieve import PolicyRetriever
from app.rag.schemas import RetrievedClause
from app.scoring.models import RuleOutcome
from app.scoring.rules import Rule, RuleSet

# values that identify a person or an account: never sent, whatever their shape
HIDDEN_FIELDS = frozenset(
    {"pan", "aadhaar", "account_no", "gstin", "udyam", "licence_no", "dob", "registration"}
)
SEARCH_CLAUSES = 5  # reranked clauses added for the question, beside the report's cited ones
MAX_VALUE = 200
_ABOUT_TERM = re.compile(r"\b(loan|tenure|term|repay\w*|emi|instalments?)\b", re.I)
_ABOUT_AGE = re.compile(r"\b(age|aged|maturity)\b", re.I)
_TOKEN = re.compile(r"<[A-Z_]+(?:_\d+)?>")
# A typed question is free text, and the shared masker does not join a number written in groups
# (in a document that would swallow figures that sit side by side). Here any run of 9 to 18
# digits, together or spaced, is hidden. Amounts written with commas are left alone.
_LONG_NUMBER = re.compile(r"(?<![0-9A-Za-z.])\+?\d(?:[ -]?\d){8,17}(?![0-9A-Za-z])")


class Names:
    """Replaces person names (whole, or any part of three letters or more) with tokens."""

    def __init__(self, names: Iterable[str]) -> None:
        self.full = [n.strip() for n in names if n and len(n.strip()) >= 3]

    def mask(self, value: str) -> str:
        for i, name in enumerate(self.full, start=1):
            token = f"<NAME_{i}>"
            value = re.sub(re.escape(name), token, value, flags=re.IGNORECASE)
            for part in name.split():
                if len(part) >= 3:
                    value = re.sub(rf"\b{re.escape(part)}\b", token, value, flags=re.IGNORECASE)
        return value

    def present_in(self, value: str) -> bool:
        return self.mask(value) != value


def mask_text(value: str, names: Names, addresses: Sequence[str] = ()) -> str:
    """Names, known addresses and every identifier pattern, as tokens."""
    for address in addresses:
        if len(address.strip()) >= 6:
            value = re.sub(re.escape(address.strip()), "<ADDRESS_1>", value, flags=re.IGNORECASE)
    return Masker().mask(names.mask(value))


def mask_question(question: str, names: Names, addresses: Sequence[str] = ()) -> str:
    return _LONG_NUMBER.sub("<ACCT_0>", mask_text(question, names, addresses))


@dataclass(frozen=True)
class FieldRow:
    role: str  # primary | co
    doc_type: str
    name: str
    value: str


@dataclass
class Material:
    result: dict[str, Any]
    rules: list[dict[str, Any]]
    fields: list[dict[str, str]]  # id, label, value
    clauses: list[dict[str, str]]  # clause_id, title, text
    names: Names
    addresses: list[str] = field(default_factory=list)

    def rule_ids(self) -> set[str]:
        return {r["rule_id"] for r in self.rules}

    def clause_ids(self) -> set[str]:
        return {c["clause_id"] for c in self.clauses}

    def field_labels(self) -> dict[str, str]:
        return {f["id"]: f["label"] for f in self.fields}

    def cited_text(self, sentence: str, citations: Iterable[tuple[str, str]]) -> str:
        """What a sentence's citations say, for checking its time figures: each cited rule with
        its clause, each cited clause with its rules and each cited field. The loan's own term
        counts only in a sentence about the loan, and the ages only in one about age: otherwise
        a 36-month tenure would let "a business three years old" through."""
        cited = set(citations)
        rule_ids = {i for k, i in cited if k == "rule"}
        clause_ids = {i for k, i in cited if k == "clause"}
        clause_ids |= {r["clause_id"] for r in self.rules if r["rule_id"] in rule_ids}
        rule_ids |= {r["rule_id"] for r in self.rules
                     if ("clause", r["clause_id"]) in cited}  # fmt: skip
        field_ids = {i for k, i in cited if k == "field"}
        parts = [f"{r['result']} | {r.get('needed') or ''}"
                 for r in self.rules if r["rule_id"] in rule_ids]  # fmt: skip
        parts += [c["text"] for c in self.clauses if c["clause_id"] in clause_ids]
        parts += [f"{f['id']}: {f['value']}" for f in self.fields if f["id"] in field_ids]
        facts = self.result.get("facts") or {}
        case = facts.get("case") or {}
        if _ABOUT_TERM.search(sentence):
            terms = {k: case[k] for k in ("tenure_months", "repayment_years") if k in case}
            parts.append(json.dumps(terms))
        if _ABOUT_AGE.search(sentence):
            ages = [{k: v for k, v in p.items() if k.startswith("age")}
                    for p in facts.get("persons") or []]  # fmt: skip
            parts.append(json.dumps(ages))
        return "\n".join(parts)

    def block(self) -> str:
        """The data given to the model, as one JSON document, already masked."""
        data = {
            "result": self.result,
            "rules": self.rules,
            "fields": [{"id": f["id"], "value": f["value"]} for f in self.fields],
            "clauses": self.clauses,
        }
        # `<` inside a value could close the data tag: the tag characters are only ours
        raw = json.dumps(data, separators=(",", ":"), default=str, ensure_ascii=False)
        masked = mask_text(raw, self.names, self.addresses)
        return masked.replace("</", "<\\/")

    def number_source(self) -> str:
        """What a number in an answer may be copied from: the material without ids and tokens,
        so the digits of "CM-INC-10" or "<NAME_1>" do not make "10" or "1" look like a figure."""
        return _TOKEN.sub(" ", ID_PATTERN.sub(" ", self.block()))


def _field_label(role: str, doc_type: str, name: str, n: int) -> str:
    words = f"{doc_type.replace('_', ' ').capitalize()} · {name.replace('_', ' ')}"
    if n > 1:
        words += f" ({n})"
    return f"Co-applicant · {words}" if role == "co" else words


def field_entries(rows: Sequence[FieldRow]) -> list[dict[str, str]]:
    """`payslip.employer`, `co.payslip.employer`, `payslip.net#2` for a second payslip."""
    seen: dict[str, int] = {}
    out = []
    for r in rows:
        name = re.sub(r"[^a-z0-9]+", "_", r.name.casefold()).strip("_")
        base = f"{'co.' if r.role == 'co' else ''}{r.doc_type}.{name}"
        n = seen[base] = seen.get(base, 0) + 1
        if name in HIDDEN_FIELDS:
            value = "<HIDDEN>"
        elif name in ADDRESS_FIELDS:
            value = "<ADDRESS_1>"
        elif name in NAME_FIELDS:
            value = "<PERSON_NAME>"
        else:
            value = str(r.value)[:MAX_VALUE]
        out.append({
            "id": base if n == 1 else f"{base}#{n}",
            "label": _field_label(r.role, r.doc_type, name, n),
            "value": value,
        })  # fmt: skip
    return out


_NEEDS = {
    "gte": "at least",
    "lte": "at most",
    "gt": "more than",
    "lt": "less than",
    "eq": "equal to",
}


def needed_text(rule: Rule) -> str | None:
    """The rule's own threshold in words with its unit ("at least 24 months"), so the model can
    quote it. Only numeric thresholds; commas keep a large amount from reading as an account."""
    if "months" in rule.field:
        unit = " months"
    elif "years" in rule.field or rule.field.startswith("age_at"):
        unit = " years"
    else:
        unit = ""

    def one(op: str | None, threshold: Any) -> str | None:
        if (
            op not in _NEEDS
            or isinstance(threshold, bool)
            or not isinstance(threshold, int | float)
        ):
            return None
        whole = threshold == int(threshold)
        return f"{_NEEDS[op]} {f'{int(threshold):,}' if whole else threshold}{unit}"

    if rule.tiers:
        steps = [(one(t.operator, t.threshold), t.points) for t in rule.tiers]
        return "; ".join(f"{words} earns {points:g}" for words, points in steps if words) or None
    return one(rule.operator, rule.threshold)


def rule_entry(r: RuleOutcome, rule: Rule | None = None) -> dict[str, Any]:
    entry = {
        "rule_id": r.rule_id,
        "stage": STAGE_LABEL.get(r.stage, r.stage),
        "passed": r.passed,
        "points": None if r.kind == "hard" else f"{r.points_awarded:g} of {r.points_max:g}",
        "result": message_for(r),
        "clause_id": r.clause_id,
        "person": r.role,
    }
    if rule is not None and (needed := needed_text(rule)):
        entry["needed"] = needed
    return entry


def result_entry(report: dict[str, Any]) -> dict[str, Any]:
    """The report's own result. Not the model-written summary and never the counter-offer box."""
    return {
        "recommendation": report.get("recommendation_text"),
        "band": report.get("band"),
        "total_score": report.get("total_score"),
        "stage_scores": [
            {"stage": s["label"], "score": s["score"], "out_of": s["max"]}
            for s in report.get("stage_scores") or []
        ],
        "stopped": report.get("stop_text"),
        "precedent_bonus": report.get("precedent_bonus") or None,
        "facts": report.get("facts") or {},
        "notes": [
            f.get("message") for f in report.get("findings") or [] if f.get("severity") == "note"
        ],  # fmt: skip
    }


def build_material(
    report: dict[str, Any], rules: Sequence[RuleOutcome], fields: Sequence[FieldRow],
    clauses: Sequence[RetrievedClause], *, names: Sequence[str], addresses: Sequence[str] = (),
    ruleset: RuleSet | None = None,
) -> Material:  # fmt: skip
    # names read from documents may be spelled differently from the form: hide those too
    seen_names = [f.value for f in fields if f.name in NAME_FIELDS]
    # thresholds only from the rules version the run used: a later file may say otherwise
    same = ruleset is not None and (report.get("versions") or {}).get("rules") == ruleset.version
    by_id = {r.rule_id: r for r in ruleset.rules} if ruleset is not None and same else {}
    return Material(
        result=result_entry(report),
        rules=[rule_entry(r, by_id.get(r.rule_id)) for r in rules],
        fields=field_entries(fields),
        clauses=[{"clause_id": c.clause_id, "title": c.title, "text": c.text} for c in clauses],
        names=Names(dict.fromkeys([*names, *seen_names])),
        addresses=[a for a in addresses if a],
    )


# --- from the database ----------------------------------------------------------------------
def applicants_of(form: dict[str, Any]) -> tuple[list[str], list[str]]:
    people = form.get("applicants") or []
    return ([str(a.get("full_name") or "") for a in people],
            [str(a.get("address") or "") for a in people])  # fmt: skip


def run_versions(conn: Connection, report: dict[str, Any]) -> dict[str, str] | None:
    """The policy documents the run used (E-91, E-125). None only for a report that recorded no
    version: then the active ones are read."""
    wanted: dict[str, str] = (report.get("versions") or {}).get("policy") or {}
    if not wanted:
        return None
    out = {}
    for loan_type, version in wanted.items():
        doc = conn.execute(
            text("""SELECT id FROM policy_documents
                    WHERE loan_type = :lt AND version = :v AND status <> 'draft'
                    ORDER BY published_at DESC NULLS LAST LIMIT 1"""),
            {"lt": loan_type, "v": version},
        ).scalar()  # fmt: skip
        if doc is not None:
            out[loan_type] = str(doc)
    return out


def _rules(conn: Connection, case_id: UUID) -> list[RuleOutcome]:
    rows = conn.execute(
        text("""SELECT r.rule_id, s.stage, r.kind, r.passed, r.points_awarded, r.points_max,
                       r.clause_id, r.evidence
                FROM rule_results r JOIN stage_runs s ON s.id = r.stage_run_id
                WHERE s.case_id = :c ORDER BY r.rule_id"""),
        {"c": case_id},
    ).all()
    out = []
    for r in rows:
        evidence = dict(r.evidence or {})
        role = evidence.pop("role", None)
        if "removed" in evidence:  # bureau data past its retention time stays gone
            evidence = {"field": "removed by retention", "value": None}
        out.append(RuleOutcome(
            rule_id=r.rule_id, stage=r.stage, kind=r.kind, passed=r.passed,
            points_awarded=float(r.points_awarded or 0), points_max=float(r.points_max or 0),
            clause_id=r.clause_id or "", role=role, evidence=evidence,
        ))  # fmt: skip
    return out


def _fields(conn: Connection, case_id: UUID) -> list[FieldRow]:
    """The stored **masked** values only; the local raw values are never read here."""
    rows = conn.execute(
        text("""SELECT COALESCE(d.role, 'primary') AS role, d.doc_type, f.field_name, f.value_masked
                FROM extracted_fields f JOIN documents d ON d.id = f.document_id
                WHERE d.case_id = :c AND d.status = 'accepted'
                ORDER BY role DESC, d.doc_type, d.uploaded_at, f.field_name"""),
        {"c": case_id},
    ).all()
    return [FieldRow(r.role, r.doc_type, r.field_name, r.value_masked or "") for r in rows]


def clauses_for(
    retriever: PolicyRetriever, report: dict[str, Any], rules: Sequence[RuleOutcome],
    loan_type: str, question: str,
) -> list[RetrievedClause]:  # fmt: skip
    """The clauses the report cites, then the best reranked ones for the question."""
    cited = {c["clause_id"] for c in report.get("citations") or []}
    cited |= {r.clause_id for r in rules if not r.passed and r.clause_id}
    found = retriever.by_ids(sorted(cited), loan_type)
    have = {c.clause_id for c in found}
    for c in retriever.search(question, loan_type, top_k=SEARCH_CLAUSES):
        if c.clause_id not in have:
            found.append(c)
            have.add(c.clause_id)
    return found


def load_material(
    conn: Connection, retriever: PolicyRetriever, *, case_id: UUID, loan_type: str,
    form: dict[str, Any], report: dict[str, Any], question: str, ruleset: RuleSet | None = None,
) -> Material:  # fmt: skip
    retriever.docs = run_versions(conn, report)
    rules = _rules(conn, case_id)
    names, addresses = applicants_of(form)
    return build_material(
        report, rules, _fields(conn, case_id),
        clauses_for(retriever, report, rules, loan_type, question),
        names=names, addresses=addresses, ruleset=ruleset,
    )  # fmt: skip
