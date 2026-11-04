"""Migrations apply on a clean database, and roll back. Uses a throwaway database."""

import pytest
from alembic import command
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.db.migrate import alembic_config

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "users", "cases", "applicants", "documents", "extracted_fields", "stage_runs",
    "rule_results", "reports", "eval_scores", "llm_calls", "officer_actions", "precedents",
    "audit_log", "policy_documents", "policy_chunks", "rules", "rule_set_versions",
    "mock_identity", "mock_bureau", "mock_gst", "mock_udyam", "test_cases",
    "fairness_attributes", "admin_actions", "upload_links",
}  # fmt: skip


def test_migrations_apply_and_roll_back(clean_db_url: str) -> None:
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "head")

    engine = create_engine(clean_db_url)
    with engine.connect() as conn:
        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert tables >= EXPECTED_TABLES
        dim = conn.execute(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'precedents'::regclass AND attname = 'embedding'"
            )
        ).scalar_one()
        assert dim == 384
        hnsw = conn.execute(
            text("SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%USING hnsw%'")
        ).scalar_one()
        assert hnsw == 2

    command.downgrade(cfg, "base")
    with engine.connect() as conn:
        left = {
            r[0]
            for r in conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }
        assert not (EXPECTED_TABLES & left)
    engine.dispose()


def test_audit_log_is_append_only_and_override_needs_reason(clean_db_url: str) -> None:
    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO audit_log (action, entity) VALUES ('t', 'x')"))
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET action = 'y'"))
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log"))

    with engine.begin() as conn:
        officer = conn.execute(
            text(
                "INSERT INTO users (name, email, password_hash, role) "
                "VALUES ('o', 'o@example.test', 'x', 'officer') RETURNING id"
            )
        ).scalar_one()
        case = conn.execute(
            text(
                "INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months) "
                "VALUES ('CASE-2026-0001', 'personal', :u, 100000, 12) RETURNING id"
            ),
            {"u": officer},
        ).scalar_one()
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO officer_actions (case_id, officer_id, action, "
                "original_recommendation, final_decision, reason, second_click_at) "
                "VALUES (:c, :o, 'override', 'reject', 'approve', '  ', now())"
            ),
            {"c": case, "o": officer},
        )
    engine.dispose()


def test_seed_loads_rules_policy_and_answer_keys(clean_db_url: str) -> None:
    from app.db import seed
    from app.scoring.rules import load_rules

    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)
    with engine.begin() as conn:
        assert seed.seed_rules(conn) == len(load_rules().rules)
        assert seed.seed_policy(conn) >= 60
        assert seed.seed_rules(conn)  # idempotent: second run upserts, no duplicate-key error
        # every rule's clause exists as a policy chunk
        orphans = conn.execute(
            text(
                "SELECT count(*) FROM rules r WHERE NOT EXISTS "
                "(SELECT 1 FROM policy_chunks c WHERE c.clause_id = r.policy_clause)"
            )
        ).scalar_one()
        assert orphans == 0
        if (seed.OUTPUT / "index.json").exists():
            seed.seed_mock(conn)
            assert seed.seed_tests(conn) == 100
            splits = dict(
                conn.execute(text("SELECT split, count(*) FROM test_cases GROUP BY split")).all()
            )
            assert splits == {"dev": 60, "test": 40}
    engine.dispose()


def test_role_grants_isolate_fairness_and_protect_audit_log(clean_db_url: str) -> None:
    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)

    def can(conn: Connection, role: str, table: str, priv: str) -> bool:
        return bool(
            conn.execute(
                text("SELECT has_table_privilege(:r, :t, :p)"), {"r": role, "t": table, "p": priv}
            ).scalar_one()
        )

    with engine.connect() as conn:
        if not conn.execute(
            text("SELECT count(*) FROM pg_roles WHERE rolname = 'app_rw'")
        ).scalar_one():
            pytest.skip("roles could not be created on this server")
        # the pipeline role cannot see fairness attributes in any way
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            assert not can(conn, "app_rw", "fairness_attributes", priv)
        assert can(conn, "app_rw", "cases", "SELECT") and can(conn, "app_rw", "cases", "INSERT")
        # audit log: insert only
        assert can(conn, "app_rw", "audit_log", "INSERT")
        assert not can(conn, "app_rw", "audit_log", "UPDATE")
        assert not can(conn, "app_rw", "audit_log", "DELETE")
        # monitoring role reads, never writes
        assert can(conn, "report_ro", "fairness_attributes", "SELECT")
        assert not can(conn, "report_ro", "fairness_attributes", "INSERT")
    engine.dispose()


