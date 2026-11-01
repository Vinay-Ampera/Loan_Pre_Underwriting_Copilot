"""Langfuse and OpenTelemetry (Tempo) tracing.

Content-free by design: a trace holds stage names, model names, token counts, cost, latency and
evaluation scores, keyed by the case's database id. No prompt, reply or document text is sent, so
nothing here can carry personal data (SECURITY.md). Tracing never fails a case: every setup or send
error is swallowed after a warning. Off when the Langfuse keys are missing or
LANGFUSE_ENABLED=false.
"""

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from app.core.config import get_settings
from app.observability import metrics

log = logging.getLogger("loan_copilot.tracing")
_client: Any = None
_client_set = False
_otel_ready = False


def set_langfuse(client: Any) -> None:
    """Tests (and nothing else) install a stand-in client."""
    global _client, _client_set
    _client, _client_set = client, True


def _langfuse() -> Any:
    global _client, _client_set
    if _client_set:
        return _client
    _client_set = True
    s = get_settings()
    if not (s.langfuse_enabled and s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse  # noqa: PLC0415 - only when tracing is on

        _client = Langfuse(
            public_key=s.langfuse_public_key.get_secret_value(),
            secret_key=s.langfuse_secret_key.get_secret_value(),
            host=s.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("langfuse disabled: %s", type(exc).__name__)
        _client = None
    return _client


def trace_id_for(case_uuid: str) -> str | None:
    """The Langfuse trace id for a case; the same on every resume, so runs join one trace."""
    lf = _langfuse()
    if lf is None:
        return None
    try:
        return str(lf.create_trace_id(seed=str(case_uuid)))
    except Exception:  # noqa: BLE001
        return None


def _tracer() -> Any:
    """An OpenTelemetry tracer when OTEL_EXPORTER_OTLP_ENDPOINT is set (Tempo), else None."""
    global _otel_ready
    endpoint = get_settings().otel_exporter_otlp_endpoint
    if not endpoint:
        return None
    from opentelemetry import trace  # noqa: PLC0415

    if not _otel_ready:
        _otel_ready = True
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
            from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
            from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

            provider = TracerProvider(
                resource=Resource.create({"service.name": "loan-copilot-api"})
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
            trace.set_tracer_provider(provider)
        except Exception as exc:  # noqa: BLE001
            log.warning("otel disabled: %s", type(exc).__name__)
            return None
    return trace.get_tracer("loan_copilot")


@contextmanager
def _safely(factory: Callable[[], Any]) -> Iterator[Any]:
    """Enter a context manager built by `factory`; if that fails yield None and carry on."""
    with ExitStack() as stack:
        try:
            entered = stack.enter_context(factory())
        except Exception as exc:  # noqa: BLE001
            log.warning("tracing skipped: %s", type(exc).__name__)
            entered = None
        yield entered


@contextmanager
def stage_span(case_uuid: str, stage: str) -> Iterator[None]:
    """One span per pipeline stage: Langfuse (trace keyed by the case) and Tempo."""
    started = time.perf_counter()
    lf = _langfuse()
    tracer = _tracer()
    with ExitStack() as stack:
        if tracer is not None:
            attrs = {"lc.case_id": str(case_uuid), "lc.stage": stage}
            stack.enter_context(
                _safely(lambda: tracer.start_as_current_span(f"stage.{stage}", attributes=attrs))
            )
        if lf is not None:
            stack.enter_context(_safely(lambda: lf.start_as_current_observation(
                trace_context={"trace_id": lf.create_trace_id(seed=str(case_uuid))},
                name=stage, as_type="span", metadata={"stage": stage})))  # fmt: skip
        try:
            yield
        finally:
            metrics.STAGE_SECONDS.labels(stage).observe(time.perf_counter() - started)


@contextmanager
def generation(role: str) -> Iterator[Callable[..., None]]:
    """One Langfuse generation per model call. The yielded function records the result."""
    lf = _langfuse()
    with _safely(lambda: lf.start_as_current_observation(name=role, as_type="generation")) as gen:

        def done(model: str, tokens_in: int, tokens_out: int, cost: float, latency_ms: int,
                 fallback: bool) -> None:  # fmt: skip
            if gen is None:
                return
            try:
                gen.update(
                    model=model, usage_details={"input": tokens_in, "output": tokens_out},
                    cost_details={"total": cost} if cost else None,
                    metadata={"latency_ms": latency_ms, "fallback_used": fallback},
                )  # fmt: skip
            except Exception as exc:  # noqa: BLE001
                log.warning("tracing update skipped: %s", type(exc).__name__)

        yield done


def score_case(case_uuid: str, scores: dict[str, float]) -> None:
    """Attach evaluation scores to the case's trace, then flush so a short run still sends."""
    lf = _langfuse()
    if lf is None:
        return
    try:
        trace_id = lf.create_trace_id(seed=str(case_uuid))
        for name, value in scores.items():
            lf.create_score(trace_id=trace_id, name=name, value=float(value))
        lf.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("langfuse scores skipped: %s", type(exc).__name__)
