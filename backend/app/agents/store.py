"""Database writes for a pipeline run: the case rows, one `stage_runs` row per stage with its
`rule_results`, LLM call and evaluation logs, the report and the case status.

Every writer is idempotent for a (case, stage) or (case, run) pair, so a node that runs again
after a crash or a correction replaces its own rows instead of duplicating them. No document
text is stored here; extracted values are stored masked (and locally, as the schema allows).
"""

import json
import mimetypes
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from app.agents.assemble import DocSummary
from app.agents.report import Report
from app.agents.results import RuleCheck
from app.agents.state import EvalRecord, LLMCallRecord
from app.agents.submission import Submission
from app.intake.masker import Masker
from app.observability import tracing
from app.scoring.models import CaseInput

SYSTEM_EMAIL = "pipeline@local.invalid"


def _j(value: Any) -> str:
    return json.dumps(value, default=str)


def ensure_system_user(conn: Connection) -> UUID:
    row = conn.execute(
        text("""INSERT INTO users (name, email, password_hash, role)
                VALUES ('Pipeline runner', :e, '!', 'officer')
                ON CONFLICT (email) DO UPDATE SET name = users.name RETURNING id"""),
        {"e": SYSTEM_EMAIL},
    ).one()
    return UUID(str(row[0]))


def next_case_no(conn: Connection) -> str:
    year = conn.execute(text("SELECT extract(year FROM now())::int")).scalar_one()
    n = conn.execute(
        text("SELECT coalesce(max(substring(case_no from 11)::int), 0) + 1 FROM cases "
             "WHERE case_no LIKE :p"), {"p": f"CASE-{year}-%"},
    ).scalar_one()  # fmt: skip
    return f"CASE-{year}-{n:04d}"


def create_case(conn: Connection, sub: Submission, user_id: UUID) -> UUID:
    """A fresh case row (and applicants) for a submission. A case with the same external id is
    replaced, so a command-line rerun starts clean."""
    app = sub.application
    conn.execute(text("DELETE FROM cases WHERE form_data->>'external_id' = :e"), {"e": sub.case_id})
    case_id = conn.execute(
        text("""INSERT INTO cases (case_no, loan_type, status, created_by, loan_amount, tenure_months,
                                   purpose, form_data)
                VALUES (:no, :lt, 'uploaded', :u, :amt, :ten, :purpose, CAST(:form AS jsonb))
                RETURNING id"""),
        {"no": next_case_no(conn), "lt": sub.loan_type, "u": user_id, "amt": app["loan_amount"],
         "ten": app["tenure_months"], "purpose": app.get("purpose"),
         "form": _j({"external_id": sub.case_id, "loan_details": app.get("loan_details", {}),
                     "application_date": app["application_date"]})},
    ).scalar_one()  # fmt: skip
    for a in app["applicants"]:
        conn.execute(
            text("""INSERT INTO applicants (case_id, role, full_name, dob, pan, aadhaar_last4, address,
                        phone, employment_type, employer_or_business, declared_monthly_income,
                        relationship_to_primary)
                    VALUES (:c, :role, :name, :dob, :pan, :a4, :addr, :phone, :emp, :biz, :inc, :rel)"""),
            {"c": case_id, "role": a["role"], "name": a["full_name"], "dob": a["dob"], "pan": a.get("pan"),
             "a4": a.get("aadhaar_last4"), "addr": a.get("address"), "phone": a.get("phone"),
             "emp": a["employment_type"] if a["employment_type"] in ("salaried", "self_employed") else None,
             "biz": a.get("employer_or_business"), "inc": a.get("declared_monthly_income"),
             "rel": a.get("relationship_to_primary")},
        )  # fmt: skip
    conn.execute(text("UPDATE test_cases SET case_ref = :c WHERE case_id = :e"),
                 {"c": case_id, "e": sub.case_id})  # fmt: skip
    return case_id  # type: ignore[no-any-return]


