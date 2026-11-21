"""email_outbox: wait before trying a failed email again

Revision ID: 0023
Revises: 0022

Notifications Part 3 (hardening). A row whose send failed was tried again on the very next
pass of the email loop, so a mail server that was down for a minute used up all three tries in
that minute. `next_attempt_at` says when the row may be tried again: at once for a new row, one
minute after the first failure, five minutes after the second. The queue index now follows it.
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE email_outbox ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now();
UPDATE email_outbox SET next_attempt_at = created_at;
DROP INDEX IF EXISTS email_outbox_queue_idx;
CREATE INDEX email_outbox_queue_idx ON email_outbox (status, next_attempt_at);
"""

DOWN = """
DROP INDEX IF EXISTS email_outbox_queue_idx;
CREATE INDEX email_outbox_queue_idx ON email_outbox (status, created_at);
ALTER TABLE email_outbox DROP COLUMN IF EXISTS next_attempt_at;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
