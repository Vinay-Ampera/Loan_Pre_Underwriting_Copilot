"""case_chat_messages: the "Ask this case" turns; the case assistant's prompt name

Revision ID: 0028
Revises: 0027

Stage 12 Part E. One row per question: the **masked** question, the answer with its citations
(null for a fixed answer), the outcome and the report version. The auditor never reads it, so
`report_ro` gets no grant. The AI control prompt tables list the names a prompt may have; they
gain `case_assistant`.
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

OLD = "'supervisor', 'extraction', 'kyc', 'risk', 'policy', 'decision'"
PROMPT_TABLES = ("ai_prompt_versions", "ai_prompt_drafts")

UP = """
CREATE TABLE case_chat_messages (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id        uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    user_id        uuid NOT NULL REFERENCES users(id),
    report_version integer NOT NULL,
    question       text NOT NULL CHECK (char_length(question) BETWEEN 1 AND 2000),
    answer         jsonb,
    outcome        text NOT NULL CHECK (outcome IN
                       ('answered', 'fixed_text', 'refused', 'what_if', 'off', 'limited')),
    retries        integer NOT NULL DEFAULT 0,
    model          text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX case_chat_messages_case_idx ON case_chat_messages (case_id, user_id, created_at);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON case_chat_messages TO app_rw';
        EXECUTE 'GRANT ALL ON case_chat_messages TO migrator';
    END IF;
END
$$;
"""


def _names(names: str) -> None:
    for table in PROMPT_TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_name_check")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_name_check CHECK (name IN ({names}))"
        )


def upgrade() -> None:
    op.execute(UP)
    _names(f"{OLD}, 'case_assistant'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_chat_messages")
    # published prompt versions are append-only: the guard is lifted only to remove this name
    op.execute("ALTER TABLE ai_prompt_versions DISABLE TRIGGER ai_prompt_versions_append_only")
    for table in PROMPT_TABLES:
        op.execute(f"DELETE FROM {table} WHERE name = 'case_assistant'")  # noqa: S608
    op.execute("ALTER TABLE ai_prompt_versions ENABLE TRIGGER ai_prompt_versions_append_only")
    _names(OLD)
