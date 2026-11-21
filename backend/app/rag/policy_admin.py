"""Policy text tools for the knowledge base (Stage 10c). Pure code: no database, no model.

convert_upload   a .md, .txt or .docx upload to Markdown text (Word files are read with the
                 standard library: the zip and its XML, no macros, no external entities)
autofix          formatting fixes only: clause headings into `## ID | source | title`, source
                 tag spelling, spaces and quotes, missing front-matter fields, the next version
                 label. It never changes the words or the numbers of a clause.
check            errors (block publishing), warnings (publishing needs a tick) and the fixes
                 auto-fix would make, each with a line number where there is one
diff_docs        clause-by-clause comparison of two versions, word by word for changed clauses
rule_drift       a changed clause that no longer mentions a number its linked rule uses:
                 scoring reads the rules file, so the text and the score would disagree
legacy_import    an old document with plain headings and no clause IDs: headings become
                 clauses, an existing clause ID is reused when the title matches, new IDs are
                 proposed; the admin checks every ID before saving the draft
clause edits     replace, add or remove one clause in the text, leaving the rest byte for byte
"""

import difflib
import io
import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree as ET  # noqa: N817 - the usual short name

import yaml
from rapidfuzz import fuzz

from app.intake import injection
from app.intake.masker import find_leaks
from app.rag.policy_loader import (
    CLAUSE_HEADING,
    Clause,
    PolicyDoc,
    PolicyFormatError,
    parse_text,
    split_front_matter,
)
from app.scoring.rules import Rule, RuleSet

LOAN_TYPES = ("common", "personal", "home", "education", "business", "vehicle")
PREFIX = {"common": "CM", "personal": "PL", "home": "HL", "education": "ED", "business": "BL",
          "vehicle": "VL"}  # fmt: skip
SOURCES = {"public": "public", "rbi": "RBI", "sample": "sample"}
TITLES = {
    "common": "Sample Bank Common Credit Policy",
    "personal": "Sample Bank Personal Loan Policy",
    "home": "Sample Bank Home Loan Policy",
    "education": "Sample Bank Education Loan Policy",
    "business": "Sample Bank Business Loan Policy",
    "vehicle": "Sample Bank Vehicle Loan Policy",
}
FRONT_FIELDS = ("doc_id", "loan_type", "title", "version", "effective_from")
VERSION_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})-(\d{1,3})$")
CLAUSE_ID_RE = re.compile(r"^(CM|PL|HL|ED|BL|VL)-[A-Z]+-\d{2}$")
MAX_UPLOAD_BYTES = 1_000_000
MAX_TEXT_CHARS = 200_000
MAX_DOCX_XML = 5_000_000
MAX_CLAUSES = 200
LONG_CLAUSE_WORDS = 250
SHORT_CLAUSE_WORDS = 5
FAR_FUTURE_DAYS = 400
RENAME_SIMILARITY = 85
TITLE_MATCH = 85
# FORCE_OUTCOME fires on ordinary policy wording ("a credit score of 700 ... approval"), so a
# policy is checked for the other patterns only (the same choice as agents/guardrails.check_text)
POLICY_INJECTION_SKIP = {"FORCE_OUTCOME"}

# a line that is meant to be a clause heading but is not in the exact form
_ID = r"(?P<id>(?:CM|PL|HL|ED|BL|VL)\s*[-–—]\s*[A-Za-z]+\s*[-–—]\s*\d{1,2})"
LOOSE_HEADING = re.compile(
    r"^\s*(?P<hashes>#{1,6})?\s*(?:clause\s+)?" + _ID + r"(?![\w-])(?P<rest>.*)$", re.I
)
SEP = "|:-–— "


class ConversionError(ValueError):
    pass


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    message: str
    line: int | None = None
    clause_id: str | None = None


@dataclass(frozen=True)
class Fix:
    line: int | None
    before: str
    after: str
    why: str


@dataclass
class CheckResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    fixed_text: str | None = None
    doc: PolicyDoc | None = None
    changes: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_json(self, today: date | None = None) -> dict[str, Any]:
        d = self.doc
        summary = None
        if d is not None:
            later = today is not None and d.effective_from > today
            summary = {"version": d.version, "title": d.title, "clauses": len(d.clauses),
                       "effective_from": d.effective_from.isoformat(),
                       "takes_effect": "scheduled" if later else "now"}  # fmt: skip
        return {
            "ok": self.ok,
            "errors": [asdict(i) for i in self.errors],
            "warnings": [asdict(i) for i in self.warnings],
            "fixes": [asdict(f) for f in self.fixes],
            "fixed_text": self.fixed_text,
            "summary": summary,
            "changes": self.changes,
        }


# --------------------------------------------------------------------------- version labels
def label_key(label: str) -> tuple[int, int, int, int]:
    m = VERSION_RE.match(label)
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4])) if m else (0, 0, 0, 0)


