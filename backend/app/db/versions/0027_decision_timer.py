"""cases.sla_due_at and the two reminder claims; the two overdue notification kinds

Revision ID: 0027
Revises: 0026

Stage 12 Part C. `sla_due_at` is set each time a report waits for the officer (the report-ready
time plus SLA_WORKING_DAYS of Monday-to-Friday time). `sla_officer_notified_for` and
`sla_admin_notified_for` hold the due time each reminder was sent for, so each goes once per due
time (E-118). Cases already waiting get their due time from the app's first check (E-129), not
here, because the working-day sum lives in code (`app/workflow/sla.py`).
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

KINDS = (
    "'applicant_sent', 'applicant_request_received', 'run_ready', 'run_stopped_fix', "
    "'decision_corrected', 'case_reassigned', 'precedent_added', 'precedent_not_added', "
    "'link_expiring', 'message_failed', 'issue_filed', 'precedent_pending', 'precedent_held'"
)
NEW = "'case_overdue', 'case_overdue_admin'"


def upgrade() -> None:
    op.execute("""
ALTER TABLE cases ADD COLUMN sla_due_at timestamptz;
ALTER TABLE cases ADD COLUMN sla_officer_notified_for timestamptz;
ALTER TABLE cases ADD COLUMN sla_admin_notified_for timestamptz;
CREATE INDEX cases_sla_due_idx ON cases (sla_due_at) WHERE status = 'awaiting_confirmation';
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_kind_check;
""")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check "
        f"CHECK (kind IN ({KINDS}, {NEW}))"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM notifications WHERE kind IN ({NEW})")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_kind_check")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({KINDS}))"
    )
    op.execute("""
DROP INDEX IF EXISTS cases_sla_due_idx;
ALTER TABLE cases DROP COLUMN IF EXISTS sla_admin_notified_for;
ALTER TABLE cases DROP COLUMN IF EXISTS sla_officer_notified_for;
ALTER TABLE cases DROP COLUMN IF EXISTS sla_due_at;
""")
