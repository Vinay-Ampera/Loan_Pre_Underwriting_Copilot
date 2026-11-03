"""Case endpoints. Every route here is for loan officers and only for their own cases: an admin
account gets 403, another officer's case gets 404. The read-only auditor may use the read routes
for every case, with names, identifiers and addresses masked and no document files (SECURITY.md
D3); every write route stays officer-only. The UI shows what these endpoints return; it
computes nothing (scores, bands and stop decisions all come from the pipeline).
"""

import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.agents import store
from app.agents.state import DB_STAGES
from app.agents.submission import DocumentRef, Submission
from app.api import display
from app.api.deps import (
    User,
    case_reader,
    get_conn,
    get_engine,
    get_settings_dep,
    officer_only,
    write_audit,
)
from app.api.reportpdf import build_report_pdf
from app.api.runner import Runner
from app.api.schemas import CO_APPLICANT, LOAN_FIELDS, CaseIn, OfficerActionIn, ResumeIn
from app.core.config import REPO_ROOT, Settings
from app.intake.fields import ADDRESS_FIELDS, NAME_FIELDS
from app.intake.upload import check_case_size, check_upload
from app.scoring.facts import applicable_requirements
from app.scoring.rules import RuleSet

router = APIRouter(prefix="/cases", tags=["cases"])

UPLOADABLE = ("draft", "uploaded", "stopped")
MIN_OVERRIDE_REASON = 15
DECISION_OF = {"recommend_approve": "approve", "refer": "refer", "recommend_reject": "reject"}
EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}


# --------------------------------------------------------------------------- helpers
def _ruleset(request: Request) -> RuleSet:
    rs: RuleSet = request.app.state.ruleset
    return rs


def _runner(request: Request) -> Runner:
    runner: Runner = request.app.state.runner
    return runner


def upload_root(settings: Settings) -> Path:
    root = settings.upload_dir
    return root if root.is_absolute() else REPO_ROOT / root


def get_case(conn: Connection, case_id: UUID, user: User, *, lock: bool = False) -> Any:
    sql = "SELECT * FROM cases WHERE id = :i" + (
        "" if user.role == "auditor" else " AND created_by = :u"  # the auditor reads every case
    )
    row = conn.execute(
        text(sql + (" FOR UPDATE" if lock else "")), {"i": case_id, "u": user.id}
    ).first()
    if row is None:  # not yours looks the same as not there
        raise HTTPException(404, "Case not found.")
    return row


def _applicant_dict(a: dict[str, Any]) -> dict[str, Any]:
    """An applicant as kept in the case form. The contact email is stored in its own column only
    (it is for customer messages, never part of the application the pipeline reads)."""
    return {**{k: v for k, v in a.items() if k != "email"}, "dob": str(a["dob"])}


def _emails(conn: Connection, case_id: UUID) -> dict[str, str | None]:
    rows = conn.execute(
        text("SELECT role, email FROM applicants WHERE case_id = :c"), {"c": case_id}
    )
    return {r.role: r.email for r in rows}


def _case_form(row: Any) -> dict[str, Any]:
    form: dict[str, Any] = row.form_data
    return form


def build_submission(conn: Connection, row: Any) -> Submission:
    form = _case_form(row)
    application = {
        "case_id": row.case_no, "loan_type": row.loan_type,
        "application_date": form["application_date"], "loan_amount": float(row.loan_amount),
        "tenure_months": row.tenure_months, "purpose": row.purpose,
        "applicants": form["applicants"], "loan_details": form.get("loan_details", {}),
    }  # fmt: skip
    return Submission(
        case_id=row.case_no, application=application, documents=_doc_refs(conn, row.id)
    )


def _doc_refs(conn: Connection, case_id: UUID) -> list[DocumentRef]:
    rows = conn.execute(
        text("""SELECT d.file_path, d.original_name, a.role FROM documents d
                JOIN applicants a ON a.id = d.applicant_id
                WHERE d.case_id = :c AND d.status = 'accepted' AND d.file_path IS NOT NULL
                ORDER BY d.uploaded_at"""), {"c": case_id})  # fmt: skip
    return [DocumentRef(role=r.role, path=r.file_path, name=r.original_name) for r in rows]


