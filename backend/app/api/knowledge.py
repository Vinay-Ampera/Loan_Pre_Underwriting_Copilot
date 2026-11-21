"""Knowledge base (Stage 10c): the policy library, changes to a policy, the learnings (approved
precedents) and the index tools.

Reading the policy in force and searching it: officers and the admin. Everything else: the admin
only (the auditor gets 403 everywhere here; the audit log records each change). Publishing,
retiring, re-indexing and changing a precedent need a written reason and the second click. The
rules file is not editable here: scoring reads it, and changing it needs a golden-set rerun.
"""

from collections.abc import Callable
from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection

from app.api.deps import User, admin_only, case_reader, get_conn
from app.learning import maintenance
from app.rag import policy_admin as pa
from app.rag import policy_store as kb
from app.scoring.rules import RuleSet

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
MIN_REASON = 10


class BodyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(max_length=pa.MAX_TEXT_CHARS)
    origin: Literal["upload", "edit", "restore", "legacy"] = "edit"


class CheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loan_type: str = Field(max_length=20)
    body: str = Field(max_length=pa.MAX_TEXT_CHARS)


class ClauseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["edit", "add", "remove"]
    clause_id: str | None = Field(None, max_length=20)
    source_tag: str = Field("", max_length=10)
    title: str = Field("", max_length=200)
    text: str = Field("", max_length=20_000)
    after: str | None = Field(None, max_length=20)
    topic: str | None = Field(None, max_length=10, pattern=r"^[A-Za-z]{2,6}$")


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=500)
    second_click: bool = False


class PublishIn(ReasonIn):
    accept_warnings: bool = False


class ReindexIn(ReasonIn):
    force: bool = False


def _confirmed(body: ReasonIn) -> str:
    if not body.second_click:
        raise HTTPException(422, "Confirm the change with the second click.")
    reason = body.reason.strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(422, f"Give a reason of at least {MIN_REASON} characters.")
    return reason


