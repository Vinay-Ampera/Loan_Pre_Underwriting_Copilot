# CLAUDE.md: Loan Pre-Underwriting Copilot

Read this file first. It tells you what the project is, which document to open for which question (all planning documents are in `docs/`), and the rules you must not break.

## What this project is

A copilot for banks and NBFCs. A loan officer uploads an applicant's documents; a LangGraph multi-agent pipeline checks them stage by stage, scores the case **in code**, and writes a report with a recommendation and policy citations. **A human confirms every case.** Overrides become reviewer-approved "precedents" stored in the knowledge base. No model is trained. Capstone project; **synthetic data only**; solo developer; trainer approves the docs before any implementation.

Loan types: personal, home, education, business, vehicle. One blended "Sample Bank" policy based on public SBI, HDFC, ICICI criteria and RBI rules.

## Document map

| Question | Open |
|---|---|
| What are we building, for whom, which rules and scores, which data? | `docs/PRD.md` (long, the source of truth) |
| In what order do we build it, and when is a stage done? | `docs/IMPLEMENTATION_PLAN.md` (long) |
| How do the pieces fit? Diagrams | `docs/ARCHITECTURE.md`, `docs/diagrams/` |
| What does each agent do, with which model, with which checks? | `docs/AGENTS.md` |
| Tables and columns | `docs/DATABASE.md` |
| Masking, injection, roles, secrets, retention | `docs/SECURITY.md` |
| Tests, metrics, CI gate, golden set | `docs/TESTING.md` |
| Code layout, naming, git workflow, review checklist | `docs/CODE_STYLE.md` |
| Screens, components, wording, tokens | `docs/DESIGN_SYSTEM.md` |

Suggested reading order for a new session: `docs/PRD.md` → `docs/ARCHITECTURE.md` → `docs/AGENTS.md` → the stage you are working on in `docs/IMPLEMENTATION_PLAN.md` → the relevant topic doc.

## Locked decisions (do not change without asking the user)

1. **Human confirms every case**, whatever the score. Confirm and override each need a second click; override needs a written reason. Wording is "recommended", never "approved".
2. **Scoring is code.** Stage weights: KYC 20, Documents 15, Income and FOIR 30, Credit and behaviour 25, Policy fit 10. Bands: 85 and above recommend approve, 60 to 84 refer, below 60 recommend reject. Hard rules override bands.
3. **Fixed pipeline order with gates:** Supervisor → Extraction → KYC → (Policy ‖ Risk) → Decision. A hard fail stops the run and produces a short report. A failed check retries once, then is marked `unverified` and passed to the officer.
4. **Hard-fail classes:** fix-type (stop, correct, resume) and eligibility-type (stop, recommend reject).
5. **Age cap 55 at maturity for every applicant and co-applicant** (see open item OI-1 in `docs/PRD.md`). Minimum 21 (education student 18).
6. **Co-applicant:** optional second upload set for home; mandatory for education. Same pipeline per person, combined FOIR.
7. **Rules live in a rules file plus policy documents** linked by rule ID. Learning never edits them.
8. **Learning = precedent store** in RAG. Reviewer approves each precedent. Used only for borderline cases, same loan type, above a similarity threshold, never over a hard rule, capped bonus, expiry date.
9. **Security:** synthetic data only; mask PII before any cloud LLM call (text only, never raw PDFs); local OCR first; document text is data, not instructions; roles for officer, reviewer, admin; audit log; secrets in `.env`.
10. **Stack:** React + TypeScript + Tailwind; FastAPI; LangGraph with Postgres checkpoints; LiteLLM; Neon Postgres + pgvector; BGE-small (384-d) with a local cross-encoder reranker; PaddleOCR; PyMuPDF + pdfplumber + OpenCV; Langfuse; Prometheus, Loki, Tempo, Grafana; GitHub Actions; Docker Compose at the last stage.
11. **Models:** Gemini Flash (Supervisor, Extraction, Decision), Groq gpt-oss-20b (KYC, Risk), NVIDIA Nemotron (Policy), a free fallback via LiteLLM. Verify exact IDs and limits at Stage 1.
12. **No Celery or Redis in v1.** Local disk for uploads. Policy updates via files plus a re-index command.
13. **Data:** 100 synthetic cases (60 dev, 40 held-out test), answer key per case. Never tune on the test split.
14. **Fairness** attributes are monitoring-only, in a separate table the pipeline cannot read.
15. **Nothing is dropped without the user's permission.** DPO, TRL, Colab and the tuned Qwen model are *deferred*, not removed.

## Hard constraints for any code you write

- No real PII, ever. No secrets in git.
- No arithmetic on money, age or ratios inside an LLM prompt or agent. Call `scoring/`.
- Every LLM input is masked. Every LLM output is a validated Pydantic schema.
- Every finding has a `rule_id`; policy claims have a `clause_id` that exists in retrieved text.
- Never use gender, religion, caste or similar attributes.
- Write a test with each change; keep CI green including the evaluation gate.
- Update the matching doc in the same PR if behaviour changes.

## How to work

1. Start from the stage in `docs/IMPLEMENTATION_PLAN.md`. Do not start a stage before the previous stage's exit criteria pass.
2. If a requirement is ambiguous or conflicts with a locked decision, **ask the user** instead of guessing.
3. Report progress by stage and exit criterion, not by file count.
4. Prefer small PRs, trunk-based, conventional commits (`docs/CODE_STYLE.md`).
5. When you finish, say what changed, what you verified and what is left.

## Commands (fill in as stages land)

```
backend:   uvicorn app.main:app --reload
tests:     pytest -q
lint:      ruff check . && ruff format --check . && mypy app
frontend:  npm run dev
data:      python -m synthetic.generate --split dev|test
reindex:   python -m app.rag.reindex
eval:      python -m app.eval.run --split dev
stack:     docker compose up   (Stage 8)
diagrams:  python3 docs/diagrams/make_diagrams.py
```

## Current status

Planning complete; documents awaiting trainer approval. No code written. Next: Stage 1 (Foundation and synthetic data).

## Open items

See `docs/PRD.md` section 15 (OI-1 to OI-7). Ask the user before resolving any of them.
