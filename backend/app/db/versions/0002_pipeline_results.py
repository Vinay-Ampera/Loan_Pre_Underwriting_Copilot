"""pipeline results: stage_runs, rule_results, reports, eval_scores, llm_calls

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE stage_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    applicant_id  uuid REFERENCES applicants(id),
    stage         text NOT NULL CHECK (stage IN ('extraction', 'kyc', 'policy', 'risk', 'decision')),
    status        text NOT NULL CHECK (status IN ('passed', 'failed', 'stopped', 'unverified')),
    score         numeric(5, 2),
    max_score     numeric(5, 2),
    hard_fail     boolean NOT NULL DEFAULT false,
    fail_class    text CHECK (fail_class IN ('fix', 'eligibility')),
    findings      jsonb NOT NULL DEFAULT '[]'::jsonb,
    model_used    text,
    prompt_version text,
    retries       integer NOT NULL DEFAULT 0,
    fallback_used boolean NOT NULL DEFAULT false,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz
);
CREATE INDEX stage_runs_case_idx ON stage_runs (case_id, stage);

CREATE TABLE rule_results (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stage_run_id   uuid NOT NULL REFERENCES stage_runs(id) ON DELETE CASCADE,
    rule_id        text NOT NULL,
    kind           text NOT NULL CHECK (kind IN ('hard', 'soft')),
    passed         boolean NOT NULL,
    points_awarded numeric(5, 2) NOT NULL DEFAULT 0,
    points_max     numeric(5, 2) NOT NULL DEFAULT 0,
    evidence       jsonb NOT NULL DEFAULT '{}'::jsonb,
    clause_id      text
);
CREATE INDEX rule_results_run_idx ON rule_results (stage_run_id);
CREATE INDEX rule_results_rule_idx ON rule_results (rule_id);

CREATE TABLE reports (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id          uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    version          integer NOT NULL DEFAULT 1,
    summary_md       text,
    rejection_reason text,
    report_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    pdf_path         text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (case_id, version)
);

CREATE TABLE eval_scores (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id      uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    stage_run_id uuid REFERENCES stage_runs(id) ON DELETE CASCADE,
    metric       text NOT NULL,
    value        double precision NOT NULL,
    method       text NOT NULL CHECK (method IN ('code', 'judge')),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE llm_calls (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id           uuid REFERENCES cases(id) ON DELETE SET NULL,
    stage_run_id      uuid REFERENCES stage_runs(id) ON DELETE SET NULL,
    provider          text NOT NULL,
    model             text NOT NULL,
    tokens_in         integer,
    tokens_out        integer,
    cost_usd          numeric(10, 6),
    latency_ms        integer,
    langfuse_trace_id text,
    fallback_used     boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_calls_case_idx ON llm_calls (case_id);
"""

DOWN = """
DROP TABLE IF EXISTS llm_calls, eval_scores, reports, rule_results, stage_runs CASCADE;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
