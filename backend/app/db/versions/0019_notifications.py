"""In-app notifications (inbox) for officers and admins

Revision ID: 0019
Revises: 0018

One row is one thing a person should know. It carries a fixed title from a table in code
(`app/notifications/inbox.py`), a short fixed body, the kind, and a pointer to the case (an id for
the link, and the plain case number). It never holds a name, an identifier, a number, a score,
a band or an outcome. `case_id` cascades, so deleting a case removes its notifications.

`upload_links.expiry_notified_for` remembers the expiry time a "link expires within a day" notice
was written for, so each expiry (also a later, extended one) is announced exactly once.
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE notifications (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id),
    kind        text NOT NULL CHECK (kind IN (
                    'applicant_sent', 'applicant_request_received', 'run_ready',
                    'run_stopped_fix', 'decision_corrected', 'case_reassigned',
                    'precedent_added', 'precedent_not_added', 'link_expiring',
                    'message_failed', 'issue_filed', 'precedent_pending', 'precedent_held')),
    title       text NOT NULL CHECK (length(btrim(title)) > 0),
    body        text NOT NULL DEFAULT '',
    case_id     uuid REFERENCES cases(id) ON DELETE CASCADE,
    case_ref    text CHECK (case_ref IS NULL OR case_ref ~ '^CASE-[0-9]{4}-[0-9]{4}$'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    read_at     timestamptz
);
CREATE INDEX notifications_user_idx ON notifications (user_id, read_at, created_at DESC);

ALTER TABLE upload_links ADD COLUMN expiry_notified_for timestamptz;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON notifications TO migrator';
    END IF;
END
$$;
"""

DOWN = """
ALTER TABLE upload_links DROP COLUMN expiry_notified_for;
DROP TABLE notifications;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