def _checklist(rs: RuleSet, row: Any, docs: list[Any]) -> list[dict[str, Any]]:
    form = _case_form(row)
    employment = {a["role"]: a["employment_type"] for a in form["applicants"]}
    out: list[dict[str, Any]] = []
    for req in applicable_requirements(rs, row.loan_type, employment, form.get("loan_details", {})):
        roles = [r for r in ("primary", "co") if r in employment] if req.kyc else [req.applicant]
        types = req.any_of or [req.type]
        # one statement file covers many months: the pipeline counts months, the checklist files
        needed = 1 if types == ["bank_statement"] else req.min_count
        for role in roles:
            if role not in employment:
                continue
            have = sum(1 for d in docs if d.status == "accepted" and d.role == role
                       and d.doc_type in types)  # fmt: skip
            out.append({"type": "/".join(types), "types": types, "applicant": role,
                        "needed": needed, "have": have, "kyc": req.kyc,
                        "met": have >= needed})  # fmt: skip
    return out


def _accepted_types(rs: RuleSet, row: Any) -> set[str]:
    form = _case_form(row)
    employment = {a["role"]: a["employment_type"] for a in form["applicants"]}
    reqs = applicable_requirements(rs, row.loan_type, employment, form.get("loan_details", {}))
    return {t for r in reqs for t in (r.any_of or [r.type])} | {"other"}


def _documents(conn: Connection, case_id: UUID) -> list[Any]:
    return list(conn.execute(
        text("""SELECT d.id, d.doc_type, d.original_name, d.mime, d.status, d.reject_reason, d.page_count,
                       d.upload_checks, d.uploaded_at, a.role
                FROM documents d LEFT JOIN applicants a ON a.id = d.applicant_id
                WHERE d.case_id = :c ORDER BY a.role DESC, d.uploaded_at"""), {"c": case_id}))  # fmt: skip


def _fields(
    conn: Connection, case_id: UUID, *, auditor: bool = False
) -> dict[UUID, list[dict[str, Any]]]:
    out: dict[UUID, list[dict[str, Any]]] = {}
    rows = conn.execute(
        text("""SELECT f.document_id, f.field_name, f.value_masked, f.value_local, f.needs_review
                FROM extracted_fields f JOIN documents d ON d.id = f.document_id
                WHERE d.case_id = :c ORDER BY f.field_name"""), {"c": case_id})  # fmt: skip
    for r in rows:
        raw = bytes(r.value_local).decode(errors="replace") if r.value_local is not None else None
        shown = display.display_text(raw) if raw is not None else (r.value_masked or "")
        if auditor:
            hidden = r.field_name in NAME_FIELDS | ADDRESS_FIELDS | {"dob"}
            shown = "masked" if hidden else display.display_text(r.value_masked or shown)
        out.setdefault(r.document_id, []).append(
            {"name": r.field_name, "value": shown, "needs_review": r.needs_review}
        )
    return out


def _stage_rows(conn: Connection, case_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("SELECT stage, status, score, max_score, hard_fail FROM stage_runs WHERE case_id = :c"),
        {"c": case_id})  # fmt: skip
    got = {r.stage: {"stage": r.stage, "status": r.status, "score": None if r.score is None else float(r.score),
                     "max_score": None if r.max_score is None else float(r.max_score),
                     "hard_fail": r.hard_fail} for r in rows}  # fmt: skip
    return [got[s] for s in DB_STAGES if s in got]


def _latest_report(conn: Connection, case_id: UUID) -> tuple[int, dict[str, Any]] | None:
    row = conn.execute(
        text("SELECT version, report_json FROM reports WHERE case_id = :c ORDER BY version DESC LIMIT 1"),
        {"c": case_id})  # fmt: skip
    r = row.first()
    return None if r is None else (r.version, r.report_json)


