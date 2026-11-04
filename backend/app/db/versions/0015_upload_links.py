"""applicant upload links: upload_links, the applicant_submitted case status, the upload_link
message template

Revision ID: 0015
Revises: 0014

Stage 10, Part C. A link belongs to one officer. Only the SHA-256 of its token is stored, so a
database leak cannot be turned into working links; the token itself is shown once, when the link
is created. A link either stands alone (the case is created when the applicant sends the request)
or is bound to an existing case (`case_id`), which is how "ask the applicant" for missing items
works. `disabled_at` ends it at once; `expires_at` ends it on its own.

`cases.status` gains 'applicant_submitted' (the applicant pressed Send to the bank). The outbox
template list gains 'upload_link', and `outbox.link_id` says which link a message carried (never
the token).

Downgrade turns applicant_submitted cases back into drafts and removes upload_link messages.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE upload_links (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash    text NOT NULL UNIQUE,
    officer_id    uuid NOT NULL REFERENCES users(id),
    created_by    uuid NOT NULL REFERENCES users(id),
    loan_type     text CHECK (loan_type IN ('personal', 'home', 'education', 'business', 'vehicle')),
    case_id       uuid REFERENCES cases(id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expires_at    timestamptz NOT NULL,
    disabled_at   timestamptz,
    disabled_by   uuid REFERENCES users(id),
    last_used_at  timestamptz,
    files_count   integer NOT NULL DEFAULT 0,
    bytes_total   bigint NOT NULL DEFAULT 0
);
CREATE INDEX upload_links_officer_idx ON upload_links (officer_id, created_at DESC);
CREATE INDEX upload_links_case_idx ON upload_links (case_id);

ALTER TABLE cases DROP CONSTRAINT cases_status_check;
ALTER TABLE cases ADD CONSTRAINT cases_status_check
    CHECK (status IN ('draft', 'uploaded', 'applicant_submitted', 'running', 'stopped',
                      'awaiting_confirmation', 'confirmed', 'overridden'));

ALTER TABLE outbox DROP CONSTRAINT outbox_template_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_template_check
    CHECK (template IN ('general_contact', 'contact_soon', 'visit_branch', 'blank', 'upload_link'));
ALTER TABLE outbox ADD COLUMN link_id uuid REFERENCES upload_links(id) ON DELETE SET NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON upload_links TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON upload_links TO migrator';
    END IF;
END
$$;
"""

DOWN = """
ALTER TABLE outbox DROP COLUMN link_id;
DELETE FROM outbox WHERE template = 'upload_link';
ALTER TABLE outbox DROP CONSTRAINT outbox_template_check;
ALTER TABLE outbox ADD CONSTRAINT outbox_template_check
    CHECK (template IN ('general_contact', 'contact_soon', 'visit_branch', 'blank'));

UPDATE cases SET status = 'draft' WHERE status = 'applicant_submitted';
ALTER TABLE cases DROP CONSTRAINT cases_status_check;
ALTER TABLE cases ADD CONSTRAINT cases_status_check
    CHECK (status IN ('draft', 'uploaded', 'running', 'stopped', 'awaiting_confirmation',
                      'confirmed', 'overridden'));

DROP TABLE upload_links;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
