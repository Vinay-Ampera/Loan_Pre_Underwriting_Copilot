"""The intake desk's upload step, shared by the officer's route and the applicant's link.

For every file in a zip, a folder or a list: unpack safely, run the normal upload checks, read the
file once (text layer or OCR), classify it, extract its fields locally and save that result next
to the file so Extraction never reads it again; apply the duplicate rules; store accepted files
under generated names; then work out which person each file belongs to. Nothing is trusted from
a name. A rejected or repeated file is not stored, only its row (with the reason) is.
"""

import json
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.api.deps import write_audit
from app.api.filestore import FileStore
from app.api.schemas import CO_APPLICANT
from app.core.config import Settings
from app.intake import archive, readcache
from app.intake.duplicates import CaseDocuments, Verdict, sha256_hex
from app.intake.inventory import Item, assign_roles, needed_from
from app.intake.pipeline import process_file
from app.scoring.rules import RuleSet

EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}


def read_parts(files: list[Any], settings: Settings) -> list[tuple[str, bytes]]:
    """Read the uploaded parts into memory, stopping as soon as together they pass what one case
    may hold (a request cannot make the server hold more than that)."""
    cap = (settings.max_case_upload_mb + 1) * 1024 * 1024
    total = 0
    parts: list[tuple[str, bytes]] = []
    for f in files:
        data = f.file.read(cap - total + 1)
        total += len(data)
        if total > cap:
            raise archive.ArchiveError(
                "too_large", "The upload is larger than the size limit for one case."
            )
        parts.append(((f.filename or "file")[:300], data))
    return parts


def case_date(form: dict[str, Any]) -> date:
    try:
        return date.fromisoformat(form["application_date"])
    except (KeyError, ValueError):
        return date.today()


def _unique_name(label: str, taken: set[str]) -> str:
    """The pipeline tells files apart by (person, name): keep names distinct across the case."""
    if label not in taken:
        return label
    stem, dot, ext = label.rpartition(".")
    n = 2
    while True:
        candidate = f"{stem} ({n}).{ext}" if dot else f"{label} ({n})"
        if candidate not in taken:
            return candidate
        n += 1


def _insert(conn: Connection, case_id: UUID, **v: Any) -> UUID:
    defaults: dict[str, Any] = {
        "path": None,
        "mime": "application/octet-stream",
        "pages": None,
        "chk": {},
        "sha": None,
        "rej": None,
        "dup": None,
        "kind": None,
        "cls": None,
    }
    p = {**defaults, **v}
    return conn.execute(  # type: ignore[no-any-return]
        text("""INSERT INTO documents (case_id, doc_type, classification, file_path, original_name,
                    mime, page_count, sha256, upload_checks, status, reject_reason, duplicate_of,
                    duplicate_kind, uploaded_at)
                VALUES (:c, :t, :cls, :path, :name, :mime, :pages, :sha, CAST(:chk AS jsonb),
                        :st, :rej, :dup, :kind, clock_timestamp()) RETURNING id"""),
        {"c": case_id, "t": p["type"], "cls": p["cls"], "path": p["path"], "name": p["name"],
         "mime": p["mime"], "pages": p["pages"], "sha": p["sha"], "chk": json.dumps(p["chk"]),
         "st": p["status"], "rej": p["rej"], "dup": p["dup"], "kind": p["kind"]},
    ).scalar_one()  # fmt: skip