def test_admin_action_needs_a_reason_and_a_real_decision(clean_db_url: str) -> None:
    command.upgrade(alembic_config(clean_db_url), "head")
    engine = create_engine(clean_db_url)
    with engine.begin() as conn:
        uid = conn.execute(
            text("""INSERT INTO users (name, email, password_hash, role)
                                   VALUES ('A', 'a@example.test', 'x', 'admin') RETURNING id""")
        ).scalar_one()
        case = conn.execute(text("""INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months)
                                    VALUES ('CASE-2026-0001', 'personal', :u, 1000, 12) RETURNING id"""),
                            {"u": uid}).scalar_one()  # fmt: skip
    insert = text("""INSERT INTO admin_actions (case_id, admin_id, action, previous_decision,
                         final_decision, reason, second_click_at)
                     VALUES (:c, :u, 'override', 'approve', :f, :r, now())""")
    for final, reason in (("reject", "   "), ("maybe", "a real reason")):
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(insert, {"c": case, "u": uid, "f": final, "r": reason})
    with engine.begin() as conn:
        conn.execute(insert, {"c": case, "u": uid, "f": "reject", "r": "a real reason"})
    engine.dispose()


def test_stage_10_migrations_apply_roll_back_and_keep_what_the_old_shape_can_hold(
    clean_db_url: str,
) -> None:  # fmt: skip
    """0014 and 0015 on a database that already holds cases: files keep their person, a case with
    no amount and a case sent by an applicant exist only in the new shape, the files survive
    their applicant row being replaced, and going back to 0013 removes exactly what 0013 cannot
    hold, then forward again."""
    cfg = alembic_config(clean_db_url)
    command.upgrade(cfg, "0013")
    engine = create_engine(clean_db_url)
    with engine.begin() as conn:
        officer = conn.execute(
            text(
                "INSERT INTO users (name, email, password_hash, role) VALUES ('o', 'o@example.test', 'x', 'officer') RETURNING id"
            )
        ).scalar_one()
        case = conn.execute(text("INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months) VALUES ('CASE-2026-0001', 'personal', :u, 1000, 12) RETURNING id"), {"u": officer}).scalar_one()  # fmt: skip
        applicant = conn.execute(text("INSERT INTO applicants (case_id, role, full_name, dob) VALUES (:c, 'co', 'A B', '1990-01-01') RETURNING id"), {"c": case}).scalar_one()  # fmt: skip
        conn.execute(text("INSERT INTO documents (case_id, applicant_id, doc_type, original_name, mime, status) VALUES (:c, :a, 'pan_card', 'p.pdf', 'application/pdf', 'accepted')"), {"c": case, "a": applicant})  # fmt: skip

    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        # the old row was given the person it already had
        assert conn.execute(text("SELECT role FROM documents")).scalar_one() == "co"
        # a desk case has no amount yet; an applicant's case has the new status
        conn.execute(
            text(
                "INSERT INTO cases (case_no, loan_type, created_by) VALUES ('CASE-2026-0002', 'home', :u)"
            ),
            {"u": officer},
        )
        conn.execute(text("INSERT INTO cases (case_no, loan_type, created_by, status, loan_amount, tenure_months) VALUES ('CASE-2026-0003', 'home', :u, 'applicant_submitted', 5, 5)"), {"u": officer})  # fmt: skip
        # a repeat is a row with no file; a value outside the allowed kinds is refused
        conn.execute(text("INSERT INTO documents (case_id, doc_type, original_name, mime, status, duplicate_kind) VALUES (:c, 'pan_card', 'again.pdf', 'application/pdf', 'ignored', 'exact')"), {"c": case})  # fmt: skip
        # replacing the applicant rows no longer deletes the files
        conn.execute(text("DELETE FROM applicants WHERE case_id = :c"), {"c": case})
        assert (
            conn.execute(
                text("SELECT count(*) FROM documents WHERE case_id = :c"), {"c": case}
            ).scalar_one()
            == 2
        )
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("UPDATE documents SET role = 'stranger'"))
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("INSERT INTO upload_links (token_hash, officer_id, created_by, expires_at) VALUES ('h', :u, :u, now()), ('h', :u, :u, now())"), {"u": officer})  # fmt: skip

    command.downgrade(cfg, "0013")
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT case_no FROM cases ORDER BY case_no"))] == [
            "CASE-2026-0001",
            "CASE-2026-0003",
        ]
        assert (
            conn.execute(
                text("SELECT status FROM cases WHERE case_no = 'CASE-2026-0003'")
            ).scalar_one()
            == "draft"
        )
        assert (
            conn.execute(text("SELECT count(*) FROM documents")).scalar_one() == 1
        )  # the repeat row is gone
    command.upgrade(cfg, "head")
    engine.dispose()