def save_documents(
    conn: Connection, case_id: UUID, sub: Submission, summaries: list[DocSummary], inp: CaseInput
) -> None:
    conn.execute(text("DELETE FROM documents WHERE case_id = :c"), {"c": case_id})
    applicants = {r[0]: (r[1], r[2]) for r in conn.execute(
        text("SELECT role, id, full_name FROM applicants WHERE case_id = :c"), {"c": case_id})}  # fmt: skip
    masker = Masker()
    for _, name in applicants.values():
        masker.add_known("NAME", name)
    paths = {(d.role, d.name): d.path for d in sub.documents}
    kept_inputs = iter(inp.documents)
    for s in summaries:
        doc_id = conn.execute(
            text("""INSERT INTO documents (case_id, applicant_id, role, doc_type, file_path, original_name,
                        mime, sha256, upload_checks, status, reject_reason)
                    VALUES (:c, :a, :role, :t, :p, :n, :m, :sha, CAST(:chk AS jsonb), :st, :rej)
                    RETURNING id"""),
            {"c": case_id, "a": applicants[s.role][0], "role": s.role, "t": s.doc_type or "unknown",
             "p": paths.get((s.role, s.name)), "n": s.name,
             "m": mimetypes.guess_type(s.name)[0] or "application/octet-stream",
             "sha": s.sha256 or None, "chk": _j({"flags": s.quality_flags, "issues": s.issues}),
             "st": "accepted" if s.accepted else "rejected", "rej": s.reject_code},
        ).scalar_one()  # fmt: skip
        if not s.kept:
            continue
        for key, value in next(kept_inputs).fields.items():
            if value is None:
                continue
            conn.execute(
                text("""INSERT INTO extracted_fields (document_id, field_name, value_masked, value_local,
                            needs_review) VALUES (:d, :f, :vm, :vl, :nr)"""),
                {"d": doc_id, "f": key, "vm": masker.mask(str(value)), "vl": str(value).encode(),
                 "nr": key in s.low_confidence_fields},
            )  # fmt: skip


def save_stage(
    conn: Connection, case_id: UUID, stage: str, *, status: str, score: float | None,
    max_score: float | None, hard_fail: bool = False, fail_class: str | None = None,
    findings: list[Any] | None = None, model: str | None = None, prompt_version: int | None = None,
    retries: int = 0, fallback_used: bool = False, checks: list[RuleCheck] | None = None,
) -> UUID:  # fmt: skip
    conn.execute(text("DELETE FROM stage_runs WHERE case_id = :c AND stage = :s"),
                 {"c": case_id, "s": stage})  # fmt: skip
    run_id = conn.execute(
        text("""INSERT INTO stage_runs (case_id, stage, status, score, max_score, hard_fail, fail_class,
                    findings, model_used, prompt_version, retries, fallback_used, finished_at)
                VALUES (:c, :s, :st, :sc, :mx, :hf, :fc, CAST(:f AS jsonb), :m, :pv, :r, :fb, now())
                RETURNING id"""),
        {"c": case_id, "s": stage, "st": status, "sc": score, "mx": max_score, "hf": hard_fail,
         "fc": fail_class, "f": _j(findings or []), "m": model,
         "pv": None if prompt_version is None else str(prompt_version), "r": retries, "fb": fallback_used},
    ).scalar_one()  # fmt: skip
    for c in checks or []:
        conn.execute(
            text("""INSERT INTO rule_results (stage_run_id, rule_id, kind, passed, points_awarded,
                        points_max, evidence, clause_id)
                    VALUES (:r, :id, :k, :p, :pa, :pm, CAST(:e AS jsonb), :cl)"""),
            {"r": run_id, "id": c.rule_id, "k": c.kind, "p": c.passed, "pa": c.points, "pm": c.points_max,
             "e": _j({**c.evidence, "role": c.role}), "cl": c.clause_id},
        )  # fmt: skip
    return run_id  # type: ignore[no-any-return]


def stage_run_ids(conn: Connection, case_id: UUID) -> dict[str, UUID]:
    rows = conn.execute(text("SELECT stage, id FROM stage_runs WHERE case_id = :c"), {"c": case_id})
    return {r[0]: r[1] for r in rows}


