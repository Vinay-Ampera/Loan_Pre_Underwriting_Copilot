"""The knowledge base service (Stage 10c): what the admin's policy screens do, in one place.

A change always goes through a draft (one per loan type, `policy_drafts`), which can be saved
even when it fails the format check. A draft that passes is staged as a `draft` policy version
with its clauses embedded, so the retrieval check can compare it with the version in force;
search never reads a staged draft. Publishing needs: no errors, a retrieval check run on this
exact text with no errors, a tick for the warnings, a written reason and the second click. A
future effective date schedules the version instead of making it active.

Published versions are never edited or deleted: "delete" is retire (a scheduled or superseded
version), and "roll back" is restore (an older version's text copied into the draft with a new
label, then published like any other change). Every step writes the audit log.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.rag import policy_admin as pa
from app.rag import versions
from app.rag.config import load_rag_config
from app.rag.evaluate import BASELINE_PATH, check_targets, evaluate, load_queries
from app.rag.index import Embed, check_rule_clauses, insert_version, reindex, write_chunks
from app.rag.policy_loader import CLAUSE_HEADING, PolicyDoc, PolicyFormatError, load_all
from app.rag.retrieve import PolicyRetriever
from app.scoring.rules import Rule, RuleSet

RetrieverFactory = Callable[[Connection], PolicyRetriever]
ORIGINS = ("upload", "edit", "restore", "legacy")


class KbError(Exception):
    def __init__(self, status: int, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status, self.message, self.detail = status, message, detail


def sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def check_loan(loan_type: str) -> str:
    if loan_type not in pa.LOAN_TYPES:
        raise KbError(404, "Unknown loan type.")
    return loan_type


def _audit(conn: Connection, actor: UUID | None, action: str, entity_id: Any, after: dict[str, Any],
           before: dict[str, Any] | None = None) -> None:  # fmt: skip
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, before, after)
                VALUES (:u, :a, 'policy_documents', :e, CAST(:b AS jsonb), CAST(:f AS jsonb))"""),
        {"u": actor, "a": action, "e": None if entity_id is None else str(entity_id),
         "b": None if before is None else json.dumps(before, default=str),
         "f": json.dumps(after, default=str)},
    )  # fmt: skip


# --------------------------------------------------------------------------- reading
def rule_json(r: Rule) -> dict[str, Any]:
    return {"rule_id": r.rule_id, "kind": r.kind, "stage": r.stage, "field": r.field,
            "operator": r.operator, "threshold": r.threshold,
            "tiers": [t.model_dump() for t in r.tiers] if r.tiers else None, "points": r.points,
            "on_fail": r.on_fail, "fail_class": r.fail_class}  # fmt: skip


def _cites(conn: Connection, ids: list[str]) -> dict[str, int]:
    rows = conn.execute(
        text("""SELECT c->>'clause_id' AS cid, count(DISTINCT r.case_id) AS n
                FROM reports r
                CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.report_json->'citations', '[]'::jsonb)) c
                WHERE r.created_at > now() - interval '30 days' AND c->>'clause_id' = ANY(:ids)
                GROUP BY 1"""),
        {"ids": ids},
    )  # fmt: skip
    return {r.cid: r.n for r in rows}


def _row(conn: Connection, doc_id: UUID | str) -> Any:
    row = conn.execute(
        text("""SELECT d.*, pu.name AS published_by_name, ru.name AS retired_by_name,
                       cu.name AS created_by_name,
                       (SELECT count(*) FROM policy_chunks c WHERE c.policy_document_id = d.id) AS n_clauses,
                       (SELECT count(*) FROM policy_chunks c WHERE c.policy_document_id = d.id
                                                              AND c.embedding IS NOT NULL) AS n_embedded
                FROM policy_documents d LEFT JOIN users pu ON pu.id = d.published_by
                     LEFT JOIN users ru ON ru.id = d.retired_by LEFT JOIN users cu ON cu.id = d.created_by
                WHERE d.id = :i"""),
        {"i": doc_id},
    ).first()  # fmt: skip
    if row is None:
        raise KbError(404, "Policy version not found.")
    return row


