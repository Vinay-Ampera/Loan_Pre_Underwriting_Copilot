"""sign-in sessions: user_sessions

Revision ID: 0013
Revises: 0012

One row per sign-in. The access token (15 minutes) carries the row's id; the refresh token lives
in an HttpOnly cookie and only its SHA-256 hash is stored, so a database leak cannot be replayed.
The row holds the two limits the server enforces (idle since `last_active`, and a hard maximum
since `started_at`) and the previous refresh hash, which is how a stolen, already-rotated
refresh token is recognised. Rows are written and read by the API only.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE user_sessions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at        timestamptz NOT NULL DEFAULT now(),
    last_active       timestamptz NOT NULL DEFAULT now(),
    refresh_hash      text NOT NULL,
    prev_refresh_hash text,
    rotated_at        timestamptz,
    revoked_at        timestamptz,
    revoked_reason    text CHECK (revoked_reason IN ('logout', 'idle', 'max', 'reuse', 'inactive'))
);
CREATE INDEX user_sessions_user_idx ON user_sessions (user_id, started_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON user_sessions TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON user_sessions TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE IF EXISTS user_sessions;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
