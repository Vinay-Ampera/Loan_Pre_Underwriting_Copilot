"""login lockout: failed attempt counter and lock time on users

Revision ID: 0008
Revises: 0007

SECURITY.md section 4: lockout after repeated failures. The API counts failures per user and
refuses logins until `locked_until` has passed.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE users
    ADD COLUMN failed_logins integer NOT NULL DEFAULT 0,
    ADD COLUMN locked_until  timestamptz;
"""

DOWN = """
ALTER TABLE users DROP COLUMN failed_logins, DROP COLUMN locked_until;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