def _summary(r: Any) -> dict[str, Any]:
    return {"id": str(r.id), "loan_type": r.loan_type, "title": r.title, "version": r.version,
            "status": r.status, "origin": r.origin, "effective_from": r.effective_from,
            "reason": r.reason, "published_by": r.published_by_name, "published_at": r.published_at,
            "retired_by": r.retired_by_name, "retired_at": r.retired_at,
            "retired_reason": r.retired_reason, "clauses": r.n_clauses,
            "embedded": r.n_embedded}  # fmt: skip


def version_view(
    conn: Connection, doc_id: UUID | str, *, rules: RuleSet, admin: bool
) -> dict[str, Any]:
    r = _row(conn, doc_id)
    if not admin and r.status != "active":
        raise KbError(403, "Officers can read the policy in force only.")
    doc = versions.load_doc(conn, r.id)
    cites = _cites(conn, [c.clause_id for c in doc.clauses]) if admin else {}
    meta, body, _ = pa.read_front(doc.raw)
    intro = body.split("\n## ", 1)[0].strip() if "## " in body else body.strip()
    return {
        **_summary(r),
        "intro": "\n".join(ln for ln in intro.split("\n") if not ln.startswith("# ")).strip(),
        "clause_list": [
            {"clause_id": c.clause_id, "title": c.title, "source_tag": c.source_tag, "text": c.text,
             "rules": [rule_json(x) for x in pa.linked_rules(rules, c.clause_id)],
             "cited_30d": cites.get(c.clause_id, 0) if admin else None}
            for c in doc.clauses
        ],
        "body": doc.raw if admin else None,
    }  # fmt: skip


def overview(
    conn: Connection, *, admin: bool, rules: RuleSet, today: date | None = None
) -> list[dict[str, Any]]:
    versions.promote_due(conn, rules, today)
    rows = conn.execute(
        text("""SELECT d.id, d.loan_type, d.title, d.version, d.status, d.effective_from,
                       d.published_at, u.name AS published_by,
                       (SELECT count(*) FROM policy_chunks c WHERE c.policy_document_id = d.id) AS n,
                       (SELECT count(*) FROM policy_chunks c WHERE c.policy_document_id = d.id
                                                              AND c.embedding IS NULL) AS missing
                FROM policy_documents d LEFT JOIN users u ON u.id = d.published_by
                WHERE d.status IN ('active', 'scheduled')"""),
    ).all()  # fmt: skip
    drafts = {
        r.loan_type: r
        for r in conn.execute(text("SELECT loan_type, updated_at FROM policy_drafts"))
    }
    out = []
    for lt in pa.LOAN_TYPES:
        act = next((r for r in rows if r.loan_type == lt and r.status == "active"), None)
        sch = next((r for r in rows if r.loan_type == lt and r.status == "scheduled"), None)
        out.append({
            "loan_type": lt,
            "active": None if act is None else {
                "id": str(act.id), "title": act.title, "version": act.version,
                "effective_from": act.effective_from, "published_at": act.published_at,
                "published_by": act.published_by, "clauses": act.n, "missing_embeddings": act.missing},
            "scheduled": None if sch is None else {
                "id": str(sch.id), "version": sch.version, "effective_from": sch.effective_from},
            "draft": None if not admin or lt not in drafts else {"updated_at": drafts[lt].updated_at},
        })  # fmt: skip
    return out


