"""human actions and learning: officer_actions, precedents, audit_log

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE officer_actions (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id                 uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    officer_id              uuid NOT NULL REFERENCES users(id),
    action                  text NOT NULL CHECK (action IN ('confirm', 'override')),
    original_recommendation text NOT NULL,
    final_decision          text NOT NULL,
    reason                  text,
    second_click_at         timestamptz NOT NULL,
    created_at              timestamptz NOT NULL DEFAULT now(),
    -- an override must carry a written reason
    CONSTRAINT override_needs_reason
        CHECK (action = 'confirm' OR length(btrim(coalesce(reason, ''))) > 0)
);
CREATE INDEX officer_actions_case_idx ON officer_actions (case_id);

-- status 'held' = failed the code-side hard-rule check; it never reaches the admin or RAG.
CREATE TABLE precedents (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_case_id          uuid NOT NULL REFERENCES cases(id),
    status                  text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'held', 'approved', 'rejected', 'expired')),
    loan_type               text NOT NULL
        CHECK (loan_type IN ('personal', 'home', 'education', 'business', 'vehicle')),
    rule_ids                text[] NOT NULL DEFAULT '{}',
    original_score          numeric(5, 2),
    original_recommendation text NOT NULL,
    final_decision          text NOT NULL,
    officer_reason          text NOT NULL,
    report_summary          text NOT NULL,
    embedding               vector(384),
    proposed_by             uuid NOT NULL REFERENCES users(id),
    reviewed_by             uuid REFERENCES users(id),
    reviewed_at             timestamptz,
    valid_until             date,
    times_used              integer NOT NULL DEFAULT 0,
    created_at              timestamptz NOT NULL DEFAULT now(),
    -- only an admin-reviewed precedent can be approved, and it must expire
    CONSTRAINT approved_is_reviewed
        CHECK (status <> 'approved'
               OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL
                   AND valid_until IS NOT NULL AND embedding IS NOT NULL))
);
CREATE INDEX precedents_embedding_idx ON precedents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX precedents_type_status_idx ON precedents (loan_type, status);

CREATE TABLE audit_log (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id  uuid REFERENCES users(id),
    action    text NOT NULL,
    entity    text NOT NULL,
    entity_id text,
    before    jsonb,
    after     jsonb,
    at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_entity_idx ON audit_log (entity, entity_id);
CREATE INDEX audit_log_at_idx ON audit_log (at);

-- append-only, enforced even for roles that hold UPDATE/DELETE by mistake
CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_change
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
"""

DOWN = """
DROP TABLE IF EXISTS audit_log, precedents, officer_actions CASCADE;
DROP FUNCTION IF EXISTS audit_log_immutable();
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
