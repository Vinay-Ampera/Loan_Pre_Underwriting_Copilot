"""Parse policy Markdown into clauses: from a file in data/policy or from text kept in the database.

A policy is YAML front matter (doc_id, loan_type, title, version, effective_from) followed by
clauses, each headed `## <CLAUSE-ID> | <public|RBI|sample> | <title>`. Text before the first
clause is an introduction and is not indexed. The format check the admin sees
(`app/rag/policy_admin.py`) reports every problem with a line number; this parser stops at the
first one.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.core.config import REPO_ROOT

POLICY_DIR = REPO_ROOT / "data" / "policy"
CLAUSE_HEADING = re.compile(
    r"^## (?P<id>(?:CM|PL|HL|ED|BL|VL)-[A-Z]+-\d{2}) \| "
    r"(?P<source>public|RBI|sample) \| (?P<title>.+)$"
)


@dataclass(frozen=True)
class Clause:
    clause_id: str
    source_tag: str
    title: str
    text: str


@dataclass(frozen=True)
class PolicyDoc:
    doc_id: str
    loan_type: str
    title: str
    version: str
    effective_from: date
    path: Path | None
    clauses: list[Clause]
    raw: str = ""

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.raw.encode("utf-8")).hexdigest()


class PolicyFormatError(ValueError):
    pass


def split_front_matter(raw: str) -> tuple[str, str] | None:
    """(front matter, body) or None when the text does not start with a `---` block."""
    if not raw.startswith("---\n"):
        return None
    parts = raw.split("---\n", 2)
    if len(parts) < 3:
        return None
    return parts[1], parts[2]


def parse_text(raw: str, name: str = "policy", path: Path | None = None) -> PolicyDoc:
    split = split_front_matter(raw)
    if split is None:
        raise PolicyFormatError(f"{name}: missing front matter")
    front, body = split
    try:
        meta: Any = yaml.safe_load(front)
    except yaml.YAMLError as exc:
        raise PolicyFormatError(f"{name}: front matter is not valid YAML") from exc
    if not isinstance(meta, dict):
        raise PolicyFormatError(f"{name}: front matter is not a list of fields")
    clauses: list[Clause] = []
    current: dict[str, str] | None = None
    lines: list[str] = []

    def flush() -> None:
        if current is not None:
            clauses.append(Clause(text=" ".join(" ".join(lines).split()), **current))

    for line in body.splitlines():
        if line.startswith("## "):
            m = CLAUSE_HEADING.match(line)
            if not m:
                raise PolicyFormatError(f"{name}: bad clause heading: {line!r}")
            flush()
            current = {"clause_id": m["id"], "source_tag": m["source"], "title": m["title"]}
            lines = []
        elif current is not None:
            lines.append(line)
    flush()
    try:
        return PolicyDoc(
            doc_id=str(meta["doc_id"]), loan_type=str(meta["loan_type"]), title=str(meta["title"]),
            version=str(meta["version"]), effective_from=_date(meta["effective_from"]), path=path,
            clauses=clauses, raw=raw,
        )  # fmt: skip
    except KeyError as exc:
        raise PolicyFormatError(f"{name}: front matter has no {exc.args[0]}") from exc


def _date(value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PolicyFormatError(f"effective_from {value!r} is not a date (YYYY-MM-DD)") from exc


def parse_policy(path: Path) -> PolicyDoc:
    return parse_text(path.read_text(encoding="utf-8"), path.name, path)


def load_all(directory: Path = POLICY_DIR) -> list[PolicyDoc]:
    return [parse_policy(p) for p in sorted(directory.glob("*.md"))]
