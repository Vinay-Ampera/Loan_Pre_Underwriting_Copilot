# Implementation Plan

Ten stages. Each stage ends with something runnable and a test gate. Do not start a stage until the previous exit criteria pass. No dates yet (deadline not fixed); effort is S (≈1 day), M (2-3 days), L (4-6 days) for a solo developer.

Trainer approval of the documents comes first. Nothing below starts before that.

```
1 Foundation   2 Intake & parsers   3 Rules & scoring   4 RAG & Policy
5 Agent pipeline   6 API & frontend   7 Learning, eval, observability
8 UI revamp (Pramaan)   9 Customer notifications   10 Hardening & Docker
```

Stages 8 and 9 were added on 2026-11-02 (the old Stage 8 is now Stage 10). Stage 8 was built first (2026-11-02). After both, there is a **review window**: the user collects additions and corrections, and they are done before Stage 10 starts. Docker is always last.

**Where progress is recorded:** this file says what each stage builds and when it is done. Status, build notes, measured results and decisions live in `PROGRESS.md`. Do not add build notes here.

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

## Stage 8: UI revamp, "Pramaan" (L)

**Goal:** a polished, bank-grade interface that shows the underwriting flow, with the Ampera colour and fonts, light and dark themes, and an admin Users screen. Scoring, rules, agents and the second-click rules do not change.

Tasks
1. **Design tokens and fonts:** Ampera purple brand (`#7C70AF` accents, a darker purple for buttons and links that passes AA), lavender tint surfaces, Outfit headings and Inter body through `@fontsource` packages (bundled, no runtime Google request). Status colours stay; the "unverified" colour moves off purple so it is not confused with the brand. Tokens for both themes in `frontend/src/styles/tokens.css`.
2. **Theme toggle:** system, dark, light as a three-way pill in the sidebar. System is the default; the choice is kept in the browser. All colours come from tokens; no per-theme stylesheet.
3. **Login as the landing page:** split layout with a brand panel (the 5-stage journey, the score bar, "a human confirms every case", a "Pramaan is a sample bank, synthetic data only" note) and the sign-in form. No signup and no public page.
4. **App shell:** a sidebar (Home, Cases, New case; admin: Home, Precedents, Users) replacing the thin top bar, with user, role and the theme toggle.
5. **Home screens:** officer home with summary tiles (awaiting confirmation, referred, stopped, in progress) and recent cases; admin home with pending precedents and user counts.
6. **Case workspace:** a 5-stage stepper (intake and screening, verification and documents, risk and ratios, decisioning and conditions, officer sign-off) showing where the case is and where it stopped.
7. **Report:** score ring and band, a Credit / Capacity / Collateral strip (display only; Collateral reads "not scored in v1"), a separate Conditions list for missing items, and the existing stage cards. The recommendation wording rules stay.
8. **Admin Users screen:** list, create, disable, reset password; backed by new admin endpoints that reuse the `users_cli` rules and write to the audit log. (Changed 2026-11-03: the admin now reads every case and corrects decisions; see `SECURITY.md` D4.)
9. **Motion:** light entrance and progress animation, a one-time typing effect on the report summary, all off under `prefers-reduced-motion`.
10. **Brand name:** replace the display name "Sample Bank" with "Pramaan" in the UI and docs (policy and rules identifiers unchanged).
11. Update `DESIGN_SYSTEM.md` and the other affected docs in the same change.
12. **Follow-ups agreed 2026-11-02 (after the first build):** trim the login page (stages and a short About only; the score weights and bands move behind sign-in, to Help); add the plain sentence "Can't sign in? Contact your admin." under the form (no email, no phone, no settings values, no request form, no new endpoint); no footer on the login page; a slim footer on every signed-in page (name, sample-bank note, Help link, app version); a role-based **Help** page behind sign-in (officer guide and admin guide). Static content, no migration, no backend change. Tests: the login page shows no weights, the contact sentence shows, the footer is on signed-in pages only, Help shows the right guide per role.

Deliverables: the revamped frontend, the Users endpoints, updated tests and docs.

Exit criteria
- Every screen works in light, dark and system modes; text contrast passes WCAG AA in both.
- Browser tests pass for officer and admin, including the admin Users flow and one case per loan type.
- Reduced-motion is respected (checked in a browser test or a CSS test).
- Roles are enforced on the new endpoints; creating, disabling and resetting a user are audit-logged.
- No change to scoring, bands or the confirm/override rules.

