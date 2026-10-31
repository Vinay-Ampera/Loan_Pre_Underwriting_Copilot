"""Hand-built CaseInput objects for scoring tests (no generated data needed)."""

from datetime import date

from app.scoring.models import (
    BureauInput,
    CaseInput,
    DocumentInput,
    LoanRecord,
    PersonInput,
    StatementAnalytics,
)

APP_DATE = date(2026, 10, 20)


def person(role: str = "primary", *, dob: date = date(1990, 5, 14), emp: str = "salaried",
           income: float | None = 60000, cibil: int | None = 790, loans: list[LoanRecord] | None = None,
           name: str = "Rekha Sinha") -> PersonInput:  # fmt: skip
    return PersonInput(
        role=role,  # type: ignore[arg-type]
        full_name=name, dob=dob, pan="ABCPS1234F", address="12, Park Road, Pune, Maharashtra 411001",
        employment_type=emp, declared_monthly_income=income, months_in_current_employment=60,
        total_experience_months=120, identity_match=True,
        bureau=BureauInput(cibil_score=cibil, active_loans=loans or [],
                           enquiry_dates=[date(2026, 9, 1)]) if cibil is not None else None,
    )  # fmt: skip


def kyc_docs(role: str = "primary", *, name: str = "Rekha Sinha", dob: str = "1990-05-14",
             q: float = 95) -> list[DocumentInput]:  # fmt: skip
    common = dict(role=role, quality_score=q, avg_confidence=0.96)
    return [
        DocumentInput(doc_type="pan_card", fields={"name": name, "dob": dob, "pan": "ABCPS1234F"}, **common),  # type: ignore[arg-type]
        DocumentInput(doc_type="aadhaar", fields={
            "name": name, "dob": dob, "aadhaar": "234567890124",
            "address": "12, Park Road, Pune, Maharashtra 411001"}, **common),  # type: ignore[arg-type]
        DocumentInput(doc_type="photo", fields={"name": name}, **common),  # type: ignore[arg-type]
    ]  # fmt: skip


def income_docs(role: str = "primary", net: float = 60000, slips: int = 3) -> list[DocumentInput]:
    common = dict(role=role, quality_score=95, avg_confidence=0.96, tie_out_ok=True)
    docs = [
        DocumentInput(doc_type="payslip", fields={"employee": "Rekha Sinha", "net": net, "month": f"2026-0{7 + i}",
                                                  "pan": "ABCPS1234F"}, content_key=f"m{i}", **common)  # type: ignore[arg-type]
        for i in range(slips)
    ]  # fmt: skip
    docs.append(
        DocumentInput(
            doc_type="bank_statement",
            units=6,
            statement=StatementAnalytics(months=6, income_months=6, credits_total=net * 6),
            **common,
        )
    )  # type: ignore[arg-type]
    return docs


def personal_case(**over: object) -> CaseInput:
    """A personal-loan case that scores 100: salaried, clean documents, good bureau record."""
    base = dict(
        case_id="T-PL-1", loan_type="personal", application_date=APP_DATE, loan_amount=300000,
        tenure_months=36, purpose="home renovation", persons=[person()],
        documents=[*kyc_docs(), *income_docs()],
    )  # fmt: skip
    base.update(over)
    return CaseInput(**base)  # type: ignore[arg-type]
