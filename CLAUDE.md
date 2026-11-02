# CLAUDE.md: Loan Pre-Underwriting Copilot

Read this file first. It tells you what the project is, which document to open for which question (all planning documents are in `docs/`), and the rules you must not break.

## What this project is

A copilot for banks and NBFCs. A loan officer uploads an applicant's documents; a LangGraph multi-agent pipeline checks them stage by stage, scores the case **in code**, and writes a report with a recommendation and policy citations. **A human confirms every case.** Overrides become admin-approved "precedents" stored in the knowledge base. No model is trained. Capstone project; **synthetic data only**; solo developer; trainer approves the docs before any implementation.

Loan types: personal, home, education, business, vehicle. One blended policy based on public SBI, HDFC, ICICI criteria and RBI rules. The fictional bank and the product are both named **Pramaan** (display name from Stage 8; policy and rules files keep their `Sample Bank` identifiers).

## Document map

| Question | Open |
|---|---|
| What are we building, for whom, which rules and scores, which data? | `docs/PRD.md` (long, the source of truth) |
| In what order do we build it, and when is a stage done? | `docs/IMPLEMENTATION_PLAN.md` (what each stage builds, exit criteria) |
| Where does the project stand? Build notes, measured results, decisions log | `docs/PROGRESS.md` |
| How do the pieces fit? Diagrams | `docs/ARCHITECTURE.md`, `docs/diagrams/` |
| What does each agent do, with which model, with which checks? | `docs/AGENTS.md` |
| Tables and columns | `docs/DATABASE.md` |
| Masking, injection, roles, secrets, retention | `docs/SECURITY.md` |
| Tests, metrics, CI gate, golden set | `docs/TESTING.md` |
| Code layout, naming, git workflow, review checklist | `docs/CODE_STYLE.md` |
| Screens, components, wording, tokens | `docs/DESIGN_SYSTEM.md` |
| Tricky cases already decided (check before building anything that looks like a repeat) | `docs/EDGE_CASES.md` |

Suggested reading order for a new session: `docs/PRD.md` → `docs/ARCHITECTURE.md` → `docs/AGENTS.md` → `docs/PROGRESS.md` (status) → the stage you are working on in `docs/IMPLEMENTATION_PLAN.md` → the relevant topic doc.

## Locked decisions (do not change without asking the user)

1. **Human confirms every case**, whatever the score. Confirm and override each need a second click; override needs a written reason. Wording is "recommended", never "approved".
2. **Scoring is code.** Stage weights: KYC 20, Documents 15, Income and FOIR 30, Credit and behaviour 25, Policy fit 10. Bands: 85 and above recommend approve, 60 to 84 refer, below 60 recommend reject. Hard rules override bands.
3. **Fixed pipeline order with gates:** Supervisor → Extraction → KYC → (Policy ‖ Risk) → Decision. A hard fail stops the run and produces a short report. A failed check retries once, then is marked `unverified` and passed to the officer.
4. **Hard-fail classes:** fix-type (stop, correct, resume) and eligibility-type (stop, recommend reject).
5. **Age cap 55 at maturity for every applicant and co-applicant** (see open item OI-1 in `docs/PRD.md`). Minimum 21 (education student 18).
6. **Co-applicant:** optional second upload set for home; mandatory for education. Same pipeline per person, combined FOIR.
7. **Rules live in a rules file plus policy documents** linked by rule ID. Learning never edits them.
8. **Learning = precedent store** in RAG. Override → LLM summary by loan type → rule-based hard-rule check in code (a hard-rule breach is held, never enters RAG) → **admin** approves → stored. Three gates: officer, code, admin. Used only for borderline cases, same loan type, above a similarity threshold, never over a hard rule, capped bonus, expiry date.
9. **Security:** synthetic data only; mask PII before any cloud LLM call (text only, never raw PDFs); local OCR first; document text is data, not instructions; roles: admin on top, any number of loan officers under the admin (count is configurable); audit log; secrets in `.env`.
10. **Stack:** React + plain JavaScript + CSS (one `.css` file per component or page; no TypeScript, no Tailwind; changed by the user 2026-11-01); FastAPI; LangGraph with Postgres checkpoints; LiteLLM; Neon Postgres + pgvector; BGE-small (384-d) with a local cross-encoder reranker; PaddleOCR; PyMuPDF + pdfplumber + OpenCV; Langfuse; Prometheus, Loki, Tempo, Grafana; GitHub Actions; Docker Compose at the last stage.
11. **Models:** Gemini Flash (Supervisor, Extraction, Decision), Groq gpt-oss-20b (KYC, Risk), NVIDIA Nemotron (Policy), a free fallback via LiteLLM. Verify exact IDs and limits at Stage 1.
12. **No Celery or Redis in v1.** Local disk for uploads. Policy updates via files plus a re-index command.
13. **Data:** 100 synthetic cases (60 dev, 40 held-out test), answer key per case. Never tune on the test split.
14. **Fairness** attributes are monitoring-only, in a separate table the pipeline cannot read.
15. **Nothing is dropped without the user's permission.** DPO, TRL, Colab and the tuned Qwen model are **removed** (user decision, 2026-10-31): no model training and no local LLM. Only LLM calls go through APIs; embeddings, reranker and OCR still run locally from the pip venv.
16. **UI (Stage 8, decided 2026-11-02):** brand and bank name **Pramaan**; Ampera purple with a darker purple for buttons (AA contrast); fonts Outfit (headings) and Inter (body) bundled via `@fontsource`; light, dark and system themes with a three-way toggle; login is the landing page (no public page, no signup); admin has a Users screen. Only colour feel and fonts are taken from amperadei.com, never its images, copy or policy. The 5-stage underwriting stepper and a display-only Credit / Capacity / Collateral strip are added; scoring and weights do not change.
17. **Customer notifications (Stage 9, decided 2026-11-02, built 2026-11-02):** the officer sends the customer a short, no-reply contact request. It carries **no confidential data and no outcome hint** (no name, score, status, missing items or reason), only an optional case reference, the officer's contact details and a fixed fraud warning (bank staff never ask for an OTP, PIN or password). Templates plus a blank option; a code check blocks forbidden content; the officer sends with a second confirming click. v1 delivery is a terminal log plus a Sent Items screen; no real email or SMS.
18. **Stage order (2026-11-02):** Stage 8 UI, Stage 9 notifications, then a review window for additions, then Stage 10 hardening and Docker (the old Stage 8). Docker is always last.

