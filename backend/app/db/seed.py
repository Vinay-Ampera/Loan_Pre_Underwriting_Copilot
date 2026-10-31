"""Load rules, policy, mock-service records and answer keys into Postgres.

`python -m app.db.seed [--only rules,policy,mock,tests]`. Idempotent (upserts).
Policy chunks are stored without embeddings; Stage 4's re-index command adds them.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, create_engine, text

from app.core.config import REPO_ROOT, get_settings
from app.rag.policy_loader import load_all
from app.scoring.rules import load_rules

OUTPUT = REPO_ROOT / "data" / "synthetic" / "output"


def seed_rules(conn: Connection) -> int:
    rs = load_rules()
    conn.execute(
        text(
            "INSERT INTO rule_set_versions (version, checksum) VALUES (:v, :c) "
            "ON CONFLICT (version) DO UPDATE SET checksum = EXCLUDED.checksum, loaded_at = now()"
        ),
        {"v": rs.version, "c": rs.checksum},
    )
    sql = text(
        """INSERT INTO rules (rule_id, loan_type, stage, kind, field, operator, threshold, points,
               policy_clause, source_tag, version, active, loan_types, subject, roles, when_cond,
               tiers, fail_class, on_fail)
           VALUES (:rule_id, :loan_type, :stage, :kind, :field, :operator, CAST(:threshold AS jsonb),
               :points, :policy_clause, :source_tag, :version, true, :loan_types, :subject, :roles,
               CAST(:when_cond AS jsonb), CAST(:tiers AS jsonb), :fail_class, :on_fail)
           ON CONFLICT (rule_id) DO UPDATE SET loan_type = EXCLUDED.loan_type, stage = EXCLUDED.stage,
               kind = EXCLUDED.kind, field = EXCLUDED.field, operator = EXCLUDED.operator,
               threshold = EXCLUDED.threshold, points = EXCLUDED.points,
               policy_clause = EXCLUDED.policy_clause, source_tag = EXCLUDED.source_tag,
               version = EXCLUDED.version, active = true, loan_types = EXCLUDED.loan_types,
               subject = EXCLUDED.subject, roles = EXCLUDED.roles, when_cond = EXCLUDED.when_cond,
               tiers = EXCLUDED.tiers, fail_class = EXCLUDED.fail_class, on_fail = EXCLUDED.on_fail"""
    )
    for r in rs.rules:
        conn.execute(
            sql,
            {
                "rule_id": r.rule_id,
                "loan_type": r.loan_types[0] if len(r.loan_types) == 1 else "common",
                "stage": r.stage, "kind": r.kind, "field": r.field,
                "operator": r.operator or "tiers",
                "threshold": None if r.threshold is None else json.dumps(r.threshold),
                "points": r.points, "policy_clause": r.policy_clause, "source_tag": r.source,
                "version": rs.version, "loan_types": list(r.loan_types), "subject": r.subject,
                "roles": r.roles, "when_cond": json.dumps(r.when) if r.when else None,
                "tiers": json.dumps([t.model_dump() for t in r.tiers]) if r.tiers else None,
                "fail_class": r.fail_class, "on_fail": r.on_fail,
            },
        )  # fmt: skip
    return len(rs.rules)


def seed_policy(conn: Connection) -> int:
    n = 0
    for doc in load_all():
        doc_id = conn.execute(
            text(
                """INSERT INTO policy_documents (loan_type, title, version, source_tag, file_path,
                       effective_from, active)
                   VALUES (:lt, :title, :version, 'sample', :path, :eff, true)
                   ON CONFLICT (loan_type, version) DO UPDATE SET title = EXCLUDED.title,
                       file_path = EXCLUDED.file_path, effective_from = EXCLUDED.effective_from
                   RETURNING id"""
            ),
            {"lt": doc.loan_type, "title": doc.title, "version": doc.version,
             "path": str(doc.path.relative_to(REPO_ROOT)), "eff": doc.effective_from},
        ).scalar_one()  # fmt: skip
        for c in doc.clauses:
            conn.execute(
                text(
                    """INSERT INTO policy_chunks (policy_document_id, clause_id, text, metadata)
                       VALUES (:d, :cid, :t, CAST(:m AS jsonb))
                       ON CONFLICT (policy_document_id, clause_id)
                       DO UPDATE SET text = EXCLUDED.text, metadata = EXCLUDED.metadata,
                                     embedding = NULL"""
                ),
                {"d": doc_id, "cid": c.clause_id, "t": c.text,
                 "m": json.dumps({"source_tag": c.source_tag, "title": c.title})},
            )  # fmt: skip
            n += 1
    return n


def _records(out: Path, name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads((out / "records" / f"{name}.json").read_text())
    return rows


def seed_mock(conn: Connection, out: Path = OUTPUT) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in _records(out, "identity"):
        conn.execute(text(
            "INSERT INTO mock_identity (pan, name, dob, aadhaar_hash, address) "
            "VALUES (:pan, :name, :dob, :aadhaar_hash, :address) ON CONFLICT (pan) DO UPDATE SET "
            "name = EXCLUDED.name, dob = EXCLUDED.dob, aadhaar_hash = EXCLUDED.aadhaar_hash, "
            "address = EXCLUDED.address"), r)  # fmt: skip
    counts["identity"] = len(_records(out, "identity"))
    for r in _records(out, "bureau"):
        conn.execute(text(
            "INSERT INTO mock_bureau (pan, cibil_score, active_loans, enquiries) VALUES "
            "(:pan, :cibil_score, CAST(:l AS jsonb), CAST(:e AS jsonb)) ON CONFLICT (pan) DO UPDATE "
            "SET cibil_score = EXCLUDED.cibil_score, active_loans = EXCLUDED.active_loans, "
            "enquiries = EXCLUDED.enquiries"),
            {"pan": r["pan"], "cibil_score": r["cibil_score"], "l": json.dumps(r["active_loans"]),
             "e": json.dumps(r["enquiries"])})  # fmt: skip
    counts["bureau"] = len(_records(out, "bureau"))
    for r in _records(out, "gst"):
        conn.execute(text(
            "INSERT INTO mock_gst (gstin, legal_name, pan, turnover_12m, filings) VALUES "
            "(:gstin, :legal_name, :pan, :turnover_12m, CAST(:f AS jsonb)) ON CONFLICT (gstin) "
            "DO UPDATE SET legal_name = EXCLUDED.legal_name, pan = EXCLUDED.pan, "
            "turnover_12m = EXCLUDED.turnover_12m, filings = EXCLUDED.filings"),
            {**{k: r[k] for k in ("gstin", "legal_name", "pan", "turnover_12m")}, "f": json.dumps(r["filings"])})  # fmt: skip
    counts["gst"] = len(_records(out, "gst"))
    for r in _records(out, "udyam"):
        conn.execute(text(
            "INSERT INTO mock_udyam (udyam_no, legal_name, pan, registered_on) VALUES "
            "(:udyam_no, :legal_name, :pan, :registered_on) ON CONFLICT (udyam_no) DO UPDATE SET "
            "legal_name = EXCLUDED.legal_name, pan = EXCLUDED.pan, "
            "registered_on = EXCLUDED.registered_on"), r)  # fmt: skip
    counts["udyam"] = len(_records(out, "udyam"))
    return counts


def seed_tests(conn: Connection, out: Path = OUTPUT) -> int:
    index = json.loads((out / "index.json").read_text())
    for r in index:
        conn.execute(
            text(
                """INSERT INTO test_cases (case_id, split, loan_type, scenario, expected_band,
                       expected_stop_stage, expected_flags, target_score)
                   VALUES (:case_id, :split, :loan_type, :scenario, :expected_band,
                       :expected_stop_stage, CAST(:flags AS jsonb), :target_score)
                   ON CONFLICT (case_id) DO UPDATE SET split = EXCLUDED.split,
                       scenario = EXCLUDED.scenario, expected_band = EXCLUDED.expected_band,
                       expected_stop_stage = EXCLUDED.expected_stop_stage,
                       expected_flags = EXCLUDED.expected_flags, target_score = EXCLUDED.target_score"""
            ),
            {**{k: r[k] for k in ("case_id", "split", "loan_type", "scenario", "expected_band",
                                  "expected_stop_stage", "target_score")},
             "flags": json.dumps(r["expected_flags"])},
        )  # fmt: skip
    for f in json.loads((out / "fairness.json").read_text()):
        conn.execute(
            text(
                """INSERT INTO fairness_attributes (case_id, applicant_role, gender, age_band, city_tier)
                   VALUES (:case_id, :applicant_role, :gender, :age_band, :city_tier)
                   ON CONFLICT (case_id, applicant_role) DO UPDATE SET gender = EXCLUDED.gender,
                       age_band = EXCLUDED.age_band, city_tier = EXCLUDED.city_tier"""
            ),
            f,
        )
    return len(index)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="rules,policy,mock,tests")
    args = ap.parse_args()
    parts = set(args.only.split(","))
    engine = create_engine(get_settings().sqlalchemy_url())
    with engine.begin() as conn:  # one transaction: all or nothing
        if "rules" in parts:
            print("rules:", seed_rules(conn))
        if "policy" in parts:
            print("policy clauses:", seed_policy(conn))
        if "mock" in parts:
            print("mock records:", seed_mock(conn))
        if "tests" in parts:
            print("test cases:", seed_tests(conn))


if __name__ == "__main__":
    main()
