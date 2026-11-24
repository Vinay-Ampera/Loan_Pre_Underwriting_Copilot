"""2-step verification: users.mfa_* columns and user_recovery_codes

Revision ID: 0025
Revises: 0024

After the password, an admin or the auditor gives a 6-digit code from an authenticator app
(SECURITY.md 4h). `mfa_secret` is the shared key, sealed with a key derived from JWT_SECRET, so a
database copy alone cannot make codes. `mfa_pending_secret` holds a new key between the QR code and
the first code that confirms it. `mfa_last_step` is the 30-second step of the last code accepted,
so a code works once. Recovery codes are stored as SHA-256 hashes and spent on use. An admin's
reset of someone's 2-step sends that person a fixed "your 2-step verification was reset" email
(a new `email_outbox` kind; no code or key is ever emailed).
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE users
    ADD COLUMN mfa_secret         text,
    ADD COLUMN mfa_pending_secret text,
    ADD COLUMN mfa_enabled_at     timestamptz,
    ADD COLUMN mfa_last_step      bigint;

CREATE TABLE user_recovery_codes (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    used_at    timestamptz
);
CREATE INDEX user_recovery_codes_user_idx ON user_recovery_codes (user_id);

ALTER TABLE email_outbox DROP CONSTRAINT IF EXISTS email_outbox_kind_check;
ALTER TABLE email_outbox ADD CONSTRAINT email_outbox_kind_check
    CHECK (kind IN ('notice', 'account_created', 'password_reset', 'two_step_reset'));

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON user_recovery_codes TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON user_recovery_codes TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DELETE FROM email_outbox WHERE kind = 'two_step_reset';
ALTER TABLE email_outbox DROP CONSTRAINT IF EXISTS email_outbox_kind_check;
ALTER TABLE email_outbox ADD CONSTRAINT email_outbox_kind_check
    CHECK (kind IN ('notice', 'account_created', 'password_reset'));
DROP TABLE IF EXISTS user_recovery_codes;
ALTER TABLE users
    DROP COLUMN IF EXISTS mfa_secret,
    DROP COLUMN IF EXISTS mfa_pending_secret,
    DROP COLUMN IF EXISTS mfa_enabled_at,
    DROP COLUMN IF EXISTS mfa_last_step;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