Risks: scope creep in visuals. Mitigation: tokens first, then the shell, then screens in the order above; cut motion before cutting contrast or tests.

---

## Stage 9: Customer notifications (M) — built 2026-11-02, see `PROGRESS.md`

**Goal:** after a case is assessed or stopped, the officer can send the customer a short, safe contact request, and every message is recorded in a Sent Items list.

Tasks
1. **Data:** migration for an outbox table and for the contact fields (customer email on the applicant, a phone number on each user); see `DATABASE.md`. Customer email is a new optional form field (synthetic values only).
2. **Templates in code:** one neutral subject for every message; a short generic body; a fixed fraud footer that cannot be removed; the officer's name, email and phone; an optional case reference. No outcome hint of any kind. Templates differ only in tone (for example "please contact us" versus "please visit the branch"). A **blank** option lets the officer write their own text.
3. **Content check in code:** before a send, scan the subject and body for forbidden content (PAN and Aadhaar patterns, account and phone numbers, scores and rule IDs, the words approved, rejected, eligible, a request for an OTP, PIN or password) and a missing footer. A hit **blocks** the send and says why.
4. **Flow:** the draft appears in the case workspace after confirm, override or a stopped run. The officer edits, clicks Send, then confirms in a second dialog. A send writes an outbox row, prints the message in the backend terminal through the console sender, and marks it sent. A failed send is shown as failed; the officer can retry.
5. **Sent Items screen:** the officer's own sent and failed messages with date, case reference, template and status. No access to another officer's items; admin sees counts only.
6. **Sender interface:** a small `Sender` interface with the console sender as the only v1 implementation, so a real mail or SMS service can be swapped in by config later.
7. **Audit:** draft created, edited, sent, blocked and failed are written to the audit log.
8. Update `PRD.md`, `DATABASE.md`, `SECURITY.md`, `ARCHITECTURE.md`, `TESTING.md` and `DESIGN_SYSTEM.md`.
9. **Issue reports to the admin (confirmed by the user 2026-11-02).** An officer files an issue (case reference, category, short text, a warning not to paste personal data); the admin reads all issues in an inbox; an officer sees only their own. Same migration style, the same content check as task 3 (PAN, Aadhaar, phone and account patterns blocked), audit rows for filed, read and closed. Separate from the customer message feature; decision 17 is not changed.

Deliverables: migration, notification module and API routes, officer screens (draft dialog, Sent Items), tests, docs.

Exit criteria
- Each template and the blank option produce a message that passes the content check.
- A message with forbidden content is blocked (tests for every pattern in task 3).
- Nothing is sent without the second confirmation.
- No name, score, status, missing item or reason appears in any message (test).
- The fraud footer is always present and cannot be edited out.
- Sent Items lists each message with its status; another officer's items return 404.

Risks: the blank option lets the officer type a leak. Mitigation: the code check blocks it and the second confirmation shows the final text.

---

## Stage 10: Hardening, Docker and demo (M)

**Goal:** a reproducible package and a smooth demo.

Tasks
1. Security pass against `SECURITY.md`: secrets, retention job, audit coverage, PII leak scan on logs and traces.
2. Docker Compose: frontend, API (with graph runner), local Langfuse if used, Prometheus, Loki, Tempo, Grafana. The Stage 9 sender stays the console sender; a real mail or SMS service is not part of v1. Postgres stays on Neon, with an optional local Postgres service for offline use.
3. Grafana dashboards: applications per day, time to decision, override-rate trend, tokens and cost per case, latency per agent.
4. Model versions and policy versions tagged on releases.
5. Run the 40 test cases once, record final results. Fold in the additions and corrections from the review window.
6. Demo script, a short README, and a clean `.env.example`.
7. Update all docs to match what was built.

Exit criteria
- `docker compose up` brings up the full stack on a clean machine with only `.env` filled in.
- Final test-set results recorded.
- Demo script runs end to end without manual fixes.

---

## Order of risk

Highest risks first so we meet them early: synthetic data realism (Stage 1), OCR on photos and statement tables (Stage 2), free-tier rate limits (Stage 5), evaluation noise from small data (Stage 7), visual scope creep (Stage 8). Where a risk bites, cut scope in this order: scanned statement styles, education case count, Grafana dashboards, UI motion. Never cut the human confirmation, hard rules or masking.

## Definition of done (every stage)

Tests written and passing, docs updated if behaviour changed, no real PII, secrets only in `.env`, PR reviewed against `CODE_STYLE.md`, CI green.