def _officer_action(conn: Connection, case_id: UUID) -> dict[str, Any] | None:
    r = conn.execute(
        text("""SELECT o.action, o.original_recommendation, o.final_decision, o.reason, o.created_at,
                       u.name AS officer
                FROM officer_actions o JOIN users u ON u.id = o.officer_id
                WHERE o.case_id = :c ORDER BY o.created_at DESC LIMIT 1"""), {"c": case_id}).first()  # fmt: skip
    return None if r is None else {
        "action": r.action, "original_recommendation": r.original_recommendation,
        "final_decision": r.final_decision, "reason": r.reason, "at": r.created_at, "officer": r.officer,
    }  # fmt: skip


def _last_failure(conn: Connection, case_id: UUID, status: str) -> dict[str, Any] | None:
    """The run's error type when the latest run of an unfinished case failed, else None. A failed
    run puts the case back to `uploaded` (or `stopped`), so the officer needs to be told why."""
    if status not in ("uploaded", "stopped"):
        return None
    r = conn.execute(
        text("""SELECT action, at, after FROM audit_log
                WHERE entity = 'case' AND entity_id = :i
                  AND action IN ('pipeline_failed', 'case_submitted', 'case_resumed_after_fix')
                ORDER BY at DESC, id DESC LIMIT 1"""), {"i": str(case_id)}).first()  # fmt: skip
    if r is None or r.action != "pipeline_failed":
        return None
    return {"error": (r.after or {}).get("error", "Error"), "at": r.at}


def _summary(row: Any) -> dict[str, Any]:
    return {
        "id": row.id, "case_no": row.case_no, "loan_type": row.loan_type, "status": row.status,
        "loan_amount": float(row.loan_amount), "tenure_months": row.tenure_months,
        "purpose": row.purpose, "total_score": None if row.total_score is None else float(row.total_score),
        "band": row.band, "recommendation": row.recommendation, "stopped_stage": row.stopped_stage,
        "stop_class": row.stop_class, "created_at": row.created_at, "updated_at": row.updated_at,
    }  # fmt: skip


# --------------------------------------------------------------------------- list, create, read
@router.get("")
def list_cases(
    status: str | None = None, loan_type: str | None = None, q: str | None = None,
    user: User = Depends(case_reader), conn: Connection = Depends(get_conn),
) -> list[dict[str, Any]]:  # fmt: skip
    auditor = user.role == "auditor"
    rows = conn.execute(
        text("""SELECT c.*, u.name AS officer_name,
                       (SELECT a.full_name FROM applicants a WHERE a.case_id = c.id AND a.role = 'primary') AS applicant,
                       floor(extract(epoch FROM (now() - c.created_at)) / 86400)::int AS age_days
                FROM cases c JOIN users u ON u.id = c.created_by
                WHERE (CAST(:all AS boolean) OR c.created_by = :u)
                  AND (CAST(:st AS text) IS NULL OR c.status = :st)
                  AND (CAST(:lt AS text) IS NULL OR c.loan_type = :lt)
                  AND (CAST(:q AS text) IS NULL OR c.case_no ILIKE '%' || :q || '%'
                       OR (NOT CAST(:all AS boolean) AND EXISTS (SELECT 1 FROM applicants a WHERE a.case_id = c.id
                                  AND a.full_name ILIKE '%' || :q || '%')))
                ORDER BY c.updated_at DESC LIMIT 200"""),
        {"u": user.id, "all": auditor, "st": status or None, "lt": loan_type or None, "q": (q or "").strip() or None},
    )  # fmt: skip
    return [{**_summary(r), "applicant": display.mask_name(r.applicant) if auditor else r.applicant,
             "officer": r.officer_name, "age_days": r.age_days} for r in rows]  # fmt: skip


def _insert_applicants(conn: Connection, case_id: UUID, body: CaseIn) -> None:
    conn.execute(text("DELETE FROM applicants WHERE case_id = :c"), {"c": case_id})
    for a in body.applicants:
        conn.execute(
            text("""INSERT INTO applicants (case_id, role, full_name, dob, pan, aadhaar_last4, address, phone,
                        employment_type, employer_or_business, declared_monthly_income, relationship_to_primary,
                        email)
                    VALUES (:c, :role, :name, :dob, :pan, :a4, :addr, :phone, :emp, :biz, :inc, :rel, :email)"""),
            {"c": case_id, "role": a.role, "name": a.full_name, "dob": a.dob, "pan": a.pan,
             "a4": a.aadhaar_last4, "addr": a.address, "phone": a.phone,
             "emp": None if a.employment_type == "student" else a.employment_type,
             "biz": a.employer_or_business, "inc": a.declared_monthly_income,
             "rel": a.relationship_to_primary, "email": a.email},
        )  # fmt: skip


