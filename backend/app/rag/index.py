"""Build and refresh the policy index: parse files, embed changed clauses, record versions.

A clause is re-embedded only when its text hash changed or its embedding is missing. A new
`version` in a file's front matter becomes a new `policy_documents` row and becomes the active
one for that loan type; older versions stay for old reports. An edit under the same version is
picked up through the file checksum.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from app.core.config import REPO_ROOT
from app.rag.embedder import embed_passages
from app.rag.policy_loader import Clause, PolicyDoc, load_all

Embed = Callable[[list[str]], list[list[float]]]


@dataclass
class DocReport:
    loan_type: str
    version: str
    new_version: bool = False
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

    @property
    def touched(self) -> bool:
        return any(d.touched for d in self.docs)

    def as_json(self) -> dict[str, object]:
        return {
            "embedded": self.embedded,
            "docs": [
                {
                    "loan_type": d.loan_type, "version": d.version, "new_version": d.new_version,
                    "added": d.added, "changed": d.changed, "removed": d.removed,
                    "unchanged": d.unchanged,
                }
                for d in self.docs
            ],
        }  # fmt: skip


def file_checksum(doc: PolicyDoc) -> str:
    return hashlib.sha256(doc.path.read_bytes()).hexdigest()


def clause_hash(c: Clause) -> str:
    return hashlib.sha256(f"{c.source_tag}|{c.title}|{c.text}".encode()).hexdigest()


def embedding_text(c: Clause) -> str:
    return f"{c.title}. {c.text}"


def _upsert_document(conn: Connection, doc: PolicyDoc, checksum: str) -> tuple[str, bool]:
    """Return (document id, is_new_version)."""
    row = conn.execute(
        text("SELECT id FROM policy_documents WHERE loan_type = :lt AND version = :v"),
        {"lt": doc.loan_type, "v": doc.version},
    ).first()
    if row is None:
        doc_id = conn.execute(
            text(
                """INSERT INTO policy_documents (loan_type, title, version, source_tag, file_path,
                       effective_from, active, checksum, indexed_at)
                   VALUES (:lt, :title, :v, 'sample', :path, :eff, true, :sum, now())
                   RETURNING id"""
            ),
            {"lt": doc.loan_type, "title": doc.title, "v": doc.version, "eff": doc.effective_from,
             "path": _rel(doc), "sum": checksum},
        ).scalar_one()  # fmt: skip
        new = True
    else:
        doc_id = row[0]
        conn.execute(
            text(
                """UPDATE policy_documents SET title = :title, file_path = :path,
                       effective_from = :eff, active = true, checksum = :sum, indexed_at = now()
                   WHERE id = :id"""
            ),
            {"title": doc.title, "path": _rel(doc), "eff": doc.effective_from, "sum": checksum,
             "id": doc_id},
        )  # fmt: skip
        new = False
    # one active version per loan type
    conn.execute(
        text("UPDATE policy_documents SET active = false WHERE loan_type = :lt AND id <> :id"),
        {"lt": doc.loan_type, "id": doc_id},
    )
    return str(doc_id), new


def _rel(doc: PolicyDoc) -> str:
    try:
        return str(doc.path.relative_to(REPO_ROOT))
    except ValueError:  # a policy directory outside the repo (tests)
        return str(doc.path)


def index_document(
    conn: Connection, doc: PolicyDoc, embed: Embed, force: bool = False
) -> tuple[DocReport, int]:
    checksum = file_checksum(doc)
    doc_id, new = _upsert_document(conn, doc, checksum)
    report = DocReport(doc.loan_type, doc.version, new_version=new)
    existing = {
        r.clause_id: (r.metadata or {}).get("text_hash") if r.has_embedding else None
        for r in conn.execute(
            text(
                """SELECT clause_id, metadata, embedding IS NOT NULL AS has_embedding
                   FROM policy_chunks WHERE policy_document_id = :d"""
            ),
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
    vectors = embed([embedding_text(c) for c in pending])
    for c, vec in zip(pending, vectors, strict=True):
        conn.execute(
            text(
                """INSERT INTO policy_chunks
                       (policy_document_id, clause_id, text, embedding, metadata)
                   VALUES (:d, :cid, :t, CAST(:e AS vector), CAST(:m AS jsonb))
                   ON CONFLICT (policy_document_id, clause_id) DO UPDATE SET
                       text = EXCLUDED.text, embedding = EXCLUDED.embedding,
                       metadata = EXCLUDED.metadata"""
            ),
            {
                "d": doc_id, "cid": c.clause_id, "t": c.text, "e": str(vec),
                "m": json.dumps({"source_tag": c.source_tag, "title": c.title,
                                 "text_hash": clause_hash(c)}),
            },
        )  # fmt: skip
    keep = [c.clause_id for c in doc.clauses]
    gone = conn.execute(
        text(
            """DELETE FROM policy_chunks WHERE policy_document_id = :d
               AND NOT (clause_id = ANY(:keep)) RETURNING clause_id"""
        ),
        {"d": doc_id, "keep": keep},
    )
    report.removed = sorted(r[0] for r in gone)
    return report, len(pending)


def reindex(
    conn: Connection,
    docs: list[PolicyDoc] | None = None,
    embed: Embed = embed_passages,
    force: bool = False,
) -> ReindexReport:
    report = ReindexReport()
    for doc in docs if docs is not None else load_all():
        doc_report, embedded = index_document(conn, doc, embed, force)
        report.docs.append(doc_report)
        report.embedded += embedded
    conn.execute(
        text(
            """INSERT INTO audit_log (action, entity, entity_id, after)
               VALUES ('policy_reindex', 'policy_documents', NULL, CAST(:a AS jsonb))"""
        ),
        {"a": json.dumps(report.as_json())},
    )
    return report
