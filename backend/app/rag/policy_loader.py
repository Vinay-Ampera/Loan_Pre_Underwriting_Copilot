"""Parse policy Markdown into clauses. The Stage 4 re-index command builds on this."""

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
    path: Path
    clauses: list[Clause]


class PolicyFormatError(ValueError):
    pass


def parse_policy(path: Path) -> PolicyDoc:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise PolicyFormatError(f"{path.name}: missing front matter")
    _, front, body = raw.split("---\n", 2)
    meta: dict[str, Any] = yaml.safe_load(front)
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
                raise PolicyFormatError(f"{path.name}: bad clause heading: {line!r}")
            flush()
            current = {"clause_id": m["id"], "source_tag": m["source"], "title": m["title"]}
            lines = []
        elif current is not None:
            lines.append(line)
    flush()
    return PolicyDoc(
        doc_id=meta["doc_id"], loan_type=meta["loan_type"], title=meta["title"],
        version=str(meta["version"]), effective_from=meta["effective_from"], path=path,
        clauses=clauses,
    )  # fmt: skip


def load_all(directory: Path = POLICY_DIR) -> list[PolicyDoc]:
    return [parse_policy(p) for p in sorted(directory.glob("*.md"))]
