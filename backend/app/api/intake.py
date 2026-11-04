"""The intake desk (Stage 10, Parts A and B): start a case from documents, upload a zip, a folder
or many files, read the inventory, correct a file's type or person, see which identity fields the
cards offer, save the application form, and download the case's files.

Officers use every route here for their own cases only (another officer's case is a 404). The
admin may read the inventory, the offered identity values and the files of any case; every write
is officer-only. The auditor reaches nothing here. Nothing in this module reads a claim (amount,
tenure, purpose, employment, income...) from a document: the only values taken from documents
are the five identity fields in `intake/prefill.py`.
"""

import io
import zipfile
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.agents import store as case_store
from app.api import identity, ingest
from app.api.cases import (
    SUBMITTABLE,
    _accepted_types,
    _case_form,
    _documents,
    _emails,
    _form_data,
    _insert_applicants,
    _is_masked,
    _merge_masked,
    _ruleset,
    file_store,
    get_case,
    people_of,
)
from app.api.deps import (
    User,
    case_reader,
    get_conn,
    get_settings_dep,
    officer_only,
    write_audit,
)
from app.api.schemas import CO_APPLICANT, CaseIn, LoanType, SendIn
from app.core.config import Settings
from app.intake import archive
from app.intake.inventory import Row, build_inventory

router = APIRouter(prefix="/cases", tags=["intake"])


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_type: LoanType
    # the date the files are checked against; empty means today. Only needed to replay a dated
    # case (the synthetic ones); the form may leave its own date empty and keep this one.
    application_date: date | None = None


class DocPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_type: str | None = Field(default=None, max_length=40)
    role: Literal["primary", "co", "none"] | None = None


class IntakeStateIn(BaseModel):
    """What the officer says about the people on the case before the form exists. Employment
    type is a claim (the applicant's or the officer's), never read from a document."""

    model_config = ConfigDict(extra="forbid")

    employment: (
        dict[Literal["primary", "co"], Literal["salaried", "self_employed"] | None] | None
    ) = None
    co: bool | None = None


def _intake_case(conn: Connection, case_id: UUID, user: User, *, lock: bool = False) -> Any:
    row = get_case(conn, case_id, user, lock=lock)
    return row


def inventory_for(conn: Connection, rs: Any, row: Any) -> dict[str, Any]:
    form = _case_form(row)
    raw = list(conn.execute(
        text("""SELECT d.id, d.original_name, d.status, d.doc_type, d.classification, d.role,
                       d.role_source, d.type_source, d.reject_reason, d.duplicate_kind,
                       d.upload_checks, dup.original_name AS dup_name
                FROM documents d LEFT JOIN documents dup ON dup.id = d.duplicate_of
                WHERE d.case_id = :c ORDER BY d.uploaded_at, d.original_name"""),
        {"c": row.id}))  # fmt: skip
    rows = [Row(
        id=str(r.id), name=r.original_name, status=r.status, doc_type=r.doc_type,
        classification=r.classification, role=r.role, role_source=r.role_source,
        type_source=r.type_source, reject_code=r.reject_reason,
        message=(r.upload_checks or {}).get("message", ""), duplicate_of=r.dup_name,
        duplicate_kind=r.duplicate_kind, warnings=(r.upload_checks or {}).get("warnings", []),
    ) for r in raw]  # fmt: skip
    docs = _documents(conn, row.id)
    people = people_of(row, docs)
    co_rule = CO_APPLICANT[row.loan_type]
    if form.get("applicants") and "co" not in people:
        co_rule = "not_allowed"
    inv = build_inventory(
        rs,
        row.loan_type,
        rows,
        co_rule=co_rule,
        employment=people,
        details=form.get("loan_details", {}),
        co_added=bool(form.get("intake", {}).get("co")) or "co" in people,
    )
    inv["proceeded"] = bool(form.get("intake", {}).get("proceeded"))
    inv["stage"] = "form" if form.get("applicants") else "intake"
    return inv


