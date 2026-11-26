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
9. **Security:** synthetic data only; mask PII before any cloud LLM call (text only, never raw PDFs); local OCR first; document text is data, not instructions; roles: admin on top, any number of loan officers under the admin (count is configurable), plus exactly one read-only **auditor** (added 2026-11-03, changed 2026-11-03 later the same day: sees counts, charts and static tables only, never a case, report, document or message, changes nothing, created only by the CLI); the **admin** reads every officer's case (documents too) and may **correct** a decision only after the officer has decided it, with a written reason and a second click, as a separate record beside the officer's, never over a hard rule; the admin may also **reassign** a case the officer has not decided to another officer, so an officer always decides first; the system-wide audit log is read by the auditor only (the admin sees each case's own audit tab); the admin and the auditor sign in with **2-step verification** (a code from an authenticator app such as Google or Microsoft Authenticator after the password, set up at the first sign-in, eight recovery codes; an admin resets another person's 2-step, never their own; officers not yet; added by the user 2026-11-24, `docs/SECURITY.md` 4h); secrets in `.env`.
10. **Stack:** React + plain JavaScript + CSS (one `.css` file per component or page; no TypeScript, no Tailwind; changed by the user 2026-11-01); FastAPI; LangGraph with Postgres checkpoints; LiteLLM; Neon Postgres + pgvector; BGE-small (384-d) with a local cross-encoder reranker; PaddleOCR; PyMuPDF + pdfplumber + OpenCV; Langfuse; Prometheus, Loki, Tempo, Grafana; GitHub Actions; Docker Compose at the last stage.
11. **Models:** Gemini Flash (Supervisor, Extraction, Decision), Groq gpt-oss-20b (KYC, Risk), NVIDIA Nemotron (Policy), a free fallback via LiteLLM. Verify exact IDs and limits at Stage 1. Case assistant chat (Stage 12): Gemini Flash, with the Decision fallbacks.
12. **No Celery or Redis in v1.** Local disk for uploads. Policy updates via files plus a re-index command. **Changed by the user 2026-11-21 (Stage 10c, knowledge base):** the database holds every policy version and is the source of truth; the admin changes policies in the browser (draft, format check, retrieval check, reason and second click; scheduled versions; retire, never delete); `data/policy` files are starting data imported by `python -m app.rag.reindex` only when their version label is new. The rules file is still edited by hand only (scoring numbers never change from the browser). Officers read the policy in force (read-only).
13. **Data:** 100 synthetic cases (60 dev, 40 held-out test), answer key per case. Never tune on the test split.
14. **Fairness** attributes are monitoring-only, in a separate table the pipeline cannot read.
15. **Nothing is dropped without the user's permission.** DPO, TRL, Colab and the tuned Qwen model are **removed** (user decision, 2026-10-31): no model training and no local LLM. Only LLM calls go through APIs; embeddings, reranker and OCR still run locally from the pip venv.
16. **UI (Stage 8, decided 2026-11-02):** brand and bank name **Pramaan**; Ampera purple with a darker purple for buttons (AA contrast); fonts Outfit (headings) and Inter (body) bundled via `@fontsource`; light, dark and system themes with a three-way toggle; login is the landing page (no public page, no signup; the only exception is the Stage 10 applicant upload link, decision 19); admin has a Users screen. Only colour feel and fonts are taken from amperadei.com, never its images, copy or policy. The 5-stage underwriting stepper and a display-only Credit / Capacity / Collateral strip are added; scoring and weights do not change.
17. **Customer notifications (Stage 9, decided 2026-11-02, built 2026-11-02):** the officer sends the customer a short, no-reply contact request. It carries **no confidential data and no outcome hint** (no name, score, status, missing items or reason), only an optional case reference, the officer's contact details and a fixed fraud warning (bank staff never ask for an OTP, PIN or password). Templates plus a blank option; a code check blocks forbidden content; the officer sends with a second confirming click. v1 delivery was a terminal log plus a Sent Items screen. **Changed by the user 2026-11-19 (Notifications Part 2):** real email over SMTP (Resend in the demo) when `NOTIFICATION_SENDER=smtp`, only to `EMAIL_ALLOWLIST`, anything else redirected to `EMAIL_REDIRECT_TO` (demo inbox) or held; the content rules above are unchanged; no applicant receipt email; staff get "new notice, sign in" emails (per-person switch) and account created or password reset emails, never a password. No SMS.
18. **Stage order (2026-11-02; updated 2026-11-25):** Stage 8 UI, Stage 9 notifications, then a review window for additions, then Stage 10 (intake desk and applicant upload link, added 2026-11-04), then Stage 11 hardening and Docker (the old Stage 8; built 2026-11-21). Stage 12 (post-demo features, added 2026-11-25) comes after it, adds no service, and must keep the Dockerfile and docker-compose.yml building and starting, with every new setting in `.env.example`.
19. **Intake automation (Stage 10, decided 2026-11-04; Parts A to C built 2026-11-04, Part D built 2026-11-18):** (a) bulk upload (zip, folder, files) with an inventory of received, missing, extra, unrecognised and duplicate files, each file read once and cached; (b) only name, date of birth, PAN, Aadhaar last four and address are filled from the PAN and Aadhaar cards, the officer confirms, and every claim field (amount, tenure, purpose, employment, income, loan-type fields) stays manual, so E-31 is amended and not dropped; (c) a 7-day revocable upload link for one officer, upload-only, no applicant account, no status tracking, which relaxes decision 16 for that one page family only; (d) bundle-PDF split last and switchable; (e) cross-case duplicate check out of v1. Second click on outward or irreversible actions only (list in `docs/IMPLEMENTATION_PLAN.md` Stage 10).

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
users:     python -m app.api.users_cli create --email E --name N --role officer|admin|auditor | password --email E | reset-2-step --email E --reason R   (or the admin Users screen; the auditor is created and reset by the CLI only, one allowed)
tests:     pytest -q                              (DB tests use a throwaway database)
lint:      ruff check . && ruff format --check . && mypy
frontend:  cd frontend && npm run dev | npm run build | npm test | npm run lint
browser:   cd frontend && npm run e2e          (Playwright + installed Chrome, throwaway database)
db:        python -m app.db.check | python -m app.db.migrate | python -m app.db.seed
llm:       python -m app.services.llm_probe | python -m app.services.llm_smoke [--break-primary]
data:      python -m synthetic.generate --split dev|test|all && python -m synthetic.verify
fixtures:  python -m synthetic.fixtures
reindex:   python -m app.rag.reindex [--force]   (imports data/policy files whose label is new; the knowledge base page changes policies)
rag eval:  python -m app.rag.evaluate --split dev [--write-baseline]
chat eval: python -m app.chat.evaluate --split dev [--no-llm] [--write-baseline]   (golden set data/eval/chat_dev.yaml)
intake:    python -m app.intake.cli FILE [--llm] | python -m app.intake.evaluate --split dev
bundles:   python -m app.intake.evaluate_bundles --split dev [--mode digital|all]   (several documents in one PDF)
scoring:   python -m app.scoring.replay --split dev [--case ID] [--verbose]
pipeline:  python -m app.agents.run --split dev [--case ID] [--no-llm] [--force-429] [--cache] | --resume ID | --crash-before STAGE
eval:      python -m app.eval.run --split dev   | python -m app.eval.judge --split dev   (judge model grades stored reports; needs keys)
retention: python -m app.db.retention [--dry-run]   (also runs daily inside the app, RETENTION_HOURS)
release:   python -m app.release --tag vX.Y.Z [--no-db]   (writes docs/releases/<tag>.json, prints the git tag command)
email:     python -m app.notifications.email_check [--to ADDR]   (one real test email, allow-list only)
stack:     docker compose up -d --build   (or make up; profiles local-db and mail; see README.md)
diagrams:  python3 docs/diagrams/make_diagrams.py
```

## Current status

Stages 1 to 10c are built and committed: Stage 8 (`25e6ad6`, `ff177fa`), Stage 9 (`a91f035`), the review-window additions and the reshaped auditor role (`28c5f56`), sessions (`2a850e6`, see `docs/SECURITY.md` 4a), Stage 10 Parts A to C (`d2bcae7`) and Part D (`f3c4a2c`), the admin AI control page, Stage 10b (`f521e32`), in-app notifications Part 1 (`135b5b1`) and Part 2, real email (`7b96d95`), and the knowledge base, Stage 10c (`d484bff`). The post-demo cleanup (2026-11-21: intake wording after "ask for more", the collateral cell of the 3C strip, every LLM call logged with its stage and role in migration 0022, the judge given masked facts, phone and account numbers in the leak check, `docs/AGENTS.md` corrected) is committed (`319af64`). Run `python -m app.db.migrate` (up to 0025). Notifications Part 3 (hardening and close-out: one email per transaction, retry waits, address check, email metrics, a browser test of the inbox; migration 0023) and Stage 11 (hardening, Docker, demo) were built 2026-11-21 and are committed (`61f34df`, `0d8b1e8`). Stage 11 holds: retention job (migration 0024), log guards, audit-coverage test, dashboards row 6, release manifest (`python -m app.release`), judge runner (`python -m app.eval.judge`, replacing RAGAS and DeepEval, user decision), final test-split results with the models off (`docs/baselines/test-final.json`), the demo script (now in the presentation folder, see below), README, `requirements.lock`, `Dockerfile` and `docker-compose.yml`. 2-step verification for the admin and the auditor (migration 0025) was built 2026-11-24 and is committed (`4fecc6a`). Stage 12 (post-demo features, Parts A to E: counter-offer, Insights, export and decision timers, score breakdown chart, "Ask this case" chat) is planned in the docs (`1a8fa15`, 2026-11-25). Part A (counter-offer box; rules file now `2026.11.25-1`, record it with `python -m app.db.seed --only rules`) is committed (`27fbe2f`). Part B (Insights: `/admin/insights`, `/auditor/insights`, the officer's Home tile; migration 0026) is committed (`df1747c`). Parts C (queue export and decision timers; migration 0027, apply with `python -m app.db.migrate`) and D (score breakdown chart, PDF "Points lost" column) were built 2026-11-26 and are committed (`7d68000`). Part E ("Ask this case" chat; migration 0028, `app/chat/`, tab on the case page) was built 2026-11-26 and awaits the user's commit; its real-model golden run is the user's. Left to the user: the real-model test-split run (command in `docs/PROGRESS.md` "Stage 11 build notes"), a real send to Resend, and a demo run. Full status, build notes and the decisions log are in `docs/PROGRESS.md`.

## Demo and presentation files

Demo scripts, slide decks and presentation documents live in **`~/Documents/Loan_Pre_Underwriting_Copilot`**, outside this repo (user decision, 2026-11-23). The top level holds the POC deck and the workflow and architecture PDFs; `CEO_Presentation/` holds the CEO deck, the CEO script and the 25-minute demo walk-through. Never overwrite an existing deck: save a new copy. Read them there and save every new or changed demo or presentation file there, never in `docs/`. Project documentation and code stay in this repo.

## Open items

See `docs/PRD.md` section 15 (OI-1 to OI-7). Ask the user before resolving any of them.
