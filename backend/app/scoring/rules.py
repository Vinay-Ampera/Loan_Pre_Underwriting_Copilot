"""Rules file loader with schema validation and a version checksum.

Scoring logic lives in `app.scoring`; nothing else computes scores. The file is
`data/rules/rules.yaml`; it carries a `rules_version` that reports store.
"""

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import REPO_ROOT

RULES_PATH = REPO_ROOT / "data" / "rules" / "rules.yaml"

LoanType = Literal["personal", "home", "education", "business", "vehicle"]
Stage = Literal["kyc", "documents", "income", "credit", "policy"]
Operator = Literal["gte", "lte", "gt", "lt", "eq", "ne", "in"]
SourceTag = Literal["public", "RBI", "sample"]

RULE_ID_RE = re.compile(r"^(CM|PL|HL|ED|BL|VL)-[A-Z]+-\d{2}[A-Z]?$")


class Tier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator: Operator
    threshold: float | bool | str
    points: float = Field(ge=0)


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    loan_types: list[LoanType]
    stage: Stage
    kind: Literal["hard", "soft"]
    subject: Literal["each", "case"] | None = None
    roles: list[Literal["primary", "co"]] | None = None
    when: dict[str, str | bool] | None = None
    field: str
    operator: Operator | None = None
    threshold: float | bool | str | list[str] | None = None
    tiers: list[Tier] | None = None
    points: float = 0
    fail_class: Literal["fix", "eligibility"] | None = None
    on_fail: Literal["stop", "cap_refer"] | None = None
    policy_clause: str
    source: SourceTag

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if not RULE_ID_RE.match(self.rule_id):
            raise ValueError(f"{self.rule_id}: bad rule_id format")
        if self.kind == "soft":
            single = self.operator is not None and self.threshold is not None
            if single == (self.tiers is not None):
                raise ValueError(f"{self.rule_id}: soft rule needs operator+threshold OR tiers")
            if self.points <= 0:
                raise ValueError(f"{self.rule_id}: soft rule needs points > 0")
            if self.tiers and max(t.points for t in self.tiers) != self.points:
                raise ValueError(f"{self.rule_id}: points must equal the best tier")
            if self.subject or self.roles or self.fail_class or self.on_fail:
                raise ValueError(f"{self.rule_id}: soft rule has hard-rule fields")
        else:
            if self.operator is None or self.threshold is None or self.tiers:
                raise ValueError(f"{self.rule_id}: hard rule needs operator+threshold only")
            if self.points != 0:
                raise ValueError(f"{self.rule_id}: hard rule carries no points")
            if self.subject is None or self.on_fail is None:
                raise ValueError(f"{self.rule_id}: hard rule needs subject and on_fail")
            if self.subject == "each" and not self.roles:
                raise ValueError(f"{self.rule_id}: subject each needs roles")
            if (self.on_fail == "stop") != (self.fail_class is not None):
                raise ValueError(f"{self.rule_id}: stop rules (only) carry fail_class")
        return self

    @property
    def group(self) -> str:
        """Rules that differ only by a trailing letter (HL-POL-11A/B/C) are alternatives."""
        return re.sub(r"[A-Z]$", "", self.rule_id)


class Scoring(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage_weights: dict[Stage, float]
    bands: dict[Literal["approve_min", "refer_min"], float]
    eligibility_score_cap: float


class AgeRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_age: int
    student_min_age: int
    max_age_at_maturity: int


class PrecedentRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bonus_max: float
    similarity_min: float
    valid_months: int


class Pricing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate_pct: dict[LoanType, float]


class AmountBand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    max: float | None = None  # None = no upper bound


class EducationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collateral_required_above: float
    margin_free_fee_up_to: float
    margin_pct_india: float
    margin_pct_abroad: float


class TamperParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weak_codes: list[str]
    weak_hints_needed: int


class StatementParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    salary_keywords: list[str]
    recurring_amount_tolerance_pct: float
    recurring_min_months: int
    min_income_credit: float
    salary_cross_check_tolerance_pct: float


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    existing_loan_min_remaining_emis: int
    foir_cap_pct: float
    enquiry_window_days: int
    return_window_months: int
    coapp_verified_min_ratio: float
    party_match_min: float
    price_tolerance_pct: float
    home_amount_bands: list[AmountBand]
    disallowed_purposes: list[str]
    education: EducationParams
    tamper: TamperParams
    statement: StatementParams


class DocRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    kyc: bool = False
    min_count: int = 1
    applicant: Literal["primary", "co"] = "primary"
    when: dict[str, str] | None = None
    any_of: list[str] | None = None


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: dict[str, str]
    scoring: Scoring
    age: AgeRules
    precedent: PrecedentRules
    pricing: Pricing
    params: Params
    documents: dict[str, list[DocRequirement]]
    rules: list[Rule]
    checksum: str = ""

    @property
    def version(self) -> str:
        return self.meta["rules_version"]

    def rules_for(self, loan_type: str) -> list[Rule]:
        return [r for r in self.rules if loan_type in r.loan_types]

    def required_documents(self, loan_type: str) -> list[DocRequirement]:
        return [*self.documents["all"], *self.documents.get(loan_type, [])]

    def max_points(self, loan_type: str) -> dict[str, float]:
        """Best-case soft points per stage; alternatives in one group count once."""
        groups: dict[tuple[str, str], float] = defaultdict(float)
        for r in self.rules_for(loan_type):
            if r.kind == "soft":
                key = (r.stage, r.group)
                groups[key] = max(groups[key], r.points)
        out: dict[str, float] = defaultdict(float)
        for (stage, _), pts in groups.items():
            out[stage] += pts
        return dict(out)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        ids = [r.rule_id for r in self.rules]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate rule_id: {sorted(dupes)}")
        if sum(self.scoring.stage_weights.values()) != 100:
            raise ValueError("stage weights must total 100")
        for loan in ("personal", "home", "education", "business", "vehicle"):
            got = self.max_points(loan)
            for stage, weight in self.scoring.stage_weights.items():
                if got.get(stage, 0) != weight:
                    raise ValueError(f"{loan}/{stage}: rule points {got.get(stage, 0)} != {weight}")
        return self


def load_rules(path: Path = RULES_PATH) -> RuleSet:
    raw = path.read_bytes()
    data: dict[str, Any] = yaml.safe_load(raw)
    ruleset = RuleSet.model_validate(data)
    return ruleset.model_copy(update={"checksum": hashlib.sha256(raw).hexdigest()})
