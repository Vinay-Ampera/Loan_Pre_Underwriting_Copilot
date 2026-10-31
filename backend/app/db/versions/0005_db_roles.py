"""database roles and grants: app_rw, report_ro, migrator

Revision ID: 0005
Revises: 0004

Roles are created NOLOGIN (no password in git). An admin gives them a login and password
by hand, for example `ALTER ROLE app_rw LOGIN PASSWORD '...'` in the Neon console. If the
migrating user may not create roles, the migration logs a notice and skips; grants then
need to be applied by someone who can.
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UP = """
DO $$
BEGIN
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
            CREATE ROLE app_rw NOLOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_ro') THEN
            CREATE ROLE report_ro NOLOGIN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
            CREATE ROLE migrator NOLOGIN;
        END IF;
    EXCEPTION WHEN insufficient_privilege THEN
        RAISE NOTICE 'cannot create roles here; skipping role setup';
        RETURN;
    END;

    -- app_rw: everything except fairness_attributes; audit_log insert-only
    EXECUTE 'GRANT USAGE ON SCHEMA public TO app_rw, report_ro, migrator';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON
        users, cases, applicants, documents, extracted_fields, stage_runs, rule_results,
        reports, eval_scores, llm_calls, officer_actions, precedents, policy_documents,
        policy_chunks, rules, rule_set_versions, mock_identity, mock_bureau, mock_gst,
        mock_udyam, test_cases TO app_rw';
    EXECUTE 'GRANT INSERT ON audit_log TO app_rw';
    EXECUTE 'REVOKE ALL ON fairness_attributes FROM app_rw';

    -- report_ro: read-only monitoring, including the isolated fairness table
    EXECUTE 'GRANT SELECT ON
        cases, applicants, stage_runs, rule_results, reports, eval_scores, llm_calls,
        officer_actions, test_cases, fairness_attributes, audit_log TO report_ro';

    EXECUTE 'GRANT ALL ON ALL TABLES IN SCHEMA public TO migrator';
END
$$;
"""

DOWN = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_rw, report_ro, migrator;
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
