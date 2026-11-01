"""a precedent outlives the case it came from

Revision ID: 0009
Revises: 0008

Re-creating a synthetic case (evaluation runs do this) deletes the old `cases` row. A precedent is
reviewed knowledge with its own summary, so the link to its source case becomes optional and is
cleared instead of blocking the delete.
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE precedents ALTER COLUMN source_case_id DROP NOT NULL;
ALTER TABLE precedents DROP CONSTRAINT precedents_source_case_id_fkey;
ALTER TABLE precedents ADD CONSTRAINT precedents_source_case_id_fkey
    FOREIGN KEY (source_case_id) REFERENCES cases(id) ON DELETE SET NULL;
"""

DOWN = """
DELETE FROM precedents WHERE source_case_id IS NULL;
ALTER TABLE precedents DROP CONSTRAINT precedents_source_case_id_fkey;
ALTER TABLE precedents ADD CONSTRAINT precedents_source_case_id_fkey
    FOREIGN KEY (source_case_id) REFERENCES cases(id);
ALTER TABLE precedents ALTER COLUMN source_case_id SET NOT NULL;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
