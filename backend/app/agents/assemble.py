"""Extraction stage: uploaded files -> checked documents -> the structured `CaseInput`.

For each file: intake (upload checks, text or OCR, classify, fields, validators, tamper hints), a
duplicate check, and, when required fields are missing, one masked LLM pass that only fills gaps.
Then the application form, the mock identity, bureau and GST lookups and the bank-statement
analytics are added to build the `CaseInput` the rules engine scores. Raw text stays in this
module's stack frames: it is never put in state, logs or a prompt (masked text only).
"""

import asyncio
import hashlib
import pickle
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.agents.runtime import AgentContext, to_record
from app.agents.state import Flag, LLMCallRecord
from app.agents.submission import DocumentRef, Submission
from app.intake import readcache
from app.intake.duplicates import CaseDocuments, Verdict, document_key, sha256_hex
from app.intake.masker import Masker
from app.intake.models import DocType
from app.intake.pipeline import IntakeResult, enrich, process_file
from app.scoring import analytics
from app.scoring.models import (
    BureauInput,
    CaseInput,
    DocumentInput,
    GstInput,
    LoanRecord,
    PersonInput,
    Role,
)

KYC_TYPES = {"pan_card", "aadhaar", "photo"}
TIE_CODES = {"NET_PAY_MISMATCH", "GROSS_SUM_MISMATCH", "DEDUCTION_SUM_MISMATCH", "TAXABLE_MISMATCH",
             "PROFIT_MISMATCH", "TOTAL_MISMATCH", "BALANCE_BREAK"}  # fmt: skip
TIE_TYPES = {"payslip", "form16", "itr", "pnl_balance_sheet", "gst_returns", "bank_statement"}


class DocSummary(BaseModel):
    """One uploaded file as the officer and the report see it. No text, no raw identifiers."""

    name: str
    role: Role
    accepted: bool
    kept: bool = False  # False for a rejected upload or an ignored duplicate
    doc_type: str = ""
    reject_code: str | None = None
    message: str = ""
    quality_score: float | None = None
    avg_confidence: float | None = None
    quality_flags: list[str] = Field(default_factory=list)
    tamper_hints: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    sha256: str = ""


class ExtractionOutput(BaseModel):
    documents: list[DocSummary]
    shortfalls: list[dict[str, Any]] = Field(default_factory=list)
    unreadable: list[str] = Field(default_factory=list)


@dataclass
class Extracted:
    output: ExtractionOutput
    case_input: CaseInput
    flags: list[Flag] = field(default_factory=list)
    calls: list[LLMCallRecord] = field(default_factory=list)


def _tie_out(doc_type: str, issue_codes: list[str]) -> bool | None:
    if doc_type not in TIE_TYPES:
        return None
    return not any(c in TIE_CODES for c in issue_codes)


async def _read_one(ctx: AgentContext, ref: DocumentRef, as_of: date) -> IntakeResult | None:
    """Intake for one file, off the event loop. One retry, then the file is reported unreadable."""
    data = await asyncio.to_thread(Path(ref.path).read_bytes)
    early = await asyncio.to_thread(_early_read, ctx, ref.path, data, as_of)
    if early is not None:  # read once at the intake desk: nothing is read again (E-54)
        return early
    cached = _cache_path(ctx, data, ref.name, as_of)
    if cached is not None and cached.exists():
        cached_result: IntakeResult = pickle.loads(cached.read_bytes())  # noqa: S301 - our own file
        return cached_result
    for _ in range(2):
        try:
            async with ctx.intake_slots:
                res = await asyncio.to_thread(process_file, data, ref.name, as_of=as_of)
        except Exception:  # noqa: BLE001 - a parser crash must not take the case down
            continue
        if cached is not None:
            cached.write_bytes(pickle.dumps(res))
        return res
    return None


def _early_read(ctx: AgentContext, path: str, data: bytes, as_of: date) -> IntakeResult | None:
    """The result saved when the file was accepted at the desk, if it still fits these bytes and
    this application date. The model pass needs the page text, which is never saved, so a file
    that pass would work on is read again; every other file is not."""
    sidecar = Path(path + readcache.READ_SUFFIX)
    if not sidecar.is_file():
        return None
    saved = readcache.load(sidecar.read_bytes(), sha256_hex(data), as_of)
    if saved is None or saved.document is None:
        return None
    if ctx.router is not None and (saved.missing or saved.document.doc_type is DocType.UNKNOWN):
        return None
    return saved


