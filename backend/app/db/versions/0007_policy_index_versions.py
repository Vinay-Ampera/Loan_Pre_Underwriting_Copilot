"""policy index versions: content checksum and index time on policy documents

Revision ID: 0007
Revises: 0006

The re-index command compares the checksum of each policy file with the stored one, so an edited
clause is picked up even when the version label was not bumped. Chunk-level hashes live in
`policy_chunks.metadata` (`text_hash`).
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE policy_documents
    ADD COLUMN checksum   char(64),
    ADD COLUMN indexed_at timestamptz;
"""

DOWN = """
ALTER TABLE policy_documents DROP COLUMN checksum, DROP COLUMN indexed_at;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
