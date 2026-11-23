# Pramaan: Loan Pre-Underwriting Copilot

A copilot for banks and NBFCs. A loan officer uploads an applicant's documents. A LangGraph multi-agent pipeline checks them stage by stage (KYC, documents, income and FOIR, credit, policy fit), scores the case **in code**, and writes a report with a recommendation and policy citations. **A human confirms every case**: the system only recommends.

Capstone project. **Synthetic data only**: no real personal data anywhere.

## Run with Docker

You need Docker with Compose, and a Postgres database with pgvector (a free [Neon](https://neon.tech) project, or the local one below).

```
cp .env.example .env        # fill in DATABASE_URL, JWT_SECRET and the model keys
docker compose up -d --build
```

- App: http://localhost:8000
- Grafana: http://localhost:3000 (`admin` and `GRAFANA_ADMIN_PASSWORD`, default `admin`)
- Prometheus: http://localhost:9090

On start the app container migrates the database, loads the rules, mock records and policy documents, then serves the API and the frontend. Then create the first accounts (each command asks for the password):

```
docker compose exec app python -m app.api.users_cli create --email admin@pramaan.test --name "Admin" --role admin
docker compose exec app python -m app.api.users_cli create --email officer@pramaan.test --name "Officer" --role officer
docker compose exec app python -m app.api.users_cli create --email auditor@pramaan.test --name "Auditor" --role auditor
```

Options:
- **Offline database:** `docker compose --profile local-db up -d`, with `DATABASE_URL=postgresql://postgres:postgres@db:5432/pramaan` in `.env`.
- **Catch every email in a page:** `docker compose --profile mail up -d` starts Mailpit on http://localhost:8025. Set `NOTIFICATION_SENDER=smtp`, `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_SECURITY=none` and an empty `SMTP_USERNAME`.
- **No model keys:** set `LLM_ENABLED=false`. Every text is then written by code; the scores do not change.

## Run without Docker

```
make setup                  # .venv with the Python packages, npm packages for the frontend
cp .env.example .env        # fill it in
make migrate && .venv/bin/python -m app.db.seed && .venv/bin/python -m app.rag.reindex
cd frontend && npm run build && cd ..
make backend                # http://localhost:8000 (serves frontend/dist); or `make frontend` for the dev server
make grafana                # optional: the observability stack for an app running on this machine
```

Python 3.12 and Node 22. The synthetic cases are made with `python -m synthetic.generate --split all`.

## Try it

The demo walk-through (25 minutes, with the cases to use and what each screen should show) and the presentation material are kept outside this repository, with the author's presentation files.

## Tests and evaluation

```
make test                   # backend tests (a throwaway database next to DATABASE_URL)
make test-fe                # frontend tests
cd frontend && npm run e2e  # browser tests in Chrome
make lint
python -m app.eval.run --split dev      # agreement with the answer keys (the CI gate)
python -m app.eval.judge --split dev    # the judge model grades stored reports (needs the keys)
```

## How it is built

React with JavaScript and CSS, FastAPI, LangGraph with Postgres checkpoints, LiteLLM (Gemini, Groq, NVIDIA and a free fallback), Postgres with pgvector, local BGE-small embeddings with a cross-encoder reranker, local OCR, Langfuse, Prometheus, Loki, Tempo and Grafana, GitHub Actions and Docker Compose.

Safety rules that hold everywhere:
- Every model input is masked first (no raw PAN, Aadhaar, phone or account number), and document text is treated as data, never as instructions.
- Scores, FOIR and ages are worked out in code, and hard rules always win.
- Roles are admin, officer and one read-only auditor.
- Secrets live only in `.env`.

## Documents

Start with [CLAUDE.md](CLAUDE.md), then [docs/](docs/):

- [PRD](docs/PRD.md): what is built and why (the source of truth)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) and [progress](docs/PROGRESS.md)
- [Architecture](docs/ARCHITECTURE.md), [agents](docs/AGENTS.md), [database](docs/DATABASE.md)
- [Security](docs/SECURITY.md), [testing](docs/TESTING.md), [edge cases](docs/EDGE_CASES.md)
- [Design system](docs/DESIGN_SYSTEM.md), [code style](docs/CODE_STYLE.md)
