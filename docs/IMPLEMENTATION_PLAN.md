# Implementation Plan

Eight stages. Each stage ends with something runnable and a test gate. Do not start a stage until the previous exit criteria pass. No dates yet (deadline not fixed); effort is S (≈1 day), M (2-3 days), L (4-6 days) for a solo developer.

Trainer approval of the documents comes first. Nothing below starts before that.

```
1 Foundation   2 Intake & parsers   3 Rules & scoring   4 RAG & Policy
5 Agent pipeline   6 API & frontend   7 Learning, eval, observability   8 Hardening & Docker
```

---

## Stage 1: Foundation and synthetic data (L)

**Goal:** repo, database, config, and the synthetic world that everything else tests against.

Tasks
1. Create the repo (trunk-based) with the folder layout from `CODE_STYLE.md`. Add `.env.example`, `.gitignore`, pre-commit hooks.
2. Create the Neon project. Enable pgvector. Write migrations for all tables in `DATABASE.md`.
3. Verify free LLM access and limits for Gemini Flash, Groq gpt-oss-20b, NVIDIA Nemotron and one fallback. Record real model IDs and limits (closes OI-5). Set up LiteLLM config.
4. Write the sample policy documents (common + five loan types) with clause IDs, tagged `public`, `RBI` or `sample`.
5. Write the rules file (common + per loan) with weights and bands.
6. Build mock services: identity (PAN/Aadhaar), bureau (CIBIL), GST, Udyam, backed by synthetic records.
7. Build the data generator: identities with valid checksums, payslips, bank statements (3-4 styles), ITR, Form 16, loan-specific documents, photo variants, tampered variants, password-protected files.
8. Generate 100 cases (60 dev, 40 test) with answer keys. Generate small unit-test fixtures separately.

Deliverables: running database, rules and policy files, 100 cases with answer keys, mock services.

Exit criteria
- Migrations apply on a clean Neon database.
- All 100 cases have the full document set and an answer-key row.
- Score targets cover 30, 40, 55, 67, 85, 98 and 100 across the set.
- A script confirms every generated PAN and Aadhaar passes the validators.

Risks: generator takes longer than expected. Mitigation: build personal and home first; add the rest in the same stage but allow education last.

---

## Stage 2: Document intake and parsers (L)

**Goal:** turn an uploaded file into masked, validated, structured fields.

Tasks
1. Upload-time checks: type and size, password-protected rejection, blur and crop score, per-page type detection.
2. Digital PDF extraction (PyMuPDF, pdfplumber tables).
3. Image pipeline (OpenCV deskew, blur score) and local OCR (PaddleOCR, Tesseract fallback).
4. Document classifier.
5. PII masker (PAN, Aadhaar, phone, account numbers, email). Keep a reversible local map so matching runs before masking, and the LLM only sees masked text.
6. LLM extraction into Pydantic schemas with per-field confidence.
7. Code validators: ID formats and checksums, totals, dates, running balances.
8. Tamper hint checks.
9. Bank statement parsers for the 3-4 synthetic styles (digital first).

Deliverables: `intake` module with CLI to run a file and print structured output.

Exit criteria
- Field-level accuracy on dev documents meets the target agreed after a first baseline (see `TESTING.md`).
- 100% of password-protected test files rejected; blurry samples handled as specified.
- Masking test: zero raw PAN or Aadhaar patterns in any text sent to an LLM client.
- Tampered samples are flagged by at least one hint.

---

## Stage 3: Rules engine and scoring (M)

**Goal:** all scoring in code, tested without any LLM.

Tasks
1. Rules loader with schema validation and version checksum.
2. Evaluators for each operator and field; FOIR, DTI, LTV, age at maturity, tenure limits.
3. Stage scorers: KYC, Documents, Income and FOIR, Credit and behaviour, Policy fit (precedent bonus stubbed).
4. Hard-fail logic with the two classes (fix-type, eligibility-type), score cap, early stop.
5. Bank-statement analytics: salary credit detection, cheque and NACH return detection, bounce counts, credit-to-GST ratio for business.
6. Name, PAN, DOB and address matching with fuzzy thresholds.
7. Co-applicant aggregation (combined FOIR, per-person KYC).

Deliverables: `scoring` module, rule-result records with evidence.

Exit criteria
- Unit tests for every rule operator and every hard rule.
- Replaying the dev answer-key inputs (structured fields, no documents) reproduces the expected score band for at least the agreed share of cases.
- Changing a threshold in the rules file changes behaviour with no code change.

