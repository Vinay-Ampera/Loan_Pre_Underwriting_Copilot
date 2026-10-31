"""Output guardrails (AGENTS.md ground rules, SECURITY.md sections 3 and 8).

Every piece of model-written text passes `check_text` before it reaches a report. A failure goes
back to the model once with the reasons; a second failure means the stage is `unverified` and the
report uses text written by code. Nothing here can change a score: scores never come from a model.
"""

import re

from app.intake import injection

# Protected attributes are never inputs and never appear in a reason (SECURITY.md section 8).
PROTECTED = re.compile(
    r"\b(gender|male|female|man|woman|men|women|sex|religion|religious|caste|hindu|muslim|christian|"
    r"sikh|jain|buddhist|tribe|tribal|ethnic\w*|race|racial|transgender|marital status|pregnan\w*)\b",
    re.I,
)
# The system recommends; the officer decides. Words that claim a decision was taken are banned.
ACTION_WORDS = re.compile(r"\b(approved|rejected|sanctioned|declined|disbursed|denied)\b", re.I)
# A recommendation must read as one. These forms are fine: "recommend approval", "recommended".
SCORE_CLAIM = re.compile(r"\b(total|final|overall)\s+score\s+(is|of|=)\s*\d", re.I)


def check_text(text: str, *, allow_numbers: bool = True) -> list[str]:
    """Reasons `text` may not be used. Empty list = clean."""
    issues: list[str] = []
    if m := PROTECTED.search(text):
        issues.append(f"mentions a protected attribute ({m.group(0).lower()})")
    if m := ACTION_WORDS.search(text):
        issues.append(f"claims a decision was taken ({m.group(0).lower()}); use 'recommended'")
    # FORCE_OUTCOME is for inputs: in a report, "score ... approve band" is ordinary wording
    if [p for p in injection.scan(text) if p != "FORCE_OUTCOME"]:
        issues.append("contains instruction-like text")
    if not allow_numbers and SCORE_CLAIM.search(text):
        issues.append("states a score; scores come from the rules engine")
    return issues


def check_cites(text: str, known_ids: set[str], pattern: re.Pattern[str]) -> list[str]:
    """Every rule or clause id the text mentions must exist in this case."""
    unknown = sorted({m for m in pattern.findall(text) if m not in known_ids})
    return [f"cites {', '.join(unknown)}, which is not part of this case"] if unknown else []


ID_PATTERN = re.compile(r"\b(?:CM|PL|HL|ED|BL|VL)-[A-Z]+-\d{2}\b")
