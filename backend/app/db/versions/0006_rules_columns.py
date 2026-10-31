"""rules: columns for what the rules file carries beyond the first design

Revision ID: 0006
Revises: 0005

`loan_type` stays a single value ('common' when a rule spans several loan types); the real list
is in `loan_types`. Tier-scored rules store their tiers and use operator 'tiers'.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE rules
    ADD COLUMN loan_types text[] NOT NULL DEFAULT '{}',
    ADD COLUMN subject    text CHECK (subject IN ('each', 'case')),
    ADD COLUMN roles      text[],
    ADD COLUMN when_cond  jsonb,
    ADD COLUMN tiers      jsonb,
    ADD COLUMN fail_class text CHECK (fail_class IN ('fix', 'eligibility')),
    ADD COLUMN on_fail    text CHECK (on_fail IN ('stop', 'cap_refer'));
"""

DOWN = """
ALTER TABLE rules
    DROP COLUMN loan_types, DROP COLUMN subject, DROP COLUMN roles, DROP COLUMN when_cond,
    DROP COLUMN tiers, DROP COLUMN fail_class, DROP COLUMN on_fail;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
