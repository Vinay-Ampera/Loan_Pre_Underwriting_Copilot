"""LLM extraction pass (FR-7): masked text in, validated Pydantic out.

Runs only for fields the local pass could not fill (or for unrecognised documents). Every value the
model returns is un-tokenised locally, must occur in the source text, and is then checked by the
same code validators as any other field. The model never sees a raw identifier: `assert_masked`
stops the call otherwise.
"""

from pathlib import Path

from litellm.router import Router
from pydantic import BaseModel, Field

from app.intake import checks
from app.intake.fields import SPECS, parse_date, parse_money
from app.intake.masker import Masker, assert_masked
from app.intake.models import DocType, ExtractedField
from app.services.llm import LLMResult, complete

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "extraction.md"
MAX_CHARS = 6000  # keeps the prompt small for free-tier token limits
LLM_CONFIDENCE_CAP = 0.90  # a model's own confidence is never trusted above this
NOT_IN_SOURCE_PENALTY = 0.5
GENERIC_FIELDS = ["name", "employer", "monthly_salary", "date", "amount"]


class LLMField(BaseModel):
    name: str
    value: str | float | int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class LLMFields(BaseModel):
    fields: list[LLMField] = Field(default_factory=list)


def system_prompt() -> str:
    return PROMPT_PATH.read_text().split("-->", 1)[-1].strip()


def wanted_fields(doc_type: DocType, have: set[str]) -> list[str]:
    names = [s.name for s in SPECS.get(doc_type, ())] or GENERIC_FIELDS
    return [n for n in names if n not in have]


def build_messages(doc_type: DocType, masked_text: str, wanted: list[str]) -> list[dict[str, str]]:
    user = (f"document_type: {doc_type.value}\nwanted: {', '.join(wanted)}\n"
            f"<document>\n{masked_text[:MAX_CHARS]}\n</document>")  # fmt: skip
    return [{"role": "system", "content": system_prompt()}, {"role": "user", "content": user}]


def _coerce(name: str, value: str | float | int | None) -> str | float | int | None:
    if value is None or value == "":
        return None
    kind = next((s.kind for specs in SPECS.values() for s in specs if s.name == name), "text")
    if kind in ("money", "inline_money") and not isinstance(value, int | float):
        return parse_money(str(value))
    if kind == "date":
        d = parse_date(str(value))
        return d.isoformat() if d else str(value)
    if kind == "id":
        return str(value).replace(" ", "").upper()
    if kind == "digits":
        return "".join(ch for ch in str(value) if ch.isdigit())
    return value


async def llm_extract(router: Router, doc_type: DocType, raw_text: str, masker: Masker,
                      wanted: list[str], calls: "list[LLMResult[LLMFields]] | None" = None,
                      ) -> list[ExtractedField]:  # fmt: skip
    """Ask for `wanted` fields. `raw_text` is the local text; only its masked form is sent."""
    if not wanted:
        return []
    messages = build_messages(doc_type, masker.mask(raw_text), wanted)
    assert_masked(*(m["content"] for m in messages))
    result = await complete(router, "extraction", messages, LLMFields)
    if calls is not None:  # the pipeline logs tokens and cost for every call
        calls.append(result)
    out: list[ExtractedField] = []
    for f in result.output.fields:
        if f.name not in wanted or f.value is None:
            continue
        raw_value = f.value if isinstance(f.value, int | float) else masker.unmask(f.value)
        value = _coerce(f.name, raw_value)
        if value is None:
            continue
        conf = min(f.confidence, LLM_CONFIDENCE_CAP)
        if not checks.present_in_source(value, raw_text):
            conf *= NOT_IN_SOURCE_PENALTY  # not in the document: possibly invented
        out.append(
            ExtractedField(name=f.name, value=value, confidence=round(conf, 3), source="llm")
        )
    return out