---

## Stage 4: RAG and the Policy agent (M)

**Goal:** grounded retrieval of policy clauses and (later) precedents.

Tasks
1. Chunk policy documents by clause ID; embed with BGE-small; store in `policy_chunks`.
2. Retrieval: vector search, cross-encoder rerank, metadata filters (loan type, active version).
3. Self-RAG style grounding check: every cited clause must exist in retrieved text; answer must be supported.
4. Policy agent output schema with citations.
5. Re-index command for policy and rules updates, recording versions.
6. Retrieval evaluation set: queries mapped to expected clause IDs.

Exit criteria
- Citation validity 100% on the retrieval set (no clause cited that was not retrieved).
- Recall at k and rerank metrics meet the baseline-then-target process.
- Re-index run picks up an edited clause.

---

## Stage 5: Agent pipeline on LangGraph (L)

**Goal:** the full multi-agent run, from submitted case to report, with pause and resume.

Tasks
1. Define graph state and nodes: Supervisor, Extraction, KYC, Policy and Risk in parallel, Decision.
2. Gates after each node: hard-fail stop, low-confidence flag, retry once then unverified.
3. LiteLLM routing per agent with fallback on 429 and errors; token and cost logging.
4. Guardrails: injection scan, schema validation, citation requirement, banned terms and protected attributes, "recommend" wording.
5. Postgres checkpointer for pause (awaiting officer) and resume (after correction or confirmation).
6. Report builder: stage scores, findings with rule IDs and clause links, rejection reason text, combined co-applicant sections.
7. Online evaluation hooks per agent (code checks first, judge only when inconclusive).
8. Run the 60 dev cases end to end from the command line.

Exit criteria
- All 60 dev cases complete or stop at the stage the answer key expects.
- Killing the process mid-run and resuming from the checkpoint gives the same result.
- A forced 429 on a primary model triggers the fallback and the case still completes.
- Injection test documents do not change any score or recommendation.

---

## Stage 6: API and frontend (L)

**Goal:** loan officer and admin use the system through a browser.

Tasks
1. FastAPI: auth with roles, case CRUD, uploads with checks, submit, status, report, confirm and override, admin precedent queue, audit writes.
2. Background execution of the graph from the API (no Celery in v1).
3. React screens per `DESIGN_SYSTEM.md`: login, case queue, new case form, upload with per-file results, case detail with document viewer, extracted fields, stage cards and report, confirm panel with double confirmation, override with reason, admin precedent queue.
4. PDF export of the report.
5. End-to-end test with a browser test tool for one case per loan type.

Exit criteria
- One case per loan type completed through the UI.
- Roles enforced: officer cannot approve precedents; admin cannot upload.
- Confirm and override both need a second click; override blocked without a reason.

---

## Stage 7: Learning loop, evaluation and observability (L)

**Goal:** the system learns from overrides; quality and cost are measured.

Tasks
1. Precedent creation on override (reason plus LLM summary), hard-rule check, admin approval, expiry date, embedding.
2. Precedent retrieval inside the Policy agent: borderline only, same loan type, similarity threshold, capped bonus, never over a hard rule.
3. RAGAS and DeepEval suites; full run on dev and test; GitHub Actions gate on PRs with metric thresholds.
4. Fairness report from the separate attributes table (monitoring only).
5. Langfuse tracing with masked data only: tokens, cost and latency per agent, evaluation scores attached.
6. Tune thresholds on dev; record the baseline; set targets (closes OI-3 and OI-7).
7. A demo scenario: override a borderline case, approve the precedent, rerun a similar case, show the changed recommendation.

Exit criteria
- Precedent demo works and the precedent is visible in the report.
- Hard-rule cases never pass because of a precedent (test).
- CI blocks a PR that drops key metrics below threshold.
- Langfuse shows per-case tokens, cost and latency with no PII.

---

## Stage 8: Hardening, Docker and demo (M)

**Goal:** a reproducible package and a smooth demo.

Tasks
1. Security pass against `SECURITY.md`: secrets, retention job, audit coverage, PII leak scan on logs and traces.
2. Docker Compose: frontend, API (with graph runner), local Langfuse if used, Prometheus, Loki, Tempo, Grafana. Postgres stays on Neon, with an optional local Postgres service for offline use.
3. Grafana dashboards: applications per day, time to decision, override-rate trend, tokens and cost per case, latency per agent.
4. Model versions and policy versions tagged on releases.
5. Run the 40 test cases once, record final results.
6. Demo script, a short README, and a clean `.env.example`.
7. Update all docs to match what was built.

