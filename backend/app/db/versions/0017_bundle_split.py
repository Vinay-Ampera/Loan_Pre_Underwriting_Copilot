"""several documents in one PDF: a bundle row, its pieces and their page range

Revision ID: 0017
Revises: 0016

Stage 10, Part D. A multi-page PDF whose pages are different documents is stored as it came, as a
row with status 'bundle' (its proposed split waits in `upload_checks`), and becomes status
'split' once the officer confirms the split. Each piece is an ordinary document row (its own
file) with `parent_document_id` pointing at the original and `page_from`, `page_to` (1-based,
inclusive) saying which pages it was cut from. Deleting the original keeps the pieces.

Downgrade removes the bundle rows and the pieces' links (the pieces stay as ordinary files).
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('accepted', 'rejected', 'ignored', 'bundle', 'split'));

ALTER TABLE documents
    ADD COLUMN parent_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
    ADD COLUMN page_from integer CHECK (page_from >= 1),
    ADD COLUMN page_to   integer CHECK (page_to >= page_from);
CREATE INDEX documents_parent_idx ON documents (parent_document_id) WHERE parent_document_id IS NOT NULL;
"""

DOWN = """
DROP INDEX documents_parent_idx;
ALTER TABLE documents DROP COLUMN page_to, DROP COLUMN page_from, DROP COLUMN parent_document_id;

DELETE FROM documents WHERE status IN ('bundle', 'split');
ALTER TABLE documents DROP CONSTRAINT documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN ('accepted', 'rejected', 'ignored'));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