def next_label(taken: Iterable[str], today: date) -> str:
    """Today's label (`YYYY.MM.DD-N`), always sorting after every label already used."""
    keys = [label_key(t) for t in taken]
    latest = max(keys, default=(0, 0, 0, 0))
    same_day = [k[3] for k in keys if k[:3] == (today.year, today.month, today.day)]
    cand = (today.year, today.month, today.day, max(same_day, default=0) + 1)
    if cand <= latest:
        cand = (latest[0], latest[1], latest[2], latest[3] + 1)
    return f"{cand[0]:04d}.{cand[1]:02d}.{cand[2]:02d}-{cand[3]}"


# --------------------------------------------------------------------------- converting uploads
@dataclass(frozen=True)
class Converted:
    text: str
    notes: list[str]
    kind: Literal["md", "txt", "docx"]


def convert_upload(filename: str, data: bytes) -> Converted:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ConversionError("The file is larger than 1 MB. A policy is a short text document.")
    ext = Path(filename).suffix.lower()
    kind: Literal["md", "txt", "docx"]
    if ext in (".md", ".markdown"):
        text, notes = decode_text(data)
        kind = "md"
    elif ext == ".txt":
        text, notes = decode_text(data)
        kind = "txt"
        notes.append("Plain text is read line by line; a line that starts with a clause ID "
                     "(for example HL-ELIG-01) is taken as a clause heading.")  # fmt: skip
    elif ext == ".docx":
        text, notes = docx_to_markdown(data)
        kind = "docx"
    elif ext == ".doc":
        raise ConversionError(
            "Old Word .doc files cannot be read. Save it as .docx and upload it again."
        )
    else:
        raise ConversionError("Upload a .md, .txt or .docx file.")
    text = normalise_newlines(text)
    if not text.strip():
        raise ConversionError("The file has no text.")
    if len(text) > MAX_TEXT_CHARS:
        raise ConversionError("The text is longer than 200,000 characters.")
    return Converted(text, notes, kind)


def decode_text(data: bytes) -> tuple[str, list[str]]:
    if b"\x00" in data[:4096]:
        raise ConversionError("This does not look like a text file.")
    try:
        return data.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), [
            "The file was not UTF-8, so it was read as Windows-1252. Check symbols such as the "
            "rupee sign and accented letters."
        ]


def normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_to_markdown(data: bytes) -> tuple[str, list[str]]:
    """Paragraph text of a Word file; Title and Heading 1 become `#`, Heading 2 `##`, lower
    headings `###`, list items `- `, table rows `cell | cell`. Everything else is dropped."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ConversionError("This .docx file is damaged or is not a Word file.") from None
    with zf:
        try:
            info = zf.getinfo("word/document.xml")
        except KeyError:
            raise ConversionError("This .docx file has no document text.") from None
        if info.file_size > MAX_DOCX_XML:
            raise ConversionError("The text inside this Word file is too large.")
        xml = zf.read(info)
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ConversionError("This Word file contains markup that is not allowed.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ConversionError("The text of this Word file could not be read.") from None
    body = root.find(f"{_W}body")
    if body is None:
        raise ConversionError("This .docx file has no document text.")
    out: list[str] = []
    paragraphs = tables = 0
    for el in body:
        if el.tag == f"{_W}p":
            line = _docx_paragraph(el)
            if line:
                out.append(line)
                paragraphs += 1
        elif el.tag == f"{_W}tbl":
            tables += 1
            for tr in el.iter(f"{_W}tr"):
                cells = [" ".join(_docx_text(p) for p in tc.iter(f"{_W}p")).strip()
                         for tc in tr.iter(f"{_W}tc")]  # fmt: skip
                if any(cells):
                    out.append(" | ".join(cells))
    note = f"Read {paragraphs} paragraph(s)"
    note += f" and {tables} table(s)" if tables else ""
    note += " from the Word file. Formatting, images and comments were left out."
    return "\n\n".join(out) + "\n", [note]


def _docx_text(p: ET.Element) -> str:
    parts: list[str] = []
    for node in p.iter():
        if node.tag == f"{_W}t" and node.text:
            parts.append(node.text)
        elif node.tag in (f"{_W}tab", f"{_W}br", f"{_W}cr"):
            parts.append(" ")
    return "".join(parts)


def _docx_paragraph(p: ET.Element) -> str:
    text = " ".join(_docx_text(p).split())
    if not text:
        return ""
    style_el = p.find(f"{_W}pPr/{_W}pStyle")
    style = (style_el.get(f"{_W}val") or "") if style_el is not None else ""
    style = style.lower().replace(" ", "")
    if style in ("title", "heading1"):
        return f"# {text}"
    if style == "heading2":
        return f"## {text}"
    if style.startswith("heading"):
        return f"### {text}"
    if p.find(f"{_W}pPr/{_W}numPr") is not None:
        return f"- {text}"
    return text


# --------------------------------------------------------------------------- front matter
def render_front(meta: dict[str, Any]) -> str:
    """Front matter in the fixed order, then any extra fields as they were."""
    lines = ["---"]
    for k in FRONT_FIELDS:
        if k not in meta:
            continue
        v = meta[k]
        if k == "effective_from":
            lines.append(f"{k}: {v.isoformat() if isinstance(v, date) else v}")
        elif k in ("version", "title"):
            lines.append(f"{k}: {json.dumps(str(v), ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {v}")
    extra = {k: v for k, v in meta.items() if k not in FRONT_FIELDS}
    if extra:
        lines.append(yaml.safe_dump(extra, sort_keys=False, allow_unicode=True).rstrip())
    lines.append("---")
    return "\n".join(lines) + "\n"


def read_front(raw: str) -> tuple[dict[str, Any] | None, str, int]:
    """(fields or None, body, number of lines the front matter takes)."""
    split = split_front_matter(raw)
    if split is None:
        return None, raw, 0
    front, body = split
    try:
        meta = yaml.safe_load(front)
    except yaml.YAMLError:
        return None, body, front.count("\n") + 2
    return (meta if isinstance(meta, dict) else None), body, front.count("\n") + 2


def set_front(raw: str, **fields: Any) -> str:
    meta, body, _ = read_front(raw)
    if meta is None:
        return raw
    return render_front({**meta, **fields}) + body


def default_front(
    loan_type: str, taken: Iterable[str], today: date, title: str | None
) -> dict[str, Any]:
    return {"doc_id": f"policy-{loan_type}", "loan_type": loan_type,
            "title": title or TITLES[loan_type], "version": next_label(taken, today),
            "effective_from": today}  # fmt: skip


# --------------------------------------------------------------------------- auto-fix
def _norm_id(raw_id: str) -> str:
    parts = re.split(r"\s*[-–—]\s*", raw_id.strip())
    return f"{parts[0].upper()}-{parts[1].upper()}-{int(parts[2]):02d}"


def _split_rest(rest: str) -> tuple[str | None, str]:
    """(source tag or None, title) from what follows a clause ID on a heading line."""
    rest = rest.strip().lstrip(SEP).strip()
    if "|" in rest:
        parts = [p.strip() for p in rest.split("|")]
        if parts[0].lower() in SOURCES:
            return SOURCES[parts[0].lower()], " | ".join(p for p in parts[1:] if p).strip()
        return None, " | ".join(p for p in parts if p).strip()
    m = re.match(r"^(public|rbi|sample)\b\s*[:\-–—]?\s*(.*)$", rest, re.I)
    if m:
        return SOURCES[m[1].lower()], m[2].strip().strip(SEP).strip()
    m = re.match(r"^(.*?)\s*[(\[](public|rbi|sample)[)\]]\s*$", rest, re.I)
    if m:
        return SOURCES[m[2].lower()], m[1].strip().strip(SEP).strip()
    return None, rest.strip(SEP).strip()


def loose_heading(line: str) -> tuple[str, str | None, str] | None:
    """(clause id, source or None, title) when the line is meant as a clause heading."""
    m = LOOSE_HEADING.match(line)
    if not m:
        return None
    rest = m["rest"]
    if not m["hashes"] and not (rest.strip() == "" or rest.lstrip()[:1] in "|:-–—"):
        return None  # body text that happens to start with an ID
    src, title = _split_rest(rest)
    return _norm_id(m["id"]), src, title


_CHAR_FIXES = (
    ("“", '"', "curly quotes"), ("”", '"', "curly quotes"), ("‘", "'", "curly quotes"),
    ("’", "'", "curly quotes"), (" ", " ", "non-breaking spaces"), ("​", "", "hidden characters"),
    ("﻿", "", "hidden characters"), ("\t", "    ", "tabs"),
)  # fmt: skip


def autofix(
    text: str, loan_type: str, *, current: PolicyDoc | None, taken: Iterable[str], today: date
) -> tuple[str, list[Fix]]:
    """Formatting fixes only. Returns (fixed text, what was changed)."""
    taken = list(taken)
    fixes: list[Fix] = []
    out = normalise_newlines(text)
    counts: dict[str, int] = {}
    for bad, good, what in _CHAR_FIXES:
        n = out.count(bad)
        if n:
            out = out.replace(bad, good)
            counts[what] = counts.get(what, 0) + n
    lines = out.split("\n")
    trailing = sum(1 for ln in lines if ln != ln.rstrip())
    lines = [ln.rstrip() for ln in lines]
    for what, n in counts.items():
        fixes.append(Fix(None, "", "", f"Replaced {n} {what}."))
    if trailing:
        fixes.append(Fix(None, "", "", f"Removed spaces at the end of {trailing} line(s)."))

    current_src = {c.clause_id: c.source_tag for c in current.clauses} if current else {}
    meta, _, front_lines = read_front("\n".join(lines))
    start = front_lines if meta is not None else 0
    for i in range(start, len(lines)):
        ln = lines[i]
        if CLAUSE_HEADING.match(ln):
            continue
        got = loose_heading(ln)
        if got is None:
            continue
        cid, src, title = got
        why = "Clause heading put in the form ## ID | source | title."
        if src is None and cid in current_src:
            src = current_src[cid]
            why += " The source tag was taken from the version in force."
        if src is None or not title:
            continue  # cannot be completed by formatting alone; the check explains what is missing
        fixed = f"## {cid} | {src} | {title}"
        if fixed != ln:
            fixes.append(Fix(i + 1, ln, fixed, why))
            lines[i] = fixed
    out = "\n".join(lines)

    meta, body, _ = read_front(out)
    if split_front_matter(out) is None:
        first = next((ln[2:].strip() for ln in out.split("\n") if ln.startswith("# ")), None)
        new = default_front(loan_type, taken, today, current.title if current else first)
        out = render_front(new) + "\n" + out.lstrip("\n")
        fixes.append(Fix(1, "", "front matter", "Added the front matter (title, version label, "
                         "effective date) that every policy needs."))  # fmt: skip
    elif meta is not None:
        patch: dict[str, Any] = {}
        for k, v in default_front(
            loan_type, taken, today, current.title if current else None
        ).items():
            if k == "loan_type" and meta.get(k) not in (None, ""):
                continue  # a different loan type is an error, never fixed silently
            if meta.get(k) in (None, ""):
                patch[k] = v
        version = str(meta.get("version", ""))
        if version and (not VERSION_RE.match(version) or version in taken
                        or (taken and label_key(version) <= max(label_key(t) for t in taken))):  # fmt: skip
            patch["version"] = next_label(taken, today)
        if patch:
            for k, v in patch.items():
                before = "" if meta.get(k) in (None, "") else str(meta.get(k))
                after = v.isoformat() if isinstance(v, date) else str(v)
                why = ("Version label set to the next free label." if k == "version"
                       else f"Added the missing {k}.")  # fmt: skip
                fixes.append(Fix(None, f"{k}: {before}" if before else "", f"{k}: {after}", why))
            out = render_front({**meta, **patch}) + body
    if not out.endswith("\n"):
        out += "\n"
    return out, fixes


# --------------------------------------------------------------------------- checks
def prefix_of(clause_id: str) -> str:
    return clause_id.split("-", 1)[0]


def linked_rules(rules: RuleSet, clause_id: str) -> list[Rule]:
    return [r for r in rules.rules if r.policy_clause == clause_id]


def check(
    text: str, loan_type: str, *, rules: RuleSet, current: PolicyDoc | None,
    taken: Iterable[str], today: date,
) -> CheckResult:  # fmt: skip
    taken = [t for t in taken if t]
    res = CheckResult()
    err = res.errors

    def e(code: str, msg: str, line: int | None = None, cid: str | None = None) -> None:
        err.append(Issue("error", code, msg, line, cid))

    def w(code: str, msg: str, line: int | None = None, cid: str | None = None) -> None:
        res.warnings.append(Issue("warning", code, msg, line, cid))

    if loan_type not in LOAN_TYPES:
        e("LOAN_TYPE_WRONG", f"Unknown loan type {loan_type!r}.")
        return res
    if not text.strip():
        e("EMPTY", "The text is empty.")
        return res
    if len(text) > MAX_TEXT_CHARS:
        e("TOO_LARGE", "The text is longer than 200,000 characters.")
        return res
    text = normalise_newlines(text)
    fixed, fixes = autofix(text, loan_type, current=current, taken=taken, today=today)
    res.fixes = fixes
    res.fixed_text = fixed if fixed != text else None

    meta, body, front_lines = read_front(text)
    if split_front_matter(text) is None:
        e("FRONT_MATTER_MISSING", "The text must start with front matter between two --- lines "
          "(doc_id, loan_type, title, version, effective_from). Auto-fix can add it.", 1)  # fmt: skip
    elif meta is None:
        e("FRONT_MATTER_BAD", "The front matter is not valid. Each line must be `name: value`.", 1)
    else:
        _check_front(meta, loan_type, taken, e)

    lines = body.split("\n")
    seen: dict[str, int] = {}
    heading_line: dict[str, int] = {}
    in_clause: str | None = None
    words: dict[str, int] = {}
    for n, ln in enumerate(lines, start=front_lines + 1):
        if ln.startswith("## "):
            m = CLAUSE_HEADING.match(ln)
            if not m:
                got = loose_heading(ln)
                if got and got[1] is None:
                    e("HEADING_BAD", f"Clause {got[0]} has no source tag. Write it as "
                      f"`## {got[0]} | public | title` (public, RBI or sample).", n, got[0])  # fmt: skip
                elif got and not got[2]:
                    e(
                        "HEADING_BAD",
                        f"Clause {got[0]} has no title after the source tag.",
                        n,
                        got[0],
                    )
                elif got:
                    e("HEADING_BAD", "Clause heading is not in the form `## ID | source | title`. "
                      "Auto-fix can correct it.", n, got[0])  # fmt: skip
                else:
                    e("HEADING_BAD", "A `## ` heading must be a clause heading: "
                      "`## HL-ELIG-01 | public | Age and tenure`. Use `###` for other headings.", n)  # fmt: skip
                in_clause = None
                continue
            cid = m["id"]
            in_clause = cid
            if prefix_of(cid) != PREFIX[loan_type]:
                e("CLAUSE_PREFIX", f"Clause {cid} does not belong in the {loan_type} policy: its "
                  f"ID must start with {PREFIX[loan_type]}-.", n, cid)  # fmt: skip
            if cid in seen:
                e(
                    "CLAUSE_DUPLICATE",
                    f"Clause {cid} appears twice (lines {seen[cid]} and {n}).",
                    n,
                    cid,
                )
            else:
                seen[cid] = n
                heading_line[cid] = n
                words[cid] = 0
            continue
        if loose_heading(ln) is not None and not ln.startswith("## "):
            e("HEADING_BAD", "This line looks like a clause heading but is not one, so its text "
              "would join the clause above. Write it as `## ID | source | title`.", n)  # fmt: skip
            continue
        if in_clause is not None and in_clause in words:
            words[in_clause] += len(ln.split())
        for pid in injection.scan(ln):
            if pid not in POLICY_INJECTION_SKIP:
                e("INJECTION", "This line reads like an instruction to the AI model "
                  f"({pid.replace('_', ' ').lower()}). Policy text must only state policy.", n, in_clause)  # fmt: skip
                break
        leaks = find_leaks(ln)
        if leaks:
            e("PERSONAL_DATA", f"This line holds what looks like personal data ({', '.join(leaks)}). "
              "A policy never names a person or an account.", n, in_clause)  # fmt: skip
    for cid, n in words.items():
        if n == 0:
            e("CLAUSE_EMPTY", f"Clause {cid} has no text.", heading_line[cid], cid)
    if not seen and not any(i.code == "HEADING_BAD" for i in err):
        e("NO_CLAUSES", "No clauses were found. Each clause starts with `## ID | source | title`. "
          "For an old document without clause IDs, use the old-format import.")  # fmt: skip
    if len(seen) > MAX_CLAUSES:
        e("TOO_MANY_CLAUSES", f"A policy may have at most {MAX_CLAUSES} clauses.")
    if err:
        return res

    try:
        doc = parse_text(text)
    except PolicyFormatError as exc:
        e("PARSE", str(exc))
        return res
    res.doc = doc
    ids = {c.clause_id for c in doc.clauses}
    for cid in sorted(
        {r.policy_clause for r in rules.rules if prefix_of(r.policy_clause) == PREFIX[loan_type]}
        - ids
    ):
        rids = ", ".join(r.rule_id for r in linked_rules(rules, cid))
        e("RULE_CLAUSE_MISSING", f"Clause {cid} is missing, but rules {rids} cite it. Rules live in "
          "the rules file: keep the clause (its text may change), or change the rules file first.",
          None, cid)  # fmt: skip

    for c in doc.clauses:
        n = len(c.text.split())
        if n > LONG_CLAUSE_WORDS:
            w("LONG_CLAUSE", f"Clause {c.clause_id} has {n} words. Clauses over {LONG_CLAUSE_WORDS} "
              "words are found less reliably by search; consider splitting it.", heading_line.get(c.clause_id), c.clause_id)  # fmt: skip
        elif n < SHORT_CLAUSE_WORDS:
            w(
                "SHORT_CLAUSE",
                f"Clause {c.clause_id} has only {n} word(s).",
                heading_line.get(c.clause_id),
                c.clause_id,
            )
    if doc.effective_from < today:
        w("DATE_PAST", f"The effective date {doc.effective_from} is in the past. The version takes "
          "effect when it is published; the date is kept as written.")  # fmt: skip
    if doc.effective_from > today + timedelta(days=FAR_FUTURE_DAYS):
        w("DATE_FAR", f"The effective date {doc.effective_from} is more than a year away.")
    if current is not None:
        res.changes = diff_docs(current, doc)
        ch = res.changes
        if not (ch["added"] or ch["removed"] or ch["changed"]):
            w("NO_CHANGE", "No clause changed compared with the version in force.")
        moved = len(ch["changed"]) + len(ch["removed"])
        if current.clauses and moved * 2 > len(current.clauses):
            w("BIG_CHANGE", f"{moved} of {len(current.clauses)} clauses change or go. Run the "
              "retrieval check and read the comparison before publishing.")  # fmt: skip
        old = {c.clause_id: c for c in current.clauses}
        new = {c.clause_id: c for c in doc.clauses}
        for cid in ch["changed"]:
            if old[cid].source_tag != new[cid].source_tag:
                w("SOURCE_CHANGED", f"Clause {cid} source tag changes from {old[cid].source_tag} "
                  f"to {new[cid].source_tag}.", heading_line.get(cid), cid)  # fmt: skip
        for gone in ch["removed"]:
            for added in ch["added"]:
                if fuzz.token_set_ratio(old[gone].text, new[added].text) >= RENAME_SIMILARITY:
                    w("RENAMED", f"Clause {added} looks like {gone} under a new ID. Reports and "
                      "rules refer to clause IDs; keep the old ID if it is the same clause.",
                      heading_line.get(added), added)  # fmt: skip
        res.warnings.extend(rule_drift(current, doc, rules, heading_line))
    return res


def _check_front(meta: dict[str, Any], loan_type: str, taken: list[str], e: Any) -> None:
    for k in FRONT_FIELDS:
        if meta.get(k) in (None, ""):
            e("FIELD_MISSING", f"The front matter has no {k}. Auto-fix can add it.", 1)
    lt = meta.get("loan_type")
    if lt not in (None, "") and lt != loan_type:
        e("LOAN_TYPE_WRONG", f"The front matter says loan_type {lt!r}, but this is the "
          f"{loan_type} policy. Upload it under the right loan type.", 1)  # fmt: skip
    version = meta.get("version")
    if version not in (None, ""):
        v = str(version)
        if not VERSION_RE.match(v):
            e("VERSION_FORMAT", f"The version label {v!r} must look like 2027.04.01-1 "
              "(date, dash, number).", 1)  # fmt: skip
        elif v in taken:
            e("VERSION_TAKEN", f"Version {v} already exists. Each change needs a new label.", 1)
        elif taken and label_key(v) <= max(label_key(t) for t in taken):
            latest = max(taken, key=label_key)
            e("VERSION_OLDER", f"Version {v} must sort after the latest label, {latest}.", 1)
    eff = meta.get("effective_from")
    if eff not in (None, "") and not isinstance(eff, date):
        try:
            date.fromisoformat(str(eff))
        except ValueError:
            e("DATE_BAD", f"effective_from {eff!r} is not a date (YYYY-MM-DD).", 1)


# --------------------------------------------------------------------------- comparison
def word_diff(a: str, b: str) -> list[dict[str, str]]:
    aw, bw = a.split(), b.split()
    out: list[dict[str, str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"k": "same", "t": " ".join(aw[i1:i2])})
            continue
        if i2 > i1:
            out.append({"k": "del", "t": " ".join(aw[i1:i2])})
        if j2 > j1:
            out.append({"k": "add", "t": " ".join(bw[j1:j2])})
    return out


def _clause_json(c: Clause) -> dict[str, str]:
    return {"clause_id": c.clause_id, "title": c.title, "source_tag": c.source_tag, "text": c.text}


def diff_docs(old: PolicyDoc | None, new: PolicyDoc) -> dict[str, Any]:
    o = {c.clause_id: c for c in old.clauses} if old else {}
    n = {c.clause_id: c for c in new.clauses}
    added = [cid for cid in n if cid not in o]
    removed = [cid for cid in o if cid not in n]
    changed = [cid for cid in n if cid in o
               and (o[cid].text, o[cid].title, o[cid].source_tag) != (n[cid].text, n[cid].title, n[cid].source_tag)]  # fmt: skip
    meta = {}
    if old is not None:
        for k in ("title", "version", "effective_from"):
            before, after = getattr(old, k), getattr(new, k)
            if before != after:
                meta[k] = {"before": str(before), "after": str(after)}
    return {
        "from": old.version if old else None, "to": new.version,
        "added": added, "removed": removed, "changed": changed,
        "unchanged": len(n) - len(added) - len(changed),
        "meta": meta,
        "details": {
            "added": [_clause_json(n[c]) for c in added],
            "removed": [_clause_json(o[c]) for c in removed],
            "changed": [{"clause_id": c, "title_before": o[c].title, "title_after": n[c].title,
                         "source_before": o[c].source_tag, "source_after": n[c].source_tag,
                         "words": word_diff(o[c].text, n[c].text)} for c in changed],
        },
    }  # fmt: skip


# --------------------------------------------------------------------------- rule numbers
_NUM = re.compile(
    r"(?<![\w.\-])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s*"
    r"(lakhs?|lacs?|crores?|cr\b|per\s?cent|percent|%|years?|months?)?",
    re.I,
)


def numbers_in(text: str) -> set[float]:
    """Every number in the text, with lakh, crore, percent and years read in the usual ways."""
    out: set[float] = set()
    for m in _NUM.finditer(text):
        v = float(m[1].replace(",", ""))
        unit = (m[2] or "").lower().replace(" ", "")
        if unit.startswith(("lakh", "lac")):
            v *= 100_000
        elif unit.startswith(("crore", "cr")):
            v *= 10_000_000
        out.add(v)
        if unit in ("percent", "%"):
            out.add(v / 100)
        if unit.startswith("year"):
            out.add(v * 12)
    return out


def _number_strings(text: str) -> list[str]:
    return [m.group(0).strip() for m in _NUM.finditer(text)]


def _mentions(value: float, nums: set[float]) -> bool:
    return any(abs(value - n) <= 1e-9 * max(1.0, abs(value)) for n in nums)


def rule_values(rule: Rule) -> list[float]:
    vals: list[float] = []
    if isinstance(rule.threshold, int | float) and not isinstance(rule.threshold, bool):
        vals.append(float(rule.threshold))
    for t in rule.tiers or []:
        if isinstance(t.threshold, int | float) and not isinstance(t.threshold, bool):
            vals.append(float(t.threshold))
    return vals


def _fmt(v: float) -> str:
    return f"{int(v):,}" if v == int(v) else f"{v:g}"


def rule_drift(
    old: PolicyDoc, new: PolicyDoc, rules: RuleSet, lines: dict[str, int] | None = None
) -> list[Issue]:
    """A changed clause that stops mentioning a number its rule uses. Only numbers the old text
    did mention are compared, so a rule value written differently (a ratio, a month count) is
    not reported."""
    o = {c.clause_id: c for c in old.clauses}
    out: list[Issue] = []
    for c in new.clauses:
        before = o.get(c.clause_id)
        if before is None or before.text == c.text:
            continue
        old_n, new_n = numbers_in(before.text), numbers_in(c.text)
        old_s = set(_number_strings(before.text))
        fresh = [s for s in dict.fromkeys(_number_strings(c.text)) if s not in old_s]
        for r in linked_rules(rules, c.clause_id):
            lost = [v for v in rule_values(r) if _mentions(v, old_n) and not _mentions(v, new_n)]
            if not lost:
                continue
            msg = (f"Rule {r.rule_id} uses {', '.join(_fmt(v) for v in lost)} from the rules file, "
                   f"and clause {c.clause_id} no longer mentions it")  # fmt: skip
            if fresh:
                msg += f" (the clause now says {', '.join(fresh)})"
            msg += (
                ". Scoring keeps using the rules file, so change data/rules/rules.yaml too "
                "(a golden-set rerun is needed) or the report text and the score will disagree."
            )
            out.append(
                Issue("warning", "RULE_NUMBER", msg, (lines or {}).get(c.clause_id), c.clause_id)
            )
    return out


# --------------------------------------------------------------------------- old-format import
_TOPICS = (
    ("KYC", ("kyc", "pan", "aadhaar", "identity", "address proof")),
    ("FRD", ("fraud", "tamper", "forg")),
    ("CRD", ("cibil", "bureau", "enquir", "default", "repayment history", "credit history")),
    ("DOC", ("document", "papers", "proof", "certificate")),
    ("INC", ("income", "foir", "salary", "obligation", "turnover")),
    ("STAB", ("stability", "employment", "experience", "vintage", "in business")),
    ("PROD", ("tenure", "amount", "loan to value", "ltv", "margin", "moratorium", "collateral",
              "purpose", "interest", "rate")),
    ("ELIG", ("age", "eligib", "resident", "minimum", "credit score")),
)  # fmt: skip
_NUMBERED = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[A-Z][.)])\s+(?P<t>\S.{0,98})$")


def next_free_id(prefix: str, topic: str, taken: set[str]) -> str:
    nums = [int(t.rsplit("-", 1)[1]) for t in taken if t.startswith(f"{prefix}-{topic}-")]
    return f"{prefix}-{topic}-{max(nums, default=0) + 1:02d}"


def guess_topic(title: str) -> str:
    low = title.lower()
    return next((t for t, words in _TOPICS if any(w in low for w in words)), "GEN")


def _sentence_case(s: str) -> str:
    letters = [ch for ch in s if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.9:
        return s[:1].upper() + s[1:].lower()
    return s


def _heading_of(line: str) -> str | None:
    s = line.strip()
    if not s:
        return None
    if s.startswith("#"):
        return _sentence_case(s.lstrip("#").strip()) or None
    m = _NUMBERED.match(s)
    if m and len(m["t"].split()) <= 12 and not m["t"].rstrip().endswith((".", ";", ",")):
        return _sentence_case(m["t"].strip())
    letters = [ch for ch in s if ch.isalpha()]
    if letters and len(s.split()) <= 8 and sum(ch.isupper() for ch in letters) / len(letters) > 0.9:
        return _sentence_case(s)
    return None


def legacy_import(
    text: str, loan_type: str, *, current: PolicyDoc | None, known_ids: Iterable[str],
    taken: Iterable[str], today: date,
) -> tuple[str, list[dict[str, Any]]]:  # fmt: skip
    """(Markdown in the clause format, one mapping row per heading found)."""
    meta, body, _ = read_front(normalise_newlines(text))
    title = (meta or {}).get("title")
    prefix = PREFIX[loan_type]
    by_title = {c.title.lower(): c for c in current.clauses} if current else {}
    by_id = {c.clause_id: c for c in current.clauses} if current else {}
    used: set[str] = set(known_ids) | set(by_id)
    assigned: set[str] = set()
    sections: list[tuple[int, str, list[str]]] = []
    intro: list[str] = []
    title_seen = False
    for n, ln in enumerate(body.split("\n"), start=1):
        if ln.startswith("# ") and not title_seen and not sections:
            title_seen = True  # the document's own title, never a clause
            title = title or ln[2:].strip()
            continue
        h = _heading_of(ln)
        if h is not None:
            sections.append((n, h, []))
        elif sections:
            sections[-1][2].append(ln)
        else:
            intro.append(ln)
    mapping: list[dict[str, Any]] = []
    clauses: list[str] = []
    for n, heading, lines in sections:
        text_ = " ".join(" ".join(lines).split())
        row: dict[str, Any] = {"line": n, "heading": heading, "clause_id": None, "source_tag": None,
                               "title": heading, "how": "skipped", "matched": None}  # fmt: skip
        if not text_:
            row["how"] = "skipped"  # a part title with no text under it
            mapping.append(row)
            continue
        got = loose_heading(heading) or loose_heading("# " + heading)
        src: str | None = None
        if got and prefix_of(got[0]) == prefix and got[0] not in assigned:
            cid, src, title_ = got[0], got[1], got[2] or heading
            how = "kept"
        else:
            title_ = re.sub(
                r"\s*[(\[](public|rbi|sample)[)\]]\s*$", "", heading, flags=re.I
            ).strip()
            match = max(
                by_title.items(), key=lambda kv: fuzz.WRatio(kv[0], title_.lower()), default=None
            )
            if (
                match
                and fuzz.WRatio(match[0], title_.lower()) >= TITLE_MATCH
                and match[1].clause_id not in assigned
            ):
                cid, how = match[1].clause_id, "matched"
                row["matched"] = match[1].title
            else:
                cid, how = next_free_id(prefix, guess_topic(title_), used | assigned), "new"
        tag = re.search(r"[(\[](public|rbi|sample)[)\]]", heading, re.I)
        src = (
            src
            or (SOURCES[tag[1].lower()] if tag else None)
            or (by_id[cid].source_tag if cid in by_id else "sample")
        )
        assigned.add(cid)
        row.update(clause_id=cid, source_tag=src, title=title_, how=how)
        mapping.append(row)
        clauses.append(f"## {cid} | {src} | {title_}\n{text_}\n")
    front = default_front(loan_type, taken, today, title or (current.title if current else None))
    intro_text = "\n".join(intro).strip()
    parts = [render_front(front), f"# {front['title']}\n"]
    if intro_text:
        parts.append(intro_text + "\n")
    parts.extend(clauses)
    return "\n".join(parts), mapping


# --------------------------------------------------------------------------- clause edits
def _bounds(lines: list[str], clause_id: str) -> tuple[int, int] | None:
    start = next((i for i, ln in enumerate(lines)
                  if (m := CLAUSE_HEADING.match(ln)) and m["id"] == clause_id), None)  # fmt: skip
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def _render(clause_id: str, source_tag: str, title: str, text: str) -> list[str]:
    return [
        f"## {clause_id} | {source_tag} | {' '.join(title.split())}",
        " ".join(text.split()),
        "",
    ]


def replace_clause(raw: str, clause_id: str, *, source_tag: str, title: str, text: str) -> str:
    lines = raw.split("\n")
    b = _bounds(lines, clause_id)
    if b is None:
        raise KeyError(clause_id)
    return (
        "\n".join(
            lines[: b[0]] + _render(clause_id, source_tag, title, text) + lines[b[1] :]
        ).rstrip("\n")
        + "\n"
    )


def remove_clause(raw: str, clause_id: str) -> str:
    lines = raw.split("\n")
    b = _bounds(lines, clause_id)
    if b is None:
        raise KeyError(clause_id)
    return "\n".join(lines[: b[0]] + lines[b[1] :]).rstrip("\n") + "\n"


def add_clause(raw: str, *, clause_id: str, source_tag: str, title: str, text: str,
               after: str | None = None) -> str:  # fmt: skip
    lines = raw.rstrip("\n").split("\n")
    at = len(lines)
    if after is not None:
        b = _bounds(lines, after)
        if b is None:
            raise KeyError(after)
        at = b[1]
    block = _render(clause_id, source_tag, title, text)
    if at == len(lines):
        block = ["", *block[:-1]]
    return "\n".join(lines[:at] + block + lines[at:]).rstrip("\n") + "\n"


def rebuild_body(meta: dict[str, Any], clauses: list[Clause]) -> str:
    """Markdown for a version stored before bodies were kept (introduction text is lost)."""
    parts = [render_front(meta), f"# {meta.get('title', '')}\n"]
    parts.extend(f"## {c.clause_id} | {c.source_tag} | {c.title}\n{c.text}\n" for c in clauses)
    return "\n".join(parts)
