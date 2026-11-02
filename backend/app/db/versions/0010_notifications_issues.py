"""Stage 9: customer contact messages (outbox), issue reports, contact fields

Revision ID: 0010
Revises: 0009

`outbox` holds each customer message exactly as it was checked and sent. `issue_reports` holds an
officer's problem report for the admin; its case reference is plain text (not a link), so the admin
inbox can never reach case data. `users.phone` is the officer's contact number and
`applicants.email` is the customer's optional contact email (synthetic values only).
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE users ADD COLUMN phone text;
ALTER TABLE applicants ADD COLUMN email text;

CREATE TABLE outbox (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    sent_by          uuid NOT NULL REFERENCES users(id),
    recipient_email  text NOT NULL,
    template         text NOT NULL
        CHECK (template IN ('general_contact', 'contact_soon', 'visit_branch', 'blank')),
    subject          text NOT NULL,
    body             text NOT NULL,
    final_text       text,
    case_ref_included boolean NOT NULL DEFAULT false,
    status           text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'blocked', 'sent', 'failed')),
    block_reason     text,
    error            text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    sent_at          timestamptz
);
CREATE INDEX outbox_sender_idx ON outbox (sent_by, created_at DESC);
CREATE INDEX outbox_case_idx ON outbox (case_id);

CREATE TABLE issue_reports (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reported_by  uuid NOT NULL REFERENCES users(id),
    case_ref     text CHECK (case_ref IS NULL OR case_ref ~ '^CASE-[0-9]{4}-[0-9]{4}$'),
    category     text NOT NULL CHECK (category IN ('bug', 'wrong_result', 'access', 'other')),
    body         text NOT NULL,
    status       text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'read', 'closed')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    read_at      timestamptz,
    closed_at    timestamptz
);
CREATE INDEX issue_reports_status_idx ON issue_reports (status, created_at DESC);
CREATE INDEX issue_reports_user_idx ON issue_reports (reported_by, created_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON outbox, issue_reports TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON outbox, issue_reports TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE issue_reports;
DROP TABLE outbox;
ALTER TABLE applicants DROP COLUMN email;
ALTER TABLE users DROP COLUMN phone;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
