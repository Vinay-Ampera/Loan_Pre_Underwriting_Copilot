"""Upload links for applicants (Stage 10, Part C): creating, listing, extending and disabling.

An officer manages their own links; an admin may create a link naming an officer and may list and
disable any link. The auditor reaches nothing here. The token is 192 random bits, returned once
when the link is created and stored only as a SHA-256 hash; the id (never the token) is what the
audit log and the listings carry. The public side of a link is in `public.py`.
"""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.api.cases import get_case
from app.api.deps import (
    User,
    case_reader,
    get_conn,
    get_settings_dep,
    officer_only,
    require_role,
    write_audit,
)
from app.api.schemas import LoanType
from app.core.config import Settings

router = APIRouter(tags=["upload links"])
link_manager = require_role("officer", "admin")
MAX_DAYS = 30


def new_token() -> str:
    return secrets.token_urlsafe(24)  # 192 bits


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _fernet(settings: Settings) -> Fernet:
    """The key is derived from the server secret, so no extra setting is needed. Changing
    JWT_SECRET makes older copies unreadable; the officer then regenerates the link."""
    raw = hashlib.sha256(b"upload-link-token:" + settings.jwt_secret.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(raw.digest()))


def seal_token(settings: Settings, token: str) -> str:
    return _fernet(settings).encrypt(token.encode()).decode()


def open_token(settings: Settings, sealed: str | None) -> str | None:
    if not sealed:
        return None
    try:
        return _fernet(settings).decrypt(sealed.encode()).decode()
    except InvalidToken:
        return None


def link_path(token: str) -> str:
    """The token rides in the URL fragment: a fragment is never sent to a server, so it cannot
    land in an access log, a proxy log or a Referer header."""
    return f"/u#{token}"


class LinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_click: bool = False
    loan_type: LoanType | None = None
    days: int | None = Field(default=None, ge=1, le=MAX_DAYS)
    officer_id: UUID | None = None  # the admin names the officer; an officer's own id is implied


class SecondClickIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_click: bool = False


class ExpiryIn(BaseModel):
    """Set how many days from now the link stays open (shorter or longer)."""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=MAX_DAYS)
    second_click: bool = False  # needed when this shortens the link


class ExtendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int | None = Field(default=None, ge=1, le=MAX_DAYS)


