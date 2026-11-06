"""The applicant's upload page (Stage 10, Part C). The one public surface of the system: no
account, no sign-in, and only this family of routes.

What a link allows: state the loan request (the applicant's own statement), add files, read the
checklist counts for this link, and press Send to the bank. What it never allows: reading a file
back, seeing a score, a status or an outcome, or reaching another case. Unknown, expired and
disabled tokens get the same answer. The token travels in the `X-Upload-Token` header (the page
keeps it in the URL fragment, which is never sent to a server) and is never logged, audited or
returned; the audit log carries the link id. Requests are rate limited per link and per address.
"""

import json
import secrets
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.agents import store as case_store
from app.api import ingest
from app.api.cases import SUBMITTABLE, _ruleset, file_store
from app.api.deps import get_conn, get_settings_dep, write_audit
from app.api.intake import inventory_for
from app.api.links import hash_token
from app.api.ratelimit import RateLimiter
from app.api.schemas import CO_APPLICANT, LoanType, SendIn
from app.core.config import Settings
from app.intake import archive

router = APIRouter(prefix="/public", tags=["applicant upload link"])
GENERIC = "This link is not active."
BUSY = "Too many requests. Please wait a moment and try again."
CLOSED = "This link is not accepting files right now."
NO_CACHE = {"Cache-Control": "no-store"}


