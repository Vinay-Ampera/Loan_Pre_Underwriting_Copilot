"""The answer schema and the code checks every answer passes (AGENTS.md section 8, E-123).

Every sentence cites a rule of this case, a clause that was given or a field that was given; every
number is copied from the material; the wording rules hold; no raw identifier or name is present.
The model decides nothing and does no arithmetic.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.explain import invented_numbers
from app.agents.guardrails import ID_PATTERN, check_text
from app.chat.context import Material
from app.intake.masker import find_leaks

MAX_SENTENCES = 8
# beyond the shared wording guardrails: a promise or an instruction to decide
_PROMISE = re.compile(
    r"\b(eligible for|qualif(?:y|ies|ied) for"
    r"|(?:you )?(?:should|must|can) (?:approve|sanction|reject))\b",
    re.I,
)
_TOKEN = re.compile(r"<[A-Z_]+(?:_\d+)?>")
_KINDS = ("rule", "clause", "field")


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["rule", "clause", "field"]
    id: str = Field(min_length=1, max_length=120)


class Sentence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    citations: list[Citation] = Field(min_length=1, max_length=8)


class ChatAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answerable: bool
    sentences: list[Sentence] = Field(default_factory=list, max_length=MAX_SENTENCES)


def check_answer(answer: ChatAnswer, material: Material) -> list[str]:
    """Reasons the answer may not be shown. `answerable: false` is a final answer (the fixed text),
    not a failure."""
    if not answer.answerable:
        return []
    if not answer.sentences:
        return ["answerable is true but there is no sentence"]
    known = {"rule": material.rule_ids(), "clause": material.clause_ids(),
             "field": set(material.field_labels())}  # fmt: skip
    mentioned = known["rule"] | known["clause"]
    source = material.number_source()
    issues: list[str] = []
    for i, s in enumerate(answer.sentences, start=1):
        for c in s.citations:
            if c.id not in known[c.kind]:
                issues.append(f"sentence {i}: cites {c.kind} {c.id}, which was not given")
        if unknown := sorted(set(ID_PATTERN.findall(s.text)) - mentioned):
            issues.append(f"sentence {i}: names {', '.join(unknown)}, which was not given")
        plain = _TOKEN.sub(" ", ID_PATTERN.sub(" ", s.text))
        if bad := invented_numbers(plain, source):
            issues.append(f"sentence {i}: numbers not in the data ({', '.join(bad)})")
        issues += [f"sentence {i}: {p}" for p in check_text(s.text)]
        if m := _PROMISE.search(s.text):
            issues.append(f"sentence {i}: wording not allowed ({m.group(0).lower()})")
        if kinds := find_leaks(s.text):
            issues.append(f"sentence {i}: holds a raw identifier ({', '.join(kinds)})")
        if material.names.present_in(s.text):
            issues.append(f"sentence {i}: holds a person's name; say 'the applicant'")
    return issues


def citation_counts(answer: ChatAnswer | None) -> dict[str, int]:
    out = dict.fromkeys(_KINDS, 0)
    for s in answer.sentences if answer else []:
        for c in s.citations:
            out[c.kind] += 1
    return out
