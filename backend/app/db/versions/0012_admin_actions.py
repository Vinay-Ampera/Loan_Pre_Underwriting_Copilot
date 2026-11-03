"""admin corrections: admin_actions

Revision ID: 0012
Revises: 0011

An admin may correct an officer's decision once the officer has decided. The correction is its
own row next to the officer's (`officer_actions` is never touched), with the decision it replaced,
the new decision, a written reason and the time of the second click. The latest row is the
decision in force. Reassigning a waiting case to another officer changes `cases.created_by` and is
recorded in `audit_log` only.
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE admin_actions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id           uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    admin_id          uuid NOT NULL REFERENCES users(id),
    action            text NOT NULL CHECK (action IN ('override')),
    previous_decision text NOT NULL CHECK (previous_decision IN ('approve', 'refer', 'reject')),
    final_decision    text NOT NULL CHECK (final_decision IN ('approve', 'refer', 'reject')),
    reason            text NOT NULL CHECK (length(btrim(reason)) > 0),
    second_click_at   timestamptz NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX admin_actions_case_idx ON admin_actions (case_id, created_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON admin_actions TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_ro') THEN
        EXECUTE 'GRANT SELECT ON admin_actions TO report_ro';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON admin_actions TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE IF EXISTS admin_actions;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
