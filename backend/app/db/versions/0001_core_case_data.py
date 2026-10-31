"""core case data: users, cases, applicants, documents, extracted_fields

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UP = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role          text NOT NULL CHECK (role IN ('officer', 'admin')),
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE cases (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_no           text NOT NULL UNIQUE CHECK (case_no ~ '^CASE-[0-9]{4}-[0-9]{4}$'),
    loan_type         text NOT NULL
        CHECK (loan_type IN ('personal', 'home', 'education', 'business', 'vehicle')),
    status            text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'uploaded', 'running', 'stopped',
                          'awaiting_confirmation', 'confirmed', 'overridden')),
    created_by        uuid NOT NULL REFERENCES users(id),
    loan_amount       numeric(14, 2) NOT NULL CHECK (loan_amount > 0),
    tenure_months     integer NOT NULL CHECK (tenure_months > 0),
    purpose           text,
    form_data         jsonb NOT NULL DEFAULT '{}'::jsonb,
    stopped_stage     text,
    stop_class        text CHECK (stop_class IN ('fix', 'eligibility')),
    total_score       numeric(5, 2) CHECK (total_score BETWEEN 0 AND 100),
    band              text CHECK (band IN ('approve', 'refer', 'reject')),
    recommendation    text,
    policy_version    text,
    rules_version     text,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX cases_status_idx ON cases (status);
CREATE INDEX cases_created_by_idx ON cases (created_by);

CREATE TABLE applicants (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id                uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    role                   text NOT NULL CHECK (role IN ('primary', 'co')),
    full_name              text NOT NULL,
    dob                    date NOT NULL,
    pan                    text,
    aadhaar_last4          char(4),
    address                text,
    phone                  text,
    employment_type        text CHECK (employment_type IN ('salaried', 'self_employed')),
    employer_or_business   text,
    declared_monthly_income numeric(14, 2),
    relationship_to_primary text,
    created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX applicants_case_idx ON applicants (case_id);

CREATE TABLE documents (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id       uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    applicant_id  uuid REFERENCES applicants(id) ON DELETE CASCADE,
    doc_type      text NOT NULL,
    file_path     text,
    original_name text NOT NULL,
    mime          text NOT NULL,
    page_count    integer,
    source_kind   text CHECK (source_kind IN ('digital_pdf', 'scanned_pdf', 'photo')),
    sha256        char(64),
    upload_checks jsonb NOT NULL DEFAULT '{}'::jsonb,
    status        text NOT NULL CHECK (status IN ('accepted', 'rejected')),
    reject_reason text,
    uploaded_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_case_idx ON documents (case_id);

CREATE TABLE extracted_fields (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name   text NOT NULL,
    value_masked text,
    value_local  bytea,
    confidence   real CHECK (confidence BETWEEN 0 AND 1),
    source_page  integer,
    needs_review boolean NOT NULL DEFAULT false
);
CREATE INDEX extracted_fields_doc_idx ON extracted_fields (document_id);
"""

DOWN = """
DROP TABLE IF EXISTS extracted_fields, documents, applicants, cases, users CASCADE;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
