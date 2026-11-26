"""AI control (admin only): which models answer, the model settings and the editable part of the
prompts. Keys stay in `.env`: this module reports whether each key is set and can test a model,
and never returns or stores a key.

Every change needs a written reason and the second click, is stored as a new immutable version
(rollback copies an old one into a new one), is written to the audit log with what changed, and
affects only the cases that start after it (the runner binds the configuration at the start of a
run). A prompt's locked rules and the code's schemas and guardrails are not reachable from here.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text

from app.agents import prompt_check
from app.api.deps import User, admin_only, get_conn, get_settings_dep, write_audit
from app.core.config import Settings
from app.services import ai_config as ai

router = APIRouter(prefix="/admin/ai", tags=["ai-control"])
MIN_REASON = 10


class ConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    reason: str = Field(max_length=500)
    second_click: bool = False


class RollbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    reason: str = Field(max_length=500)
    second_click: bool = False


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(max_length=20000)


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(max_length=500)
    second_click: bool = False


class TestModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(max_length=60)


def _reason(reason: str, second_click: bool) -> str:
    if not second_click:
        raise HTTPException(422, "This needs a second confirmation click.")
    if len(reason.strip()) < MIN_REASON:
        raise HTTPException(422, f"Write a reason of at least {MIN_REASON} characters.")
    return reason.strip()


def _name(name: str) -> str:
    if name not in ai.PROMPT_NAMES:
        raise HTTPException(404, "Unknown prompt.")
    return name


def _saved_config(conn: Connection) -> tuple[int, dict[str, Any]]:
    snap = ai.load(conn)
    return snap.config_version, snap.config


# --------------------------------------------------------------------------- overview
@router.get("")
def overview(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    snap = ai.load(conn)  # once: the saved configuration and the edited prompts
    keys = ai.key_status(settings)
    cat = ai.catalogue()
    drafts = {r.name for r in conn.execute(text("SELECT name FROM ai_prompt_drafts"))}
    versions = snap.prompt_versions()
    return {
        "version": snap.config_version,
        "config": snap.config,
        "default": ai.default_config(),
        "roles": [{"role": r, "label": ai.ROLE_LABELS[r]} for r in ai.ROLES],
        "limits": ai.LIMITS,
        "max_fallbacks": ai.MAX_FALLBACKS,
        "providers": [
            {"id": pid, "model": p["model"], "key_env": p["key_env"], "key_set": keys[pid]}
            for pid, p in cat.items()
        ],
        "prompts": [
            {"name": n, "version": versions[n],
             "edited": n in snap.prompts, "has_draft": n in drafts}
            for n in ai.PROMPT_NAMES
        ],
    }  # fmt: skip


@router.post("/test-model")
async def test_model(
    body: TestModelIn, request: Request, user: User = Depends(admin_only),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """One tiny real call to this provider with the key from `.env`. Returns ok, latency and the
    error class; never a key and never the provider's message."""
    if body.provider not in ai.catalogue():
        raise HTTPException(404, "Unknown model.")
    probe = getattr(request.app.state, "ai_probe", ai.probe_provider)
    result: dict[str, Any] = await probe(settings, body.provider)
    with request.app.state.engine.begin() as conn:
        write_audit(conn, user.id, "ai_model_tested", "ai_config", body.provider,
                    after={"ok": bool(result["ok"]), "error": result.get("error", "")})  # fmt: skip
    return result


# --------------------------------------------------------------------------- models and settings
async def _probe_new(request: Request, settings: Settings, providers: set[str]) -> list[str]:
    """Test every provider that is not in use yet; the reasons it may not be saved."""
    import asyncio  # noqa: PLC0415

    probe = getattr(request.app.state, "ai_probe", ai.probe_provider)
    names = sorted(providers)
    results = await asyncio.gather(*(probe(settings, p) for p in names))
    return [f"{r['provider']} did not answer correctly in the test ({r.get('error') or 'no reply'})."
            for r in results if not r["ok"]]  # fmt: skip


def _insert_config(conn: Connection, user: User, cfg: dict[str, Any], reason: str, source: str,
                   back_to: int | None) -> int:  # fmt: skip
    return int(conn.execute(
        text("""INSERT INTO ai_config_versions (config, reason, source, rolled_back_to, created_by)
                VALUES (CAST(:c AS jsonb), :r, :s, :b, :u) RETURNING version"""),
        {"c": json.dumps(cfg), "r": reason, "s": source, "b": back_to, "u": user.id}).scalar_one())  # fmt: skip


