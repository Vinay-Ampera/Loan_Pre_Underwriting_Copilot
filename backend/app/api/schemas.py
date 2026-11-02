"""Request bodies. Format checks only: ages, ratios and eligibility are decided by `scoring/`."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LoanType = Literal["personal", "home", "education", "business", "vehicle"]
EmploymentType = Literal["salaried", "self_employed", "student"]

# Loan-specific form sections. The frontend renders its form from this (GET /loan-types), so the
# fields exist in one place. kind: text | number | select | boolean.
LOAN_FIELDS: dict[str, list[dict[str, Any]]] = {
    "personal": [],
    "home": [
        {"name": "property_value", "label": "Property value (INR)", "kind": "number"},
        {
            "name": "property_address",
            "label": "Property address",
            "kind": "text",
            "required": False,
        },
        {
            "name": "seller_or_builder",
            "label": "Seller or builder",
            "kind": "text",
            "required": False,
        },
        {"name": "owner_name", "label": "Property owner name", "kind": "text", "required": False},
    ],
    "education": [
        {"name": "course", "label": "Course", "kind": "text"},
        {"name": "institution", "label": "Institution", "kind": "text", "required": False},
        {"name": "country", "label": "Country of study", "kind": "text"},
        {
            "name": "course_duration_months",
            "label": "Course duration (months)",
            "kind": "number",
            "required": False,
        },
        {"name": "total_fee", "label": "Total fee (INR)", "kind": "number"},
        {"name": "moratorium_months", "label": "Moratorium (months)", "kind": "number"},
        {"name": "margin_amount", "label": "Margin money (INR)", "kind": "number"},
        {"name": "collateral_offered", "label": "Collateral offered", "kind": "boolean"},
    ],
    "business": [
        {"name": "business_name", "label": "Business name", "kind": "text"},
        {
            "name": "constitution",
            "label": "Constitution",
            "kind": "select",
            "options": ["Proprietorship", "Partnership", "Private Limited", "LLP"],
        },  # fmt: skip
        {"name": "gstin", "label": "GSTIN", "kind": "text"},
        {"name": "udyam_number", "label": "Udyam number", "kind": "text", "required": False},
        {"name": "vintage_months", "label": "Business vintage (months)", "kind": "number"},
        {"name": "annual_turnover", "label": "Annual turnover (INR)", "kind": "number"},
    ],
    "vehicle": [
        {
            "name": "vehicle_kind",
            "label": "Vehicle kind",
            "kind": "select",
            "options": ["new_car", "used_car", "two_wheeler"],
        },  # fmt: skip
        {
            "name": "vehicle_condition",
            "label": "Condition",
            "kind": "select",
            "options": ["new", "used"],
        },  # fmt: skip
        {"name": "make", "label": "Make", "kind": "text"},
        {"name": "model", "label": "Model", "kind": "text"},
        {"name": "on_road_price", "label": "On-road price (INR)", "kind": "number"},
        {"name": "dealer", "label": "Dealer", "kind": "text"},
    ],
}
CO_APPLICANT = {"personal": "not_allowed", "home": "optional", "education": "required",
                "business": "not_allowed", "vehicle": "not_allowed"}  # fmt: skip


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ApplicantIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["primary", "co"]
    full_name: str = Field(min_length=2, max_length=120)
    dob: date
    # a masked value (ABCDE****F) is accepted only when correcting a case: it keeps the stored one
    pan: str = Field(pattern=r"^[A-Z]{5}([0-9]{4}|\*{4})[A-Z]$")
    aadhaar_last4: str = Field(pattern=r"^[0-9]{4}$")
    address: str = Field(min_length=5, max_length=300)
    phone: str | None = Field(default=None, pattern=r"^([6-9][0-9]{9}|\*{6}[0-9]{4})$")
    # optional contact email for customer messages (primary applicant); a masked value keeps the stored one
    email: str | None = Field(default=None, max_length=200,
                              pattern=r"^([^@\s*]+|\*{4})@[^@\s]+\.[^@\s]+$")  # fmt: skip
    employment_type: EmploymentType
    employer_or_business: str | None = Field(default=None, max_length=160)
    declared_monthly_income: float | None = Field(default=None, ge=0)
    relationship_to_primary: str | None = Field(default=None, max_length=60)
    residential_status: Literal["resident", "NRI"] = "resident"
    months_in_current_employment: int | None = Field(default=None, ge=0, le=1200)
    total_experience_months: int | None = Field(default=None, ge=0, le=1200)

    @field_validator("phone", "email", mode="before")
    @classmethod
    def _blank_phone(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("pan", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


class CaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loan_type: LoanType
    loan_amount: float = Field(gt=0)
    tenure_months: int = Field(gt=0, le=600)
    purpose: str | None = Field(default=None, max_length=200)
    application_date: date | None = None  # default: today; not in the future
    loan_details: dict[str, Any] = Field(default_factory=dict)
    applicants: list[ApplicantIn] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def _shape(self) -> "CaseIn":
        if self.application_date and self.application_date > date.today():
            raise ValueError("the application date cannot be in the future")
        roles = [a.role for a in self.applicants]
        if roles.count("primary") != 1:
            raise ValueError("exactly one primary applicant is needed")
        rule = CO_APPLICANT[self.loan_type]
        if "co" in roles and rule == "not_allowed":
            raise ValueError(f"a {self.loan_type} loan has no co-applicant")
        if "co" not in roles and rule == "required":
            raise ValueError(f"a {self.loan_type} loan needs a co-applicant")
        if len(roles) > 2 or roles.count("co") > 1:
            raise ValueError("at most one co-applicant")
        allowed = {f["name"] for f in LOAN_FIELDS[self.loan_type]}
        extra = set(self.loan_details) - allowed
        if extra:
            raise ValueError(f"unknown loan details: {', '.join(sorted(extra))}")
        missing = [f["label"] for f in LOAN_FIELDS[self.loan_type]
                   if self.loan_details.get(f["name"]) in (None, "")
                   and f["kind"] != "boolean" and f.get("required", True)]  # fmt: skip
        if missing:
            raise ValueError(f"missing loan details: {', '.join(missing)}")
        return self


class ResumeIn(BaseModel):
    """A fix-type stop: the corrected form (optional); files are replaced by uploading again."""

    model_config = ConfigDict(extra="forbid")

    case: CaseIn | None = None


class OfficerActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_click: bool = False
    reason: str | None = Field(default=None, max_length=2000)
    final_decision: Literal["approve", "refer", "reject"] | None = None


class PrecedentApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_until: date | None = None  # default: today + the rules file's valid_months


class PrecedentRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)


class UserCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Literal["officer", "admin"] = "officer"


EMAIL_PATTERN = r"^[^@\s*]+@[^@\s]+\.[^@\s]+$"


class MessageIn(BaseModel):
    """Start a customer message. `body` defaults to the template text; the footer and the contact
    lines are added by the server."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    template: Literal["general_contact", "contact_soon", "visit_branch", "blank"]
    body: str | None = Field(default=None, max_length=2000)
    include_case_ref: bool = False
    recipient_email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)


class MessageEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    body: str = Field(max_length=2000)
    include_case_ref: bool = False
    recipient_email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_click: bool = False


class IssueIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Literal["bug", "wrong_result", "access", "other"]
    case_ref: str | None = Field(default=None, pattern=r"^CASE-[0-9]{4}-[0-9]{4}$")
    body: str = Field(min_length=10, max_length=1000)

    @field_validator("case_ref", mode="before")
    @classmethod
    def _blank_ref(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v