def _is_masked(a: Any) -> bool:
    return "*" in a.pan or "*" in (a.phone or "") or "*" in (a.email or "")


def _show_details(details: dict[str, Any]) -> dict[str, Any]:
    """Loan details with identifier patterns masked (a business loan carries a GSTIN)."""
    return {k: display.display_text(v) if isinstance(v, str) else v for k, v in details.items()}


def _merge_masked(
    body: CaseIn, stored: list[dict[str, Any]], stored_details: dict[str, Any],
    stored_emails: dict[str, str | None] | None = None,
) -> None:  # fmt: skip
    """A corrected form shows PAN, phone and GSTIN masked. A value left masked keeps the stored one."""
    for k, v in body.loan_details.items():
        if isinstance(v, str) and "*" in v:
            old = stored_details.get(k)
            if not isinstance(old, str) or display.display_text(old) != v:
                raise HTTPException(422, f"Type the full value for {k.replace('_', ' ')}.")
            body.loan_details[k] = old
    by_role = {a["role"]: a for a in stored}
    for a in body.applicants:
        old = by_role.get(a.role)
        if "*" in a.pan:
            if old is None or display.mask_pan(old["pan"]) != a.pan:
                raise HTTPException(422, f"Type the full PAN for the {a.role} applicant.")
            a.pan = old["pan"]
        if a.phone and "*" in a.phone:
            if old is None or display.mask_phone(old["phone"]) != a.phone:
                raise HTTPException(422, f"Type the full mobile number for the {a.role} applicant.")
            a.phone = old["phone"]
        stored_emails = stored_emails or {}
        if a.email and "*" in a.email:
            if (
                not stored_emails.get(a.role)
                or display.display_text(stored_emails[a.role] or "") != a.email
            ):
                raise HTTPException(422, f"Type the full email for the {a.role} applicant.")
            a.email = stored_emails[a.role]


def _form_data(case_no: str, body: CaseIn, application_date: str) -> str:
    return json.dumps({
        "external_id": case_no, "application_date": application_date,
        "loan_details": body.loan_details,
        "applicants": [_applicant_dict(a.model_dump(mode="python")) for a in body.applicants],
    }, default=str)  # fmt: skip


