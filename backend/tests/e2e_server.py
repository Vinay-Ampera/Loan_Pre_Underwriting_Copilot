"""The API on a throwaway database for the browser tests (frontend/e2e). Not a test itself.

    cd backend && ../.venv/bin/python -m tests.e2e_server [port]

Creates a database next to the one in DATABASE_URL, migrates it, indexes the policy with the
test embedder, adds an officer, an admin, the read-only auditor and one pending precedent, then serves the API and the built
frontend (frontend/dist) on 127.0.0.1. Models are off, so the report text is written by code.
The database is dropped when the process ends. Passwords below are for this throwaway database.

2-step verification is on for admins and the auditor, as in the app. The admin and the auditor
already have it set up with the fixed keys below, so `frontend/e2e/helpers.js` can type their codes;
"E2E Second Admin" has not, so the browser test of the setup screen starts from scratch.
"""

import signal
import sys
import tempfile
import uuid
from pathlib import Path

import uvicorn
from alembic import command
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.api import mfa
from app.api.main import create_app
from app.api.security import hash_password
from app.core.config import Settings, get_settings
from app.db.migrate import alembic_config
from app.rag.index import reindex
from app.rag.retrieve import PolicyRetriever
from tests.rag_helpers import fake_embed_passages, fake_rerank, fake_vector

PASSWORD = "e2e-password-123"  # noqa: S105 - throwaway database only
# the same keys are in frontend/e2e/helpers.js (TWO_STEP_KEYS); throwaway database only
TWO_STEP_KEYS = {
    "admin@example.test": "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP",
    "auditor@example.test": "KRSXG5CTMVZGK5DTKRSXG5CTMVZGK5DT",
}


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    base = make_url(get_settings().sqlalchemy_url())
    name = f"lc_e2e_{uuid.uuid4().hex[:8]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    engine = None
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        jwt_secret=SecretStr("e2e-" + uuid.uuid4().hex),
        upload_dir=Path(tempfile.mkdtemp(prefix="lc_e2e_uploads_")),
    )
    try:
        command.upgrade(alembic_config(url), "head")
        engine = create_engine(url)
        with engine.begin() as conn:
            reindex(conn, embed=fake_embed_passages)
            for who, role in (("officer", "officer"), ("admin", "admin"), ("auditor", "auditor"),
                              ("second admin", "admin")):  # fmt: skip
                conn.execute(
                    text(
                        "INSERT INTO users (name, email, password_hash, role) VALUES (:n, :e, :h, :r)"
                    ),
                    {
                        "n": f"E2E {who.title()}",
                        "e": f"{who.split()[0]}@example.test",
                        "h": hash_password(PASSWORD),
                        "r": role,
                    },
                )
            for email, key in TWO_STEP_KEYS.items():
                conn.execute(
                    text("""UPDATE users SET mfa_secret = :k, mfa_enabled_at = now()
                            WHERE email = :e"""),
                    {"k": mfa.seal(settings, key), "e": email},
                )
            officer = conn.execute(text("SELECT id FROM users WHERE role = 'officer'")).scalar_one()
            case = conn.execute(
                text("""INSERT INTO cases (case_no, loan_type, created_by, loan_amount, tenure_months, status)
                        VALUES ('CASE-2026-9001', 'personal', :u, 200000, 36, 'overridden') RETURNING id"""),
                {"u": officer},
            ).scalar_one()
            conn.execute(
                text("""INSERT INTO precedents (source_case_id, loan_type, rule_ids, original_score,
                            original_recommendation, final_decision, officer_reason, report_summary, proposed_by)
                        VALUES (:c, 'personal', '{PL-FOIR-01}', 72, 'refer', 'approve',
                                'Stable employer for ten years and a clean repayment history.',
                                'Personal loan, refer band. Borderline FOIR.', :u)"""),
                {"c": case, "u": officer},
            )
        app = create_app(
            settings,
            engine=engine,
            saver=InMemorySaver(),
            use_llm=False,
            embed=fake_embed_passages,
            ctx_kwargs={
                "retriever_factory": lambda c: PolicyRetriever(
                    c, embed=fake_vector, rerank_fn=fake_rerank
                )
            },
        )
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        signal.signal(signal.SIGTERM, lambda *_: setattr(server, "should_exit", True))
        server.run()
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