Exit criteria
- `docker compose up` brings up the full stack on a clean machine with only `.env` filled in.
- Final test-set results recorded.
- Demo script runs end to end without manual fixes.

---

## Order of risk

Highest risks first so we meet them early: synthetic data realism (Stage 1), OCR on photos and statement tables (Stage 2), free-tier rate limits (Stage 5), evaluation noise from small data (Stage 7). Where a risk bites, cut scope in this order: scanned statement styles, education case count, Grafana dashboards. Never cut the human confirmation, hard rules or masking.

## Definition of done (every stage)

Tests written and passing, docs updated if behaviour changed, no real PII, secrets only in `.env`, PR reviewed against `CODE_STYLE.md`, CI green.

---

## Stage 2 build notes (2026-10-31)

- **OCR engine:** RapidOCR (the PaddleOCR PP-OCR detection and recognition models run through onnxruntime) is the primary engine. The `paddlepaddle`/`paddlex` wheels pin PyYAML 6.0.2 and `opencv-contrib-python`, which clash with LiteLLM and the headless OpenCV already in the venv. `app/intake/ocr.py` still tries PaddleOCR, then Tesseract, if either is installed. Same models, same local-only guarantee. Needs the user's OK to keep (CLAUDE.md decision 10 says "PaddleOCR").
- **Measured on the dev split (607 documents):** upload accepted 100%; classifier 98.7%; field accuracy 100% on digital PDFs, 99% on good and mild photos, 100% on scanned statements, 30% on `poor` photos (the officer sees `missing_required_fields` and a quality score near 57); zero raw PAN/Aadhaar/GSTIN/email after masking; every tamper case has at least one hint; 0.8% of clean documents get the weak `ROUND_SALARY` hint.
- **Calibrated quality score** (feeds CM-DOC-11 / CM-KYC-13): digital 95, good photo 94, mild photo 80, poor photo 57. Scanned statements measure about 90 because the generated scans are sharp; the design targets (72 and 55) were for degraded images.
- Blur reject below 10, warn below 60 (variance of the Laplacian at 1000 px width). Cropped = page aspect ratio outside 1.30 to 1.55. Images under 500 px on the short side are treated as ID photographs and get no blur or crop verdict.
- Cross-document tamper hints (`salary_credit_hint`, `odd_credit_hints`) are functions in `tamper.py`; the Risk agent calls them in Stage 5.

---

## Stage 3 build notes (2026-10-31)

- **Module `app/scoring/`:** `rules.py` (loader, schema, checksum), `evaluate.py` (reference evaluator, now with a public `evaluate_rule` and "unverified = fail/0 points"), `finance.py` (EMI, age, FOIR, DTI, LTV: the only place these are computed), `matching.py` (names, PAN, DOB, address), `analytics.py` (bank-statement analytics), `facts.py` (derive the facts the rules read, with co-applicant aggregation), `engine.py` (`score_case`: stage groups, early stop, caps, precedent-bonus stub), `models.py` (inputs and the `ScoreReport`), `replay.py` (dev-split replay).
- **Rules file additions** (`rules_version` 2026.10.31-2): `pricing` (rate per loan type for sizing the new instalment) and `params` (existing-loan cut-off, bands, disallowed purposes, education margin/collateral limits, tamper hint rules, statement detection). No threshold or parameter lives in code.
- **Early stop:** groups run extraction, KYC, risk (income and credit), policy. A hard `stop` failure ends the run after its group; later groups never derive facts. Fix-type gives `fix_required` with no score; eligibility-type gives `recommend_reject` with an indicative score capped at 59.
- **Where values come from:** FOIR = (bureau EMIs with more than 12 instalments left + new EMI at the pricing rate) / combined verified income. Education sizes the new EMI over the repayment period, not the moratorium. Income is the documented figure held down to what the bank statement supports. Details and decided edge cases: `docs/EDGE_CASES.md` E-13 to E-18.
- **Replay result (dev):** band 60 of 60, stop stage and class 60 of 60, score and failed rules 59 of 60. Agreed minimums: band 95%, exact 90%. The test split was not run (final evaluation only).
- **Precedent bonus:** `apply_precedent_bonus` is a stub (0 until Stage 4 and 7). It is capped by `precedent.bonus_max`, only touches a refer-band case that no cap rule holds, and never overrides a hard rule.

