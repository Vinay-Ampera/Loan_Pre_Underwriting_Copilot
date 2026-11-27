"""One question: routing in code, then the model with its checks, then a fixed text when anything
fails (ARCHITECTURE.md 3g, E-122 to E-124). No database here; `api/chat.py` stores the turn.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from app.agents.runtime import AgentContext, ask, prompt_text
from app.agents.state import LLMCallRecord
from app.chat.check import ChatAnswer, check_answer
from app.chat.context import Material
from app.intake import injection

ROLE = "case_assistant"
STAGE = "chat"
MAX_QUESTION = 500
CANNOT = "I can't answer that from this case's documents and policy."
GREETING = (
    "Hello. Ask me about this case, for example why a stage lost points, what a document shows "
    "or what a policy rule says."
)
THANKS = "You're welcome. Ask me anything else about this case."
WHAT_IF = (
    "Chat does not work out other amounts or tenures. If a change would help, the report shows "
    "it under Other amounts or tenures."
)
OFF = (
    "Chat is off because the AI models are switched off. The report and its citations are "
    "still here."
)
LIMITED = "You have asked many questions in the last hour. Please try again a little later."
MASKED_NOTE = "Personal numbers in your question were hidden before it was sent."
FIXED = {"fixed_text": CANNOT, "refused": CANNOT, "what_if": WHAT_IF, "off": OFF,
         "limited": LIMITED}  # fmt: skip

_CHANGED = r"(?:amount|tenure|term|loan|emi|income|salary|rate|product)"
_WHAT_IF = re.compile(
    r"\bwhat\s+if\b|\bwhat\s+(?:would|will)\s+happen\b|\bwhat\s+happens\s+if\b"
    r"|\b(?:suppose|assume|assuming|imagine)\b"
    rf"|\bif\b[^.?!]{{0,60}}\b{_CHANGED}\b[^.?!]{{0,30}}\b(?:was|were|is|becomes?|changed?|"
    r"reduced|increased|lower(?:ed)?|higher|longer|shorter|raised|cut)\b"
    r"|\bif\b[^.?!]{0,40}\b(?:borrow|ask|apply|take|choose|pick)(?:s|ed)?\b"
    r"|\b(?:would|could|can|will)\b[^.?!]{0,40}\b(?:smaller|lower|higher|larger|bigger|longer|"
    rf"shorter|different|another)\s+(?:loan\s+)?{_CHANGED}\b"
    r"|\bhow\s+much\s+(?:can|could)\b[^.?!]{0,30}\b(?:borrow|get|be\s+lent)\b",
    re.I,
)
# "Why does it recommend approve?" is a question, not an order: the outcome-forcing pattern only
# counts when the text does not begin as a question
_ASKS = re.compile(
    r"^\s*(?:why|what|which|how|when|where|who|is|are|was|were|does|do|did|has|have)\b", re.I
)


# only a message that is nothing but a greeting: "hi, why did KYC lose points?" is a question
_GREETING = re.compile(
    r"^\W*(?:(?P<hello>h+i+|h+e+y+|hello+|hai|namaste|good\s+(?:morning|afternoon|evening))"
    r"(?:\s+(?:there|pramaan))?|(?P<thanks>(?:ok(?:ay)?\s+)?(?:thanks|thank\s+(?:you|u))))\W*$",
    re.I,
)


def small_talk(question: str) -> str | None:
    """The reply to a bare greeting or thanks, or None."""
    found = _GREETING.match(question)
    if not found:
        return None
    return GREETING if found["hello"] else THANKS


def fixed_reply(outcome: str, question: str) -> str | None:
    """The fixed text of a turn that has no answer. Read from the stored (masked) question."""
    if outcome == "fixed_text" and (reply := small_talk(question)):
        return reply
    return FIXED.get(outcome)


def route(question: str) -> str | None:
    """'refused' (reads like an instruction), 'what_if', 'fixed_text' (a greeting), or None to
    ask the model."""
    if small_talk(question):
        return "fixed_text"
    hits = injection.scan(question)
    if _ASKS.match(question):
        hits = [h for h in hits if h != "FORCE_OUTCOME"]
    if hits:
        return "refused"
    return "what_if" if _WHAT_IF.search(question) else None


class Models(Protocol):
    def models(self) -> Any: ...


@dataclass
class Turn:
    outcome: str  # answered | fixed_text | refused | what_if | off | limited
    answer: ChatAnswer | None = None
    calls: list[LLMCallRecord] = field(default_factory=list)
    retries: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def model(self) -> str | None:
        return self.calls[-1].model if self.calls else None


def messages_for(material: Material, question: str) -> Callable[[list[str]], list[dict[str, str]]]:
    """`question` is already masked. Both blocks are data; the locked prompt part says so."""
    system, _ = prompt_text(ROLE)
    case = material.block()
    safe = question.replace("</", "<\\/")

    def build(issues: list[str]) -> list[dict[str, str]]:
        user = f"<case>\n{case}\n</case>\n<question>\n{safe}\n</question>"
        if issues:
            user += "\nYour previous answer failed these checks. Fix them:\n" + "\n".join(
                f"- {i}" for i in issues
            )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    return build


async def answer(ctx: Models, material: Material, question: str) -> Turn:
    """Ask the model; one retry with the reasons; then the fixed text."""
    asked = await ask(
        cast(AgentContext, ctx), STAGE, ROLE, messages_for(material, question), ChatAnswer,
        lambda o: check_answer(o, material), max_tokens=1500,
    )  # fmt: skip
    if asked.skipped:
        return Turn("off")
    done = asked.output is not None and asked.output.answerable
    return Turn(
        "answered" if done else "fixed_text",
        answer=asked.output if done else None,
        calls=asked.calls, retries=asked.retries, issues=asked.issues,
    )  # fmt: skip


def stored_answer(turn: Turn, material: Material | None) -> dict[str, Any] | None:
    """What is kept with the turn: the sentences, and the text of each cited clause and the label
    of each cited field, so a chip can open them later."""
    if turn.answer is None or material is None:
        return None
    cited = [c for s in turn.answer.sentences for c in s.citations]
    clause_ids = {c.id for c in cited if c.kind == "clause"}
    field_ids = {c.id for c in cited if c.kind == "field"}
    labels = material.field_labels()
    return {
        "sentences": [s.model_dump() for s in turn.answer.sentences],
        "clauses": {c["clause_id"]: {"title": c["title"], "text": c["text"]}
                    for c in material.clauses if c["clause_id"] in clause_ids},
        "fields": {i: labels[i] for i in sorted(field_ids)},
    }  # fmt: skip
