"""PII masker (SECURITY.md section 2).

Text is extracted and matched locally on raw values; only the masked text goes to an LLM. The token
map is reversible, lives in memory on this machine, and is never logged or serialised.

  PAN, Aadhaar, GSTIN, phone, email, account numbers   -> regex
  names and other known strings (from the form / rules) -> `add_known`
`assert_masked` is the guard every LLM call passes through; `safe` is for log lines.
"""

import re
from dataclasses import dataclass, field

# Order matters: longer / more specific patterns first so a GSTIN is not eaten as a PAN.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("GSTIN", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")),
    ("AADHAAR", re.compile(r"(?<!\d)[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?!\d)")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+91[ -]?|0)?[6-9]\d{9}(?!\d)")),
    ("ACCT", re.compile(r"(?<![\d,.])\d{9,18}(?![\d,]|\.\d)")),
)
# What must never reach an LLM: used by the guard and by the CI leak test.
_LEAK_PATTERNS = (_PATTERNS[1], _PATTERNS[2], _PATTERNS[3], _PATTERNS[0])
_TOKEN = re.compile(r"<([A-Z]+)_(\d+)>")


class MaskingError(Exception):
    """Raw PII was found where only masked text may go."""


@dataclass
class Masker:
    """One instance per case so tokens stay stable across that case's documents."""

    _forward: dict[tuple[str, str], str] = field(default_factory=dict)
    _reverse: dict[str, str] = field(default_factory=dict)
    _known: list[tuple[str, str]] = field(default_factory=list)  # (kind, raw), longest first
    _count: dict[str, int] = field(default_factory=dict)

    def _token(self, kind: str, raw: str) -> str:
        key = (kind, raw)
        if key not in self._forward:
            n = self._count.get(kind, 0) + 1
            self._count[kind] = n
            tok = f"<{kind}_{n}>"
            self._forward[key] = tok
            self._reverse[tok] = raw
        return self._forward[key]

    def add_known(self, kind: str, raw: str) -> None:
        """Register a value found locally (a name, an address) so it is tokenised wherever it appears."""
        raw = raw.strip()
        if len(raw) >= 3 and (kind, raw) not in self._known:
            self._known.append((kind, raw))
            self._known.sort(key=lambda kr: -len(kr[1]))

    def mask(self, text: str) -> str:
        for kind, raw in self._known:
            text = re.sub(re.escape(raw), lambda _m, k=kind, r=raw: self._token(k, r), text,  # type: ignore[misc]
                          flags=re.IGNORECASE)  # fmt: skip
        for kind, pattern in _PATTERNS:
            text = pattern.sub(lambda m, k=kind: self._token(k, m.group(0)), text)  # type: ignore[misc]
        return text

    def unmask(self, text: str) -> str:
        return _TOKEN.sub(lambda m: self._reverse.get(m.group(0), m.group(0)), text)

    def tokens(self) -> int:
        return len(self._reverse)


def find_leaks(text: str) -> list[str]:
    """Kinds of raw identifier still present in `text` (never the values themselves)."""
    return [kind for kind, pattern in _LEAK_PATTERNS if pattern.search(text)]


def assert_masked(*texts: str) -> None:
    """Guard for the LLM boundary. Raises without echoing the offending value."""
    for t in texts:
        kinds = find_leaks(t)
        if kinds:
            raise MaskingError(f"raw identifiers in LLM input: {', '.join(kinds)}")


def safe(text: str, limit: int = 200) -> str:
    """Log-safe form of any text: identifiers masked, length capped. Use this in log lines."""
    out = Masker().mask(text)
    return out if len(out) <= limit else out[:limit] + "..."
