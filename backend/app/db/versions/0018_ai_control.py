"""AI control: saved model configurations, published prompts and prompt drafts

Revision ID: 0018
Revises: 0017

The admin may change the models, the model settings and the editable part of the six prompts from
the browser (docs/SECURITY.md section 11). Every published change is a new row and rows are never
changed or deleted (a trigger refuses it), so the history is complete and a rollback is just a
newer row that copies an older one. Nothing here holds an API key: keys stay in `.env`.

  ai_config_versions   the whole model configuration (roles, router, switch), one row per version
  ai_prompt_versions   one published prompt body per (name, version); versions continue above the
                       version in the prompt file
  ai_prompt_drafts     at most one unpublished draft per prompt, with the hash of the text that
                       last passed the test (publishing needs that hash to match the draft)

With no rows at all the system behaves exactly as before: the file defaults are used.
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

NAMES = "('supervisor', 'extraction', 'kyc', 'risk', 'policy', 'decision')"

UP = f"""
CREATE TABLE ai_config_versions (
    version        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    config         jsonb NOT NULL,
    reason         text NOT NULL CHECK (length(btrim(reason)) > 0),
    source         text NOT NULL CHECK (source IN ('edit', 'rollback')),
    rolled_back_to integer REFERENCES ai_config_versions(version),
    created_by     uuid REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_prompt_versions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL CHECK (name IN {NAMES}),
    version        integer NOT NULL CHECK (version >= 2),
    body           text NOT NULL CHECK (length(btrim(body)) > 0),
    reason         text NOT NULL CHECK (length(btrim(reason)) > 0),
    source         text NOT NULL CHECK (source IN ('edit', 'rollback')),
    rolled_back_to integer,
    created_by     uuid REFERENCES users(id),
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, version)
);

CREATE TABLE ai_prompt_drafts (
    name        text PRIMARY KEY CHECK (name IN {NAMES}),
    body        text NOT NULL CHECK (length(btrim(body)) > 0),
    tested_hash text,
    tested_ok   boolean NOT NULL DEFAULT false,
    tested_at   timestamptz,
    updated_by  uuid REFERENCES users(id),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION ai_versions_are_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% rows are never changed or deleted; publish a new version', TG_TABLE_NAME;
END
$$;
CREATE TRIGGER ai_config_versions_append_only BEFORE UPDATE OR DELETE ON ai_config_versions
    FOR EACH ROW EXECUTE FUNCTION ai_versions_are_append_only();
CREATE TRIGGER ai_prompt_versions_append_only BEFORE UPDATE OR DELETE ON ai_prompt_versions
    FOR EACH ROW EXECUTE FUNCTION ai_versions_are_append_only();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT ON ai_config_versions, ai_prompt_versions TO app_rw';
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ai_prompt_drafts TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'report_ro') THEN
        EXECUTE 'GRANT SELECT ON ai_config_versions, ai_prompt_versions TO report_ro';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON ai_config_versions, ai_prompt_versions, ai_prompt_drafts TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE IF EXISTS ai_prompt_drafts, ai_prompt_versions, ai_config_versions;
DROP FUNCTION IF EXISTS ai_versions_are_append_only();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
