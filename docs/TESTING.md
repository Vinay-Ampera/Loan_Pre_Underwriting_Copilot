# TESTING

## 1. Layers

| Layer | What | Tools | When |
|---|---|---|---|
| Unit | ID validators, masker, FOIR, DTI, LTV, age at maturity, rule operators, scorers, hard-fail logic | pytest | Every commit |
| Parser | Field extraction accuracy on dev documents, upload checks, OCR, bank statement styles | pytest + fixtures | Every commit (small set), nightly (full) |
| Agent | Each agent against recorded model responses; schema, citations, gates, retries | pytest, recorded fixtures | Every commit |
| Integration | Full pipeline on a few cases per loan type, pause and resume, fallback on 429 | pytest | Every PR |
| Golden set | 60 dev and 40 test cases against the answer key | custom runner, RAGAS, DeepEval | PR gate (dev), release (test) |
| UI end to end | One case per loan type through the browser | Playwright | Pre-release |
| Security | PII leak scan, injection set, role checks | pytest | Every PR |
| Fairness | Approval-rate parity report | script | Per evaluation run |

## 2. Test data

- 100 synthetic cases: 60 dev, 40 test (`PRD.md` section 11).
- Small unit-test fixtures are separate and tiny (`backend/tests/fixtures/`, rebuilt by `python -m synthetic.fixtures`).
- Generate the 100 cases with `python -m synthetic.generate` (deterministic for a seed; output is gitignored) and check the Stage 1 exit criteria with `python -m synthetic.verify`.
- Answer-key scores come from the rules file through a reference evaluator (`app/scoring/evaluate.py`), not from guesses. Soft facts that depend on document measurement (blur, OCR confidence) are design targets, calibrated in Stage 2.
- The **test split is held out**. It is run only at release and for the final report. Never tune on it.
- Each case has an answer key: expected band, expected stop stage, expected flags, target score.
- Score spread covers roughly 30, 40, 55, 67, 85, 98 and 100.
- Special files: password-protected PDFs, blurry and cropped photos, tampered documents, poisoned documents for injection tests.

## 2b. Parser baseline (Stage 2, dev split, `python -m app.intake.evaluate --split dev`)

| Measure | Result | Target going forward |
|---|---|---|
| Field accuracy, digital PDFs | 100% | 99% or more |
| Field accuracy, good and mild photos | 99% | 97% or more |
| Field accuracy, scanned statements | 100% | 97% or more |
| Field accuracy, poor photos | 30% | no target; low-confidence fields are flagged, never guessed |
| Classifier accuracy | 98.7% | 98% or more |
| Raw PAN/Aadhaar/GSTIN/email in masked text | 0 | 0 (fixed) |
| Password-protected files rejected | 3 of 3 | 100% (fixed) |
| Tampered cases with at least one hint | 5 of 5 | 100% |

The held-out test split is run once, for the final report (`--allow-test`).

## 2c. Scoring replay (Stage 3, dev split, `python -m app.scoring.replay --split dev`)

The engine is fed structured inputs only (application form, the field values each document carries, the mock identity, bureau and GST records). No document is opened and no LLM is called. Four values are measured by intake on real documents and cannot be read from fields, so the answer key supplies them: document quality, field confidence, totals tie-out, and income regularity. Everything else, including FOIR, LTV, ages, matching and statement counts, is derived by the engine independently of the generator.

| Measure | Result | Agreed minimum |
|---|---|---|
| Band reproduced | 60 of 60 | 95% |
| Stop stage and class reproduced | 60 of 60 | 100% |
| Total score, stage scores and failed rule IDs reproduced | 59 of 60 | 90% |

The one miss is SYN-BL-D13 (see EDGE_CASES E-17). Unit tests cover every operator, every hard rule (generated from the rules file, so a new hard rule is tested automatically), every soft-rule tier, and the "change a threshold in the file, behaviour changes" check.

## 2d. Pipeline run (Stage 5, `python -m app.agents.run --split dev --no-llm --cache`)

The whole graph on the real files of the 60 dev cases (intake, rules engine, agents, report), models off. The answer key is used only to compare; the pipeline never reads it.

| Measure | Result | Target |
|---|---|---|
| Case finishes (paused for the officer, or stopped for a correction) | 60 of 60 | 100% |
| Stop stage and class as expected | 60 of 60 | 100% |
| Band as the key says | 58 of 60 (96.7%) | reported, no target yet (OI-7) |
| Mean score error on scored cases | 1.6 points over 32 cases | reported |
| Kill the process mid-run, resume from the checkpoint | same result (tested for kyc, risk and decision, and with a real `exit 137`) | same result |
| Forced 429 on every primary model | case completes through the fallbacks (real LiteLLM Router, mocked providers) | completes |
| Poisoned documents and an obedient model | no score, band or recommendation changes | unchanged |

