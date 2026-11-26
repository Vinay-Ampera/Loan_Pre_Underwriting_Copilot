"""Time figures with their units (EDGE_CASES E-133).

The invented-number check only asks whether the digits exist somewhere in the material, so "20
years" passed where the case says 20 months. Here a time figure is read with its unit, and months
and years are compared as months, in code: 24 months and "two years" are the same figure.

Two uses. The report's written text (`unit_slips`) is refused only when a figure appears in the
material in the other unit, so ordinary wording is never refused by mistake. A chat answer, whose
sentences cite their sources, must match a time figure of what it cites (`chat/check.py`).
"""

import re
from dataclasses import dataclass

_ONES = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
_TEENS = ("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
          "eighteen", "nineteen")  # fmt: skip
_TENS = ("twenty", "thirty", "forty", "fifty", "sixty")
WORDS = {w: i for i, w in enumerate((*_ONES, *_TEENS), start=1)}
WORDS |= {w: 10 * i for i, w in enumerate(_TENS, start=2)}
_WORD = (rf"(?:(?:{'|'.join(_TENS)})(?:[- ](?:{'|'.join(_ONES)}))?"
         rf"|{'|'.join(sorted((*_ONES, *_TEENS), key=len, reverse=True))})")  # fmt: skip
_NUM = r"\d+(?:\.\d+)?"

# in prose: "24 months", "two years", "a 30-year term"
_PROSE = re.compile(
    rf"(?<![\w.])(\d[\d,]*(?:\.\d+)?|{_WORD})(?:\s*-\s*|\s*)(years?|yrs?|months?|mths?)\b", re.I
)
# in data, where the field name carries the unit: "business vintage months: 20 (needed 24)"
_FIELD = re.compile(
    rf"(months|years)(?:[ _][a-z]+)*\"?\s*[:=]\s*\"?({_NUM})(?:\"?\s*\(needed\s+({_NUM}))?", re.I
)
# ages are in years: "age at maturity: 58 (needed 55)"
_AGE = re.compile(
    rf"age[ _]at[ _](?:application|maturity)\"?\s*[:=]\s*\"?({_NUM})"
    rf"(?:\"?\s*\(needed\s+({_NUM}))?",
    re.I,
)
_WINDOW = re.compile(r"[a-z][ _](\d+)m\b", re.I)  # "cheque nach returns 12m", "enquiries_6m"


@dataclass(frozen=True)
class Span:
    number: float
    unit: str  # months | years
    start: int = 0
    end: int = 0
    text: str = ""

    @property
    def months(self) -> float:
        return round(self.number * (12 if self.unit == "years" else 1), 4)


def _value(token: str) -> float:
    token = token.lower().replace(",", "")
    if token[0].isdigit():
        return float(token)
    return float(sum(WORDS[w] for w in re.split(r"[- ]", token)))


def said(text: str) -> list[Span]:
    """The time figures written in `text`, each with its unit and place."""
    return [
        Span(_value(m[1]), "years" if m[2].lower().startswith("y") else "months",
             m.start(), m.end(), m[0])
        for m in _PROSE.finditer(text)
    ]  # fmt: skip


def known(source: str) -> list[Span]:
    """Every time figure the material states, in prose or through a field name."""
    out = said(source)
    for m in _FIELD.finditer(source):
        out += [Span(float(v), m[1].lower()) for v in (m[2], m[3]) if v]
    for m in _AGE.finditer(source):
        out += [Span(float(v), "years") for v in (m[1], m[2]) if v]
    out += [Span(float(m[1]), "months") for m in _WINDOW.finditer(source)]
    return out


def unit_slips(text: str, source: str) -> list[str]:
    """Figures the material has in the other unit only ("20 years" for 20 months). A figure the
    material does not hold as a time at all is left to the invented-number check."""
    facts = known(source)
    stated = {f.months for f in facts}
    return [
        f"'{s.text}' has the wrong unit; copy the unit the data uses"
        for s in said(text)
        if s.months not in stated and any(f.number == s.number and f.unit != s.unit for f in facts)
    ]


def without(text: str, spans: list[Span]) -> str:
    """`text` with these figures removed (already checked, so not checked again as numbers)."""
    for s in sorted(spans, key=lambda s: -s.start):
        text = f"{text[: s.start]} {text[s.end :]}"
    return text
