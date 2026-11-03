"""auditor role: widen the users.role check

Revision ID: 0011
Revises: 0010

SECURITY.md section 4 (D3): one read-only `auditor` account, created only by the CLI. No new
tables. `audit_log` is append-only and references users, so the downgrade cannot delete an
auditor. It turns the account into a disabled officer with an unusable password instead: it can
never sign in, and the audit trail keeps its actor.
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('officer', 'admin', 'auditor'));
-- exactly one active auditor for now (the CLI checks first; this makes it hold under a race)
CREATE UNIQUE INDEX users_one_active_auditor ON users (role) WHERE role = 'auditor' AND active;
"""

DOWN = """
DROP INDEX users_one_active_auditor;
UPDATE users SET role = 'officer', active = false, password_hash = '!' WHERE role = 'auditor';
ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('officer', 'admin'));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
