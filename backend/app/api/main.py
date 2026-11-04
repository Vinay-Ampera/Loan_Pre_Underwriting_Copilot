"""The FastAPI app.

    uvicorn app.main:app --reload        (from backend/)

The graph runs inside this process (see `runner.py`). `create_app` takes optional stand-ins for
the database engine, the checkpoint saver, the model router and the embedder, which is how the
tests run the whole API without network access. If `frontend/dist` exists it is served too.
"""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import Engine, create_engine

from app.agents.checkpoint import postgres_saver
from app.agents.graph import Pipeline
from app.agents.runtime import AgentContext, Services
from app.api import (
    admin,
    admin_cases,
    auditor,
    auth,
    cases,
    intake,
    issues,
    links,
    messages,
    public,
    users,
)
from app.api.runner import Runner
from app.api.security import DEFAULT_SECRET
from app.core.config import REPO_ROOT, Settings, get_settings
from app.monitoring import auditor_view
from app.notifications.sender import Sender, build_sender
from app.observability import metrics
from app.rag.embedder import embed_passages
from app.scoring.rules import load_rules

log = logging.getLogger("loan_copilot")
DIST = REPO_ROOT / "frontend" / "dist"


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    saver: BaseCheckpointSaver[str] | None = None,
    router: Any = None,
    use_llm: bool | None = None,
    embed: Callable[[list[str]], list[list[float]]] | None = None,
    ctx_kwargs: dict[str, Any] | None = None,
    recover: bool = True,
    sender: Sender | None = None,
) -> FastAPI:  # fmt: skip
    settings = settings or get_settings()
    if settings.app_env != "dev" and settings.jwt_secret.get_secret_value() == DEFAULT_SECRET:
        raise RuntimeError("JWT_SECRET is still the placeholder; set a long random value in .env")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            eng = engine or create_engine(settings.sqlalchemy_url(), pool_size=8, max_overflow=8,
                                          pool_pre_ping=True)  # fmt: skip
            the_saver = saver or await stack.enter_async_context(
                postgres_saver(settings.sqlalchemy_url())
            )
            llm_on = settings.llm_enabled if use_llm is None else use_llm
            the_router = router
            if the_router is None and llm_on:
                from app.services.llm import build_router  # noqa: PLC0415 - only when models are on

                the_router = build_router()
            ruleset = load_rules()
            ctx = AgentContext(ruleset=ruleset, engine=eng, router=the_router, services=Services.from_store(),
                               **(ctx_kwargs or {}))  # fmt: skip
            runner = Runner(Pipeline(ctx, the_saver), eng)
            app.state.settings, app.state.engine, app.state.ruleset = settings, eng, ruleset
            app.state.runner, app.state.embed = runner, embed or embed_passages
            app.state.sender = sender or build_sender(settings.notification_sender)
            app.state.monitor_engine = auditor_view.build_engine(settings, eng)
            if recover:
                n = runner.recover()
                if n:
                    log.info("continuing %d case(s) left running by the last process", n)
            try:
                yield
            finally:
                await runner.shutdown()
                if app.state.monitor_engine is not eng:
                    app.state.monitor_engine.dispose()
                if engine is None:
                    eng.dispose()

    app = FastAPI(title="Loan Pre-Underwriting Copilot", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json")  # fmt: skip
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"],
                           allow_headers=["Authorization", "Content-Type"])  # fmt: skip
    for r in (
        auth.router,
        intake.router,  # before cases: /cases/intake must not be read as a case id
        cases.router,
        admin.router,
        admin_cases.router,
        auditor.router,
        auditor_view.router,
        users.router,
        messages.router,
        issues.router,
        links.router,
        public.router,
    ):
        app.include_router(r, prefix="/api/v1")

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        """Aggregate counters only (no case numbers, names or text); scrape from the internal network."""
        body, content_type = metrics.render()
        return Response(body, media_type=content_type)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if DIST.is_dir():  # the built frontend, one process for the browser tests and a simple deploy
        assets = DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith(("api/", "metrics")):
                raise HTTPException(404)
            target = (DIST / path).resolve()
            if path and target.is_file() and DIST.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(DIST / "index.html")

    return app
