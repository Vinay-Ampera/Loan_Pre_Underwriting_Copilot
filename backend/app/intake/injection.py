"""Prompt-injection scan (SECURITY.md section 3). Document text is data, never instructions.

The scan never changes a score or blocks a case. It adds the flag `possible_prompt_injection`
so the officer sees it, and the text still goes to the model only as quoted data.
"""

import re

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "IGNORE_INSTRUCTIONS",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instructions?|rules?|polic(?:y|ies)|prompt)",
            re.I,
        ),
    ),
    (
        "ROLE_SWITCH",
        re.compile(
            r"\b(you are now|act as|system\s*:|assistant\s*,|admin mode|developer mode)", re.I
        ),
    ),
    (
        "REVEAL_PROMPT",
        re.compile(
            r"\b(reveal|print|show|output)\b.{0,30}\b(system prompt|instructions|prompt)", re.I
        ),
    ),
    (
        "FORCE_OUTCOME",
        re.compile(
            r"\b(mark|set|rate|score|output|recommend)\b.{0,40}\b(approved?|approval|score\s*(of|=|to)?\s*\d+|foir\s*(to|=)\s*\d|hard_fail|band)",
            re.I,
        ),
    ),
    ("JSON_PAYLOAD", re.compile(r'\{\s*"(band|hard_fail|score|decision|approved)"', re.I)),
)


def scan(text: str) -> list[str]:
    """Pattern ids that matched (never the matched text)."""
    return [pid for pid, pat in _PATTERNS if pat.search(text)]