"Expected" means the answer key, except for the 9 dev cases whose PAN or Aadhaar photograph is in the generator's `poor` tier (SYN-PL-D06, PL-D08, HL-D07, VL-D03, VL-D05, BL-D03, BL-D05, BL-D06, ED-D04). The local OCR cannot read them (Stage 2: about 30% of fields; upscaling, sharpening, contrast and deblurring did not help), so the right outcome is a fix-type stop at KYC asking for a clearer copy, and the runner expects that (EDGE_CASES E-27). The two band misses are SYN-VL-D04 and SYN-BL-D04 (key reject, pipeline refer: mild-photo quality 80 against the key's 72, E-18). Before the E-28 change SYN-PL-D07 also missed: three payslips with a round gross salary raised the weak hint three times.

Live run, models on (Gemini Flash, Groq gpt-oss-20b, Nemotron, with OpenRouter and NVIDIA fallbacks), 5 cases across 4 loan types and a co-applicant: all finished, stop stage and band as keyed, model-written summaries cited rule and clause ids, and the masking guard (which raises on any raw PAN, Aadhaar, GSTIN or email) never fired. Policy findings failed the grounding check in 4 of 6 runs and fell back to code-written findings (Stage 4 behaviour with free-tier Nemotron). Free-tier latency is 2 to 4 minutes a case, mostly Gemini 503s that fall back to OpenRouter.

Pipeline tests (`backend/tests/test_pipeline.py`, `test_agent_units.py`, `test_llm_fallback.py`) need the generated cases and a database; they use scripted models, so no network or keys.

## 2e. API, frontend and browser tests (Stage 6)

