"""intake desk: person, classification and duplicate columns on documents; cases may start
before the request is known

Revision ID: 0014
Revises: 0013

Stage 10, Parts A and B. A file is now filed to a person (`role`) before the application form
exists, so `role` lives on the document itself (it was only reachable through `applicants`).
`classification` is what the classifier found; `doc_type` stays what the officer sees (the
officer may change it, `type_source` says who decided). `role_source` is 'auto' or 'officer'.
A repeat of a file already in the case is kept as a row with status 'ignored' and `duplicate_of`
(no file is stored for it); `duplicate_kind` is exact, same_document or conflict.

A case opened at the desk has no amount or tenure until the officer (or the applicant's request)
gives them, so both columns may be empty. Their CHECK (greater than zero) still holds for a value.

The foreign key from documents to applicants is now ON DELETE SET NULL: saving a corrected form
used to delete the applicant rows and, through the cascade, every uploaded file's row.

Downgrade removes the cases that have no amount (they cannot exist in the old shape).
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE documents
    ADD COLUMN role           text CHECK (role IN ('primary', 'co')),
    ADD COLUMN role_source    text NOT NULL DEFAULT 'auto' CHECK (role_source IN ('auto', 'officer')),
    ADD COLUMN classification text,
    ADD COLUMN type_source    text NOT NULL DEFAULT 'detected' CHECK (type_source IN ('detected', 'officer')),
    ADD COLUMN duplicate_of   uuid REFERENCES documents(id) ON DELETE SET NULL,
    ADD COLUMN duplicate_kind text CHECK (duplicate_kind IN ('exact', 'same_document', 'conflict'));

UPDATE documents d SET role = a.role FROM applicants a WHERE a.id = d.applicant_id;

ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('accepted', 'rejected', 'ignored'));

ALTER TABLE cases ALTER COLUMN loan_amount DROP NOT NULL;
ALTER TABLE cases ALTER COLUMN tenure_months DROP NOT NULL;

-- Saving a corrected form replaces the applicant rows. A file now belongs to a person by `role`,
-- so deleting an applicant must not delete the person's files (it used to, through the cascade).
ALTER TABLE documents DROP CONSTRAINT documents_applicant_id_fkey;
ALTER TABLE documents ADD CONSTRAINT documents_applicant_id_fkey
    FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE SET NULL;
"""

DOWN = """
ALTER TABLE documents DROP CONSTRAINT documents_applicant_id_fkey;
ALTER TABLE documents ADD CONSTRAINT documents_applicant_id_fkey
    FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE;

DELETE FROM cases WHERE loan_amount IS NULL OR tenure_months IS NULL;
ALTER TABLE cases ALTER COLUMN loan_amount SET NOT NULL;
ALTER TABLE cases ALTER COLUMN tenure_months SET NOT NULL;

DELETE FROM documents WHERE status = 'ignored';
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN ('accepted', 'rejected'));

ALTER TABLE documents
    DROP COLUMN duplicate_kind, DROP COLUMN duplicate_of, DROP COLUMN type_source,
    DROP COLUMN classification, DROP COLUMN role_source, DROP COLUMN role;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