def reassign_roles(
    conn: Connection, store: FileStore, rs: RuleSet, case: Any, form: dict[str, Any]
) -> None:  # fmt: skip
    """File every accepted file the officer has not filed by hand to a person."""
    rows = list(conn.execute(
        text("""SELECT id, doc_type, file_path, role, role_source FROM documents
                WHERE case_id = :c AND status = 'accepted' ORDER BY uploaded_at, original_name"""),
        {"c": case.id}))  # fmt: skip
    co_rule = CO_APPLICANT[case.loan_type]
    applicants = form.get("applicants")
    if applicants and not any(a["role"] == "co" for a in applicants):
        co_rule = "not_allowed"  # the form is saved and has no co-applicant
    roles = ["primary", "co"] if co_rule != "not_allowed" else ["primary"]
    items = []
    for i, r in enumerate(rows):
        doc = readcache.peek(store.get_read_result(r.file_path)) if r.file_path else None
        fields = {f.name: f.value for f in doc.fields} if doc else {}
        fixed = r.role if r.role_source == "officer" else None
        items.append(Item(str(r.id), r.doc_type, fields, i, fixed))
    chosen = assign_roles(
        items, co_rule=co_rule, needed_from=needed_from(rs, case.loan_type, roles)
    )
    for r in rows:
        if r.role_source == "officer":
            continue
        conn.execute(
            text("""UPDATE documents d SET role = :r,
                        applicant_id = (SELECT a.id FROM applicants a
                                        WHERE a.case_id = d.case_id AND a.role = :r)
                    WHERE d.id = :d"""),
            {"r": chosen.get(str(r.id)), "d": r.id},
        )


