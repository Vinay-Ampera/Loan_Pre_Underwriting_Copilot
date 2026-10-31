"""Plain-language explanations of results the code already decided (KYC and Risk agents).

The model gets a small masked list of items and returns one sentence for each. It cannot add a
result, change a number or score: unknown keys, invented numbers and banned wording all fail the
check, and a second failure leaves the item with the code-written message.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.guardrails import check_text
from app.agents.runtime import AgentContext, Asked, ask, prompt_text
from app.intake.masker import Masker

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    text: str = Field(min_length=1, max_length=400)


class Explanations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanations: list[Explanation]


def _canon(n: str) -> str:
    """85, 85.0 and 1,200 vs 1200 are the same number."""
    value = float(n.replace(",", ""))
    return str(int(value)) if value == int(value) else str(value)


def invented_numbers(text: str, source: str) -> list[str]:
    """Numbers in `text` that do not occur in the data the model was given."""
    known = {_canon(n) for n in _NUMBER.findall(source)}
    return sorted({n for n in _NUMBER.findall(text) if _canon(n) not in known})


def check_explanations(out: Explanations, keys: set[str], source: str) -> list[str]:
    issues: list[str] = []
    got = [e.key for e in out.explanations]
    if unknown := sorted(set(got) - keys):
        issues.append(f"unknown keys: {', '.join(unknown)}")
    if missing := sorted(keys - set(got)):
        issues.append(f"missing keys: {', '.join(missing)}")
    for e in out.explanations:
        issues += [f"{e.key}: {i}" for i in check_text(e.text, allow_numbers=False)]
        if bad := invented_numbers(e.text, source):
            issues.append(f"{e.key}: numbers not in the data ({', '.join(bad)})")
    return issues


async def explain(
    ctx: AgentContext, stage: str, role: str, items: list[dict[str, Any]], tag: str
) -> tuple[dict[str, str], Asked[Explanations]]:
    """{key: text} for the items the model explained, and the call outcome. Items need a `key`."""
    if not items:
        return {}, Asked(output=None, skipped=True)
    body, _ = prompt_text(role)
    masker = Masker()
    source = json.dumps(items, separators=(",", ":"), default=str)
    keys = {i["key"] for i in items}

    def build(issues: list[str]) -> list[dict[str, str]]:
        user = f"<{tag}>\n{source}\n</{tag}>"
        if issues:
            user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
                f"- {i}" for i in issues
            )
        return [{"role": "system", "content": body}, {"role": "user", "content": masker.mask(user)}]

    asked = await ask(
        ctx,
        stage,
        role,
        build,
        Explanations,
        lambda o: check_explanations(o, keys, source),
        max_tokens=1800,
    )
    texts = {e.key: e.text for e in asked.output.explanations} if asked.output else {}
    return texts, asked