async def _save_config(
    request: Request, conn: Connection, user: User, settings: Settings, cfg: dict[str, Any],
    reason: str, source: str, back_to: int | None,
) -> dict[str, Any]:  # fmt: skip
    problems = ai.validate_config(cfg, settings)
    if problems:
        raise HTTPException(422, " ".join(problems))
    _, current = _saved_config(conn)
    changes = ai.diff_config(current, cfg)
    if not changes:
        raise HTTPException(422, "Nothing changed.")
    problems = await _probe_new(request, settings, ai.newly_used(current, cfg))
    if problems:
        raise HTTPException(422, " ".join(problems))
    version = _insert_config(conn, user, cfg, reason, source, back_to)
    write_audit(conn, user.id, "ai_config_changed", "ai_config", str(version),
                before=None, after={"version": version, "source": source, "rolled_back_to": back_to,
                                    "reason": reason, "changes": changes})  # fmt: skip
    conn.commit()
    ai.refresh(request.app.state.engine, settings)
    return {"version": version, "changes": list(changes)}


@router.put("/config")
async def save_config(
    body: ConfigIn, request: Request, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    reason = _reason(body.reason, body.second_click)
    return await _save_config(request, conn, user, settings, body.config, reason, "edit", None)


@router.get("/config/history")
def config_history(
    _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> list[dict[str, Any]]:
    return [
        {"version": r.version, "reason": r.reason, "source": r.source,
         "rolled_back_to": r.rolled_back_to, "by": r.by, "at": r.created_at, "config": r.config}
        for r in ai.config_versions(conn)
    ]  # fmt: skip


@router.post("/config/rollback")
async def rollback_config(
    body: RollbackIn, request: Request, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    reason = _reason(body.reason, body.second_click)
    row = conn.execute(text("SELECT config FROM ai_config_versions WHERE version = :v"),
                       {"v": body.version}).first()  # fmt: skip
    if row is None:
        raise HTTPException(404, "That version does not exist.")
    return await _save_config(
        request,
        conn,
        user,
        settings,
        ai.with_new_roles(row.config),
        reason,
        "rollback",
        body.version,
    )


# --------------------------------------------------------------------------- prompts
def _prompt_view(conn: Connection, name: str) -> dict[str, Any]:
    fp = ai.file_prompt(name)
    snap = ai.load(conn)
    editable, version = snap.prompts.get(name, (fp.editable, fp.version))
    versions = [
        {"version": r.version, "reason": r.reason, "source": r.source, "rolled_back_to": r.rolled_back_to,
         "by": r.by, "at": r.created_at, "body": r.body}
        for r in conn.execute(text(
            """SELECT v.version, v.reason, v.source, v.rolled_back_to, v.created_at, v.body, u.name AS by
               FROM ai_prompt_versions v LEFT JOIN users u ON u.id = v.created_by
               WHERE v.name = :n ORDER BY v.version DESC LIMIT 30"""), {"n": name})
    ]  # fmt: skip
    d = conn.execute(text("SELECT body, tested_ok, tested_hash, tested_at, updated_at FROM ai_prompt_drafts WHERE name = :n"),
                     {"n": name}).first()  # fmt: skip
    draft = None
    if d is not None:
        draft = {"body": d.body, "updated_at": d.updated_at, "tested_at": d.tested_at,
                 "tested": bool(d.tested_ok and d.tested_hash == ai.sha(d.body))}  # fmt: skip
    return {"name": name, "role": ai.ROLE_LABELS.get(name, name), "version": version,
            "edited": name in snap.prompts, "editable": editable, "file_editable": fp.editable,
            "file_version": fp.version, "locked": fp.locked, "max_chars": ai.MAX_PROMPT_CHARS,
            "versions": versions, "draft": draft}  # fmt: skip


@router.get("/prompts/{name}")
def read_prompt(
    name: str, _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    return _prompt_view(conn, _name(name))


@router.put("/prompts/{name}/draft")
def save_draft(
    name: str, body: DraftIn, user: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:  # fmt: skip
    """Keep working text. No confirmation: nothing is in use until it is tested and published."""
    _name(name)
    problems = ai.validate_prompt_body(name, body.body)
    if problems:
        raise HTTPException(422, " ".join(problems))
    conn.execute(
        text("""INSERT INTO ai_prompt_drafts (name, body, updated_by, updated_at)
                VALUES (:n, :b, :u, now())
                ON CONFLICT (name) DO UPDATE SET body = :b, updated_by = :u, updated_at = now(),
                    tested_ok = false, tested_hash = NULL, tested_at = NULL"""),
        {"n": name, "b": body.body.strip(), "u": user.id})  # fmt: skip
    return _prompt_view(conn, name)


@router.delete("/prompts/{name}/draft")
def discard_draft(
    name: str, _: User = Depends(admin_only), conn: Connection = Depends(get_conn)
) -> dict[str, Any]:
    _name(name)
    conn.execute(text("DELETE FROM ai_prompt_drafts WHERE name = :n"), {"n": name})
    return _prompt_view(conn, name)


@router.post("/prompts/{name}/test")
async def test_draft(
    name: str, request: Request, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn),
) -> dict[str, Any]:  # fmt: skip
    """Run the draft on a fixed synthetic sample with the role's real model, schema and guardrails.
    A pass is remembered for exactly this text; any later edit clears it."""
    _name(name)
    d = conn.execute(text("SELECT body FROM ai_prompt_drafts WHERE name = :n"), {"n": name}).first()
    if d is None:
        raise HTTPException(409, "Save a draft first.")
    router_ = request.app.state.runner.pipeline.ctx.router
    if router_ is None or not ai.active().llm_enabled:
        raise HTTPException(409, "Models are switched off, so the prompt cannot be tested now.")
    system = f"{d.body.strip()}\n\n{ai.file_prompt(name).locked}"
    tester = getattr(request.app.state, "ai_prompt_tester", prompt_check.try_prompt)
    result: dict[str, Any] = await tester(router_, name, system)
    conn.execute(
        text("""UPDATE ai_prompt_drafts SET tested_ok = :ok, tested_hash = :h, tested_at = now()
                WHERE name = :n"""),
        {"ok": bool(result["ok"]), "h": ai.sha(d.body), "n": name})  # fmt: skip
    write_audit(conn, user.id, "ai_prompt_tested", "ai_prompt", name,
                after={"ok": bool(result["ok"]), "issues": len(result["issues"]),
                       "model": result.get("model")})  # fmt: skip
    return result


def _next_version(conn: Connection, name: str) -> int:
    top = conn.execute(
        text("SELECT COALESCE(max(version), 0) FROM ai_prompt_versions WHERE name = :n"),
        {"n": name},
    ).scalar_one()
    return max(int(top), ai.file_prompt(name).version) + 1


def _publish(request: Request, conn: Connection, user: User, settings: Settings, name: str,
             body: str, reason: str, source: str, back_to: int | None) -> dict[str, Any]:  # fmt: skip
    version = _next_version(conn, name)
    before = ai.load(conn).prompts.get(
        name, (ai.file_prompt(name).editable, ai.file_prompt(name).version)
    )
    conn.execute(
        text("""INSERT INTO ai_prompt_versions (name, version, body, reason, source, rolled_back_to, created_by)
                VALUES (:n, :v, :b, :r, :s, :t, :u)"""),
        {"n": name, "v": version, "b": body.strip(), "r": reason, "s": source, "t": back_to, "u": user.id})  # fmt: skip
    conn.execute(text("DELETE FROM ai_prompt_drafts WHERE name = :n"), {"n": name})
    write_audit(conn, user.id, "ai_prompt_published", "ai_prompt", name,
                before={"version": before[1], "sha": ai.sha(before[0])[:12]},
                after={"version": version, "sha": ai.sha(body.strip())[:12], "source": source,
                       "rolled_back_to": back_to, "reason": reason, "chars": len(body.strip())})  # fmt: skip
    view = _prompt_view(conn, name)  # read inside this transaction, before it is committed
    conn.commit()
    ai.refresh(request.app.state.engine, settings)
    return view


@router.post("/prompts/{name}/publish")
def publish_draft(
    name: str, body: PublishIn, request: Request, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    reason = _reason(body.reason, body.second_click)
    _name(name)
    d = conn.execute(text("SELECT body, tested_ok, tested_hash FROM ai_prompt_drafts WHERE name = :n"),
                     {"n": name}).first()  # fmt: skip
    if d is None:
        raise HTTPException(409, "There is no draft to publish.")
    if problems := ai.validate_prompt_body(name, d.body):
        raise HTTPException(422, " ".join(problems))
    if not (d.tested_ok and d.tested_hash == ai.sha(d.body)):
        raise HTTPException(
            409,
            "Test this exact text first. A draft that has not passed the test cannot be published.",
        )
    return _publish(request, conn, user, settings, name, d.body, reason, "edit", None)


@router.post("/prompts/{name}/rollback")
def rollback_prompt(
    name: str, body: RollbackIn, request: Request, user: User = Depends(admin_only),
    conn: Connection = Depends(get_conn), settings: Settings = Depends(get_settings_dep),
) -> dict[str, Any]:  # fmt: skip
    """Bring an older text back as a new version. Version 1 style (the file's own text) is
    `version` = the file version."""
    reason = _reason(body.reason, body.second_click)
    _name(name)
    fp = ai.file_prompt(name)
    if body.version == fp.version:
        old = fp.editable
    else:
        row = conn.execute(text("SELECT body FROM ai_prompt_versions WHERE name = :n AND version = :v"),
                           {"n": name, "v": body.version}).first()  # fmt: skip
        if row is None:
            raise HTTPException(404, "That version does not exist.")
        old = row.body
    current = ai.load(conn).prompts.get(name, (fp.editable, fp.version))[0]
    if old.strip() == current.strip():
        raise HTTPException(422, "That is already the text in use.")
    return _publish(request, conn, user, settings, name, old, reason, "rollback", body.version)