def detail(
    conn: Connection, loan_type: str, *, admin: bool, rules: RuleSet, today: date | None = None
) -> dict[str, Any]:
    lt = check_loan(loan_type)
    versions.promote_due(conn, rules, today)
    act = versions.active_doc(conn, lt)
    out: dict[str, Any] = {
        "loan_type": lt,
        "active": None if act is None else version_view(conn, act[0], rules=rules, admin=admin),
        "scheduled": None, "versions": None, "draft": None,
    }  # fmt: skip
    sch = conn.execute(
        text("SELECT id FROM policy_documents WHERE loan_type = :lt AND status = 'scheduled'"),
        {"lt": lt},
    ).first()
    if sch is not None:
        out["scheduled"] = version_view(conn, sch.id, rules=rules, admin=True) if admin else {
            k: v for k, v in _summary(_row(conn, sch.id)).items()
            if k in ("version", "effective_from", "title")}  # fmt: skip
    if admin:
        rows = conn.execute(
            text("""SELECT id FROM policy_documents WHERE loan_type = :lt AND status <> 'draft'
                    ORDER BY coalesce(published_at, created_at) DESC"""),
            {"lt": lt},
        ).all()
        out["versions"] = [_summary(_row(conn, r.id)) for r in rows]
        out["draft"] = draft_view(conn, lt, rules=rules, today=today)
    return out


def compare(conn: Connection, a: UUID, b: UUID) -> dict[str, Any]:
    old, new = versions.load_doc(conn, a), versions.load_doc(conn, b)
    if old.loan_type != new.loan_type:
        raise KbError(422, "Compare two versions of the same policy.")
    return pa.diff_docs(old, new)


# --------------------------------------------------------------------------- drafts
def _taken(conn: Connection, lt: str) -> list[str]:
    return versions.labels(conn, lt)


def _current(conn: Connection, lt: str) -> PolicyDoc | None:
    act = versions.active_doc(conn, lt)
    return None if act is None else act[1]


def run_check(
    conn: Connection, lt: str, body: str, *, rules: RuleSet, today: date
) -> pa.CheckResult:
    return pa.check(
        body, lt, rules=rules, current=_current(conn, lt), taken=_taken(conn, lt), today=today
    )


def start_text(conn: Connection, lt: str, today: date) -> str:
    """The active version's text with the next version label and today's date."""
    cur = _current(conn, lt)
    taken = _taken(conn, lt)
    if cur is None:
        return pa.render_front(pa.default_front(lt, taken, today, None)) + f"\n# {pa.TITLES[lt]}\n"
    return pa.set_front(cur.raw, version=pa.next_label(taken, today), effective_from=today)


def _draft_row(conn: Connection, lt: str) -> Any:
    return conn.execute(
        text("""SELECT d.*, u.name AS updated_by_name FROM policy_drafts d
                LEFT JOIN users u ON u.id = d.updated_by WHERE d.loan_type = :lt"""),
        {"lt": lt},
    ).first()


def draft_view(
    conn: Connection, lt: str, *, rules: RuleSet, today: date | None = None
) -> dict[str, Any] | None:
    today = today or date.today()
    d = _draft_row(conn, lt)
    if d is None:
        return None
    res = run_check(conn, lt, d.body, rules=rules, today=today)
    retrieval = d.retrieval_report if d.retrieval_hash == d.body_hash else None
    blockers = []
    if not res.ok:
        blockers.append("Fix the errors first.")
    elif d.document_id is None:
        blockers.append("Save the draft again so it can be checked.")
    if res.ok and retrieval is None:
        blockers.append("Run the retrieval check on this text.")
    if retrieval and retrieval.get("errors"):
        blockers.append("The retrieval check found errors.")
    sched = conn.execute(
        text("SELECT version FROM policy_documents WHERE loan_type = :lt AND status = 'scheduled'"),
        {"lt": lt},
    ).first()
    if sched is not None:
        blockers.append(
            f"Version {sched.version} is scheduled; retire it before publishing another."
        )
    warnings = len(res.warnings) + len((retrieval or {}).get("warnings", []))
    return {
        "loan_type": lt, "body": d.body, "origin": d.origin,
        "based_on": None if d.based_on is None else str(d.based_on),
        "updated_at": d.updated_at, "updated_by": d.updated_by_name,
        "check": res.as_json(today), "retrieval": retrieval,
        "clauses": None if res.doc is None else [
            {"clause_id": c.clause_id, "title": c.title, "source_tag": c.source_tag, "text": c.text}
            for c in res.doc.clauses],
        "retrieval_stale": d.retrieval_report is not None and retrieval is None,
        "can_publish": not blockers, "blockers": blockers, "warning_count": warnings,
    }  # fmt: skip


