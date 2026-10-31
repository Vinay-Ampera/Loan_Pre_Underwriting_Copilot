"""Policy agent schemas. The model writes only `PolicyLLMOutput`; the rest is filled in by code."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetrievedClause(BaseModel):
    clause_id: str
    title: str
    text: str
    source_tag: str
    doc_loan_type: str  # the policy file it came from: common or one loan type
    doc_version: str
    active: bool = True
    relevance: float  # 0..1: rerank score for search hits, 1.0 for rule-linked clauses
    vector_similarity: float | None = None
    via: Literal["search", "rule"] = "search"


class ClauseRef(BaseModel):
    clause_id: str
    text: str
    relevance: float


class PrecedentMatch(BaseModel):
    id: str
    similarity: float
    summary: str
    final_decision: str = ""


class FitFindingLLM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str | None = None  # the rules-file rule this finding is about, when there is one
    clause_ids: list[str]  # every clause the statement relies on
    assessment: Literal["fits", "concern", "info"]
    statement: str = Field(min_length=1, max_length=600)
    quote: str = Field(min_length=1, max_length=400)  # words copied from a cited clause


class PolicyLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fit_findings: list[FitFindingLLM]


class FitFinding(FitFindingLLM):
    source: Literal["model", "code"] = "model"


class PolicyResult(BaseModel):
    clauses: list[ClauseRef]
    precedent_matches: list[PrecedentMatch]
    fit_findings: list[FitFinding]
    score: float | None  # policy-fit points from the scoring code (10 max); None if not reached
    unverified: bool = False  # grounding failed twice: the officer sees code-written findings
    llm_skipped: bool = False  # run without a model: findings are code-written by design
    grounding_issues: list[str] = Field(default_factory=list)
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    fallback_used: bool = False
    retries: int = 0
