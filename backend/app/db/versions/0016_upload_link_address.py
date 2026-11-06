"""upload links: a sealed copy of the token so the owner can copy the address later

Revision ID: 0016
Revises: 0015

Stage 10 review fix. Only the SHA-256 of a token is used to find a link; `token_enc` is the same
token encrypted with a key derived from the server secret, readable only through the
authenticated "address" route (the owning officer and the admin, every look audited). Links made
before this migration have no sealed copy: their address cannot be shown, and "Regenerate" gives
the officer a new one.

`documents.uploaded_via` marks the files that came through an applicant link, so the applicant's
page can show (and let them remove) only their own files, never ones the officer added.
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE upload_links ADD COLUMN token_enc text")
    op.execute("ALTER TABLE documents ADD COLUMN uploaded_via text")


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP COLUMN uploaded_via")
    op.execute("ALTER TABLE upload_links DROP COLUMN token_enc")