class RequestIn(BaseModel):
    """What the applicant states. Every value is a claim, shown to the officer as such."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    loan_type: LoanType | None = None
    loan_amount: float = Field(gt=0, le=10_000_000_000)
    tenure_months: int = Field(gt=0, le=600)
    purpose: str | None = Field(default=None, max_length=200)
    employment_type: Literal["salaried", "self_employed"]
    declared_monthly_income: float | None = Field(default=None, ge=0, le=100_000_000)


def _limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
    if limiter is None:
        limiter = request.app.state.limiter = RateLimiter()
    return limiter


def _address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def resolve(request: Request, conn: Connection, settings: Settings) -> Any:
    """The active link for this request's token, or the generic refusal. Counts the request
    against the address and the link first, so guessing is slow and floods are cut off."""
    limiter, ip = _limiter(request), _address(request)
    if not limiter.allow(f"ip:{ip}", settings.address_rate_per_minute):
        raise HTTPException(429, BUSY, headers=NO_CACHE)
    token = request.headers.get("x-upload-token", "")
    row = None
    if 20 <= len(token) <= 100:
        row = conn.execute(
            text("""SELECT * FROM upload_links WHERE token_hash = :h
                    AND disabled_at IS NULL AND expires_at > now() FOR UPDATE"""),
            {"h": hash_token(token)}).first()  # fmt: skip
    if row is None:
        if not limiter.allow(f"bad:{ip}", 15):  # a guesser is slowed down further
            raise HTTPException(429, BUSY, headers=NO_CACHE)
        raise HTTPException(404, GENERIC, headers=NO_CACHE)
    if not limiter.allow(f"link:{row.id}", settings.link_rate_per_minute):
        raise HTTPException(429, BUSY, headers=NO_CACHE)
    return row


def _case(conn: Connection, link: Any) -> Any:
    if link.case_id is None:
        return None
    return conn.execute(text("SELECT * FROM cases WHERE id = :c FOR UPDATE"),
                        {"c": link.case_id}).first()  # fmt: skip


def _open(case: Any) -> bool:
    return case is not None and case.status in SUBMITTABLE


def _counts(request: Request, conn: Connection, case: Any) -> dict[str, Any] | None:
    """The checklist for this link and nothing else: item names and how many are in."""
    if case is None:
        return None
    inv = inventory_for(conn, _ruleset(request), case)
    who = {"primary": "Applicant", "co": "Co-applicant"}
    return {
        "people": [{"who": who[p["role"]],
                    "items": [{"type": i["type"], "needed": i["needed"], "have": i["have"]}
                              for i in p["checklist"]]} for p in inv["people"]],
        "after_employment": sorted({w["type"] for w in inv["depends_on_employment"]}),
        "complete": inv["complete"] and not inv["unassigned"],
    }  # fmt: skip


def _view(request: Request, conn: Connection, link: Any) -> dict[str, Any]:
    case = _case(conn, link)
    form = case.form_data if case is not None else {}
    officer_case = case is not None and form.get("origin") != "applicant"
    return {
        "active": True,
        "loan_type": link.loan_type or (case.loan_type if case is not None else None),
        "expires_on": link.expires_at.date().isoformat(),
        # the request step: open until the officer takes over the form (E-52); never on a case
        # the officer made, which has no request to take
        "request_open": not officer_case and not (case is not None and form.get("request_locked")),
        "request_received": bool(form.get("request")),
        "accepting_files": case is not None and _open(case),
        "sent": bool(form.get("applicant_sent")),
        "checklist": _counts(request, conn, case),
    }  # fmt: skip


@router.get("/link")
def read_link(
    request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    link = resolve(request, conn, settings)
    conn.execute(text("UPDATE upload_links SET last_used_at = now() WHERE id = :i"), {"i": link.id})
    return JSONResponse(_view(request, conn, link), headers=NO_CACHE)


@router.post("/request")
def send_request(
    body: RequestIn, request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    loan_type = link.loan_type or (case.loan_type if case is not None else None) or body.loan_type
    if loan_type is None:
        raise HTTPException(422, "Choose the kind of loan.", headers=NO_CACHE)
    if link.loan_type and body.loan_type and body.loan_type != link.loan_type:
        raise HTTPException(422, "This link is for a different kind of loan.", headers=NO_CACHE)
    earner = "co" if CO_APPLICANT[loan_type] == "required" else "primary"
    claim = {"loan_type": loan_type, "loan_amount": body.loan_amount,
             "tenure_months": body.tenure_months, "purpose": body.purpose,
             "employment_type": body.employment_type,
             "declared_monthly_income": body.declared_monthly_income, "earner_role": earner}  # fmt: skip

    if case is None:  # the case begins when the request arrives
        for _ in range(3):
            try:
                with conn.begin_nested():
                    case_no = case_store.next_case_no(conn)
                    new_form: dict[str, Any] = {"external_id": case_no, "loan_details": {}, "origin": "applicant",
                            "application_date": date.today().isoformat(), "request": claim,
                            "request_locked": False, "upload_link_id": str(link.id),
                            "intake": {"employment": {earner: body.employment_type}, "co": False}}  # fmt: skip
                    case_id = conn.execute(
                        text("""INSERT INTO cases (case_no, loan_type, status, created_by, loan_amount,
                                    tenure_months, purpose, form_data)
                                VALUES (:no, :lt, 'draft', :u, :a, :t, :p, CAST(:f AS jsonb))
                                RETURNING id"""),
                        {"no": case_no, "lt": loan_type, "u": link.officer_id, "a": body.loan_amount,
                         "t": body.tenure_months, "p": body.purpose, "f": json.dumps(new_form)},
                    ).scalar_one()  # fmt: skip
                break
            except Exception:  # noqa: BLE001 - a clash on the case number: try the next one
                continue
        else:
            raise HTTPException(503, "Please try again in a moment.", headers=NO_CACHE)
        conn.execute(text("UPDATE upload_links SET case_id = :c, last_used_at = now() WHERE id = :i"),
                     {"c": case_id, "i": link.id})  # fmt: skip
        write_audit(conn, None, "applicant_request_received", "upload_link", link.id,
                    after={"case_id": str(case_id)})  # fmt: skip
        write_audit(conn, None, "case_created", "case", case_id,
                    after={"case_no": case_no, "loan_type": loan_type, "via": "upload_link"})  # fmt: skip
        return JSONResponse({"received": True}, headers=NO_CACHE)

    form = dict(case.form_data)
    if form.get("origin") != "applicant":
        raise HTTPException(409, "This link does not take a request.", headers=NO_CACHE)
    if form.get("request_locked") or not _open(case):
        raise HTTPException(
            409, "Your request was already received by the bank. Please contact your loan officer "
                 "if something needs to change.", headers=NO_CACHE)  # fmt: skip
    form["request"] = claim
    intake: dict[str, Any] = dict(form.get("intake") or {})
    intake["employment"] = {**(intake.get("employment") or {}), earner: body.employment_type}
    form["intake"] = intake
    conn.execute(
        text("""UPDATE cases SET loan_amount = :a, tenure_months = :t, purpose = :p,
                    form_data = CAST(:f AS jsonb), updated_at = now() WHERE id = :c"""),
        {"a": body.loan_amount, "t": body.tenure_months, "p": body.purpose,
         "f": json.dumps(form), "c": case.id})  # fmt: skip
    write_audit(conn, None, "applicant_request_updated", "case", case.id,
                after={"link_id": str(link.id)})  # fmt: skip
    return JSONResponse({"received": True}, headers=NO_CACHE)


@router.post("/files")
def add_files(
    request: Request, files: list[UploadFile] = File(...), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    if case is None:
        return JSONResponse({"detail": "Please send your request first."}, 409, headers=NO_CACHE)
    if not _open(case):
        write_audit(conn, None, "applicant_upload_refused", "case", case.id,
                    after={"link_id": str(link.id), "status": case.status})  # fmt: skip
        return JSONResponse(
            {"detail": CLOSED}, 409, headers=NO_CACHE
        )  # committed: the officer sees it
    room = settings.link_max_files - link.files_count
    if room <= 0:
        return JSONResponse({"detail": "This link cannot take more files."}, 409, headers=NO_CACHE)
    parts: list[tuple[str, bytes]] = []
    try:
        parts = ingest.read_parts(files, settings)
        results = ingest.ingest(conn, file_store(settings), settings, _ruleset(request), case, parts,
                                actor=None, source="upload_link", max_files=room)  # fmt: skip
    except archive.ArchiveError as exc:
        write_audit(conn, None, "applicant_upload_refused", "case", case.id,
                    after={"link_id": str(link.id), "code": exc.code})  # fmt: skip
        return JSONResponse({"detail": exc.message}, 422, headers=NO_CACHE)
    conn.execute(
        text("""UPDATE upload_links SET files_count = files_count + :n, last_used_at = now(),
                    bytes_total = bytes_total + :b WHERE id = :i"""),
        {"n": len(results), "b": sum(len(d) for _, d in parts), "i": link.id})  # fmt: skip
    write_audit(conn, None, "applicant_files_received", "upload_link", link.id,
                after={"files": len(results)})  # fmt: skip
    conn.execute(text("UPDATE documents SET uploaded_via = 'applicant' WHERE id = ANY(:ids)"),
                 {"ids": [r["id"] for r in results]})  # fmt: skip
    fresh = _case(conn, link)
    shown = {"accepted": "received", "warning": "received", "ignored": "already received",
             "rejected": "not accepted"}  # fmt: skip
    return JSONResponse({
        # only the applicant's own file name, what happened to it in plain words, and why not
        "files": [{"name": r["name"], "result": shown[r["status"]],
                   "reason": r["message"] if r["status"] == "rejected" else ""} for r in results],
        "checklist": _counts(request, conn, fresh),
    }, headers=NO_CACHE)  # fmt: skip


def _removable(case: Any) -> bool:
    """The applicant may take a file back until they press Send to the bank or the officer takes
    over the form; after that the officer works from what is there."""
    form = case.form_data if case is not None else {}
    return _open(case) and not form.get("request_locked") and not form.get("applicant_sent")


def _own_file(conn: Connection, case: Any, doc_id: str) -> Any:
    try:
        UUID(doc_id)
    except ValueError:
        raise HTTPException(404, "File not found.", headers=NO_CACHE) from None
    row = conn.execute(
        text("""SELECT id, original_name, file_path, mime, status FROM documents
                WHERE id = :d AND case_id = :c AND uploaded_via = 'applicant'"""),
        {"d": doc_id, "c": case.id}).first()  # fmt: skip
    if row is None:
        raise HTTPException(404, "File not found.", headers=NO_CACHE)
    return row


@router.get("/my-files")
def my_files(
    request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    """What this applicant sent through this link: name and plain result only (nothing the
    bank read from it, no type, no score)."""
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    if case is None:
        return JSONResponse({"files": [], "can_remove": False}, headers=NO_CACHE)
    rows = conn.execute(
        text("""SELECT id, original_name, status, (file_path IS NOT NULL) AS has_file FROM documents
                WHERE case_id = :c AND uploaded_via = 'applicant' ORDER BY uploaded_at"""),
        {"c": case.id})  # fmt: skip
    shown = {"accepted": "received", "ignored": "already received", "rejected": "not accepted"}
    return JSONResponse({
        "files": [{"id": str(r.id), "name": r.original_name, "result": shown.get(r.status, "received"),
                   "can_view": bool(r.has_file)} for r in rows],
        "can_remove": _removable(case),
    }, headers=NO_CACHE)  # fmt: skip


@router.get("/files/{doc_id}")
def view_file(
    doc_id: str, request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> Response:  # fmt: skip
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    if case is None:
        raise HTTPException(404, "File not found.", headers=NO_CACHE)
    row = _own_file(conn, case, doc_id)
    store = file_store(settings)
    if not row.file_path or not store.exists(row.file_path):
        raise HTTPException(404, "File not available.", headers=NO_CACHE)
    return Response(store.read(row.file_path), media_type=row.mime, headers={
        "Content-Disposition": "inline", "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store"})  # fmt: skip


@router.post("/files/{doc_id}/remove")
def remove_file(
    doc_id: str, body: SendIn, request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    if not body.second_click:
        raise HTTPException(422, "Please confirm to remove the file.", headers=NO_CACHE)
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    if case is None:
        raise HTTPException(404, "File not found.", headers=NO_CACHE)
    if not _removable(case):
        raise HTTPException(
            409, "Files can no longer be removed here. Please contact your loan officer.",
            headers=NO_CACHE)  # fmt: skip
    row = _own_file(conn, case, doc_id)
    conn.execute(text("UPDATE documents SET duplicate_of = NULL WHERE duplicate_of = :d"),
                 {"d": row.id})  # fmt: skip
    conn.execute(text("DELETE FROM documents WHERE id = :d"), {"d": row.id})
    if row.file_path:
        file_store(settings).delete(row.file_path)
    write_audit(conn, None, "applicant_file_removed", "case", case.id,
                after={"link_id": str(link.id), "document_id": str(row.id)})  # fmt: skip
    fresh = _case(conn, link)
    return JSONResponse({"checklist": _counts(request, conn, fresh)}, headers=NO_CACHE)


@router.post("/send")
def send_to_bank(
    body: SendIn, request: Request, conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    """The second click. Tells the officer the applicant has sent what they have; a reference
    number comes back. It decides nothing and shows no outcome."""
    if not body.second_click:
        raise HTTPException(422, "Please confirm to send.", headers=NO_CACHE)
    link = resolve(request, conn, settings)
    case = _case(conn, link)
    if case is None or not _open(case):
        return JSONResponse({"detail": CLOSED}, 409, headers=NO_CACHE)
    counts = _counts(request, conn, case)
    incomplete = not (counts and counts["complete"])
    form: dict[str, Any] = dict(case.form_data)
    reference = (form.get("applicant_sent") or {}).get("reference") or (
        "PRM-" + secrets.token_hex(4).upper())  # fmt: skip
    form["applicant_sent"] = {"at": date.today().isoformat(), "incomplete": incomplete,
                              "reference": reference}  # fmt: skip
    conn.execute(
        text("""UPDATE cases SET form_data = CAST(:f AS jsonb), updated_at = now(),
                    status = CASE WHEN status IN ('draft', 'uploaded') THEN 'applicant_submitted'
                                  ELSE status END WHERE id = :c"""),
        {"f": json.dumps(form), "c": case.id})  # fmt: skip
    write_audit(conn, None, "applicant_sent", "case", case.id,
                after={"link_id": str(link.id), "incomplete": incomplete})  # fmt: skip
    return JSONResponse({"reference": reference, "incomplete": incomplete}, headers=NO_CACHE)
