"""'Ask this case' (Stage 12 Part E, SECURITY.md 4i): `GET` and `POST /cases/{id}/chat`.

The case's officer and the admin only (another officer 404, the auditor 403); each person sees
their own questions. Read-only: these routes write their own turns, the model-call log and the
audit log, and nothing else. The question is masked before it is stored or sent; its text never
reaches a log line, a trace or the audit log.
"""

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, Engine, text

from app.agents import store
from app.api.cases import get_case
from app.api.deps import User, case_reader, get_conn, write_audit
from app.api.ratelimit import RateLimiter
from app.chat import service
from app.chat.check import citation_counts
from app.chat.context import Material, Names, applicants_of, load_material, mask_question
from app.intake.masker import find_leaks
from app.observability import tracing
from app.services import ai_config

router = APIRouter(tags=["chat"])
HOUR = 3600.0
NO_REPORT = "Chat opens when the report is ready."
_HIDDEN = ("<PAN_", "<AADHAAR_", "<PHONE_", "<ACCT_", "<EMAIL_", "<GSTIN_")


class QuestionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=service.MAX_QUESTION)


def _limiter(request: Request) -> RateLimiter:
    state = request.app.state
    if not hasattr(state, "chat_limiter"):
        state.chat_limiter = RateLimiter(window=HOUR)
    limiter: RateLimiter = state.chat_limiter
    return limiter


def _latest(conn: Connection, case_id: UUID) -> Any:
    return conn.execute(
        text("SELECT version, report_json FROM reports WHERE case_id = :c ORDER BY version DESC LIMIT 1"),
        {"c": case_id},
    ).first()  # fmt: skip


def _models(request: Request) -> Any:
    """The configuration in force now (the admin's switch and models), bound to this request."""
    state = request.app.state
    ai_config.bind(ai_config.refresh(state.engine, state.settings))
    # `chat_models` is set only by the browser-test server, to script the chat without giving the
    # pipeline a model
    return getattr(state, "chat_models", None) or state.runner.pipeline.ctx


def _turn_out(row: Any) -> dict[str, Any]:
    return {
        "id": row.id, "question": row.question, "outcome": row.outcome,
        "text": service.FIXED.get(row.outcome), "answer": row.answer,
        "report_version": row.report_version, "created_at": row.created_at,
        "note": service.MASKED_NOTE if any(t in row.question for t in _HIDDEN) else None,
    }  # fmt: skip


@router.get("/cases/{case_id}/chat")
def history(
    case_id: UUID, request: Request, user: User = Depends(case_reader),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    get_case(conn, case_id, user)
    report = _latest(conn, case_id)
    rows = conn.execute(
        text("""SELECT id, question, outcome, answer, report_version, created_at
                FROM case_chat_messages WHERE case_id = :c AND user_id = :u
                ORDER BY created_at, id LIMIT 200"""),
        {"c": case_id, "u": user.id},
    ).all()
    off = _models(request).models() is None
    return {
        "report_version": None if report is None else report.version,
        "off": off,
        "off_text": service.OFF if off else None,
        "max_chars": service.MAX_QUESTION,
        "turns": [_turn_out(r) for r in rows],
    }


def _save(
    engine: Engine, *, case_id: UUID, user: User, version: int, question: str,
    turn: service.Turn, material: Material | None,
) -> dict[str, Any]:  # fmt: skip
    stored = service.stored_answer(turn, material)
    with engine.begin() as conn:
        row = conn.execute(
            text("""INSERT INTO case_chat_messages (case_id, user_id, report_version, question,
                        answer, outcome, retries, model)
                    VALUES (:c, :u, :v, :q, CAST(:a AS jsonb), :o, :r, :m)
                    RETURNING id, question, outcome, answer, report_version, created_at"""),
            {"c": case_id, "u": user.id, "v": version, "q": question, "o": turn.outcome,
             "a": None if stored is None else json.dumps(stored), "r": turn.retries,
             "m": turn.model},
        ).one()  # fmt: skip
        if turn.calls:
            store.add_calls(conn, case_id, turn.calls)
        write_audit(conn, user.id, "case_chat_asked", "case", case_id,
                    after={"outcome": turn.outcome, "report_version": version,
                           "citations": citation_counts(turn.answer)})  # fmt: skip
    return _turn_out(row)


@router.post("/cases/{case_id}/chat", response_model=None)
async def ask_case(
    case_id: UUID, body: QuestionIn, request: Request, user: User = Depends(case_reader)
) -> dict[str, Any] | JSONResponse:
    state = request.app.state
    engine: Engine = state.engine
    raw = " ".join(body.question.split())
    if not raw:
        raise HTTPException(422, "Write a question first.")
    # short transactions only: none is held open while the model is thinking
    with engine.connect() as conn:
        case = get_case(conn, case_id, user)
        report = _latest(conn, case_id)
    if report is None:
        raise HTTPException(409, NO_REPORT)
    names, addresses = applicants_of(case.form_data or {})
    question = mask_question(raw, Names(names), addresses)
    if find_leaks(question):  # never store or send what the masker could not hide
        raise HTTPException(422, "Remove personal numbers from the question and ask again.")
    keep: dict[str, Any] = {"engine": engine, "case_id": case_id, "user": user,
                            "version": report.version, "question": question}  # fmt: skip

    if not _limiter(request).allow(str(user.id), state.settings.chat_max_per_hour):
        _save(**keep, turn=service.Turn("limited"), material=None)
        return JSONResponse({"detail": service.LIMITED}, status_code=429)
    ctx = _models(request)
    if ctx.models() is None:
        return _save(**keep, turn=service.Turn("off"), material=None)
    if routed := service.route(question):
        return _save(**keep, turn=service.Turn(routed), material=None)

    def material_now() -> Material:
        with engine.connect() as conn:
            return load_material(
                conn, state.retriever_factory(conn), case_id=case_id, loan_type=case.loan_type,
                form=case.form_data or {}, report=report.report_json, question=question,
            )  # fmt: skip

    material = await asyncio.to_thread(material_now)
    with tracing.stage_span(str(case_id), service.STAGE):
        turn = await service.answer(ctx, material, question)
    return _save(**keep, turn=turn, material=material)