def state_of(row: Any, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if row.disabled_at is not None:
        return "disabled"
    return "expired" if row.expires_at <= now else "active"


def _view(row: Any) -> dict[str, Any]:
    return {
        "id": row.id, "state": state_of(row), "loan_type": row.loan_type,
        "officer": getattr(row, "officer_name", None), "officer_id": row.officer_id,
        "created_at": row.created_at, "expires_at": row.expires_at,
        "disabled_at": row.disabled_at, "last_used_at": row.last_used_at,
        "files_count": row.files_count, "case_id": row.case_id,
        "case_no": getattr(row, "case_no", None),
        "sent": bool(getattr(row, "sent", False)),
    }  # fmt: skip


_SELECT = """SELECT l.*, u.name AS officer_name, c.case_no,
                    COALESCE((c.form_data -> 'applicant_sent') IS NOT NULL, false) AS sent
             FROM upload_links l JOIN users u ON u.id = l.officer_id
             LEFT JOIN cases c ON c.id = l.case_id"""


def create_link(
    conn: Connection, settings: Settings, *, officer_id: UUID, created_by: UUID,
    loan_type: str | None = None, case_id: UUID | None = None, days: int | None = None,
) -> tuple[UUID, str, datetime]:  # fmt: skip
    token = new_token()
    expires = datetime.now(UTC) + timedelta(days=days or settings.upload_link_days)
    link_id = conn.execute(
        text("""INSERT INTO upload_links (token_hash, token_enc, officer_id, created_by, loan_type,
                    case_id, expires_at) VALUES (:h, :te, :o, :b, :lt, :c, :e) RETURNING id"""),
        {"h": hash_token(token), "te": seal_token(settings, token), "o": officer_id,
         "b": created_by, "lt": loan_type, "c": case_id, "e": expires},
    ).scalar_one()  # fmt: skip
    return link_id, token, expires


@router.post("/links", status_code=201)
def create(
    body: LinkIn, user: User = Depends(link_manager), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    if not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    if user.role == "admin":
        if body.officer_id is None:
            raise HTTPException(422, "Choose the officer this link is for.")
        officer = conn.execute(
            text("SELECT id FROM users WHERE id = :i AND role = 'officer' AND active"),
            {"i": body.officer_id}).first()  # fmt: skip
        if officer is None:
            raise HTTPException(422, "That officer is not available.")
        officer_id = body.officer_id
    else:
        officer_id = user.id
    link_id, token, expires = create_link(conn, settings, officer_id=officer_id, created_by=user.id,
                                          loan_type=body.loan_type, days=body.days)  # fmt: skip
    write_audit(conn, user.id, "upload_link_created", "upload_link", link_id,
                after={"officer_id": str(officer_id), "loan_type": body.loan_type,
                       "expires_at": expires.isoformat()})  # fmt: skip
    return {"id": link_id, "token": token, "path": link_path(token), "expires_at": expires,
            "shown_once": True}  # fmt: skip


@router.get("/links")
def list_links(
    user: User = Depends(link_manager), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:  # fmt: skip
    rows = conn.execute(
        text(f"""{_SELECT} WHERE (CAST(:all AS boolean) OR l.officer_id = :u)
                 ORDER BY l.created_at DESC LIMIT 200"""),  # noqa: S608
        {"all": user.role == "admin", "u": user.id})  # fmt: skip
    return [_view(r) for r in rows]


def _load(conn: Connection, link_id: UUID, user: User) -> Any:
    row = conn.execute(
        text(f"{_SELECT} WHERE l.id = :i AND (CAST(:all AS boolean) OR l.officer_id = :u) FOR UPDATE OF l"),  # noqa: S608
        {"i": link_id, "all": user.role == "admin", "u": user.id}).first()  # fmt: skip
    if row is None:  # not yours looks the same as not there
        raise HTTPException(404, "Link not found.")
    return row


@router.post("/links/{link_id}/disable")
def disable(
    link_id: UUID, body: SecondClickIn, user: User = Depends(link_manager),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    if not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    row = _load(conn, link_id, user)
    if row.disabled_at is None:
        conn.execute(text("UPDATE upload_links SET disabled_at = now(), disabled_by = :u WHERE id = :i"),
                     {"u": user.id, "i": link_id})  # fmt: skip
        write_audit(conn, user.id, "upload_link_disabled", "upload_link", link_id)
    return _view(_load(conn, link_id, user))


@router.post("/links/{link_id}/extend")
def extend(
    link_id: UUID, body: ExtendIn, user: User = Depends(link_manager),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """More time for a link that is still wanted. A disabled link stays disabled."""
    row = _load(conn, link_id, user)
    if row.disabled_at is not None:
        raise HTTPException(409, "This link was disabled. Create a new one.")
    start = max(row.expires_at, datetime.now(UTC))
    new_end = start + timedelta(days=body.days or settings.upload_link_days)
    conn.execute(text("UPDATE upload_links SET expires_at = :e WHERE id = :i"),
                 {"e": new_end, "i": link_id})  # fmt: skip
    write_audit(conn, user.id, "upload_link_extended", "upload_link", link_id,
                after={"expires_at": new_end.isoformat()})  # fmt: skip
    return _view(_load(conn, link_id, user))


@router.post("/links/{link_id}/expiry")
def set_expiry(
    link_id: UUID, body: ExpiryIn, user: User = Depends(link_manager),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """Open for this many more days, counted from now: longer or shorter. Shortening is the
    second-click kind of change; a disabled link stays disabled."""
    row = _load(conn, link_id, user)
    if row.disabled_at is not None:
        raise HTTPException(409, "This link was disabled. Create a new one.")
    new_end = datetime.now(UTC) + timedelta(days=body.days)
    if new_end < row.expires_at and not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    conn.execute(text("UPDATE upload_links SET expires_at = :e WHERE id = :i"),
                 {"e": new_end, "i": link_id})  # fmt: skip
    write_audit(conn, user.id, "upload_link_expiry_set", "upload_link", link_id,
                before={"expires_at": row.expires_at.isoformat()},
                after={"expires_at": new_end.isoformat(), "days": body.days})  # fmt: skip
    return _view(_load(conn, link_id, user))


@router.get("/links/{link_id}/address")
def link_address(
    link_id: UUID, user: User = Depends(link_manager), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:  # fmt: skip
    """The link's address again, for Copy. Only the officer it belongs to and the admin can ask
    (`_load` makes anyone else's link look like it is not there); every look is audited."""
    row = _load(conn, link_id, user)
    token = open_token(settings, row.token_enc)
    if row.disabled_at is not None or token is None:
        raise HTTPException(
            409, "This address cannot be shown. Regenerate the link to get a new one."
        )
    write_audit(conn, user.id, "upload_link_address_viewed", "upload_link", link_id)
    return JSONResponse({"path": link_path(token)}, headers={"Cache-Control": "no-store"})


@router.post("/links/{link_id}/regenerate")
def regenerate(
    link_id: UUID, body: SecondClickIn, user: User = Depends(link_manager),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """A new address for the same link (same case, same expiry). The old address stops working
    at once. Second click, because anyone holding the old address loses access."""
    if not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    row = _load(conn, link_id, user)
    if row.disabled_at is not None:
        raise HTTPException(409, "This link was disabled. Create a new one.")
    token = new_token()
    conn.execute(text("UPDATE upload_links SET token_hash = :h, token_enc = :te WHERE id = :i"),
                 {"h": hash_token(token), "te": seal_token(settings, token), "i": link_id})  # fmt: skip
    write_audit(conn, user.id, "upload_link_regenerated", "upload_link", link_id)
    return {"id": link_id, "path": link_path(token), "expires_at": row.expires_at}


@router.post("/cases/{case_id}/ask-applicant")
def ask_applicant(
    case_id: UUID, body: SecondClickIn, request: Request, user: User = Depends(officer_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """ "Ask the applicant" from the inventory. A case that came in through a link keeps that
    link open (extended if it was about to end); the token cannot be shown again, so the answer
    says so. Any other case gets a new link bound to it, shown once."""
    if not body.second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    case = get_case(conn, case_id, user, lock=True)
    if case.status not in ("draft", "uploaded", "applicant_submitted"):
        raise HTTPException(409, "This case can no longer receive files.")
    live = conn.execute(
        text("""SELECT id, expires_at FROM upload_links
                WHERE case_id = :c AND disabled_at IS NULL AND expires_at > now()
                ORDER BY created_at DESC LIMIT 1"""), {"c": case_id}).first()  # fmt: skip
    if live is not None:
        if live.expires_at < datetime.now(UTC) + timedelta(days=settings.upload_link_days):
            new_end = datetime.now(UTC) + timedelta(days=settings.upload_link_days)
            conn.execute(text("UPDATE upload_links SET expires_at = :e WHERE id = :i"),
                         {"e": new_end, "i": live.id})  # fmt: skip
        write_audit(conn, user.id, "applicant_asked", "case", case_id,
                    after={"link_id": str(live.id), "new_link": False})  # fmt: skip
        sealed = conn.execute(text("SELECT token_enc FROM upload_links WHERE id = :i"),
                              {"i": live.id}).scalar()  # fmt: skip
        again = open_token(settings, sealed)
        return {
            "link_id": live.id,
            "token": again,
            "path": link_path(again) if again else None,
            "new_link": False,
        }
    link_id, token, expires = create_link(conn, settings, officer_id=user.id, created_by=user.id,
                                          loan_type=case.loan_type, case_id=case_id)  # fmt: skip
    write_audit(conn, user.id, "upload_link_created", "upload_link", link_id,
                after={"officer_id": str(user.id), "case_id": str(case_id)})  # fmt: skip
    write_audit(conn, user.id, "applicant_asked", "case", case_id,
                after={"link_id": str(link_id), "new_link": True})  # fmt: skip
    return {"link_id": link_id, "token": token, "path": link_path(token), "expires_at": expires,
            "new_link": True}  # fmt: skip


@router.get("/cases/{case_id}/link")
def case_link(
    case_id: UUID, user: User = Depends(case_reader), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    """The newest link of a case, without its token (it is not kept)."""
    get_case(conn, case_id, user)
    row = conn.execute(text(f"{_SELECT} WHERE l.case_id = :c ORDER BY l.created_at DESC LIMIT 1"),  # noqa: S608
                       {"c": case_id}).first()  # fmt: skip
    return {"link": None if row is None else _view(row)}