# --------------------------------------------------------------------------- start, upload
@router.post("/intake", status_code=201)
def start_intake(
    body: StartIn, user: User = Depends(officer_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    """Open a case from documents: the loan type only. The request and the people come later."""
    import json

    if body.application_date and body.application_date > date.today():
        raise HTTPException(422, "The application date cannot be in the future.")
    for _ in range(3):
        try:
            with conn.begin_nested():
                case_no = case_store.next_case_no(conn)
                case_id = conn.execute(
                    text("""INSERT INTO cases (case_no, loan_type, status, created_by, form_data)
                            VALUES (:no, :lt, 'draft', :u, CAST(:f AS jsonb)) RETURNING id"""),
                    {"no": case_no, "lt": body.loan_type, "u": user.id,
                     "f": json.dumps({"external_id": case_no, "loan_details": {},
                                      "application_date": (body.application_date or date.today()).isoformat(),
                                      "intake": {"employment": {}, "co": False}})},
                ).scalar_one()  # fmt: skip
            break
        except IntegrityError:
            continue
    else:
        raise HTTPException(503, "Could not allocate a case number. Try again.")
    write_audit(conn, user.id, "case_created", "case", case_id,
                after={"case_no": case_no, "loan_type": body.loan_type, "via": "intake_desk"})  # fmt: skip
    return {"id": case_id, "case_no": case_no}


@router.post("/{case_id}/intake/files")
def upload_bulk(
    case_id: UUID, request: Request, files: list[UploadFile] = File(...),
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    row = get_case(conn, case_id, user, lock=True)
    if row.status not in SUBMITTABLE and not (row.status == "stopped" and row.stop_class == "fix"):
        raise HTTPException(
            409, "Files can be changed only before assessment, or to fix a stopped case."
        )
    try:
        parts = ingest.read_parts(files, settings)
        results = ingest.ingest(conn, file_store(settings), settings, _ruleset(request), row,
                                parts, actor=user.id, source="officer")  # fmt: skip
    except archive.ArchiveError as exc:
        write_audit(
            conn, user.id, "intake_upload_refused", "case", case_id, after={"code": exc.code}
        )
        conn.commit()
        raise HTTPException(422, exc.message) from None
    fresh = get_case(conn, case_id, user)
    return {"results": results, "inventory": inventory_for(conn, _ruleset(request), fresh)}


# --------------------------------------------------------------------------- inventory
@router.get("/{case_id}/inventory")
def read_inventory(
    case_id: UUID, request: Request, user: User = Depends(case_reader),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    return inventory_for(conn, _ruleset(request), get_case(conn, case_id, user))


@router.patch("/{case_id}/documents/{doc_id}")
def correct_document(
    case_id: UUID, doc_id: UUID, body: DocPatchIn, request: Request,
    user: User = Depends(officer_only), conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """Change a file's type or person from the inventory. No confirmation: it is easy to undo."""
    row = get_case(conn, case_id, user, lock=True)
    if row.status not in SUBMITTABLE and not (row.status == "stopped" and row.stop_class == "fix"):
        raise HTTPException(409, "Files can be changed only before assessment.")
    d = conn.execute(
        text("SELECT status FROM documents WHERE id = :d AND case_id = :c"),
        {"d": doc_id, "c": case_id}).first()  # fmt: skip
    if d is None or d.status != "accepted":
        raise HTTPException(404, "Document not found.")
    docs = _documents(conn, case_id)
    if body.doc_type is not None:
        if body.doc_type not in _accepted_types(_ruleset(request), row, docs) | {"unknown"}:
            raise HTTPException(422, "Unknown document type for this loan.")
        conn.execute(
            text("UPDATE documents SET doc_type = :t, type_source = 'officer' WHERE id = :d"),
            {"t": body.doc_type, "d": doc_id})  # fmt: skip
    if body.role is not None:
        role = None if body.role == "none" else body.role
        if role is not None and role not in people_of(row, docs):
            if (
                role == "co"
                and CO_APPLICANT[row.loan_type] == "optional"
                and not _case_form(row).get("applicants")
            ):
                pass  # the officer is adding the co-applicant by filing a document to them
            else:
                raise HTTPException(422, f"This case has no {role} applicant.")
        conn.execute(
            text("""UPDATE documents d SET role = :r, role_source = 'officer',
                        applicant_id = (SELECT a.id FROM applicants a
                                        WHERE a.case_id = d.case_id AND a.role = :r)
                    WHERE d.id = :d"""),
            {"r": role, "d": doc_id})  # fmt: skip
    ingest.reassign_roles(conn, file_store(request.app.state.settings), _ruleset(request), row,
                          _case_form(row))  # fmt: skip
    write_audit(conn, user.id, "document_corrected", "case", case_id,
                after={"document_id": str(doc_id), "doc_type": body.doc_type, "role": body.role})  # fmt: skip
    conn.execute(text("UPDATE cases SET updated_at = now() WHERE id = :c"), {"c": case_id})
    return inventory_for(conn, _ruleset(request), get_case(conn, case_id, user))


@router.put("/{case_id}/intake")
def set_intake_state(
    case_id: UUID, body: IntakeStateIn, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """Employment type per person and the optional co-applicant, as the officer states them."""
    import json

    row = get_case(conn, case_id, user, lock=True)
    form = dict(_case_form(row))
    if form.get("applicants"):
        raise HTTPException(409, "The application form is already saved; change these there.")
    if row.status not in SUBMITTABLE:
        raise HTTPException(409, "This case can no longer be changed.")
    intake = dict(form.get("intake", {}))
    if body.co is not None:
        if CO_APPLICANT[row.loan_type] == "not_allowed" and body.co:
            raise HTTPException(422, f"A {row.loan_type} loan has no co-applicant.")
        intake["co"] = body.co
    if body.employment is not None:
        intake["employment"] = {**intake.get("employment", {}), **body.employment}
    form["intake"] = intake
    conn.execute(text("UPDATE cases SET form_data = CAST(:f AS jsonb), updated_at = now() "
                      "WHERE id = :c"), {"f": json.dumps(form), "c": case_id})  # fmt: skip
    write_audit(conn, user.id, "intake_state_set", "case", case_id,
                after={"co": intake.get("co"), "employment": intake.get("employment")})  # fmt: skip
    return inventory_for(conn, _ruleset(request), get_case(conn, case_id, user))


@router.post("/{case_id}/intake/proceed")
def proceed_anyway(
    case_id: UUID, body: SendIn, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """Go on with documents still missing (the second click). Missing KYC documents still block
    Submit; any other missing item makes the pipeline stop with its normal fix-type result."""
    import json

    if not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    row = get_case(conn, case_id, user, lock=True)
    if row.status not in SUBMITTABLE:
        raise HTTPException(409, "This case can no longer be changed.")
    inv = inventory_for(conn, _ruleset(request), row)
    if inv["essential_missing"]:
        raise HTTPException(
            422, "KYC documents are missing. They are needed before the case can go on."
        )
    missing = sorted({m["type"] for p in inv["people"] for m in p["missing"]})
    form = dict(_case_form(row))
    form["intake"] = {**form.get("intake", {}), "proceeded": {"missing": missing}}
    conn.execute(text("UPDATE cases SET form_data = CAST(:f AS jsonb), updated_at = now() "
                      "WHERE id = :c"), {"f": json.dumps(form), "c": case_id})  # fmt: skip
    write_audit(
        conn, user.id, "proceeded_with_missing", "case", case_id, after={"missing": missing}
    )
    return inventory_for(conn, _ruleset(request), get_case(conn, case_id, user))


# --------------------------------------------------------------------------- identity, form
@router.get("/{case_id}/prefill")
def read_prefill(
    case_id: UUID, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """The identity values the cards offer, per person. Only the five identity fields; the
    response says which fields are empty and why."""
    get_case(conn, case_id, user)
    return identity.offer(conn, file_store(settings), case_id)


@router.put("/{case_id}/form")
def save_form(
    case_id: UUID, body: CaseIn, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """Save the application form of a case opened at the desk (or of any case not yet submitted).
    Identity values the officer kept as the cards gave them are marked "from documents" and need
    the confirmation tick; once the officer saves, the applicant's request is locked."""
    import json

    row = get_case(conn, case_id, user, lock=True)
    if row.status not in SUBMITTABLE:
        raise HTTPException(409, "The form can be changed only before the assessment is submitted.")
    if body.loan_type != row.loan_type:
        raise HTTPException(422, "The loan type cannot be changed.")
    form = _case_form(row)
    stored = form.get("applicants", [])
    _merge_masked(body, stored, form.get("loan_details", {}), _emails(conn, case_id))
    if any(_is_masked(a) for a in body.applicants) or any(
        isinstance(v, str) and "*" in v for v in body.loan_details.values()
    ):
        raise HTTPException(422, "Enter the full PAN, mobile number and email.")
    offered = identity.offer(conn, file_store(settings), case_id)
    marks = identity.marks(offered, [a.model_dump(mode="json") for a in body.applicants])
    if marks and not body.identity_confirmed:
        raise HTTPException(
            422,
            "Tick the box to confirm the details that were read from the PAN and Aadhaar cards.",
        )
    kept_date = body.application_date or form.get("application_date") or date.today()
    new_form = json.loads(_form_data(row.case_no, body, str(kept_date), form, marks))
    changed: list[str] = []
    request_made = form.get("request")
    if request_made and not form.get("request_locked"):
        new_form["request_locked"] = True  # the officer now owns the form (E-52)
        for key, mine, theirs in (
            ("loan_amount", body.loan_amount, request_made.get("loan_amount")),
            ("tenure_months", body.tenure_months, request_made.get("tenure_months")),
            ("purpose", body.purpose or "", request_made.get("purpose") or ""),
        ):
            if theirs is not None and str(mine) != str(theirs) and float_differs(mine, theirs):
                changed.append(key)
    conn.execute(
        text("""UPDATE cases SET loan_amount = :a, tenure_months = :t, purpose = :p,
                    form_data = CAST(:f AS jsonb),
                    status = CASE WHEN status = 'applicant_submitted' THEN 'uploaded' ELSE status END,
                    updated_at = now() WHERE id = :c"""),
        {"a": body.loan_amount, "t": body.tenure_months, "p": body.purpose,
         "f": json.dumps(new_form), "c": case_id},
    )  # fmt: skip
    _insert_applicants(conn, case_id, body)
    ingest.reassign_roles(conn, file_store(settings), _ruleset(request), get_case(conn, case_id, user),
                          new_form)  # fmt: skip
    write_audit(conn, user.id, "case_form_saved", "case", case_id,
                after={"from_documents": marks, "identity_confirmed": bool(new_form["identity_confirmed"])})  # fmt: skip
    if changed:
        write_audit(conn, user.id, "request_corrected", "case", case_id, after={"fields": changed})
    return {"id": case_id, "from_documents": marks}


def float_differs(a: Any, b: Any) -> bool:
    try:
        return abs(float(a) - float(b)) > 0.005
    except (TypeError, ValueError):
        return str(a) != str(b)


# --------------------------------------------------------------------------- files zip
@router.get("/{case_id}/files.zip")
def download_files(
    case_id: UUID, user: User = Depends(case_reader), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> Response:  # fmt: skip
    """Every accepted file of the case in one zip, built on request and named by person and
    type (the uploaded names are labels only)."""
    row = get_case(conn, case_id, user)
    store = file_store(settings)
    buf = io.BytesIO()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in conn.execute(
            text("""SELECT doc_type, role, file_path FROM documents
                    WHERE case_id = :c AND status = 'accepted' AND file_path IS NOT NULL
                    ORDER BY uploaded_at, original_name"""), {"c": case_id}):  # fmt: skip
            if not store.exists(d.file_path):
                continue
            folder = {"primary": "applicant", "co": "co-applicant"}.get(d.role, "unassigned")
            ext = d.file_path.rsplit(".", 1)[-1]
            key = f"{folder}/{d.doc_type}"
            counts[key] = counts.get(key, 0) + 1
            zf.writestr(f"{folder}/{d.doc_type}-{counts[key]}.{ext}", store.read(d.file_path))
    write_audit(
        conn, user.id, "files_downloaded", "case", case_id, after={"files": sum(counts.values())}
    )
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{row.case_no}-files.zip"',
                             "Cache-Control": "private, no-store",
                             "X-Content-Type-Options": "nosniff"})  # fmt: skip
