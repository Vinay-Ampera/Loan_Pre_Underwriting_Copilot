"""Prometheus metrics. Labels are stage, model, band-like words: never a case number or a name."""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

CASES = Counter("lc_cases_total", "Finished pipeline runs", ["status", "recommendation"])
LLM_TOKENS = Counter("lc_llm_tokens_total", "LLM tokens", ["stage", "model", "direction"])
LLM_COST = Counter("lc_llm_cost_usd_total", "LLM cost in USD", ["stage"])
LLM_LATENCY = Histogram("lc_llm_latency_seconds", "LLM call latency", ["stage"])
FALLBACKS = Counter("lc_llm_fallbacks_total", "Calls answered by a fallback model", ["stage"])
STAGE_SECONDS = Histogram("lc_stage_seconds", "Pipeline stage duration", ["stage"])
UNVERIFIED = Counter("lc_unverified_total", "Agent outputs passed on as unverified", ["stage"])
OFFICER = Counter("lc_officer_actions_total", "Officer confirm and override actions", ["action"])
PRECEDENTS = Counter("lc_precedent_events_total", "Precedent lifecycle events", ["event"])
EMAILS = Counter("lc_emails_total", "Staff email outcomes (a retry is queued)", ["kind", "status"])
CASES_CREATED = Counter("lc_new_cases_total", "New cases", ["loan_type", "origin"])
TIME_TO_DECISION = Histogram(
    "lc_time_to_decision_seconds", "From a case being created to the officer's decision",
    ["loan_type"],
    buckets=(300, 900, 1800, 3600, 4 * 3600, 8 * 3600, 86400, 2 * 86400, 7 * 86400, 30 * 86400),
)  # fmt: skip


def record_run(report: dict, calls: list) -> None:  # type: ignore[type-arg]
    CASES.labels(report.get("status", "?"), report.get("recommendation", "?")).inc()
    for u in report.get("unverified", []):
        UNVERIFIED.labels(u.get("stage", "?")).inc()
    if report.get("precedent_bonus"):
        PRECEDENTS.labels("bonus_applied").inc()
    for c in calls:
        LLM_TOKENS.labels(c.stage, c.model, "in").inc(c.tokens_in)
        LLM_TOKENS.labels(c.stage, c.model, "out").inc(c.tokens_out)
        LLM_COST.labels(c.stage).inc(c.cost_usd)
        LLM_LATENCY.labels(c.stage).observe(c.latency_ms / 1000)
        if c.fallback_used:
            FALLBACKS.labels(c.stage).inc()


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
