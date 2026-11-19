"""The intake desk's upload step, shared by the officer's route and the applicant's link.

For every file in a zip, a folder or a list: unpack safely, run the normal upload checks, read the
file once (text layer or OCR), classify it, extract its fields locally and save that result next
to the file so Extraction never reads it again; apply the duplicate rules; store accepted files
under generated names; then work out which person each file belongs to. Nothing is trusted from
a name. A rejected or repeated file is not stored, only its row (with the reason) is.

A PDF of several pages is first read page by page (Part D): when its pages are different
documents (a PAN card, then an Aadhaar card, then a statement) it is stored as it came, as a
"bundle" row with a proposed split, and nothing else happens until the officer confirms the
split. Each piece then goes through the same path as a file of its own, linked to the original
by `parent_document_id` and its page range.
"""

import json
from datetime import date
from typing import Any
from uuid import UUID

import pymupdf
from sqlalchemy import Connection, text

from app.api.deps import write_audit
from app.api.filestore import FileStore
from app.api.schemas import CO_APPLICANT
from app.core.config import Settings
from app.intake import archive, bundle, readcache, upload
from app.intake.duplicates import CaseDocuments, Verdict, sha256_hex
from app.intake.inventory import Item, assign_roles, needed_from
from app.intake.models import UploadCheck
from app.intake.pipeline import process_file
from app.intake.reader import ReadDocument, read_document
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
        "src": "detected",
        "parent": None,
        "first": None,
        "last": None,
    }
    p = {**defaults, **v}
    return conn.execute(
        text("""INSERT INTO documents (case_id, doc_type, classification, type_source, file_path,
                    original_name, mime, page_count, sha256, upload_checks, status, reject_reason,
                    duplicate_of, duplicate_kind, parent_document_id, page_from, page_to,
                    uploaded_at)
                VALUES (:c, :t, :cls, :src, :path, :name, :mime, :pages, :sha,
                        CAST(:chk AS jsonb), :st, :rej, :dup, :kind, :parent, :first, :last,
                        clock_timestamp()) RETURNING id"""),
        {"c": case_id, "t": p["type"], "cls": p["cls"], "src": p["src"], "path": p["path"],
         "name": p["name"], "mime": p["mime"], "pages": p["pages"], "sha": p["sha"],
         "chk": json.dumps(p["chk"]), "st": p["status"], "rej": p["rej"], "dup": p["dup"],
         "kind": p["kind"], "parent": p["parent"], "first": p["first"], "last": p["last"]},
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


PENDING_BUNDLE_MESSAGE = (
    "A PDF with several documents is waiting for you to confirm how it is split. "
    "Confirm the split (or remove the PDF) before going on."
)


def pending_bundles(conn: Connection, case_id: UUID) -> int:
    """Bundles stored but not yet split. Nothing can be submitted or resumed while one is open."""
    return int(conn.execute(
        text("SELECT count(*) FROM documents WHERE case_id = :c AND status = 'bundle'"),
        {"c": case_id}).scalar_one())  # fmt: skip


def _page_count(data: bytes) -> int:
    """Pages of a readable, unprotected PDF; 0 for anything else (the normal checks name why)."""
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            return 0 if doc.needs_pass or doc.is_encrypted else int(doc.page_count)
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        return 0


def piece_label(parent_name: str, first: int, last: int) -> str:
    stem = parent_name.rsplit(".", 1)[0]
    where = f"page {first}" if first == last else f"pages {first}-{last}"
    return f"{stem} ({where}).pdf"


class Desk:
    """One upload step on one case. Holds what the case already has (so a repeat is found whether
    it arrives in this upload or an earlier one) and files each file or piece in turn."""

    def __init__(
        self, conn: Connection, store: FileStore, settings: Settings, case: Any, *,
        actor: UUID | None, source: str, exclude: UUID | None = None,
    ) -> None:  # fmt: skip
        self.conn, self.store, self.settings, self.case = conn, store, settings, case
        self.actor, self.source = actor, source
        self.form: dict[str, Any] = case.form_data
        self.as_of = case_date(self.form)
        self.max_bytes = settings.max_upload_mb * 1024 * 1024
        self.bundle_bytes = max(settings.bundle_max_mb * 1024 * 1024, self.max_bytes)
        self.case_cap = settings.max_case_upload_mb * 1024 * 1024
        self.used = store.case_bytes(case.id)
        self.registry = CaseDocuments()
        self.by_sha: dict[str, tuple[UUID, str]] = {}
        self.ids_by_name: dict[str, UUID] = {}
        self.results: list[dict[str, Any]] = []
        existing = list(conn.execute(
            text("""SELECT id, original_name, sha256, file_path, status FROM documents
                    WHERE case_id = :c ORDER BY uploaded_at"""), {"c": case.id}))  # fmt: skip
        self.names = {r.original_name for r in existing}
        for r in existing:
            if r.id == exclude or r.status not in ("accepted", "bundle", "split"):
                continue
            if r.sha256:
                self.by_sha[r.sha256] = (r.id, r.original_name)
            if r.status == "accepted":
                doc = readcache.peek(store.get_read_result(r.file_path)) if r.file_path else None
                self.registry.remember(r.original_name, r.sha256 or "", doc)
                self.ids_by_name[r.original_name] = r.id

    # ---------------------------------------------------------------- results
    def record(self, row_id: UUID, name: str, status: str, code: str | None, message: str,
               doc_type: str = "", warnings: list[str] | None = None,
               dup_of: str | None = None) -> None:  # fmt: skip
        self.results.append({"id": row_id, "name": name, "status": status, "code": code,
                             "message": message, "doc_type": doc_type,
                             "warnings": warnings or [], "duplicate_of": dup_of})  # fmt: skip
        action = {"accepted": "document_uploaded", "warning": "document_uploaded",
                  "rejected": "document_rejected", "bundle": "bundle_uploaded"}.get(
            status, "document_ignored")  # fmt: skip
        write_audit(self.conn, self.actor, action, "case", self.case.id,
                    after={"result": status, "code": code, "via": self.source,
                           "doc_type": doc_type or None})  # fmt: skip

    def skipped(self, s: archive.Skipped) -> None:
        rid = _insert(self.conn, self.case.id, type="unknown", name=_unique_name(s.label, self.names),
                      status="rejected", rej=s.code, chk={"message": s.message, "warnings": []})  # fmt: skip
        self.record(rid, s.label, "rejected", s.code, s.message)

    def _reject(self, label: str, name: str, sha: str, code: str | None, message: str,
                mime: str | None) -> None:  # fmt: skip
        rid = _insert(self.conn, self.case.id, type="unknown", name=name, sha=sha,
                      status="rejected", rej=code, mime=mime or "application/octet-stream",
                      chk={"message": message, "warnings": []})  # fmt: skip
        self.names.add(name)
        self.record(rid, label, "rejected", code, message)

    # ---------------------------------------------------------------- bundles
    def _look_for_bundle(
        self, label: str, name: str, sha: str, data: bytes
    ) -> tuple[bool, tuple[UploadCheck, ReadDocument] | None]:  # fmt: skip
        """(handled, pre). A PDF of two or more pages is read page by page once. If its pages are
        several documents it is stored as a bundle awaiting the officer's split (handled). If
        they are one document the read is handed on so the file is not read again."""
        if (
            not self.settings.bundle_split_enabled
            or not label.lower().endswith(".pdf")
            or upload.sniff_mime(data) != "application/pdf"
            or _page_count(data) < bundle.MIN_PAGES
        ):
            return False, None
        check = upload.check_upload(data, label, self.bundle_bytes,
                                    bundle_pages=self.settings.bundle_max_pages)  # fmt: skip
        if not check.accepted:
            self._reject(label, name, sha, check.reject_code, check.message, check.mime)
            return True, None
        if self.used + len(data) > self.case_cap:
            self._reject(label, name, sha, "too_large",
                         "The case has reached its total upload limit.", check.mime)  # fmt: skip
            return True, None
        read = read_document(data, check)
        segments = bundle.propose(read.pages)
        if not bundle.is_bundle(segments):
            if len(data) > self.max_bytes:  # one document keeps the single-document limits
                self._reject(
                    label, name, sha, "too_large", upload.MESSAGES["too_large"], check.mime
                )
                return True, None
            if len(check.pages) > upload.MAX_PAGES:
                self._reject(label, name, sha, "too_many_pages",
                             upload.MESSAGES["too_many_pages"], check.mime)  # fmt: skip
                return True, None
            return False, (check, read)
        count = len(segments)
        msg = (f"This PDF has {len(check.pages)} pages and looks like {count} documents. "
               "Check how it is split, then confirm.")  # fmt: skip
        key = self.store.put(self.case.id, data, ".pdf")
        found = [s.as_dict() for s in segments]
        rid = _insert(self.conn, self.case.id, type="unknown", name=name, path=key,
                      mime="application/pdf", pages=len(check.pages), sha=sha, status="bundle",
                      chk={"message": msg, "warnings": list(check.warnings),
                           "bundle": {"pages": len(check.pages), "segments": found,
                                      "proposed": found}})  # fmt: skip
        self.used += len(data)
        self.names.add(name)
        self.by_sha[sha] = (rid, name)
        self.record(rid, label, "bundle", "bundle", msg, warnings=list(check.warnings))
        return True, None

    # ---------------------------------------------------------------- one file or piece
    def add(self, label: str, data: bytes, *,
            pre: tuple[UploadCheck, ReadDocument] | None = None,
            parent: tuple[UUID, int, int] | None = None,
            officer_type: str | None = None) -> None:  # fmt: skip
        """File one file (or one piece of a bundle: `parent` is the original and the page range)."""
        case = self.case
        sha = sha256_hex(data)
        name = _unique_name(label, self.names)
        link = {"parent": parent[0], "first": parent[1], "last": parent[2]} if parent else {}
        if sha in self.by_sha:
            first_id, first_name = self.by_sha[sha]
            msg = f"The same file is already in this case ({first_name}). It was ignored."
            rid = _insert(self.conn, case.id, type="unknown", name=name, sha=sha, status="ignored",
                          dup=first_id, kind="exact", chk={"message": msg, "warnings": []}, **link)  # fmt: skip
            self.names.add(name)
            self.record(rid, label, "ignored", "duplicate", msg, dup_of=first_name)
            return
        if parent is None and pre is None:
            handled, pre = self._look_for_bundle(label, name, sha, data)
            if handled:
                return
        res = process_file(data, label, as_of=self.as_of, max_bytes=self.max_bytes, pre=pre,
                           from_bundle=parent is not None)  # fmt: skip
        if res.accepted and parent is None and self.used + len(data) > self.case_cap:
            res.upload.accepted, res.upload.reject_code = False, "too_large"
            res.upload.message = "The case has reached its total upload limit."
        if not res.accepted or res.document is None:
            msg = res.upload.message or "The file could not be accepted."
            rid = _insert(self.conn, case.id, type="unknown", name=name, sha=sha, status="rejected",
                          rej=res.upload.reject_code, mime=res.upload.mime or "application/octet-stream",
                          chk={"message": msg, "warnings": []}, **link)  # fmt: skip
            self.names.add(name)
            self.record(rid, label, "rejected", res.upload.reject_code, msg)
            return
        doc = res.document
        decision = self.registry.check(name, sha, doc)
        kind = doc.doc_type.value
        if decision.verdict in (Verdict.SAME_DOCUMENT, Verdict.EXACT_DUPLICATE):
            msg = f"{decision.message}. It was ignored."
            rid = _insert(self.conn, case.id, type=kind, cls=kind, name=name, sha=sha,
                          status="ignored", dup=self.ids_by_name.get(decision.matched or ""),
                          kind="same_document", chk={"message": msg, "warnings": []}, **link)  # fmt: skip
            self.names.add(name)
            self.record(rid, label, "ignored", "duplicate", msg, kind, dup_of=decision.matched)
            return
        key = self.store.put(case.id, data, EXT[res.upload.mime or "application/pdf"])
        self.store.put_read_result(key, readcache.dump(res, self.as_of))
        self.used += len(data)
        conflict = decision.verdict is Verdict.CONFLICTING
        warnings = list(res.upload.warnings)
        msg = ("Accepted, but the image is slightly blurry. Fields read from it may be flagged "
               "for review." if warnings else "Accepted.")  # fmt: skip
        if conflict:
            msg = f"Accepted, but {decision.message}. It will be flagged for review."
        chosen = officer_type if officer_type and officer_type != kind else None
        rid = _insert(
            self.conn, case.id, type=chosen or kind, cls=kind, src="officer" if chosen else "detected",
            name=name, path=key, mime=res.upload.mime or "", pages=len(res.upload.pages) or None,
            sha=sha, status="accepted",
            dup=self.ids_by_name.get(decision.matched or "") if conflict else None,
            kind="conflict" if conflict else None,
            chk={"warnings": warnings, "blur_score": res.upload.blur_score, "message": msg},
            **link,
        )  # fmt: skip
        self.registry.remember(name, sha, doc)
        self.names.add(name)
        self.by_sha[sha] = (rid, name)
        self.ids_by_name[name] = rid
        self.record(rid, label, "warning" if warnings or conflict else "accepted", None, msg,
                    chosen or kind, warnings)  # fmt: skip

    # ---------------------------------------------------------------- the end of the step
    def finish(self, rs: RuleSet, audit_action: str, extra: dict[str, Any]) -> list[dict[str, Any]]:
        conn, case = self.conn, self.case
        if any(r["status"] in ("accepted", "warning") for r in self.results):
            reassign_roles(conn, self.store, rs, case, self.form)
            if case.status == "draft":
                conn.execute(text("UPDATE cases SET status = 'uploaded', updated_at = now() "
                                  "WHERE id = :c"), {"c": case.id})  # fmt: skip
        roles = {str(x.id): x.role for x in conn.execute(
            text("SELECT id, role FROM documents WHERE case_id = :c"), {"c": case.id})}  # fmt: skip
        for out in self.results:
            out["role"] = roles.get(str(out["id"]))
        n = self.results
        write_audit(conn, self.actor, audit_action, "case", case.id,
                    after={"files": len(n), "via": self.source, **extra,
                           "accepted": sum(r["status"] in ("accepted", "warning") for r in n),
                           "rejected": sum(r["status"] == "rejected" for r in n),
                           "ignored": sum(r["status"] == "ignored" for r in n),
                           "bundles": sum(r["status"] == "bundle" for r in n)})  # fmt: skip
        return self.results


def ingest(
    conn: Connection, store: FileStore, settings: Settings, rs: RuleSet, case: Any,
    parts: list[tuple[str, bytes]], *, actor: UUID | None, source: str,
    max_files: int | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """Returns one result per file. Raises `archive.ArchiveError` for an unsafe or too large
    upload (nothing has been written by then)."""
    max_bytes = settings.max_upload_mb * 1024 * 1024
    case_cap = settings.max_case_upload_mb * 1024 * 1024
    member_cap = max(max_bytes, settings.bundle_max_mb * 1024 * 1024) \
        if settings.bundle_split_enabled else max_bytes  # fmt: skip
    expanded = archive.expand(parts, archive.Limits(
        max_files=min(settings.max_files_per_upload, max_files or settings.max_files_per_upload),
        max_member_bytes=member_cap,
        max_total_bytes=max(case_cap - store.case_bytes(case.id), 0)))  # fmt: skip
    desk = Desk(conn, store, settings, case, actor=actor, source=source)
    for s in expanded.skipped:
        desk.skipped(s)
    for m in expanded.members:
        desk.add(m.label, m.data)
    return desk.finish(rs, "intake_upload", {"junk_skipped": expanded.junk})


def confirm_split(
    conn: Connection, store: FileStore, settings: Settings, rs: RuleSet, case: Any,
    original: Any, segments: list[bundle.Segment], *, actor: UUID,
) -> list[dict[str, Any]]:  # fmt: skip
    """Cut the stored bundle at the officer's split and file every piece as a document of its own
    (same checks, same duplicate rules). The original stays on disk and keeps its row (status
    'split'). The bundle is read once more here: raw page text is never kept between the two
    steps."""
    data = store.read(original.file_path)
    desk = Desk(conn, store, settings, case, actor=actor, source="bundle_split",
                exclude=original.id)  # fmt: skip
    whole = len(segments) == 1
    check = upload.check_upload(data, original.original_name, desk.bundle_bytes,
                                bundle_pages=settings.bundle_max_pages)  # fmt: skip
    if not check.accepted:
        raise bundle.SplitError(check.message)
    read = read_document(data, check)
    for seg in segments:
        piece = bundle.cut(data, seg)
        label = piece_label(original.original_name, seg.page_from, seg.page_to)
        if whole:  # the officer says it is one document: file the PDF as it is
            desk.add(label, piece, pre=(check, read), parent=(original.id, 1, seg.page_to),
                     officer_type=seg.doc_type)  # fmt: skip
            continue
        one = upload.check_upload(piece, label, desk.max_bytes)
        if not one.accepted:
            desk.add(label, piece, parent=(original.id, seg.page_from, seg.page_to))
            continue
        sub = read.subset(list(range(seg.page_from - 1, seg.page_to)), keep_meta=False)
        desk.add(label, piece, pre=(one, sub), parent=(original.id, seg.page_from, seg.page_to),
                 officer_type=seg.doc_type)  # fmt: skip
    conn.execute(text("UPDATE documents SET status = 'split' WHERE id = :d"), {"d": original.id})
    return desk.finish(rs, "bundle_split_confirmed",
                       {"document_id": str(original.id), "pieces": len(segments)})  # fmt: skip