## Hard constraints for any code you write

- No real PII, ever. No secrets in git.
- No arithmetic on money, age or ratios inside an LLM prompt or agent. Call `scoring/`.
- Every LLM input is masked. Every LLM output is a validated Pydantic schema.
- Every finding has a `rule_id`; policy claims have a `clause_id` that exists in retrieved text.
- Never use gender, religion, caste or similar attributes.
- Write a test with each change; keep CI green including the evaluation gate.
- Update the matching doc in the same PR if behaviour changes.

## Hard rules for Claude (also enforced in `.claude/settings.json`)

- **Never read or write `.env`** (or `.env.local`, `.env.production` etc.). Claude may read and write `.env.example` only; the user fills `.env` by hand.
- **Never run git write commands:** no `add`, `commit`, `push`, `stash`, `reset`, `rebase`, `merge`, branch switching or PR creation. Read-only git (`status`, `diff`, `log`) is fine. At the end of a piece of work, **give a suggested conventional-commit message** and stop; the user commits and pushes.

## How to work

1. Start from the stage in `docs/IMPLEMENTATION_PLAN.md`. Do not start a stage before the previous stage's exit criteria pass.
2. If a requirement is ambiguous or conflicts with a locked decision, **ask the user** instead of guessing.
3. Report progress by stage and exit criterion, not by file count.
4. Prefer small PRs, trunk-based, conventional commits (`docs/CODE_STYLE.md`).
5. When you finish, say what changed, what you verified and what is left.

## Commands (fill in as stages land)

```
setup:     virtualenv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install -e .
backend:   cd backend && uvicorn app.main:app --reload   (serves frontend/dist too if built)
users:     python -m app.api.users_cli create --email E --name N --role officer|admin | password --email E   (or the admin Users screen)
tests:     pytest -q                              (DB tests use a throwaway database)
lint:      ruff check . && ruff format --check . && mypy
frontend:  cd frontend && npm run dev | npm run build | npm test | npm run lint
browser:   cd frontend && npm run e2e          (Playwright + installed Chrome, throwaway database)
db:        python -m app.db.check | python -m app.db.migrate | python -m app.db.seed
llm:       python -m app.services.llm_probe | python -m app.services.llm_smoke [--break-primary]
data:      python -m synthetic.generate --split dev|test|all && python -m synthetic.verify
fixtures:  python -m synthetic.fixtures
reindex:   python -m app.rag.reindex [--force]
rag eval:  python -m app.rag.evaluate --split dev [--write-baseline]
intake:    python -m app.intake.cli FILE [--llm] | python -m app.intake.evaluate --split dev
scoring:   python -m app.scoring.replay --split dev [--case ID] [--verbose]
pipeline:  python -m app.agents.run --split dev [--case ID] [--no-llm] [--force-429] [--cache] | --resume ID | --crash-before STAGE
eval:      python -m app.eval.run --split dev
stack:     docker compose up   (Stage 10)
diagrams:  python3 docs/diagrams/make_diagrams.py
```

## Current status

Stages 1 to 8 are built and committed (Stage 8 as `25e6ad6` and `ff177fa`). Stage 9 (customer notifications and issue reports) is built (2026-11-02), awaiting the user's commit; run `python -m app.db.migrate` (0010) before using it. Stage 10 (hardening, Docker, demo) is planned and approved in the docs but **not started**; the review window comes first, and do not start any stage until the user says so. Full status, build notes and the decisions log are in `docs/PROGRESS.md`.

## Open items

See `docs/PRD.md` section 15 (OI-1 to OI-7). Ask the user before resolving any of them.