def ingest(
    conn: Connection, store: FileStore, settings: Settings, rs: RuleSet, case: Any,
    parts: list[tuple[str, bytes]], *, actor: UUID | None, source: str,
    max_files: int | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """Returns one result per file. Raises `archive.ArchiveError` for an unsafe or too large
    upload (nothing has been written by then)."""
    form: dict[str, Any] = case.form_data
    as_of = case_date(form)
    max_bytes = settings.max_upload_mb * 1024 * 1024
    case_cap = settings.max_case_upload_mb * 1024 * 1024
    used = store.case_bytes(case.id)
    expanded = archive.expand(parts, archive.Limits(
        max_files=min(settings.max_files_per_upload, max_files or settings.max_files_per_upload),
        max_member_bytes=max_bytes,
        max_total_bytes=max(case_cap - used, 0)))  # fmt: skip

    existing = list(conn.execute(
        text("""SELECT id, original_name, sha256, file_path, status FROM documents
                WHERE case_id = :c ORDER BY uploaded_at"""), {"c": case.id}))  # fmt: skip
    registry = CaseDocuments()
    by_sha: dict[str, tuple[UUID, str]] = {}
    names = {r.original_name for r in existing}
    ids_by_name: dict[str, UUID] = {}
    for r in existing:
        if r.status != "accepted":
            continue
        doc = readcache.peek(store.get_read_result(r.file_path)) if r.file_path else None
        registry.remember(r.original_name, r.sha256 or "", doc)
        if r.sha256:
            by_sha[r.sha256] = (r.id, r.original_name)
        ids_by_name[r.original_name] = r.id

    results: list[dict[str, Any]] = []

    def record(row_id: UUID, name: str, status: str, code: str | None, message: str,
               doc_type: str = "", warnings: list[str] | None = None,
               dup_of: str | None = None) -> None:  # fmt: skip
        results.append({"id": row_id, "name": name, "status": status, "code": code,
                        "message": message, "doc_type": doc_type, "warnings": warnings or [],
                        "duplicate_of": dup_of})  # fmt: skip
        write_audit(conn, actor, "document_uploaded" if status in ("accepted", "warning")
                    else "document_rejected" if status == "rejected" else "document_ignored",
                    "case", case.id, after={"result": status, "code": code, "via": source,
                                            "doc_type": doc_type or None})  # fmt: skip

    for s in expanded.skipped:
        rid = _insert(
            conn,
            case.id,
            type="unknown",
            name=_unique_name(s.label, names),
            status="rejected",
            rej=s.code,
            chk={"message": s.message, "warnings": []},
        )
        record(rid, s.label, "rejected", s.code, s.message)

    for m in expanded.members:
        sha = sha256_hex(m.data)
        name = _unique_name(m.label, names)
        if sha in by_sha:
            first_id, first_name = by_sha[sha]
            msg = f"The same file is already in this case ({first_name}). It was ignored."
            rid = _insert(
                conn,
                case.id,
                type="unknown",
                name=name,
                sha=sha,
                status="ignored",
                dup=first_id,
                kind="exact",
                chk={"message": msg, "warnings": []},
            )
            names.add(name)
            record(rid, m.label, "ignored", "duplicate", msg, dup_of=first_name)
            continue
        res = process_file(m.data, m.label, as_of=as_of, max_bytes=max_bytes)
        if res.accepted and used + len(m.data) > case_cap:
            res.upload.accepted, res.upload.reject_code = False, "too_large"
            res.upload.message = "The case has reached its total upload limit."
        if not res.accepted or res.document is None:
            msg = res.upload.message or "The file could not be accepted."
            rid = _insert(
                conn,
                case.id,
                type="unknown",
                name=name,
                sha=sha,
                status="rejected",
                rej=res.upload.reject_code,
                mime=res.upload.mime or "application/octet-stream",
                chk={"message": msg, "warnings": []},
            )
            names.add(name)
            record(rid, m.label, "rejected", res.upload.reject_code, msg)
            continue
        doc = res.document
        decision = registry.check(name, sha, doc)
        kind = doc.doc_type.value
        if decision.verdict in (Verdict.SAME_DOCUMENT, Verdict.EXACT_DUPLICATE):
            msg = f"{decision.message}. It was ignored."
            rid = _insert(
                conn,
                case.id,
                type=kind,
                cls=kind,
                name=name,
                sha=sha,
                status="ignored",
                dup=ids_by_name.get(decision.matched or ""),
                kind="same_document",
                chk={"message": msg, "warnings": []},
            )
            names.add(name)
            record(rid, m.label, "ignored", "duplicate", msg, kind, dup_of=decision.matched)
            continue
        key = store.put(case.id, m.data, EXT[res.upload.mime or "application/pdf"])
        store.put_read_result(key, readcache.dump(res, as_of))
        used += len(m.data)
        conflict = decision.verdict is Verdict.CONFLICTING
        warnings = list(res.upload.warnings)
        msg = ("Accepted, but the image is slightly blurry. Fields read from it may be flagged "
               "for review." if warnings else "Accepted.")  # fmt: skip
        if conflict:
            msg = f"Accepted, but {decision.message}. It will be flagged for review."
        rid = _insert(
            conn,
            case.id,
            type=kind,
            cls=kind,
            name=name,
            path=key,
            mime=res.upload.mime or "",
            pages=len(res.upload.pages) or None,
            sha=sha,
            status="accepted",
            dup=ids_by_name.get(decision.matched or "") if conflict else None,
            kind="conflict" if conflict else None,
            chk={"warnings": warnings, "blur_score": res.upload.blur_score, "message": msg},
        )
        registry.remember(name, sha, doc)
        names.add(name)
        by_sha[sha] = (rid, name)
        ids_by_name[name] = rid
        record(
            rid,
            m.label,
            "warning" if warnings or conflict else "accepted",
            None,
            msg,
            kind,
            warnings,
        )

    if any(r["status"] in ("accepted", "warning") for r in results):
        reassign_roles(conn, store, rs, case, form)
        if case.status == "draft":
            conn.execute(text("UPDATE cases SET status = 'uploaded', updated_at = now() "
                              "WHERE id = :c"), {"c": case.id})  # fmt: skip
    roles = {str(x.id): x.role for x in conn.execute(
        text("SELECT id, role FROM documents WHERE case_id = :c"), {"c": case.id})}  # fmt: skip
    for out in results:
        out["role"] = roles.get(str(out["id"]))
    write_audit(conn, actor, "intake_upload", "case", case.id,
                after={"files": len(results), "via": source, "junk_skipped": expanded.junk,
                       "accepted": sum(r["status"] in ("accepted", "warning") for r in results),
                       "rejected": sum(r["status"] == "rejected" for r in results),
                       "ignored": sum(r["status"] == "ignored" for r in results)})  # fmt: skip
    return results