- **API** (`backend/tests/test_api.py`, FastAPI test client, throwaway database, models off, fake embedder, in-memory checkpoints): sign-in, lockout and audit; token and deactivation checks; roles (admin cannot create, upload, submit, resume, confirm or override and gets 403 on `/cases`; officer gets 403 on every `/admin` route and the precedent stays pending; another officer's case is a 404); form rules per loan type; masked identifiers; masked values on a corrected form; per-file upload results (bad type, password-protected, blurry, empty are rejected and never written to disk); the KYC gate on submit; precedent approve (expiry, embedding, reviewer, audit), reject, held; **one full case per loan type over HTTP** (create, upload, submit, wait, report, PDF, confirm needs the second click, audit timeline); override rules (second click, reason, different decision); a fix-type stop resumed through `Pipeline.resume_after_fix` (report version 2).
- **Frontend unit** (`npm test` in `frontend/`, Vitest + Testing Library): confirm needs a second click; cancel and Escape record nothing; override blocked without a decision and a reason of 15+ characters; the server message is shown on failure; status chips carry text; the report says "Recommended" and shows unverified stages and clause text.
- **Browser** (`npm run e2e` in `frontend/`, Playwright with the installed Google Chrome): `backend/tests/e2e_server.py` starts the API and the built frontend on a throwaway database with an officer, an admin and one pending precedent. `loan-types.spec.js` takes one case per loan type from new case to a confirmed recommendation (form, per-file uploads, submit, progress, report, extracted fields, PDF download, second-click confirm, audit tab) and one override blocked until a reason is written. `roles.spec.js` checks the admin cannot reach or call case routes, the officer cannot reach the precedent queue, the admin approve dialog, and the plain login error.

## 3. Metrics

| Metric | Meaning |
|---|---|
| Band accuracy | Predicted band equals expected band |
| Stop-stage accuracy | Early-stopped cases stop where the key says |
| Score error | Absolute difference between predicted and target score |
| Field accuracy | Extracted fields equal ground truth (per document type) |
| Citation validity | Every cited clause exists in retrieved text (target 100%) |
| Faithfulness | RAGAS: answer supported by retrieved context |
| Retrieval quality | hit@k, recall@k and MRR on `data/rag/retrieval_eval.yaml` (50 dev queries, 12 test queries), vector-only baseline vs with rerank; targets in `data/rag/baseline.json`; `python -m app.rag.evaluate --split dev` exits non-zero on a miss |
| Hard-rule integrity | No hard-fail case passes, with or without precedents (target 100%) |
| Unverified rate | Share of agent outputs marked unverified |
| Override rate | Officer overrides over total cases (demo and monitoring) |
| Cost and latency | Tokens, cost, seconds per case and per agent |
| Fairness | Approval-rate difference across gender, age band and city tier (monitoring only) |

**Targets:** set after the first baseline run on the dev split (open item OI-7). Fixed targets from day one: citation validity 100%, hard-rule integrity 100%, zero raw PII in LLM inputs.

## 4. Online evaluation (runtime)

Cheap code checks after every agent; an LLM judge only when those are inconclusive. See `AGENTS.md` gate rules. All scores are written to `eval_scores`.

## 5. Offline evaluation

- RAGAS (faithfulness, answer relevance, context precision and recall) on the Policy agent.
- DeepEval for report quality and agreement with the answer key.
- Judge model is lighter than, and from a different family than, the generator.
- Results saved with model versions, prompt versions, policy and rules versions.

## 6. CI gate

GitHub Actions on every PR:

1. Lint, type check, unit and agent tests.
2. Security tests (PII leak, injection set).
3. Dev-split evaluation on a reduced sample; fails if any key metric falls below its threshold or drops more than an agreed margin from the baseline.
4. Dependency audit.

On release: full dev run plus one run on the held-out test split; results attached to the release tag with model versions.

**What the PR gate runs today** (`.github/workflows/ci.yml`): ruff, mypy, synthetic data, `pytest -q` (throwaway Postgres with pgvector, models off), `python -m app.eval.run --split dev` against `docs/baselines/thresholds.json` (floors, a ceiling on score error, a maximum drop from `dev-code.json`, and hard-rule integrity 1.0 with the largest precedent bonus applied to every case), dependency audit, and the frontend lint, tests and build. No API keys are used. The RAG retrieval gate (`app.rag.evaluate`, real embedder) and the RAGAS/DeepEval judge suites run locally before a release.

## 7. Regression practice

- Every bug gets a failing test first.
- Changing a rule threshold needs the golden set rerun and a note in the PR.
- Changing a prompt bumps its version and reruns the golden set.
- Record baselines in `docs/baselines/` (JSON) so changes are visible.

## 7b. Stage 8 and 9 tests

- **UI (Stage 8, built; see 7c):** every screen renders in light, dark and system themes; contrast checked for text and controls in both; theme choice persists and falls back safely without storage; reduced-motion switches animation off; admin Users flow (create, disable, reset, audit rows); roles enforced on the new endpoints; one case per loan type still completes in the browser; confirm and override second clicks unchanged.
- **Notifications (Stage 9):** each template and the blank option pass the content check; a test per forbidden pattern (PAN, Aadhaar, account number, phone, score, rule ID, outcome words, OTP/PIN/password request, missing footer) blocks the send; a case with an applicant name, score and missing items produces a message containing none of them; no send without the second confirmation; the footer cannot be removed through the API; failed sends show as failed and can be retried; another officer's items return 404; audit rows exist for draft, edit, send, block and fail.

## 7c. Stage 8 results (UI revamp)

- **Backend** (`test_api.py`): the user routes and `/admin/summary` are admin-only (officer 403, no token 401); create returns a temporary password once, lowercases the email, refuses a duplicate (409) and a bad email (422), and the new user can sign in; disable, enable and reset are audited with no password in the audit row; a disabled user's token dies at once; an admin cannot disable their own account or the last active admin; summary counts.
- **Frontend unit** (`npm test`): contrast of every text pairing for both themes against WCAG AA 4.5:1 (parsed from `tokens.css`), the system-dark block equals the dark block, unverified is not the brand purple, white panel text passes on the whole login gradient; theme read, apply, save and blocked storage; the three-way toggle; the stepper for draft, running, awaiting, confirmed and stopped (sign-off is never "done" by the system); tile counts; conditions and the 3C regrouping (no numbers added); the typing effect (full text always in the DOM, instant under reduced motion, once per view); the reduced-motion override in `base.css`; the Users screen (list, own account locked, password shown once, second click to disable, server message shown).
- **Browser** (`npm run e2e`): one case per loan type to a confirmed recommendation; roles (admin has no case routes, officer has no admin routes, including Users and summary); admin Users flow (create, duplicate refused, reset needs a second click and the new password works while the old one does not, disable blocks sign-in, enable restores it); login is the landing page with no signup; system, dark and light follow the OS and override it, the choice persists, no flash; every officer and admin screen in light and dark at desktop, tablet and phone widths with no side scrolling; tablet sidebar shows icons only; reduced motion turns animation off; tiles open the filtered list.

## 8. Demo checks (Stage 10)

- Clean case per loan type completes with report.
- Hard-fail case stops at the right stage with a short report.
- Password-protected upload rejected.
- Override, admin approval, similar case re-run shows the precedent.
- Forced model failure triggers fallback; case still completes.
- Login, theme toggle, 5-stage stepper and admin Users screen shown (Stage 8).
- A customer contact message is drafted, checked, sent and appears in Sent Items and the terminal (Stage 9).
