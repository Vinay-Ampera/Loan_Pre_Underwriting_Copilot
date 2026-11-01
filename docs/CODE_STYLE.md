# CODE_STYLE

## 1. Repository layout (monorepo, trunk-based)

```
loan-copilot/
  CLAUDE.md              index and locked decisions (stays at the repo root)
  README.md              short project overview
  docs/                  PRD.md ... TESTING.md, and the planning documents
    diagrams/            architecture + data flow images and make_diagrams.py
  backend/
    app/
      api/               FastAPI routers, schemas
      agents/            one module per agent + graph.py
      intake/            upload checks, parsers, OCR, masker, validators
      scoring/           rules loader, evaluators, stage scorers
      rag/               chunking, embeddings, retrieval, rerank, grounding
      services/          mock identity, bureau, GST, Udyam; LiteLLM wrapper
      db/                models, migrations (Alembic), seeds
      core/              config, logging, security, audit
    tests/
    prompts/             one markdown file per agent, versioned
  frontend/
    src/
      pages/ components/ api/ hooks/ styles/   (each .jsx has its .css beside it)
    e2e/                 Playwright browser tests
  data/
    policy/              sample policy documents
    rules/               rules files
    synthetic/           generator + generated cases (gitignored if large)
  ops/                   docker-compose, grafana, prometheus, loki, tempo
  .github/workflows/
```

## 2. Python

- Python 3.12. Type hints everywhere; `mypy --strict` on `app/`.
- Format and lint with `ruff` (lint + format). Line length 100.
- Pydantic v2 models for every agent input and output and every API schema.
- No business logic in routers; routers call services.
- **Scoring logic only in `scoring/`.** No arithmetic on money, age or ratios in agents or prompts.
- Pure functions for validators and evaluators; side effects only at the edges.
- No bare `except`; log with context; raise typed errors.
- Config only via `core/config.py` reading `.env`; no `os.environ` scattered in code.
- Never log raw document text or identifiers; use the masker's `safe()` helper.
- Async for I/O (FastAPI, DB, LLM calls); CPU-bound parsing runs in a worker pool.

## 3. JavaScript and React

- Plain JavaScript (ES modules), React function components. No TypeScript, no Tailwind.
- Styling is plain CSS: one `.css` file next to each component or page (`Foo.jsx` + `Foo.css`); shared tokens, reset and base styles in `frontend/src/styles/`. Colours, spacing and type come from the tokens in `DESIGN_SYSTEM.md` (CSS variables), never hard-coded.
- Animation is CSS first (transitions, keyframes, `prefers-reduced-motion` respected). Three.js only if lazy-loaded and it does not slow page load.
- ESLint + Prettier. One thin `api/client.js` wraps `fetch` (adds the JWT, turns errors into one error shape); response shapes are documented with JSDoc where they are not obvious.
- Local state in components and small hooks (`hooks/`); no business rules in the UI (it displays what the backend decides).

## 4. Naming

- Python: `snake_case` functions and files, `PascalCase` classes. Rule IDs like `PL-CIBIL-01` (loan prefix, topic, number); clause IDs like `PL-ELIG-03`.
- Database: plural `snake_case` tables, singular column names, `_id` for foreign keys.
- API: REST, plural nouns, `/api/v1/...`.
- Branches: `feat/...`, `fix/...`, `docs/...`, `chore/...`.

## 5. Git workflow

- Trunk-based: short-lived branches, small PRs into `main`.
- Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Every PR: tests, updated docs if behaviour changed, CI green including the evaluation gate.
- Release tags carry model IDs, prompt versions, policy version and rules version in the tag message.
- Never commit `.env`, data with real PII (there is none), or large generated files.

## 6. Prompts and rules files

- Prompts in `backend/prompts/<agent>.md` with a version header; changing one bumps the version.
- Rules and policy files carry `version` and `source` tags. A change needs a rerun of the golden set.

## 7. Documentation rules

- Keep each doc focused and short; `PRD.md` and `IMPLEMENTATION_PLAN.md` are the only long ones.
- If code and docs disagree, fix whichever is wrong in the same PR.
- Decisions that change locked behaviour go into `PRD.md` section 15 first.

## 8. Review checklist

- [ ] No arithmetic or rule logic in an LLM path
- [ ] Inputs to LLMs are masked
- [ ] New rule has an ID, clause link, source tag and a test
- [ ] Output schema validated; failure path tested
- [ ] No secrets or PII in code, logs or fixtures
- [ ] Docs updated
