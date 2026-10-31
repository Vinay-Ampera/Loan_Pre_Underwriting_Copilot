"""Graph state and the small shapes every node shares.

State is plain JSON (dicts, lists, strings, numbers) so the Postgres checkpointer can store it.
It never holds document text: only extracted field values, which the case tables already keep.
Parallel nodes (Policy and Risk) write disjoint keys; the three list keys and `stage_status`
have reducers so both can add to them.
"""

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

RESET = {"__reset__": True}  # first item of a list update that replaces the list instead of adding

STAGES = ("supervisor", "extraction", "kyc", "policy", "risk", "decision")
# stages with a row in `stage_runs` (the Supervisor does coordination, not scoring)
DB_STAGES = ("extraction", "kyc", "policy", "risk", "decision")

CaseStatus = Literal["running", "stopped", "awaiting_confirmation", "confirmed", "overridden"]


def append_or_reset(old: list[Any] | None, new: list[Any] | None) -> list[Any]:
    old, new = old or [], new or []
    if new and new[0] == RESET:
        return new[1:]
    return [*old, *new]


def merge_dict(old: dict[str, Any] | None, new: dict[str, Any] | None) -> dict[str, Any]:
    return {**(old or {}), **(new or {})}


class PipelineState(TypedDict, total=False):
    case_id: str  # external id, e.g. SYN-PL-D01
    case_uuid: str  # cases.id
    submission: dict[str, Any]
    status: str
    run_no: int  # 1 for the first run; +1 each time a correction re-runs the case
    plan: dict[str, Any]
    extraction: dict[str, Any]
    case_input: dict[str, Any]
    score: dict[str, Any]  # ScoreReport as JSON: the one authoritative number set
    kyc: dict[str, Any]
    policy: dict[str, Any]
    risk: dict[str, Any]
    report: dict[str, Any]
    stop: dict[str, Any] | None  # {stage, class, reason} when a hard fail ended the run
    officer: dict[str, Any] | None
    stage_status: Annotated[dict[str, str], merge_dict]
    flags: Annotated[list[dict[str, Any]], append_or_reset]
    llm_calls: Annotated[list[dict[str, Any]], append_or_reset]
    evals: Annotated[list[dict[str, Any]], append_or_reset]


class Flag(BaseModel):
    """A note for the officer that does not stop the run."""

    stage: str
    code: str
    message: str
    rule_id: str | None = None
    role: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class LLMCallRecord(BaseModel):
    stage: str
    role: str
    provider: str = ""
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    fallback_used: bool = False


class EvalRecord(BaseModel):
    stage: str
    metric: str
    value: float | None  # None = the code check was inconclusive
    method: Literal["code", "judge"] = "code"
    note: str = ""