def _cache_path(ctx: AgentContext, data: bytes, name: str, as_of: date) -> Path | None:
    """Evaluation runs re-read the same synthetic files many times. With a cache directory set
    (never in production) the intake result is keyed by file hash, name and as-of date."""
    if ctx.intake_cache is None:
        return None
    ctx.intake_cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(data + name.encode() + as_of.isoformat().encode()).hexdigest()
    return ctx.intake_cache / f"{key}.pkl"


def _person(ctx: AgentContext, a: dict[str, Any], aadhaar: str | None) -> PersonInput:
    dob = date.fromisoformat(a["dob"])
    rec = ctx.services.bureau.report(a["pan"])
    return PersonInput(
        role=a["role"], full_name=a["full_name"], dob=dob, pan=a["pan"], address=a["address"],
        employment_type=a["employment_type"],
        residential_status=a.get("residential_status", "resident"),
        declared_monthly_income=a.get("declared_monthly_income"),
        months_in_current_employment=a.get("months_in_current_employment"),
        total_experience_months=a.get("total_experience_months"),
        identity_match=ctx.services.identity.verify(a["pan"], a["full_name"], dob, aadhaar),
        bureau=BureauInput(
            cibil_score=rec.cibil_score,
            active_loans=[LoanRecord(**x) for x in rec.active_loans],
            enquiry_dates=[date.fromisoformat(e["date"]) for e in rec.enquiries],
        ) if rec else None,
    )  # fmt: skip