@router.post("", status_code=201)
def create_case(
    body: CaseIn, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    if any(_is_masked(a) for a in body.applicants) or any(
        isinstance(v, str) and "*" in v for v in body.loan_details.values()
    ):
        raise HTTPException(422, "Enter the full PAN, mobile number and email.")
    for _ in range(3):  # two officers creating at once can pick the same number
        try:
            with conn.begin_nested():
                case_no = store.next_case_no(conn)
                case_id = conn.execute(
                    text("""INSERT INTO cases (case_no, loan_type, status, created_by, loan_amount,
                                tenure_months, purpose, form_data)
                            VALUES (:no, :lt, 'draft', :u, :amt, :ten, :purpose, CAST(:form AS jsonb))
                            RETURNING id"""),
                    {"no": case_no, "lt": body.loan_type, "u": user.id, "amt": body.loan_amount,
                     "ten": body.tenure_months, "purpose": body.purpose,
                     "form": _form_data(case_no, body, (body.application_date or date.today()).isoformat())},
                ).scalar_one()  # fmt: skip
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(503, "Could not allocate a case number. Try again.")
    _insert_applicants(conn, case_id, body)
    write_audit(conn, user.id, "case_created", "case", case_id,
                after={"case_no": case_no, "loan_type": body.loan_type})  # fmt: skip
    return {"id": case_id, "case_no": case_no}


@router.get("/{case_id}")
def read_case(
    case_id: UUID, request: Request, user: User = Depends(case_reader),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    row = get_case(conn, case_id, user)
    docs = _documents(conn, case_id)
    auditor = user.role == "auditor"
    fields = _fields(conn, case_id, auditor=auditor)
    checklist = _checklist(_ruleset(request), row, docs)
    report = _latest_report(conn, case_id)
    form = _case_form(row)
    emails = _emails(conn, case_id)
    applicants = [
        {"role": a["role"], "email": display.display_text(emails.get(a["role"]) or "") or None, "full_name": a["full_name"], "dob": a["dob"],
         "pan": display.mask_pan(a["pan"]), "aadhaar": display.mask_aadhaar_last4(a["aadhaar_last4"]),
         "phone": display.mask_phone(a["phone"]), "address": a["address"],
         "employment_type": a["employment_type"], "employer_or_business": a.get("employer_or_business"),
         "declared_monthly_income": a.get("declared_monthly_income"),
         "relationship_to_primary": a.get("relationship_to_primary")}
        for a in form["applicants"]
    ]  # fmt: skip
    runner = _runner(request)
    names = [a["full_name"] for a in form["applicants"]]
    if auditor:
        for a, shown in zip(applicants, form["applicants"], strict=True):
            a["full_name"] = display.mask_name(shown["full_name"])
            a["dob"] = display.mask_dob(shown["dob"])
            a["address"] = "masked"
            a["employer_or_business"] = display.mask_name(a["employer_or_business"])
    out = {
        **_summary(row),
        "loan_details": _show_details(form.get("loan_details", {})),
        "applicants": applicants,
        "documents": [
            {"id": d.id, "role": d.role, "doc_type": d.doc_type, "name": d.original_name,
             "mime": d.mime, "status": d.status, "reject_reason": d.reject_reason,
             "warnings": (d.upload_checks or {}).get("warnings", []),
             "message": (d.upload_checks or {}).get("message", ""),
             "fields": fields.get(d.id, [])}
            for d in docs
        ],
        "checklist": checklist,
        "doc_types": sorted(_accepted_types(_ruleset(request), row)),
        "kyc_ready": all(c["met"] for c in checklist if c["kyc"]) and bool(checklist),
        "co_applicant": CO_APPLICANT[row.loan_type],
        "stages": _stage_rows(conn, case_id),
        "running": runner.is_running(case_id),
        "report_version": report[0] if report else None,
        "report": report[1] if report else None,
        "officer_action": _officer_action(conn, case_id),
        "last_failure": _last_failure(conn, case_id, row.status),
        "loan_fields": LOAN_FIELDS[row.loan_type],
    }  # fmt: skip
    if not auditor:
        return out
    # read-only view: masked, with no document files and no way to act
    officer = conn.execute(
        text("SELECT name FROM users WHERE id = :u"), {"u": row.created_by}
    ).scalar()
    scrubbed = display.scrub_for_auditor(
        {k: out[k] for k in ("report", "officer_action", "loan_details", "purpose", "documents")},
        names,
    )
    assert isinstance(scrubbed, dict)
    return {**out, **scrubbed, "read_only": True, "officer": officer}


@router.get("/{case_id}/status")
def case_status(
    case_id: UUID, request: Request, user: User = Depends(case_reader),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    row = get_case(conn, case_id, user)
    return {"status": row.status, "running": _runner(request).is_running(case_id),
            "stages": _stage_rows(conn, case_id), "updated_at": row.updated_at}  # fmt: skip


@router.get("/{case_id}/audit")
def case_audit(
    case_id: UUID, user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    get_case(conn, case_id, user)
    rows = conn.execute(
        text("""SELECT l.action, l.at, l.after, u.name AS actor FROM audit_log l
                LEFT JOIN users u ON u.id = l.actor_id
                WHERE l.entity = 'case' AND l.entity_id = :i ORDER BY l.at, l.id"""),
        {"i": str(case_id)})  # fmt: skip
    return [
        {"action": r.action, "at": r.at, "actor": r.actor or "System", "detail": r.after}
        for r in rows
    ]


# --------------------------------------------------------------------------- uploads
def _editable(row: Any) -> None:
    if row.status == "stopped" and row.stop_class == "fix":
        return
    if row.status not in ("draft", "uploaded"):
        raise HTTPException(
            409, "Files can be changed only before assessment, or to fix a stopped case."
        )


@router.post("/{case_id}/documents")
def upload_documents(
    case_id: UUID, request: Request, files: list[UploadFile] = File(...),
    role: str = Form("primary"), doc_type: str = Form("other"),
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    row = get_case(conn, case_id, user, lock=True)
    _editable(row)
    form = _case_form(row)
    if role not in {a["role"] for a in form["applicants"]}:
        raise HTTPException(422, f"This case has no {role} applicant.")
    if doc_type not in _accepted_types(_ruleset(request), row):
        raise HTTPException(422, "Unknown document type for this loan.")
    applicant_id = conn.execute(
        text("SELECT id FROM applicants WHERE case_id = :c AND role = :r"), {"c": case_id, "r": role}
    ).scalar_one()  # fmt: skip
    folder = upload_root(settings) / str(case_id)
    used = sum(os.path.getsize(p) for p in folder.glob("*")) if folder.exists() else 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    names = {
        d.original_name
        for d in _documents(conn, case_id)
        if d.role == role and d.status == "accepted"
    }
    results: list[dict[str, Any]] = []
    for f in files:
        name = Path(f.filename or "file").name[:200]
        data = f.file.read(max_bytes + 1)
        check = check_upload(data, name, max_bytes)
        if check.accepted and not check_case_size(
            [used, len(data)], settings.max_case_upload_mb * 1024 * 1024
        ):
            check.accepted, check.reject_code = False, "too_large"
            check.message = "The case has reached its total upload limit."
        path: Path | None = None
        if check.accepted:  # a rejected file is never written to disk
            shown, n = name, 1
            while shown in names:  # the pipeline tells files apart by (role, name)
                n += 1
                stem, dot, ext = name.rpartition(".")
                shown = f"{stem} ({n}).{ext}" if dot else f"{name} ({n})"
            name = shown
            names.add(name)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{uuid.uuid4().hex}{EXT[check.mime or 'application/pdf']}"
            path.write_bytes(data)
            used += len(data)
        doc_id = conn.execute(
            text("""INSERT INTO documents (case_id, applicant_id, doc_type, file_path, original_name, mime,
                        page_count, upload_checks, status, reject_reason)
                    VALUES (:c, :a, :t, :p, :n, :m, :pc, CAST(:chk AS jsonb), :st, :rej) RETURNING id"""),
            {"c": case_id, "a": applicant_id, "t": doc_type, "p": str(path) if path else None, "n": name,
             "m": check.mime or "application/octet-stream", "pc": len(check.pages) or None,
             "chk": json.dumps({"warnings": check.warnings, "blur_score": check.blur_score,
                                "message": check.message}),
             "st": "accepted" if check.accepted else "rejected", "rej": check.reject_code},
        ).scalar_one()  # fmt: skip
        status = "rejected" if not check.accepted else ("warning" if check.warnings else "accepted")
        message = check.message or (
            "Accepted, but the image is slightly blurry. Fields read from it may be flagged for review."
            if check.warnings
            else "Accepted."
        )
        results.append({"id": doc_id, "name": name, "status": status, "code": check.reject_code,
                        "message": message, "warnings": check.warnings})  # fmt: skip
        write_audit(conn, user.id, "document_uploaded" if check.accepted else "document_rejected",
                    "case", case_id, after={"doc_type": doc_type, "role": role, "result": status,
                                            "code": check.reject_code})  # fmt: skip
    if row.status == "draft" and any(r["status"] != "rejected" for r in results):
        conn.execute(text("UPDATE cases SET status = 'uploaded', updated_at = now() WHERE id = :c"),
                     {"c": case_id})  # fmt: skip
    return {"results": results}


@router.delete("/{case_id}/documents/{doc_id}", status_code=204)
def delete_document(
    case_id: UUID, doc_id: UUID, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn),
) -> Response:  # fmt: skip
    row = get_case(conn, case_id, user, lock=True)
    _editable(row)
    d = conn.execute(text("SELECT file_path FROM documents WHERE id = :d AND case_id = :c"),
                     {"d": doc_id, "c": case_id}).first()  # fmt: skip
    if d is None:
        raise HTTPException(404, "Document not found.")
    conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": doc_id})
    if d.file_path:
        Path(d.file_path).unlink(missing_ok=True)
    write_audit(
        conn, user.id, "document_removed", "case", case_id, after={"document_id": str(doc_id)}
    )
    return Response(status_code=204)


@router.get("/{case_id}/documents/{doc_id}/file")
def document_file(
    case_id: UUID, doc_id: UUID, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn),
) -> FileResponse:  # fmt: skip
    get_case(conn, case_id, user)
    d = conn.execute(text("SELECT file_path, mime FROM documents WHERE id = :d AND case_id = :c"),
                     {"d": doc_id, "c": case_id}).first()  # fmt: skip
    if d is None or not d.file_path or not Path(d.file_path).exists():
        raise HTTPException(404, "File not available.")
    return FileResponse(d.file_path, media_type=d.mime, content_disposition_type="inline",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})  # fmt: skip


# --------------------------------------------------------------------------- run
def _prepare_submit(engine: Engine, request: Request, case_id: UUID, user: User) -> Submission:
    with engine.begin() as conn:
        row = get_case(conn, case_id, user, lock=True)
        if row.status not in ("draft", "uploaded"):
            raise HTTPException(409, "This case has already been submitted.")
        docs = _documents(conn, case_id)
        checklist = _checklist(_ruleset(request), row, docs)
        missing = [
            f"{c['type']} ({c['applicant']})" for c in checklist if c["kyc"] and not c["met"]
        ]
        if missing:
            raise HTTPException(422, "KYC documents are missing: " + ", ".join(missing) + ".")
        sub = build_submission(conn, row)
        conn.execute(text("UPDATE cases SET status = 'running', updated_at = now() WHERE id = :c"),
                     {"c": case_id})  # fmt: skip
        write_audit(conn, user.id, "case_submitted", "case", case_id,
                    after={"documents": len(sub.documents)})  # fmt: skip
    return sub


@router.post("/{case_id}/submit", status_code=202)
async def submit_case(
    case_id: UUID, request: Request, user: User = Depends(officer_only),
    engine: Engine = Depends(get_engine),
) -> dict[str, Any]:  # fmt: skip
    sub = await run_in_threadpool(_prepare_submit, engine, request, case_id, user)
    runner = _runner(request)
    saver = runner.pipeline.checkpointer
    if saver is not None:
        await saver.adelete_thread(str(case_id))  # a failed earlier attempt leaves a checkpoint
    runner.start(sub, case_id)
    return {"status": "running"}


def _prepare_resume(
    engine: Engine, request: Request, case_id: UUID, user: User, body: ResumeIn
) -> tuple[dict[str, Any], list[DocumentRef]]:  # fmt: skip
    with engine.begin() as conn:
        row = get_case(conn, case_id, user, lock=True)
        if row.status != "stopped" or row.stop_class != "fix":
            raise HTTPException(409, "Only a case stopped for a correction can be resumed.")
        if body.case is not None:
            if body.case.loan_type != row.loan_type:
                raise HTTPException(422, "The loan type cannot be changed.")
            _merge_masked(
                body.case,
                _case_form(row)["applicants"],
                _case_form(row).get("loan_details", {}),
                _emails(conn, case_id),
            )
            kept = body.case.application_date or _case_form(row)["application_date"]
            form = json.loads(_form_data(row.case_no, body.case, str(kept)))
            conn.execute(
                text("""UPDATE cases SET loan_amount = :a, tenure_months = :t, purpose = :p,
                            form_data = CAST(:f AS jsonb) WHERE id = :c"""),
                {"a": body.case.loan_amount, "t": body.case.tenure_months, "p": body.case.purpose,
                 "f": json.dumps(form), "c": case_id},
            )  # fmt: skip
            _insert_applicants(conn, case_id, body.case)
            row = get_case(conn, case_id, user)
        sub = build_submission(conn, row)
        conn.execute(text("UPDATE cases SET status = 'running', updated_at = now() WHERE id = :c"),
                     {"c": case_id})  # fmt: skip
        write_audit(conn, user.id, "case_resumed_after_fix", "case", case_id,
                    after={"form_changed": body.case is not None, "documents": len(sub.documents)})  # fmt: skip
    return sub.application, sub.documents


@router.post("/{case_id}/resume", status_code=202)
async def resume_case(
    case_id: UUID, request: Request, body: ResumeIn | None = None,
    user: User = Depends(officer_only), engine: Engine = Depends(get_engine),
) -> dict[str, Any]:  # fmt: skip
    application, documents = await run_in_threadpool(
        _prepare_resume, engine, request, case_id, user, body or ResumeIn()
    )
    _runner(request).resume_after_fix(case_id, application=application, documents=documents)
    return {"status": "running"}


# --------------------------------------------------------------------------- report
@router.get("/{case_id}/report")
def case_report(
    case_id: UUID, user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    row = get_case(conn, case_id, user)
    rep = _latest_report(conn, case_id)
    if rep is None:
        raise HTTPException(404, "No report yet.")
    out: dict[str, Any] = {"version": rep[0], "report": rep[1],
                           "officer_action": _officer_action(conn, case_id)}  # fmt: skip
    if user.role == "auditor":
        names = [a["full_name"] for a in _case_form(row)["applicants"]]
        scrubbed = display.scrub_for_auditor(out, names)
        assert isinstance(scrubbed, dict)
        return scrubbed
    return out


@router.get("/{case_id}/report.pdf")
def case_report_pdf(
    case_id: UUID, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> Response:  # fmt: skip
    row = get_case(conn, case_id, user)
    rep = _latest_report(conn, case_id)
    if rep is None:
        raise HTTPException(404, "No report yet.")
    pdf = build_report_pdf(row.case_no, rep[1], _officer_action(conn, case_id))
    write_audit(conn, user.id, "report_exported", "case", case_id, after={"version": rep[0]})
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{row.case_no}-report.pdf"',
                             "Cache-Control": "private, no-store"})  # fmt: skip


# --------------------------------------------------------------------------- confirm and override
async def _act(
    request: Request, case_id: UUID, user: User, action: str, body: OfficerActionIn
) -> dict[str, Any]:  # fmt: skip
    if body.second_click is not True:
        raise HTTPException(422, "This needs a second confirmation click.")
    engine: Engine = request.app.state.engine

    def load() -> str:
        with engine.begin() as conn:
            row = get_case(conn, case_id, user, lock=True)
            if row.status != "awaiting_confirmation":
                raise HTTPException(409, "This case is not waiting for your confirmation.")
            return str(row.recommendation)

    recommendation = await run_in_threadpool(load)
    reason = (body.reason or "").strip()
    if action == "override":
        if len(reason) < MIN_OVERRIDE_REASON:
            raise HTTPException(
                422,
                f"Write the reason for the override (at least {MIN_OVERRIDE_REASON} characters).",
            )
        if body.final_decision is None:
            raise HTTPException(422, "Choose the decision you are overriding to.")
        if body.final_decision == DECISION_OF.get(recommendation):
            raise HTTPException(
                422, "That matches the recommendation. Confirm it instead of overriding."
            )
    runner = _runner(request)
    if runner.is_running(case_id):
        raise HTTPException(409, "This case is still running.")
    try:
        state = await runner.pipeline.officer_action(
            case_id, action=action, second_click=True, reason=reason or None,
            final_decision=body.final_decision, officer_id=user.id,
        )  # fmt: skip
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"status": state.get("status"), "officer": state.get("officer")}


@router.post("/{case_id}/confirm")
async def confirm_case(
    case_id: UUID, body: OfficerActionIn, request: Request, user: User = Depends(officer_only)
) -> dict[str, Any]:  # fmt: skip
    return await _act(request, case_id, user, "confirm", body)


@router.post("/{case_id}/override")
async def override_case(
    case_id: UUID, body: OfficerActionIn, request: Request, user: User = Depends(officer_only)
) -> dict[str, Any]:  # fmt: skip
    return await _act(request, case_id, user, "override", body)
