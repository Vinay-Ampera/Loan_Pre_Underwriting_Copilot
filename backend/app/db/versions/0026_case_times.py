"""cases.submitted_at and cases.report_ready_at: the two times Insights needs

Revision ID: 0026
Revises: 0025

Stage 12 Part B. `submitted_at` is the first "Submit for assessment" (the funnel's "documents
complete"); a resume after a fix or a retry after a failed run never moves it. `report_ready_at`
is when the latest report that waits for the officer was written (a fix-type stop does not set it;
E-114). Both are backfilled: `submitted_at` from the first `case_submitted` audit row, or, for a
case with a report but no such row (cases run from the command line), from its first report;
`report_ready_at` from the newest stored report whose status is `awaiting_confirmation`.
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cases ADD COLUMN submitted_at timestamptz")
    op.execute("ALTER TABLE cases ADD COLUMN report_ready_at timestamptz")
    op.execute(
        """UPDATE cases c SET submitted_at = coalesce(
               (SELECT min(a.at) FROM audit_log a
                 WHERE a.action = 'case_submitted' AND a.entity_id = c.id::text),
               (SELECT min(r.created_at) FROM reports r WHERE r.case_id = c.id))"""
    )
    op.execute(
        """UPDATE cases c SET report_ready_at = (
               SELECT max(r.created_at) FROM reports r
                WHERE r.case_id = c.id AND r.report_json->>'status' = 'awaiting_confirmation')"""
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS report_ready_at")
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS submitted_at")