async def extract(ctx: AgentContext, sub: Submission) -> Extracted:
    app = sub.application
    app_date = date.fromisoformat(app["application_date"])
    refs = sorted(sub.documents, key=lambda r: (r.role != "primary", r.name))
    results = await asyncio.gather(*(_read_one(ctx, r, app_date) for r in refs))

    registry, masker = CaseDocuments(), Masker()
    summaries: list[DocSummary] = []
    docs: list[DocumentInput] = []
    flags: list[Flag] = []
    calls: list[LLMCallRecord] = []
    txns_by_role: dict[Role, list[Any]] = {"primary": [], "co": []}
    income_kind: dict[str, Any] = {
        a["role"]: "salary" if a["employment_type"] == "salaried" else "business"
        for a in app["applicants"]
    }
    unreadable: list[str] = []
    aadhaar_by_role: dict[Role, str] = {}
    payslips: dict[Role, list[float]] = {"primary": [], "co": []}

    for ref, res in zip(refs, results, strict=True):
        if res is None:
            unreadable.append(ref.name)
            summaries.append(DocSummary(name=ref.name, role=ref.role, accepted=False,
                                        reject_code="unreadable", message="Could not read this file"))  # fmt: skip
            flags.append(Flag(stage="extraction", code="UNREADABLE_DOCUMENT", role=ref.role,
                              message=f"{ref.name} could not be read; upload it again"))  # fmt: skip
            continue
        s = DocSummary(name=ref.name, role=ref.role, accepted=res.accepted, sha256=res.sha256,
                       reject_code=res.upload.reject_code, message=res.upload.message)  # fmt: skip
        if not res.accepted or res.document is None:
            summaries.append(s)
            flags.append(Flag(stage="extraction", code="UPLOAD_REJECTED", role=ref.role,
                              message=f"{ref.name}: {res.upload.message or res.upload.reject_code}"))  # fmt: skip
            continue
        if ctx.router is not None and (res.missing or res.document.doc_type is DocType.UNKNOWN):
            llm_calls: list[Any] = []
            try:
                res = await enrich(res, ctx.router, masker, llm_calls)
            except Exception:  # noqa: BLE001 - the local values stand; the officer sees the gap
                flags.append(Flag(stage="extraction", code="LLM_FILL_FAILED", role=ref.role,
                                  message=f"{ref.name}: the model pass failed; fields left as read"))  # fmt: skip
            calls += [to_record("extraction", "extraction", c) for c in llm_calls]
        doc = res.document
        assert doc is not None
        decision = registry.add(ref.name, res.sha256, doc)
        kind = doc.doc_type.value
        issue_codes = [i.code for i in doc.issues]
        s.doc_type, s.quality_score, s.avg_confidence = kind, doc.quality_score, doc.avg_confidence
        s.quality_flags = list(doc.quality_flags)
        s.tamper_hints = [h.code for h in doc.tamper_hints]
        s.missing_fields = list(doc.meta.get("missing_fields", []))
        s.low_confidence_fields = [f.name for f in doc.fields if f.low_confidence]
        s.issues = issue_codes
        s.kept = decision.keep and doc.doc_type is not DocType.UNKNOWN
        summaries.append(s)
        for code, cond, msg in [
            ("PROMPT_INJECTION_SUSPECTED", "possible_prompt_injection" in doc.quality_flags,
             f"{ref.name} contains instruction-like text; it was treated as data only"),
            ("LOW_CONFIDENCE_FIELDS", bool(s.low_confidence_fields),
             f"{ref.name}: please check {', '.join(s.low_confidence_fields)}"),
            ("MISSING_FIELDS", bool(s.missing_fields),
             f"{ref.name}: could not read {', '.join(s.missing_fields)}"),
            ("UNRECOGNISED_DOCUMENT", doc.doc_type is DocType.UNKNOWN,
             f"{ref.name} was not recognised as a required document"),
            ("DUPLICATE_IGNORED", decision.verdict in (Verdict.EXACT_DUPLICATE, Verdict.SAME_DOCUMENT),
             f"{ref.name} repeats {decision.matched}; counted once"),
        ]:  # fmt: skip
            if cond:
                flags.append(Flag(stage="extraction", code=code, role=ref.role, message=msg))
        if not s.kept:
            continue

        fields = {f.name: f.value for f in doc.fields}
        units = 1
        if kind == "bank_statement":
            units = int(fields.get("months") or analytics.months_covered(doc.transactions) or 1)
        elif kind == "gst_returns":
            units = int(doc.meta.get("units") or 1)
        if kind == "aadhaar" and fields.get("aadhaar"):
            aadhaar_by_role[ref.role] = str(fields["aadhaar"])
        if kind == "payslip" and isinstance(fields.get("net"), int | float):
            payslips[ref.role].append(float(fields["net"]))  # type: ignore[arg-type]
        statement = None
        if kind == "bank_statement":
            txns_by_role[ref.role] += doc.transactions
            statement = analytics.analyse_statement(
                doc.transactions, ctx.ruleset.params.statement, income_kind[ref.role],
                return_window_months=ctx.ruleset.params.return_window_months, months=units,
            )  # fmt: skip
        docs.append(DocumentInput(
            doc_type=kind, role=ref.role, units=units, content_key=document_key(doc),
            fields=fields, quality_score=doc.quality_score, avg_confidence=doc.avg_confidence,
            tie_out_ok=_tie_out(kind, issue_codes), tamper_hints=[h.code for h in doc.tamper_hints],
            statement=statement,
        ))  # fmt: skip

    persons = [_person(ctx, a, aadhaar_by_role.get(a["role"])) for a in app["applicants"]]
    reg = next((x for x in docs if x.doc_type == "gst_registration"), None)
    gst_rec = ctx.services.gst.lookup(str(reg.fields.get("gstin"))) if reg else None
    inp = CaseInput(
        case_id=sub.case_id, loan_type=app["loan_type"], application_date=app_date,
        loan_amount=app["loan_amount"], tenure_months=app["tenure_months"],
        purpose=app.get("purpose") or "", persons=persons, documents=docs,
        details=app.get("loan_details", {}),
        gst=GstInput(gstin=gst_rec.gstin, pan=gst_rec.pan, turnover_12m=gst_rec.turnover_12m)
        if gst_rec else None,
    )  # fmt: skip
    from app.agents.risk import cross_document_hints  # risk owns the rule; applied here, once

    inp.extra_tamper_hints = cross_document_hints(persons, payslips, txns_by_role)
    from app.scoring.facts import document_shortfalls

    short = document_shortfalls(inp, ctx.ruleset)
    for item in short:
        flags.append(Flag(stage="extraction", code="MISSING_DOCUMENT", role=item["applicant"],
                          message=f"{item['type']}: {item['have']} of {item['needed']} provided",
                          detail=item))  # fmt: skip
    return Extracted(
        output=ExtractionOutput(documents=summaries, shortfalls=short, unreadable=unreadable),
        case_input=inp, flags=flags, calls=calls,
    )  # fmt: skip