def save_logs(
    conn: Connection, case_id: UUID, calls: list[LLMCallRecord], evals: list[EvalRecord]
) -> None:
    """Replace the case's LLM-call and evaluation logs with the run's (idempotent)."""
    ids = stage_run_ids(conn, case_id)
    trace_id = tracing.trace_id_for(str(case_id))
    conn.execute(text("DELETE FROM llm_calls WHERE case_id = :c"), {"c": case_id})
    conn.execute(text("DELETE FROM eval_scores WHERE case_id = :c"), {"c": case_id})
    for c in calls:
        conn.execute(
            text("""INSERT INTO llm_calls (case_id, stage_run_id, provider, model, tokens_in, tokens_out,
                        cost_usd, latency_ms, fallback_used, langfuse_trace_id)
                    VALUES (:c, :s, :p, :m, :ti, :to, :cost, :lat, :fb, :tr)"""),
            {"c": case_id, "s": ids.get(c.stage), "p": c.provider or "unknown", "m": c.model,
             "ti": c.tokens_in, "to": c.tokens_out, "cost": c.cost_usd, "lat": c.latency_ms,
             "fb": c.fallback_used, "tr": trace_id},
        )  # fmt: skip
    for e in evals:
        if e.value is None:
            continue
        conn.execute(
            text("""INSERT INTO eval_scores (case_id, stage_run_id, metric, value, method)
                    VALUES (:c, :s, :m, :v, :me)"""),
            {"c": case_id, "s": ids.get(e.stage), "m": e.metric, "v": e.value, "me": e.method},
        )


def save_report(conn: Connection, case_id: UUID, run_no: int, report: Report) -> None:
    conn.execute(
        text("""INSERT INTO reports (case_id, version, summary_md, rejection_reason, report_json)
                VALUES (:c, :v, :s, :r, CAST(:j AS jsonb))
                ON CONFLICT (case_id, version) DO UPDATE SET summary_md = EXCLUDED.summary_md,
                    rejection_reason = EXCLUDED.rejection_reason, report_json = EXCLUDED.report_json"""),
        {"c": case_id, "v": run_no, "s": report.summary, "r": report.rejection_reason,
         "j": report.model_dump_json()},
    )  # fmt: skip


def update_case(conn: Connection, case_id: UUID, status: str, report: Report | None = None) -> None:
    policy = (report.versions.get("policy") or {}) if report else {}
    conn.execute(
        text("""UPDATE cases SET status = :st, stopped_stage = :ss, stop_class = :sc, total_score = :t,
                    band = :b, recommendation = :rec, policy_version = coalesce(:pv, policy_version),
                    rules_version = coalesce(:rv, rules_version), updated_at = now()
                WHERE id = :c"""),
        {"c": case_id, "st": status, "ss": report.stopped_stage if report else None,
         "sc": report.stop_class if report else None, "t": report.total_score if report else None,
         "b": report.band if report else None, "rec": report.recommendation if report else None,
         "pv": ",".join(f"{k}:{v}" for k, v in sorted(policy.items())) or None,
         "rv": report.versions.get("rules") if report else None},
    )  # fmt: skip


def audit(
    conn: Connection, action: str, entity_id: UUID | str, after: dict[str, Any],
    actor_id: UUID | str | None = None,
) -> None:  # fmt: skip
    conn.execute(
        text("""INSERT INTO audit_log (actor_id, action, entity, entity_id, after)
                VALUES (:u, :a, 'case', :e, CAST(:j AS jsonb))"""),
        {"u": actor_id, "a": action, "e": str(entity_id), "j": _j(after)},
    )


def record_officer_action(
    conn: Connection, case_id: UUID, officer_id: UUID, *, action: str, original: str, final: str,
    reason: str | None,
) -> None:  # fmt: skip
    conn.execute(
        text("""INSERT INTO officer_actions (case_id, officer_id, action, original_recommendation,
                    final_decision, reason, second_click_at)
                VALUES (:c, :o, :a, :orig, :fin, :r, now())"""),
        {"c": case_id, "o": officer_id, "a": action, "orig": original, "fin": final, "r": reason},
    )


def find_case(conn: Connection, external_id: str) -> UUID | None:
    row = conn.execute(text("SELECT id FROM cases WHERE form_data->>'external_id' = :e"),
                       {"e": external_id}).first()  # fmt: skip
    return None if row is None else row[0]
