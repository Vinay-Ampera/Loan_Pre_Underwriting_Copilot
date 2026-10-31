"""policy and rules, mock services, evaluation and fairness tables

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UP = """
-- policy and rules ------------------------------------------------------------
CREATE TABLE policy_documents (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_type      text NOT NULL
        CHECK (loan_type IN ('common', 'personal', 'home', 'education', 'business', 'vehicle')),
    title          text NOT NULL,
    version        text NOT NULL,
    source_tag     text NOT NULL CHECK (source_tag IN ('public', 'RBI', 'sample')),
    file_path      text NOT NULL,
    effective_from date NOT NULL,
    active         boolean NOT NULL DEFAULT true,
    UNIQUE (loan_type, version)
);

CREATE TABLE policy_chunks (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_document_id uuid NOT NULL REFERENCES policy_documents(id) ON DELETE CASCADE,
    clause_id          text NOT NULL,
    text               text NOT NULL,
    embedding          vector(384),
    metadata           jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (policy_document_id, clause_id)
);
CREATE INDEX policy_chunks_embedding_idx ON policy_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX policy_chunks_clause_idx ON policy_chunks (clause_id);

CREATE TABLE rules (
    rule_id       text PRIMARY KEY,
    loan_type     text NOT NULL
        CHECK (loan_type IN ('common', 'personal', 'home', 'education', 'business', 'vehicle')),
    stage         text NOT NULL,
    kind          text NOT NULL CHECK (kind IN ('hard', 'soft')),
    field         text NOT NULL,
    operator      text NOT NULL,
    threshold     jsonb,
    points        numeric(5, 2) NOT NULL DEFAULT 0,
    policy_clause text,
    source_tag    text NOT NULL CHECK (source_tag IN ('public', 'RBI', 'sample')),
    version       text NOT NULL,
    active        boolean NOT NULL DEFAULT true
);
CREATE INDEX rules_type_stage_idx ON rules (loan_type, stage);

CREATE TABLE rule_set_versions (
    version   text PRIMARY KEY,
    checksum  char(64) NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    loaded_by uuid REFERENCES users(id)
);

-- mock services (synthetic records only) -------------------------------------
CREATE TABLE mock_identity (
    pan          text PRIMARY KEY,
    name         text NOT NULL,
    dob          date NOT NULL,
    aadhaar_hash char(64) NOT NULL,
    address      text
);

CREATE TABLE mock_bureau (
    pan          text PRIMARY KEY,
    cibil_score  integer NOT NULL CHECK (cibil_score BETWEEN 300 AND 900),
    active_loans jsonb NOT NULL DEFAULT '[]'::jsonb,
    enquiries    jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE mock_gst (
    gstin         text PRIMARY KEY,
    legal_name    text NOT NULL,
    pan           text NOT NULL,
    turnover_12m  numeric(16, 2) NOT NULL,
    filings       jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE mock_udyam (
    udyam_no      text PRIMARY KEY,
    legal_name    text NOT NULL,
    pan           text NOT NULL,
    registered_on date NOT NULL
);

-- evaluation ------------------------------------------------------------------
-- case_id is the synthetic case key (e.g. SYN-PL-D01); case_ref links to a real
-- cases row once the golden runner has created one.
CREATE TABLE test_cases (
    case_id            text PRIMARY KEY,
    split              text NOT NULL CHECK (split IN ('dev', 'test')),
    loan_type          text NOT NULL
        CHECK (loan_type IN ('personal', 'home', 'education', 'business', 'vehicle')),
    scenario           text NOT NULL,
    expected_band      text CHECK (expected_band IN ('approve', 'refer', 'reject')),
    expected_stop_stage text,
    expected_flags     jsonb NOT NULL DEFAULT '[]'::jsonb,
    target_score       numeric(5, 2),
    case_ref           uuid REFERENCES cases(id) ON DELETE SET NULL
);
CREATE INDEX test_cases_split_idx ON test_cases (split, loan_type);

-- monitoring only: no pipeline code and no app_rw access (see 0005)
CREATE TABLE fairness_attributes (
    case_id      text NOT NULL REFERENCES test_cases(case_id) ON DELETE CASCADE,
    applicant_role text NOT NULL CHECK (applicant_role IN ('primary', 'co')),
    gender       text,
    age_band     text,
    city_tier    text,
    PRIMARY KEY (case_id, applicant_role)
);
"""

DOWN = """
DROP TABLE IF EXISTS fairness_attributes, test_cases, mock_udyam, mock_gst, mock_bureau,
    mock_identity, rule_set_versions, rules, policy_chunks, policy_documents CASCADE;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
