"""cases.bureau_removed_at: the retention job has removed the case's bureau-derived data

Revision ID: 0024
Revises: 0023

Stage 11 security pass. Bureau-derived data is kept no longer than six months (PRD section 5,
SECURITY.md 7). The retention job (`app/db/retention.py`) removes it and stamps the case, so a
case is cleaned once. A case still waiting for the officer is cleaned but not stamped: its run
checkpoint is needed to resume, and goes on a later run after the decision.
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cases ADD COLUMN bureau_removed_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS bureau_removed_at")