def save_draft(
    conn: Connection, lt: str, body: str, *, origin: str, actor: UUID, rules: RuleSet,
    embed: Embed, today: date, based_on: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    lt = check_loan(lt)
    if origin not in ORIGINS:
        raise KbError(422, "Unknown draft origin.")
    body = pa.normalise_newlines(body)
    if len(body) > pa.MAX_TEXT_CHARS:
        raise KbError(422, "The text is longer than 200,000 characters.")
    versions.lock(conn)
    old = _draft_row(conn, lt)
    h = sha(body)
    keep_origin = old.origin if old is not None and origin == "edit" else origin
    keep_based = (
        based_on
        if based_on is not None
        else (str(old.based_on) if old is not None and old.based_on else None)
    )
    res = run_check(conn, lt, body, rules=rules, today=today)
    staged = old.document_id if old is not None and old.body_hash == h else None
    if staged is None:
        conn.execute(
            text("DELETE FROM policy_documents WHERE loan_type = :lt AND status = 'draft'"),
            {"lt": lt},
        )
        if res.ok and res.doc is not None:
            staged = insert_version(conn, res.doc, status="draft", origin=keep_origin,
                                    actor=str(actor), based_on=keep_based)  # fmt: skip
            write_chunks(conn, str(staged), res.doc, embed)
    conn.execute(
        text("""INSERT INTO policy_drafts (loan_type, body, origin, based_on, document_id, body_hash,
                    check_report, updated_by, updated_at)
                VALUES (:lt, :b, :o, :based, :doc, :h, CAST(:c AS jsonb), :u, now())
                ON CONFLICT (loan_type) DO UPDATE SET body = EXCLUDED.body, origin = EXCLUDED.origin,
                    based_on = EXCLUDED.based_on, document_id = EXCLUDED.document_id,
                    body_hash = EXCLUDED.body_hash, check_report = EXCLUDED.check_report,
                    updated_by = EXCLUDED.updated_by, updated_at = now()"""),
        {"lt": lt, "b": body, "o": keep_origin, "based": keep_based, "doc": staged, "h": h,
         "c": json.dumps(res.as_json(today), default=str), "u": actor},
    )  # fmt: skip
    if old is None or old.body_hash != h:
        _audit(conn, actor, "policy_draft_saved", staged,
               {"loan_type": lt, "origin": keep_origin, "errors": len(res.errors),
                "warnings": len(res.warnings)})  # fmt: skip
    view = draft_view(conn, lt, rules=rules, today=today)
    assert view is not None
    return view


def discard_draft(conn: Connection, lt: str, actor: UUID) -> None:
    lt = check_loan(lt)
    versions.lock(conn)
    if _draft_row(conn, lt) is None:
        raise KbError(404, "There is no draft for this policy.")
    conn.execute(text("DELETE FROM policy_drafts WHERE loan_type = :lt"), {"lt": lt})
    conn.execute(
        text("DELETE FROM policy_documents WHERE loan_type = :lt AND status = 'draft'"), {"lt": lt}
    )
    _audit(conn, actor, "policy_draft_discarded", None, {"loan_type": lt})


def edit_clause(
    conn: Connection, lt: str, *, action: str, clause_id: str | None, source_tag: str,
    title: str, body_text: str, after: str | None, topic: str | None, actor: UUID,
    rules: RuleSet, embed: Embed, today: date,
) -> dict[str, Any]:  # fmt: skip
    """Change one clause of the draft (or of the policy in force, which starts a draft)."""
    lt = check_loan(lt)
    d = _draft_row(conn, lt)
    base = d.body if d is not None else start_text(conn, lt, today)
    src = pa.SOURCES.get(source_tag.lower()) if source_tag else None
    if action != "remove" and (src is None or not title.strip() or not body_text.strip()):
        raise KbError(422, "A clause needs a source tag (public, RBI or sample), a title and text.")
    try:
        if action == "edit" and clause_id:
            body = pa.replace_clause(
                base, clause_id, source_tag=src or "sample", title=title, text=body_text
            )
        elif action == "remove" and clause_id:
            body = pa.remove_clause(base, clause_id)
        elif action == "add":
            known = {r[0] for r in conn.execute(
                text("""SELECT DISTINCT c.clause_id FROM policy_chunks c
                        JOIN policy_documents d ON d.id = c.policy_document_id WHERE d.loan_type = :lt"""),
                {"lt": lt})}  # fmt: skip
            known |= {m.group("id") for ln in base.split("\n") if (m := CLAUSE_HEADING.match(ln))}
            cid = (clause_id or "").strip().upper() or pa.next_free_id(
                pa.PREFIX[lt], (topic or "GEN").strip().upper(), known
            )
            if not pa.CLAUSE_ID_RE.match(cid) or pa.prefix_of(cid) != pa.PREFIX[lt]:
                raise KbError(422, f"A {lt} clause ID looks like {pa.PREFIX[lt]}-ELIG-05.")
            if any((m := CLAUSE_HEADING.match(ln)) and m["id"] == cid for ln in base.split("\n")):
                raise KbError(409, f"Clause {cid} is already in the draft.")
            body = pa.add_clause(base, clause_id=cid, source_tag=src or "sample", title=title,
                                 text=body_text, after=after or None)  # fmt: skip
        else:
            raise KbError(422, "Choose edit, add or remove, with a clause ID.")
    except KeyError as exc:
        raise KbError(404, f"Clause {exc.args[0]} is not in the draft.") from None
    return save_draft(
        conn, lt, body, origin="edit", actor=actor, rules=rules, embed=embed, today=today
    )


def restore(
    conn: Connection, doc_id: UUID, *, actor: UUID, rules: RuleSet, embed: Embed, today: date
) -> dict[str, Any]:
    r = _row(conn, doc_id)
    if r.status == "draft":
        raise KbError(409, "A draft cannot be restored; it is still being worked on.")
    if r.status == "active":
        raise KbError(409, "This is the version in force already.")
    if _draft_row(conn, r.loan_type) is not None:
        raise KbError(409, "Discard the current draft before restoring an older version.")
    doc = versions.load_doc(conn, r.id)
    body = pa.set_front(
        doc.raw, version=pa.next_label(_taken(conn, r.loan_type), today), effective_from=today
    )
    return save_draft(conn, r.loan_type, body, origin="restore", actor=actor, rules=rules,
                      embed=embed, today=today, based_on=str(r.id))  # fmt: skip


# --------------------------------------------------------------------------- checking
def _known(conn: Connection, docs: dict[str, str]) -> dict[str, str]:
    rows = conn.execute(
        text("""SELECT c.clause_id, d.loan_type FROM policy_chunks c
                JOIN policy_documents d ON d.id = c.policy_document_id
                WHERE d.id = ANY(CAST(:ids AS uuid[]))"""),
        {"ids": sorted(docs.values())},
    )  # fmt: skip
    return {r.clause_id: r.loan_type for r in rows}


METRICS = ("hit@1", "hit@3", "recall@5", "mrr", "citation_validity")
FILE_STATE = {
    "active": "imported, in force",
    "scheduled": "imported, scheduled",
    "superseded": "imported, replaced by a newer version",
    "retired": "imported, retired",
    "draft": "the label of the current draft",
}


def retrieval_check(conn: Connection, lt: str, *, factory: RetrieverFactory) -> dict[str, Any]:
    """Run the dev evaluation questions for this policy against the version in force and the
    draft, and keep the result with the hash of the text it was run on."""
    lt = check_loan(lt)
    d = _draft_row(conn, lt)
    if d is None:
        raise KbError(404, "There is no draft for this policy.")
    if d.document_id is None:
        raise KbError(409, "Fix the errors and save the draft before the retrieval check.")
    queries = [q for q in load_queries("dev") if lt == "common" or q.loan_type == lt]
    now_docs = versions.in_force(conn)
    draft_docs = {**now_docs, lt: str(d.document_id)}
    known_now, known_draft = _known(conn, now_docs), _known(conn, draft_docs)
    r_now, r_draft = factory(conn), factory(conn)
    r_now.docs, r_draft.docs = now_docs, draft_docs
    m_now = evaluate(conn, queries, rerank=True, retriever=r_now, known=known_now)
    m_draft = evaluate(conn, queries, rerank=True, retriever=r_draft, known=known_draft)
    errors, warnings = [], []
    if queries and m_draft["citation_validity"] < 1.0:
        errors.append("Search returned a clause that is not in the draft or the common policy "
                      "(citation validity below 100%).")  # fmt: skip
    for name in ("hit@1", "hit@3", "recall@5", "mrr"):
        if m_draft.get(name, 0.0) < m_now.get(name, 0.0) - 1e-9:
            warnings.append(f"{name} falls from {m_now[name]:.2f} to {m_draft[name]:.2f}.")
    gone = sorted({e for q in queries for e in q.expected if e not in known_draft})
    if gone:
        warnings.append(f"The evaluation questions expect clause(s) this draft removes ({', '.join(gone)}); "
                        "those questions now count as misses. Update data/rag/retrieval_eval.yaml "
                        "if the removal is intended.")  # fmt: skip
    report = {"queries": len(queries), "now": {k: m_now.get(k) for k in METRICS},
              "draft": {k: m_draft.get(k) for k in METRICS}, "errors": errors,
              "warnings": warnings, "hash": d.body_hash}  # fmt: skip
    conn.execute(
        text("""UPDATE policy_drafts SET retrieval_report = CAST(:r AS jsonb), retrieval_hash = :h
                WHERE loan_type = :lt"""),
        {"r": json.dumps(report), "h": d.body_hash, "lt": lt},
    )
    return report


def publish(
    conn: Connection, lt: str, *, actor: UUID, reason: str, accept_warnings: bool,
    rules: RuleSet, today: date,
) -> dict[str, Any]:  # fmt: skip
    lt = check_loan(lt)
    versions.lock(conn)
    d = _draft_row(conn, lt)
    if d is None:
        raise KbError(404, "There is no draft for this policy.")
    view = draft_view(conn, lt, rules=rules, today=today)
    assert view is not None
    if view["blockers"]:
        raise KbError(409, " ".join(view["blockers"]))
    if view["warning_count"] and not accept_warnings:
        raise KbError(409, "Tick that you have read the warnings before publishing.")
    res = run_check(conn, lt, d.body, rules=rules, today=today)
    doc = res.doc
    assert doc is not None
    staged = str(d.document_id)
    future = doc.effective_from > today
    other = conn.execute(
        text(
            "SELECT version, effective_from FROM policy_documents WHERE loan_type = :lt AND status = 'scheduled'"
        ),
        {"lt": lt},
    ).first()
    if other is not None:  # it would replace this one on its date, an older label over a newer
        raise KbError(409, f"Version {other.version} is scheduled for {other.effective_from}. Retire "
                      "it first (its text can be restored into a draft later).")  # fmt: skip
    conn.execute(
        text("""UPDATE policy_documents SET status = :s, reason = :why, published_by = :u,
                    published_at = now(), indexed_at = now()
                WHERE id = :i"""),
        {"s": "scheduled" if future else "draft", "why": reason, "u": actor, "i": staged},
    )  # fmt: skip
    switched: dict[str, Any] = {"replaced": None, "paused": []}
    if not future:
        switched = versions.switch(conn, lt, staged, rules=rules, actor=actor, note="published")
    conn.execute(text("DELETE FROM policy_drafts WHERE loan_type = :lt"), {"lt": lt})
    ch = res.changes or {"added": [c.clause_id for c in doc.clauses], "changed": [], "removed": []}
    _audit(conn, actor, "policy_published", staged,
           {"loan_type": lt, "version": doc.version, "status": "scheduled" if future else "active",
            "effective_from": doc.effective_from, "reason": reason, "added": ch["added"],
            "changed": ch["changed"], "removed": ch["removed"],
            "warnings": [w.code for w in res.warnings], "precedents_paused": len(switched["paused"])},
           before={"version": switched["replaced"]})  # fmt: skip
    return {"id": staged, "version": doc.version, "status": "scheduled" if future else "active",
            "effective_from": doc.effective_from, "replaced": switched["replaced"],
            "precedents_paused": len(switched["paused"])}  # fmt: skip


def retire(conn: Connection, doc_id: UUID, *, actor: UUID, reason: str) -> dict[str, Any]:
    versions.lock(conn)
    r = _row(conn, doc_id)
    if r.status == "draft":
        raise KbError(409, "A draft is discarded, not retired.")
    if r.status == "active":
        raise KbError(409, "The version in force cannot be retired. Publish a new version or "
                      "restore an older one; this one is then kept as superseded.")  # fmt: skip
    if r.status == "retired":
        raise KbError(409, "This version is already retired.")
    conn.execute(
        text("""UPDATE policy_documents SET status = 'retired', retired_by = :u, retired_at = now(),
                    retired_reason = :why WHERE id = :i"""),
        {"u": actor, "why": reason, "i": doc_id},
    )  # fmt: skip
    _audit(conn, actor, "policy_retired", doc_id,
           {"loan_type": r.loan_type, "version": r.version, "reason": reason}, before={"status": r.status})  # fmt: skip
    return {"id": str(doc_id), "status": "retired"}


# --------------------------------------------------------------------------- uploads
def convert(
    conn: Connection, lt: str, filename: str, data: bytes, *, rules: RuleSet, today: date
) -> dict[str, Any]:
    lt = check_loan(lt)
    try:
        got = pa.convert_upload(filename, data)
    except pa.ConversionError as exc:
        raise KbError(422, str(exc)) from None
    res = run_check(conn, lt, got.text, rules=rules, today=today)
    headings = sum(
        1
        for ln in got.text.split("\n")
        if CLAUSE_HEADING.match(ln) is not None or pa.loose_heading(ln) is not None
    )
    return {"text": got.text, "kind": got.kind, "notes": got.notes,
            "check": res.as_json(today), "suggest_legacy": headings == 0}  # fmt: skip


def legacy(conn: Connection, lt: str, body: str, *, today: date) -> dict[str, Any]:
    lt = check_loan(lt)
    ids = {r[0] for r in conn.execute(
        text("""SELECT DISTINCT c.clause_id FROM policy_chunks c
                JOIN policy_documents d ON d.id = c.policy_document_id WHERE d.loan_type = :lt"""),
        {"lt": lt})}  # fmt: skip
    md, mapping = pa.legacy_import(body, lt, current=_current(conn, lt), known_ids=ids,
                                   taken=_taken(conn, lt), today=today)  # fmt: skip
    return {"text": md, "mapping": mapping}


# --------------------------------------------------------------------------- search and index
def _hit(h: Any) -> dict[str, Any]:
    return {"clause_id": h.clause_id, "title": h.title, "text": h.text, "loan_type": h.doc_loan_type,
            "version": h.doc_version, "relevance": round(h.relevance, 4)}  # fmt: skip


def search(
    conn: Connection, q: str, lt: str, *, factory: RetrieverFactory, draft: bool
) -> dict[str, Any]:
    lt = check_loan(lt)
    if lt == "common":
        raise KbError(422, "Pick a loan type: search covers the common policy plus that loan type.")
    now_docs = versions.in_force(conn)
    r = factory(conn)
    r.docs = now_docs
    out: dict[str, Any] = {"active": [_hit(h) for h in r.search(q, lt, top_k=5)], "draft": None}
    if draft:
        staged = {row.loan_type: str(row.document_id) for row in conn.execute(
            text("SELECT loan_type, document_id FROM policy_drafts WHERE document_id IS NOT NULL"))}  # fmt: skip
        if staged.get(lt) or staged.get("common"):
            rd = factory(conn)
            rd.docs = {**now_docs, **{k: v for k, v in staged.items() if k in (lt, "common")}}
            out["draft"] = [_hit(h) for h in rd.search(q, lt, top_k=5)]
    return out


def index_health(conn: Connection) -> dict[str, Any]:
    rows = conn.execute(
        text("""SELECT d.loan_type, d.version, d.status, d.effective_from, d.indexed_at,
                       count(c.id) AS clauses, count(c.embedding) AS embedded
                FROM policy_documents d LEFT JOIN policy_chunks c ON c.policy_document_id = d.id
                WHERE d.status IN ('active', 'scheduled', 'draft')
                GROUP BY d.id ORDER BY d.loan_type, d.status"""),
    ).all()  # fmt: skip
    last = conn.execute(
        text("""SELECT a.at, u.name FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id
                WHERE a.action = 'policy_reindex' ORDER BY a.at DESC LIMIT 1"""),
    ).first()  # fmt: skip
    in_db = {(r.loan_type, r.version): r.status for r in conn.execute(
        text("SELECT loan_type, version, status FROM policy_documents"))}  # fmt: skip
    files = []
    try:
        docs = load_all()
    except PolicyFormatError as exc:
        docs = []
        files.append({"file": "data/policy", "version": "", "state": f"cannot be read: {exc}"})
    for doc in docs:
        newest = max(
            (v for (lt, v) in in_db if lt == doc.loan_type), key=pa.label_key, default=None
        )
        state = FILE_STATE.get(in_db.get((doc.loan_type, doc.version)) or "")
        if state is None:
            state = ("newer than the database: re-index imports it"
                     if newest is None or pa.label_key(doc.version) > pa.label_key(newest)
                     else "older than the database: ignored")  # fmt: skip
        files.append({"file": doc.path.name if doc.path else doc.loan_type, "loan_type": doc.loan_type,
                      "version": doc.version, "state": state})  # fmt: skip
    cfg = load_rag_config()
    return {
        "documents": [{"loan_type": r.loan_type, "version": r.version, "status": r.status,
                       "effective_from": r.effective_from, "indexed_at": r.indexed_at,
                       "clauses": r.clauses, "embedded": r.embedded} for r in rows],
        "last_reindex": None if last is None else {"at": last.at, "by": last.name},
        "files": files,
        "settings": {"embedding_model": cfg.embedding_model, "reranker_model": cfg.reranker_model,
                     "top_k": cfg.top_k, "candidates": cfg.candidates},
    }  # fmt: skip


def run_reindex(conn: Connection, *, actor: UUID, force: bool, rules: RuleSet, embed: Embed,
                today: date) -> dict[str, Any]:  # fmt: skip
    report = reindex(conn, embed=embed, force=force, today=today, rules=rules, actor=str(actor))
    lost = check_rule_clauses(conn, rules)
    if lost:  # the request's transaction rolls back
        raise KbError(409, "Re-index stopped: rules would cite clauses missing from the policy "
                      f"in force ({', '.join(lost)}). Nothing was changed.")  # fmt: skip
    return report.as_json()


def evaluate_in_force(conn: Connection, *, factory: RetrieverFactory) -> dict[str, Any]:
    queries = load_queries("dev")
    docs = versions.in_force(conn)
    r = factory(conn)
    r.docs = docs
    metrics = evaluate(conn, queries, rerank=True, retriever=r, known=_known(conn, docs))
    stored = json.loads(BASELINE_PATH.read_text()) if BASELINE_PATH.exists() else {}
    targets = stored.get("targets", {})
    misses = check_targets(metrics, targets)
    return {"metrics": metrics, "targets": targets, "misses": misses, "ok": not misses}
