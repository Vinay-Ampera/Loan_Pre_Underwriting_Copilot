"""Knowledge base: policy versions kept in the database, drafts, scheduled versions, precedent
maintenance

Revision ID: 0021
Revises: 0020

The admin may now change a policy from the browser (Stage 10c, docs/PRD.md decision 12 as
changed 2026-11-21). The database becomes the source of truth for policy text; the files in
data/policy are the starting data that `python -m app.rag.reindex` imports when their version
label is new.

  policy_documents   gains a lifecycle `status` (draft, scheduled, active, superseded, retired),
                     the full Markdown `body` of the version, where it came from (`origin`), who
                     published or retired it and why. `active` becomes a column computed from
                     `status`, so the two can never disagree. At most one draft, one scheduled
                     and one active row per loan type. A published row is never deleted, its
                     text never changes (except a file-imported row edited under the same label,
                     edge case E-20) and a retired row stays retired (a trigger refuses it).
  policy_drafts      the admin's working text, one per loan type, saved even when it does not
                     pass the format check. When it passes, a `draft` policy_documents row holds
                     its embedded clauses (search never reads it) for the retrieval check.
  precedents         two more states: `paused` (a policy change touched one of its rules; the
                     admin confirms it again or retires it) and `retired` (taken out early).
  precedent_uses     one row each time a precedent's bonus reached a case, for the Learnings view.
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

TYPES = "('common', 'personal', 'home', 'education', 'business', 'vehicle')"

UP = f"""
ALTER TABLE policy_documents
    ADD COLUMN status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'scheduled', 'active', 'superseded', 'retired')),
    ADD COLUMN body text,
    ADD COLUMN origin text NOT NULL DEFAULT 'file'
        CHECK (origin IN ('file', 'upload', 'edit', 'restore', 'legacy')),
    ADD COLUMN reason text,
    ADD COLUMN based_on uuid REFERENCES policy_documents(id) ON DELETE SET NULL,
    ADD COLUMN created_by uuid REFERENCES users(id),
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN published_by uuid REFERENCES users(id),
    ADD COLUMN published_at timestamptz,
    ADD COLUMN retired_by uuid REFERENCES users(id),
    ADD COLUMN retired_at timestamptz,
    ADD COLUMN retired_reason text;
ALTER TABLE policy_documents ALTER COLUMN file_path DROP NOT NULL;
UPDATE policy_documents
   SET status = CASE WHEN active THEN 'active' ELSE 'superseded' END,
       published_at = coalesce(indexed_at, now());
ALTER TABLE policy_documents DROP COLUMN active;
ALTER TABLE policy_documents ADD COLUMN active boolean GENERATED ALWAYS AS (status = 'active') STORED;
CREATE UNIQUE INDEX policy_documents_one_active ON policy_documents (loan_type) WHERE status = 'active';
CREATE UNIQUE INDEX policy_documents_one_draft ON policy_documents (loan_type) WHERE status = 'draft';
CREATE UNIQUE INDEX policy_documents_one_scheduled ON policy_documents (loan_type) WHERE status = 'scheduled';

CREATE FUNCTION policy_versions_are_kept() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status <> 'draft' THEN
            RAISE EXCEPTION 'a published policy version is never deleted; retire it instead';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'retired' AND NEW.status <> 'retired' THEN
        RAISE EXCEPTION 'a retired policy version stays retired';
    END IF;
    IF OLD.status <> 'draft' AND OLD.origin <> 'file' AND OLD.body IS NOT NULL
       AND NEW.body IS DISTINCT FROM OLD.body THEN
        RAISE EXCEPTION 'the text of a published policy version never changes; publish a new version';
    END IF;
    RETURN NEW;
END
$$;
CREATE TRIGGER policy_documents_kept BEFORE UPDATE OR DELETE ON policy_documents
    FOR EACH ROW EXECUTE FUNCTION policy_versions_are_kept();

CREATE TABLE policy_drafts (
    loan_type        text PRIMARY KEY CHECK (loan_type IN {TYPES}),
    body             text NOT NULL,
    origin           text NOT NULL DEFAULT 'edit'
        CHECK (origin IN ('upload', 'edit', 'restore', 'legacy')),
    based_on         uuid REFERENCES policy_documents(id) ON DELETE SET NULL,
    document_id      uuid REFERENCES policy_documents(id) ON DELETE SET NULL,
    body_hash        text NOT NULL,
    check_report     jsonb NOT NULL DEFAULT '{{}}'::jsonb,
    retrieval_report jsonb,
    retrieval_hash   text,
    updated_by       uuid REFERENCES users(id),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE precedents DROP CONSTRAINT precedents_status_check;
ALTER TABLE precedents ADD CONSTRAINT precedents_status_check
    CHECK (status IN ('pending', 'held', 'approved', 'rejected', 'expired', 'paused', 'retired'));
ALTER TABLE precedents
    ADD COLUMN paused_at timestamptz,
    ADD COLUMN paused_reason text,
    ADD COLUMN retired_by uuid REFERENCES users(id),
    ADD COLUMN retired_at timestamptz,
    ADD COLUMN retired_reason text;

CREATE TABLE precedent_uses (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    precedent_id uuid NOT NULL REFERENCES precedents(id) ON DELETE CASCADE,
    case_id      uuid REFERENCES cases(id) ON DELETE SET NULL,
    bonus        numeric(5, 2) NOT NULL,
    used_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX precedent_uses_precedent_idx ON precedent_uses (precedent_id, used_at DESC);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON policy_drafts, precedent_uses TO app_rw';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'migrator') THEN
        EXECUTE 'GRANT ALL ON policy_drafts, precedent_uses TO migrator';
    END IF;
END
$$;
"""

DOWN = """
DROP TABLE IF EXISTS precedent_uses, policy_drafts;
ALTER TABLE precedents DROP COLUMN paused_at, DROP COLUMN paused_reason, DROP COLUMN retired_by,
    DROP COLUMN retired_at, DROP COLUMN retired_reason;
UPDATE precedents SET status = 'approved' WHERE status = 'paused';
UPDATE precedents SET status = 'expired' WHERE status = 'retired';
ALTER TABLE precedents DROP CONSTRAINT precedents_status_check;
ALTER TABLE precedents ADD CONSTRAINT precedents_status_check
    CHECK (status IN ('pending', 'held', 'approved', 'rejected', 'expired'));

DROP TRIGGER policy_documents_kept ON policy_documents;
DROP FUNCTION policy_versions_are_kept();
DELETE FROM policy_documents WHERE status = 'draft';
DROP INDEX policy_documents_one_active, policy_documents_one_draft, policy_documents_one_scheduled;
ALTER TABLE policy_documents ADD COLUMN was_active boolean;
UPDATE policy_documents SET was_active = (status = 'active'), file_path = coalesce(file_path, '');
ALTER TABLE policy_documents DROP COLUMN active;
ALTER TABLE policy_documents RENAME COLUMN was_active TO active;
ALTER TABLE policy_documents ALTER COLUMN active SET NOT NULL, ALTER COLUMN active SET DEFAULT true,
    ALTER COLUMN file_path SET NOT NULL;
ALTER TABLE policy_documents DROP COLUMN status, DROP COLUMN body, DROP COLUMN origin,
    DROP COLUMN reason, DROP COLUMN based_on, DROP COLUMN created_by, DROP COLUMN created_at,
    DROP COLUMN published_by, DROP COLUMN published_at, DROP COLUMN retired_by,
    DROP COLUMN retired_at, DROP COLUMN retired_reason;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
