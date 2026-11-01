"""Background execution of the graph (no Celery, no Redis in v1).

A run is an asyncio task on the API's event loop. Progress is read from the database (a
`stage_runs` row appears as each stage finishes), so any API worker can answer a status request.
If the process dies mid-run, LangGraph's Postgres checkpoint is still there: `recover()` continues
every case left in `running` when the app starts.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from app.agents.graph import Pipeline
from app.agents.submission import Submission
from app.api.deps import write_audit

log = logging.getLogger("loan_copilot.runner")


class Runner:
    def __init__(self, pipeline: Pipeline, engine: Engine) -> None:
        self.pipeline = pipeline
        self.engine = engine
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def is_running(self, case_uuid: UUID | str) -> bool:
        task = self.tasks.get(str(case_uuid))
        return task is not None and not task.done()

    def _launch(
        self, case_uuid: UUID, job: Callable[[], Awaitable[Any]], *, on_error_status: str
    ) -> asyncio.Task[None]:
        key = str(case_uuid)
        if self.is_running(key):
            raise RuntimeError("this case is already running")

        async def run() -> None:
            try:
                await job()
            except asyncio.CancelledError:
                raise  # shutdown: the checkpoint stays, recover() continues it next start
            except Exception as exc:  # noqa: BLE001 - a failed run must not take the API down
                log.error("run of case %s failed: %s", key, type(exc).__name__)
                log.debug(
                    "traceback of the failed run", exc_info=True
                )  # may hold values: debug only
                with self.engine.begin() as conn:
                    conn.execute(
                        text("UPDATE cases SET status = :s, updated_at = now() WHERE id = :c"),
                        {"s": on_error_status, "c": case_uuid},
                    )
                    write_audit(conn, None, "pipeline_failed", "case", case_uuid,
                                after={"error": type(exc).__name__})  # fmt: skip

        task = asyncio.get_running_loop().create_task(run())
        self.tasks[key] = task
        task.add_done_callback(
            lambda t: self.tasks.pop(key, None) if self.tasks.get(key) is t else None
        )
        return task

    def start(self, sub: Submission, case_uuid: UUID) -> asyncio.Task[None]:
        return self._launch(case_uuid, lambda: self.pipeline.start(sub, case_uuid),
                            on_error_status="uploaded")  # fmt: skip

    def resume_after_fix(self, case_uuid: UUID, **kw: Any) -> asyncio.Task[None]:
        return self._launch(case_uuid, lambda: self.pipeline.resume_after_fix(case_uuid, **kw),
                            on_error_status="stopped")  # fmt: skip

    def _resumer(self, case_uuid: UUID) -> Callable[[], Awaitable[Any]]:
        return lambda: self.pipeline.resume(case_uuid)

    def recover(self) -> int:
        """Continue every case that was `running` when the last process ended."""
        with self.engine.connect() as conn:
            ids = [
                r[0] for r in conn.execute(text("SELECT id FROM cases WHERE status = 'running'"))
            ]
        for case_uuid in ids:
            self._launch(case_uuid, self._resumer(case_uuid), on_error_status="uploaded")
        return len(ids)

    async def shutdown(self) -> None:
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
