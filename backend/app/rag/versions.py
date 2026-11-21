"""Which policy version is in force, and which one a run uses (Stage 10c).

One version per loan type is `active`. A version with a future effective date is `scheduled` and
becomes active on that date: there is no scheduler (no Celery, no Redis), so the switch happens
the first time anything asks after the date has come (a case starting, the knowledge base page,
the re-index command). Every change of state takes one advisory lock, so two requests can never
leave a loan type with no active version or two.

A run binds the in-force versions when it starts (`for_run` then `bind`, a context variable, the
same way the AI configuration is bound). Retrieval and the report's version stamp read the bound
set, so a publish in the middle of a run reaches only the cases that start after it (E-91).
"""

import json
from contextvars import ContextVar
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from app.learning.maintenance import pause_for_policy
from app.rag import policy_admin as pa
from app.rag.policy_loader import Clause, PolicyDoc, parse_text
from app.scoring.rules import RuleSet, load_rules

LOCK = text("SELECT pg_advisory_xact_lock(hashtext('policy_versions'))")
_bound: ContextVar[dict[str, str] | None] = ContextVar("policy_versions", default=None)


def lock(conn: Connection) -> None:
    conn.execute(LOCK)


def bind(docs: dict[str, str] | None) -> None:
    """Fix the policy versions (loan type -> policy_documents.id) for the rest of this run."""
    _bound.set(docs)


def bound() -> dict[str, str] | None:
    return _bound.get()


def in_force(conn: Connection) -> dict[str, str]:
    rows = conn.execute(text("SELECT loan_type, id FROM policy_documents WHERE status = 'active'"))
    return {r.loan_type: str(r.id) for r in rows}


def for_run(
    engine: Engine, rules: RuleSet | None = None, today: date | None = None
) -> dict[str, str]:
    """Make any version whose date has come active, then return the set a new run uses."""
    with engine.begin() as conn:
        promote_due(conn, rules, today)
        return in_force(conn)


def labels(conn: Connection, loan_type: str) -> list[str]:
    """Every version label used for this loan type, except the working draft's."""
    return [
        r[0]
        for r in conn.execute(
            text(
                "SELECT version FROM policy_documents WHERE loan_type = :lt AND status <> 'draft'"
            ),
            {"lt": loan_type},
        )
    ]


def load_doc(conn: Connection, doc_id: UUID | str) -> PolicyDoc:
    """A stored version as a parsed document: from its Markdown, or rebuilt from its clauses for
    a row stored before bodies were kept."""
    row = conn.execute(
        text("""SELECT id, loan_type, title, version, effective_from, body
                FROM policy_documents WHERE id = :i"""),
        {"i": doc_id},
    ).first()  # fmt: skip
    if row is None:
        raise LookupError("Policy version not found.")
    if row.body:
        return parse_text(row.body, f"{row.loan_type} {row.version}")
    chunks = conn.execute(
        text("""SELECT clause_id, text, metadata FROM policy_chunks
                WHERE policy_document_id = :i ORDER BY clause_id"""),
        {"i": doc_id},
    ).all()
    clauses = [Clause(c.clause_id, (c.metadata or {}).get("source_tag", "sample"),
                      (c.metadata or {}).get("title", c.clause_id), c.text) for c in chunks]  # fmt: skip
    meta = {"doc_id": f"policy-{row.loan_type}", "loan_type": row.loan_type, "title": row.title,
            "version": row.version, "effective_from": row.effective_from}  # fmt: skip
    return parse_text(pa.rebuild_body(meta, clauses), f"{row.loan_type} {row.version}")


def active_doc(conn: Connection, loan_type: str) -> tuple[str, PolicyDoc] | None:
    row = conn.execute(
        text("SELECT id FROM policy_documents WHERE loan_type = :lt AND status = 'active'"),
        {"lt": loan_type},
    ).first()
    return None if row is None else (str(row.id), load_doc(conn, row.id))


def clause_hashes(conn: Connection, doc_id: str | UUID | None) -> dict[str, str]:
    if doc_id is None:
        return {}
    rows = conn.execute(
        text("SELECT clause_id, metadata FROM policy_chunks WHERE policy_document_id = :d"),
        {"d": doc_id},
    )
    return {r.clause_id: (r.metadata or {}).get("text_hash", "") for r in rows}


def switch(
    conn: Connection, loan_type: str, new_id: str | UUID, *, rules: RuleSet | None,
    actor: UUID | None, note: str,
) -> dict[str, Any]:  # fmt: skip
    """Make `new_id` the active version of its loan type. The old one becomes superseded (kept
    for old reports); precedents whose rules cite a changed or removed clause are paused."""
    old = conn.execute(
        text(
            "SELECT id, version FROM policy_documents WHERE loan_type = :lt AND status = 'active'"
        ),
        {"lt": loan_type},
    ).first()
    if old is not None and str(old.id) == str(new_id):
        return {"replaced": None, "paused": []}
    if old is not None:
        conn.execute(
            text("UPDATE policy_documents SET status = 'superseded' WHERE id = :i"), {"i": old.id}
        )
    new = conn.execute(
        text("""UPDATE policy_documents SET status = 'active',
                    published_at = coalesce(published_at, now()),
                    published_by = coalesce(published_by, :u)
                WHERE id = :i RETURNING version"""),
        {"i": new_id, "u": actor},
    ).one()  # fmt: skip
    before, after = clause_hashes(conn, old.id if old else None), clause_hashes(conn, new_id)
    touched = {cid for cid, h in before.items() if after.get(cid) != h}
    paused = (
        pause_for_policy(conn, loan_type, touched, rules or load_rules(), new.version)
        if old
        else []
    )
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, before, after)
                VALUES (:u, 'policy_activated', 'policy_documents', :e, CAST(:b AS jsonb),
                        CAST(:a AS jsonb))"""),
        {"u": actor, "e": str(new_id),
         "b": json.dumps({"version": old.version} if old else {}),
         "a": json.dumps({"loan_type": loan_type, "version": new.version, "note": note,
                          "changed_clauses": sorted(touched), "precedents_paused": len(paused)})},
    )  # fmt: skip
    return {"replaced": old.version if old else None, "paused": paused}


def promote_due(
    conn: Connection, rules: RuleSet | None = None, today: date | None = None
) -> list[str]:
    """Activate every scheduled version whose effective date has come. Returns the loan types."""
    today = today or date.today()
    due = conn.execute(
        text("""SELECT id, loan_type FROM policy_documents
                WHERE status = 'scheduled' AND effective_from <= :d"""),
        {"d": today},
    ).all()
    if not due:
        return []
    lock(conn)
    done = []
    for r in conn.execute(
        text("""SELECT id, loan_type FROM policy_documents
                WHERE status = 'scheduled' AND effective_from <= :d"""),
        {"d": today},
    ).all():  # read again under the lock: another request may have done it
        switch(
            conn, r.loan_type, r.id, rules=rules, actor=None, note="the effective date was reached"
        )
        done.append(r.loan_type)
    return done
