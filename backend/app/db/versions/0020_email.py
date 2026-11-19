"""Real email (Notifications Part 2): staff email queue, notice-email preference, delivery mode

Revision ID: 0020
Revises: 0019

`email_outbox` is the queue for email to staff (a new notice, an account created, a password
reset). A row is written in the transaction of its event and sent after the commit by a loop in
the app (no Celery, no Redis), so an email is never sent for an event that rolled back. Rows keep
how they went: printed (console), sent, redirected (to the demo inbox), held (not on the
allow-list, no redirect) or failed after three tries. Customer messages keep their own `outbox`;
`outbox.delivery` now records how a sent one went out.

`users.notice_emails` is each person's choice to get "you have a new notice" emails.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE users ADD COLUMN notice_emails boolean NOT NULL DEFAULT true;

ALTER TABLE outbox ADD COLUMN delivery text
    CHECK (delivery IS NULL OR delivery IN ('printed', 'sent', 'redirected'));

CREATE TABLE email_outbox (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id),
    kind        text NOT NULL CHECK (kind IN ('notice', 'account_created', 'password_reset')),
    recipient   text NOT NULL,
    subject     text NOT NULL,
    body        text NOT NULL,
    status      text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'printed', 'sent', 'redirected', 'held', 'failed')),
    attempts    integer NOT NULL DEFAULT 0,
    last_error  text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    sent_at     timestamptz
);
CREATE INDEX email_outbox_queue_idx ON email_outbox (status, created_at);
CREATE INDEX email_outbox_user_idx ON email_outbox (user_id, kind, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON email_outbox TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON email_outbox TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE email_outbox;
ALTER TABLE outbox DROP COLUMN delivery;
ALTER TABLE users DROP COLUMN notice_emails;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