def _run[T](fn: Callable[[], T]) -> T:
    try:
        return fn()
    except kb.KbError as exc:
        raise HTTPException(exc.status, exc.message) from None
    except maintenance.LearningError as exc:
        raise HTTPException(409, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


def _rules(request: Request) -> RuleSet:
    rules: RuleSet = request.app.state.ruleset
    return rules


def _factory(request: Request) -> kb.RetrieverFactory:
    factory: kb.RetrieverFactory = request.app.state.retriever_factory
    return factory


# --------------------------------------------------------------------------- reading
@router.get("/policies")
def list_policies(request: Request, user: User = Depends(case_reader),
                  conn: Connection = Depends(get_conn)) -> list[dict[str, Any]]:  # fmt: skip
    return kb.overview(conn, admin=user.role == "admin", rules=_rules(request))


@router.get("/policies/{loan_type}")
def read_policy(loan_type: str, request: Request, user: User = Depends(case_reader),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(
        lambda: kb.detail(conn, loan_type, admin=user.role == "admin", rules=_rules(request))
    )


@router.get("/versions/{doc_id}")
def read_version(doc_id: UUID, request: Request, user: User = Depends(case_reader),
                 conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(
        lambda: kb.version_view(conn, doc_id, rules=_rules(request), admin=user.role == "admin")
    )


@router.get("/compare")
def compare_versions(a: UUID, b: UUID, _: User = Depends(admin_only),
                     conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.compare(conn, a, b))


@router.get("/search")
def search_policy(request: Request, q: str, loan_type: str, draft: bool = False,
                  user: User = Depends(case_reader), conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    q = q.strip()
    if not 3 <= len(q) <= 300:
        raise HTTPException(422, "Type a question of 3 to 300 characters.")
    return _run(lambda: kb.search(conn, q, loan_type, factory=_factory(request),
                                  draft=draft and user.role == "admin"))  # fmt: skip


# --------------------------------------------------------------------------- checking text
@router.post("/check")
def check_text(body: CheckIn, request: Request, _: User = Depends(admin_only),
               conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    lt = body.loan_type
    if lt not in pa.LOAN_TYPES:
        raise HTTPException(404, "Unknown loan type.")
    return kb.run_check(conn, lt, body.body, rules=_rules(request), today=date.today()).as_json(
        date.today()
    )


@router.post("/convert")
def convert_file(request: Request, loan_type: str = Form(...), file: UploadFile = File(...),
                 _: User = Depends(admin_only), conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    data = file.file.read(pa.MAX_UPLOAD_BYTES + 1)
    name = file.filename or "upload"
    return _run(
        lambda: kb.convert(conn, loan_type, name, data, rules=_rules(request), today=date.today())
    )


@router.post("/legacy")
def legacy_import(body: CheckIn, _: User = Depends(admin_only),
                  conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.legacy(conn, body.loan_type, body.body, today=date.today()))


# --------------------------------------------------------------------------- drafts
@router.get("/policies/{loan_type}/draft")
def read_draft(loan_type: str, request: Request, _: User = Depends(admin_only),
               conn: Connection = Depends(get_conn)) -> dict[str, Any] | None:  # fmt: skip
    return _run(lambda: kb.draft_view(conn, kb.check_loan(loan_type), rules=_rules(request)))


@router.put("/policies/{loan_type}/draft")
def save_draft(loan_type: str, body: BodyIn, request: Request, user: User = Depends(admin_only),
               conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.save_draft(conn, loan_type, body.body, origin=body.origin, actor=user.id,
                                      rules=_rules(request), embed=request.app.state.embed,
                                      today=date.today()))  # fmt: skip


@router.post("/policies/{loan_type}/draft/start")
def start_draft(loan_type: str, request: Request, user: User = Depends(admin_only),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    """A draft that starts as the policy in force, with the next version label and today's date."""

    def go() -> dict[str, Any]:
        lt = kb.check_loan(loan_type)
        if kb.draft_view(conn, lt, rules=_rules(request)) is not None:
            raise kb.KbError(409, "A draft already exists for this policy.")
        return kb.save_draft(conn, lt, kb.start_text(conn, lt, date.today()), origin="edit",
                             actor=user.id, rules=_rules(request), embed=request.app.state.embed,
                             today=date.today())  # fmt: skip

    return _run(go)


@router.post("/policies/{loan_type}/draft/clause")
def edit_clause(loan_type: str, body: ClauseIn, request: Request, user: User = Depends(admin_only),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.edit_clause(
        conn, loan_type, action=body.action, clause_id=body.clause_id, source_tag=body.source_tag,
        title=body.title, body_text=body.text, after=body.after, topic=body.topic, actor=user.id,
        rules=_rules(request), embed=request.app.state.embed, today=date.today()))  # fmt: skip


@router.delete("/policies/{loan_type}/draft", status_code=204)
def discard_draft(loan_type: str, user: User = Depends(admin_only),
                  conn: Connection = Depends(get_conn)) -> None:  # fmt: skip
    _run(lambda: kb.discard_draft(conn, loan_type, user.id))


@router.post("/policies/{loan_type}/draft/retrieval-check")
def retrieval_check(loan_type: str, request: Request, _: User = Depends(admin_only),
                    conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.retrieval_check(conn, loan_type, factory=_factory(request)))


@router.post("/policies/{loan_type}/draft/publish")
def publish(loan_type: str, body: PublishIn, request: Request, user: User = Depends(admin_only),
            conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    reason = _confirmed(body)
    return _run(lambda: kb.publish(conn, loan_type, actor=user.id, reason=reason,
                                   accept_warnings=body.accept_warnings, rules=_rules(request),
                                   today=date.today()))  # fmt: skip


@router.post("/versions/{doc_id}/restore")
def restore_version(doc_id: UUID, request: Request, user: User = Depends(admin_only),
                    conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return _run(lambda: kb.restore(conn, doc_id, actor=user.id, rules=_rules(request),
                                   embed=request.app.state.embed, today=date.today()))  # fmt: skip


@router.post("/versions/{doc_id}/retire")
def retire_version(doc_id: UUID, body: ReasonIn, user: User = Depends(admin_only),
                   conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    reason = _confirmed(body)
    return _run(lambda: kb.retire(conn, doc_id, actor=user.id, reason=reason))


# --------------------------------------------------------------------------- index tools
@router.get("/index")
def index_health(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return kb.index_health(conn)


@router.post("/index/reindex")
def reindex_now(body: ReindexIn, request: Request, user: User = Depends(admin_only),
                conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    _confirmed(body)
    return _run(lambda: kb.run_reindex(conn, actor=user.id, force=body.force, rules=_rules(request),
                                       embed=request.app.state.embed, today=date.today()))  # fmt: skip


@router.post("/index/evaluate")
def evaluate_index(request: Request, _: User = Depends(admin_only),
                   conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    return kb.evaluate_in_force(conn, factory=_factory(request))


# --------------------------------------------------------------------------- learnings
@router.get("/learnings")
def learnings(status: str = "all", _: User = Depends(admin_only),
              conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    if status != "all" and status not in maintenance.LEARNING_STATUSES:
        raise HTTPException(422, "Unknown status.")
    return maintenance.learnings(conn, status)


@router.post("/learnings/{precedent_id}/reconfirm")
def reconfirm(precedent_id: UUID, body: ReasonIn, user: User = Depends(admin_only),
              conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    reason = _confirmed(body)
    return _run(lambda: maintenance.reconfirm(conn, precedent_id, user.id, reason))


@router.post("/learnings/{precedent_id}/retire")
def retire_learning(precedent_id: UUID, body: ReasonIn, user: User = Depends(admin_only),
                    conn: Connection = Depends(get_conn)) -> dict[str, Any]:  # fmt: skip
    reason = _confirmed(body)
    return _run(lambda: maintenance.retire(conn, precedent_id, user.id, reason))
