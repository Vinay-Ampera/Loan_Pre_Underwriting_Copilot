"""Build and refresh the policy index: store a version's clauses and embed only what is new.

Since Stage 10c the database holds every policy version (`policy_documents.body`) and the files
in data/policy are the starting data. `reindex` imports those files:

  - a file whose version label is new and sorts after every label in the database becomes a new
    version: active now, or scheduled when its effective date is in the future
  - a file edited under the label of the active, file-imported version updates that version in
    place (only the changed clauses are re-embedded, edge case E-20)
  - a file whose label is older, or names a version published from the knowledge base screen, is
    left alone with a note: an older version is never made active again

A clause is embedded only when no stored clause has the same text hash; otherwise the vector is
copied. `force` re-embeds every clause of the active and scheduled versions (after a change of
embedding model).
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Connection, text

from app.core.config import REPO_ROOT
from app.rag import policy_admin as pa
from app.rag import versions
from app.rag.embedder import embed_passages
from app.rag.policy_loader import Clause, PolicyDoc, load_all
from app.scoring.rules import RuleSet, load_rules

Embed = Callable[[list[str]], list[list[float]]]


@dataclass
class DocReport:
    loan_type: str
    version: str
    new_version: bool = False
    status: str = ""
    note: str | None = None
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0

    @property
    def touched(self) -> bool:
        return bool(self.new_version or self.added or self.changed or self.removed)


@dataclass
class ReindexReport:
    docs: list[DocReport] = field(default_factory=list)
    embedded: int = 0
    activated: list[str] = field(default_factory=list)

    @property
    def touched(self) -> bool:
        return any(d.touched for d in self.docs) or bool(self.activated)

    def as_json(self) -> dict[str, object]:
        return {
            "embedded": self.embedded,
            "activated": self.activated,
            "docs": [
                {
                    "loan_type": d.loan_type, "version": d.version, "new_version": d.new_version,
                    "status": d.status, "note": d.note, "added": d.added, "changed": d.changed,
                    "removed": d.removed, "unchanged": d.unchanged,
                }
                for d in self.docs
            ],
        }  # fmt: skip


class PolicyRulesError(ValueError):
    """A version in force (or scheduled) lacks a clause the rules file cites."""


def file_checksum(doc: PolicyDoc) -> str:
    return doc.checksum


def clause_hash(c: Clause) -> str:
    return hashlib.sha256(f"{c.source_tag}|{c.title}|{c.text}".encode()).hexdigest()


def embedding_text(c: Clause) -> str:
    return f"{c.title}. {c.text}"


def _rel(doc: PolicyDoc) -> str | None:
    if doc.path is None:
        return None
    try:
        return str(doc.path.relative_to(REPO_ROOT))
    except ValueError:  # a policy directory outside the repo (tests)
        return str(doc.path)


def _vectors_by_hash(conn: Connection, hashes: list[str]) -> dict[str, str]:
    if not hashes:
        return {}
    rows = conn.execute(
        text("""SELECT DISTINCT ON (metadata->>'text_hash') metadata->>'text_hash' AS h,
                       embedding::text AS e
                FROM policy_chunks
                WHERE metadata->>'text_hash' = ANY(:hs) AND embedding IS NOT NULL"""),
        {"hs": hashes},
    )  # fmt: skip
    return {r.h: r.e for r in rows}


def write_chunks(
    conn: Connection, doc_id: str, doc: PolicyDoc, embed: Embed | None, force: bool = False,
    report: DocReport | None = None,
) -> tuple[DocReport, int]:  # fmt: skip
    """Store the version's clauses. Returns (what changed, how many clauses were embedded).
    `embed=None` stores the text without vectors (the seed command); a later run fills them."""
    report = report or DocReport(doc.loan_type, doc.version)
    existing = {
        r.clause_id: (r.metadata or {}).get("text_hash") if r.has_embedding else None
        for r in conn.execute(
            text("""SELECT clause_id, metadata, embedding IS NOT NULL AS has_embedding
                    FROM policy_chunks WHERE policy_document_id = :d"""),
            {"d": doc_id},
        )
    }  # fmt: skip
    pending: list[Clause] = []
    for c in doc.clauses:
        if c.clause_id not in existing:
            report.added.append(c.clause_id)
            pending.append(c)
        elif force or existing[c.clause_id] != clause_hash(c):
            report.changed.append(c.clause_id)
            pending.append(c)
        else:
            report.unchanged += 1
    reuse = (
        {} if force or embed is None else _vectors_by_hash(conn, [clause_hash(c) for c in pending])
    )
    to_embed = [c for c in pending if clause_hash(c) not in reuse] if embed is not None else []
    vectors = embed([embedding_text(c) for c in to_embed]) if to_embed and embed else []
    vec = {**reuse, **{clause_hash(c): str(v) for c, v in zip(to_embed, vectors, strict=True)}}
    for c in pending:
        conn.execute(
            text("""INSERT INTO policy_chunks (policy_document_id, clause_id, text, embedding, metadata)
                    VALUES (:d, :cid, :t, CAST(:e AS vector), CAST(:m AS jsonb))
                    ON CONFLICT (policy_document_id, clause_id) DO UPDATE SET
                        text = EXCLUDED.text, embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata"""),
            {"d": doc_id, "cid": c.clause_id, "t": c.text, "e": vec.get(clause_hash(c)),
             "m": json.dumps({"source_tag": c.source_tag, "title": c.title,
                              "text_hash": clause_hash(c)})},
        )  # fmt: skip
    gone = conn.execute(
        text("""DELETE FROM policy_chunks WHERE policy_document_id = :d
                AND NOT (clause_id = ANY(:keep)) RETURNING clause_id"""),
        {"d": doc_id, "keep": [c.clause_id for c in doc.clauses]},
    )
    report.removed = sorted(r[0] for r in gone)
    return report, len(to_embed)


def insert_version(
    conn: Connection, doc: PolicyDoc, *, status: str, origin: str, actor: str | None = None,
    reason: str | None = None, based_on: str | None = None,
) -> str:  # fmt: skip
    doc_id: str = str(
        conn.execute(
            text("""INSERT INTO policy_documents (loan_type, title, version, source_tag, file_path,
                        effective_from, status, checksum, indexed_at, body, origin, reason,
                        based_on, created_by)
                    VALUES (:lt, :title, :v, 'sample', :path, :eff, :s, :sum, now(), :body, :o,
                            :why, :based, :u)
                    RETURNING id"""),
            {"lt": doc.loan_type, "title": doc.title, "v": doc.version, "path": _rel(doc),
             "eff": doc.effective_from, "s": status, "sum": doc.checksum, "body": doc.raw,
             "o": origin, "why": reason, "based": based_on, "u": actor},
        ).scalar_one()
    )  # fmt: skip
    return doc_id


def _import_one(
    conn: Connection, doc: PolicyDoc, embed: Embed | None, force: bool, today: date, rules: RuleSet
) -> tuple[DocReport, int]:
    rep = DocReport(doc.loan_type, doc.version)
    rows = conn.execute(
        text("""SELECT id, version, status, origin, checksum, body FROM policy_documents
                WHERE loan_type = :lt AND status <> 'draft'"""),
        {"lt": doc.loan_type},
    ).all()
    same = next((r for r in rows if r.version == doc.version), None)
    if same is not None:
        rep.status = same.status
        live = same.status in ("active", "scheduled")
        if live and same.origin == "file":
            if same.checksum != doc.checksum or same.body is None:
                conn.execute(
                    text("""UPDATE policy_documents SET title = :title, file_path = :path,
                                effective_from = :eff, checksum = :sum, body = :body,
                                indexed_at = now()
                            WHERE id = :id"""),
                    {"title": doc.title, "path": _rel(doc), "eff": doc.effective_from,
                     "sum": doc.checksum, "body": doc.raw, "id": same.id},
                )  # fmt: skip
            return write_chunks(conn, str(same.id), doc, embed, force, rep)
        if live:
            if same.checksum != doc.checksum:
                rep.note = (f"version {doc.version} was published from the knowledge base screen; "
                            "the file differs and was not imported. Give the file a new version label.")  # fmt: skip
                return rep, 0
            return write_chunks(conn, str(same.id), doc, embed, force, rep)
        rep.note = (
            f"version {doc.version} is {same.status}; an older version is never made active again"
        )
        return rep, 0
    newest = max(rows, key=lambda r: pa.label_key(r.version), default=None)
    if newest is not None and pa.label_key(doc.version) <= pa.label_key(newest.version):
        rep.note = f"older than version {newest.version} in the database; not imported"
        return rep, 0
    future = doc.effective_from > today
    if any(r.status == "scheduled" for r in rows):  # it would replace this one on its date
        rep.note = "another version is scheduled for this loan type; not imported"
        return rep, 0
    # inserted as superseded, then switched in, so there is never a moment with two active rows
    doc_id = insert_version(conn, doc, status="scheduled" if future else "superseded",
                            origin="file", reason=f"imported from {_rel(doc) or 'a file'}")  # fmt: skip
    rep.new_version, rep.status = True, "scheduled" if future else "active"
    out = write_chunks(conn, doc_id, doc, embed, force, rep)
    if not future:
        versions.switch(
            conn, doc.loan_type, doc_id, rules=rules, actor=None, note="imported from a file"
        )
    return out


def check_rule_clauses(conn: Connection, rules: RuleSet) -> list[str]:
    """Rules whose clause is missing from an active or scheduled version: 'RULE->CLAUSE (type)'."""
    have: dict[str, set[str]] = {}
    for r in conn.execute(
        text("""SELECT d.loan_type, d.status, c.clause_id FROM policy_documents d
                JOIN policy_chunks c ON c.policy_document_id = d.id
                WHERE d.status IN ('active', 'scheduled')"""),
    ):  # fmt: skip
        have.setdefault(f"{r.loan_type}:{r.status}", set()).add(r.clause_id)
    by_prefix = {v: k for k, v in pa.PREFIX.items()}
    missing = []
    for key, ids in have.items():
        lt = key.split(":", 1)[0]
        for rule in rules.rules:
            if (
                by_prefix.get(pa.prefix_of(rule.policy_clause)) == lt
                and rule.policy_clause not in ids
            ):
                missing.append(f"{rule.rule_id}->{rule.policy_clause} ({key})")
    return sorted(missing)


def reindex(
    conn: Connection,
    docs: list[PolicyDoc] | None = None,
    embed: Embed | None = embed_passages,
    force: bool = False,
    *,
    today: date | None = None,
    rules: RuleSet | None = None,
    actor: str | None = None,
) -> ReindexReport:
    """Import the policy files and refresh embeddings, in the caller's transaction. The caller
    checks `check_rule_clauses` afterwards and rolls back when a rule lost its clause."""
    versions.lock(conn)
    today = today or date.today()
    rules = rules or load_rules()
    report = ReindexReport(activated=versions.promote_due(conn, rules, today))
    seen: set[str] = set()
    for doc in docs if docs is not None else load_all():
        doc_report, embedded = _import_one(conn, doc, embed, force, today, rules)
        report.docs.append(doc_report)
        report.embedded += embedded
        seen.add(f"{doc.loan_type}:{doc.version}")
    if force:  # versions made on the screen have no file; re-embed them too
        for r in conn.execute(
            text("""SELECT id, loan_type, version FROM policy_documents
                    WHERE status IN ('active', 'scheduled')"""),
        ).all():  # fmt: skip
            if f"{r.loan_type}:{r.version}" not in seen:
                _, n = write_chunks(conn, str(r.id), versions.load_doc(conn, r.id), embed, True)
                report.embedded += n
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, after)
                VALUES (:u, 'policy_reindex', 'policy_documents', NULL, CAST(:a AS jsonb))"""),
        {"u": actor, "a": json.dumps({**report.as_json(), "force": force})},
    )
    return report
