"""Pydantic shapes for the scoring engine: what goes in (structured case facts) and what comes out.

Inputs are plain structured data: nothing here reads a file, calls a service or touches an LLM.
The Extraction agent (Stage 5) and the replay adapter (`replay.py`) both build a `CaseInput`.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["primary", "co"]
FieldValue = str | float | int | bool | None


# --- input ----------------------------------------------------------------------------------
class StatementAnalytics(BaseModel):
    """Numbers measured from one bank statement (see `analytics.analyse_statement`)."""

    months: int  # months the statement covers
    income_months: int  # months with at least one income credit
    credits_total: float  # income credits over the whole statement
    cheque_returns: int = 0
    nach_returns: int = 0
    salary_credit: float | None = None  # typical monthly salary credit, when one was detected
    detected_emi_monthly: float = 0.0  # recurring loan debits seen on the statement
    evidence: list[str] = Field(default_factory=list)  # short row references for the report

    @property
    def returns(self) -> int:
        return self.cheque_returns + self.nach_returns


class DocumentInput(BaseModel):
    doc_type: str
    role: Role = "primary"
    units: int = 1  # months for statements and GST returns, otherwise 1
    content_key: str | None = None  # same key = same document; counted once (EDGE_CASES E-03)
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    quality_score: float | None = None  # 0-100 from intake
    avg_confidence: float | None = None  # 0-1 from intake
    tie_out_ok: bool | None = None  # totals / running balance tie out; None = not applicable
    tamper_hints: list[str] = Field(default_factory=list)  # hint codes from intake
    statement: StatementAnalytics | None = None


class LoanRecord(BaseModel):
    lender: str = ""
    emi: float
    remaining_emis: int
    dpd_max_12m: int = 0


class BureauInput(BaseModel):
    cibil_score: int | None = None  # None = no bureau record found
    active_loans: list[LoanRecord] = Field(default_factory=list)
    enquiry_dates: list[date] = Field(default_factory=list)


class PersonInput(BaseModel):
    role: Role
    full_name: str
    dob: date
    pan: str | None = None
    address: str | None = None
    employment_type: str  # salaried | self_employed | student
    residential_status: str = "resident"
    declared_monthly_income: float | None = None
    months_in_current_employment: int | None = None
    total_experience_months: int | None = None
    identity_match: bool | None = None  # mock identity lookup result; None = not looked up
    bureau: BureauInput | None = None


class GstInput(BaseModel):
    gstin: str
    pan: str  # PAN registered against the GSTIN
    turnover_12m: float


class CaseInput(BaseModel):
    case_id: str
    loan_type: Literal["personal", "home", "education", "business", "vehicle"]
    application_date: date
    loan_amount: float
    tenure_months: int  # total tenure; for education it includes the moratorium
    purpose: str = ""
    persons: list[PersonInput]
    documents: list[DocumentInput] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)  # application "loan_details"
    gst: GstInput | None = None
    extra_tamper_hints: list[str] = Field(default_factory=list)  # cross-document hints


# --- output ---------------------------------------------------------------------------------
class RuleOutcome(BaseModel):
    rule_id: str
    stage: str
    kind: Literal["hard", "soft"]
    passed: bool
    points_awarded: float
    points_max: float
    clause_id: str
    role: str | None = None
    on_fail: str | None = None
    fail_class: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    """A note for the officer that does not change the score (FOIR over cap, name variants...)."""

    code: str
    message: str
    rule_id: str | None = None
    role: str | None = None


class ScoreReport(BaseModel):
    case_id: str
    loan_type: str
    rules_version: str
    rules_checksum: str
    total_score: float | None  # None when the run stopped early
    indicative_score: float | None  # eligibility stop: points earned so far, capped below 60
    band: Literal["approve", "refer", "reject"] | None
    recommendation: Literal["recommend_approve", "refer", "recommend_reject", "fix_required"]
    stage_scores: dict[str, float]
    stage_max: dict[str, float]
    stopped_stage: str | None
    stop_class: Literal["fix", "eligibility"] | None
    capped_to_refer: bool
    precedent_bonus: float = 0.0
    failed_rule_ids: list[str]
    stages_run: list[str]
    results: list[RuleOutcome]
    findings: list[Finding]
    case_facts: dict[str, Any]
    person_facts: list[dict[str, Any]]
