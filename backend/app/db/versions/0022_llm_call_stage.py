"""llm_calls: which part of the work made each call

Revision ID: 0022
Revises: 0021

Before this, a call was tied to its stage only through `stage_run_id`. The Supervisor has no
stage row (it scores nothing), so its calls had a null link and could not be told apart, and the
judge model's calls and the precedent summary's calls were not written at all. Every call row
now says the `stage` that asked (supervisor, extraction, kyc, policy, risk, decision, precedent)
and the model `role` it used (for example `judge` beside the decision writer). Old rows get the
stage of their stage row where they have one; the rest stay null.
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE llm_calls ADD COLUMN stage text, ADD COLUMN role text;
UPDATE llm_calls l SET stage = s.stage FROM stage_runs s WHERE l.stage_run_id = s.id;
CREATE INDEX llm_calls_stage_idx ON llm_calls (stage);
"""

DOWN = """
DROP INDEX IF EXISTS llm_calls_stage_idx;
ALTER TABLE llm_calls DROP COLUMN IF EXISTS role, DROP COLUMN IF EXISTS stage;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
