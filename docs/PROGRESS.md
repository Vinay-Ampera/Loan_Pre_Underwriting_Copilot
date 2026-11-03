# PROGRESS

Where the project stands. `IMPLEMENTATION_PLAN.md` says **what** each stage builds and when it is done; this file records **what happened**: status, build notes, measured results and decisions taken during a stage. Update this file at the end of each piece of work. Do not put build notes in the plan.

Build notes for Stages 2 to 6 were moved here unchanged from `IMPLEMENTATION_PLAN.md` on 2026-11-02.

---

## Status

| Stage | State | Notes |
|---|---|---|
| 1 Foundation and synthetic data | Built, exit criteria pass | Migrations 0001-0006 applied on Neon; rules and policy files; mock services; 100 synthetic cases with answer keys |
| 2 Intake and parsers | Built, exit criteria pass | See "Stage 2 build notes" |
| 3 Rules engine and scoring | Built, exit criteria pass | Dev replay reproduces 60/60 bands |
| 4 RAG and Policy agent | Built, exit criteria pass | See "Stage 4 build notes" |
| 5 Agent pipeline on LangGraph | Built, committed | All 60 dev cases finish and stop where expected (the 9 unreadable-ID cases stop at KYC, E-27); kill-and-resume, forced 429 and injection checks pass |
| 6 API and frontend | Built, exit criteria pass | FastAPI with roles, JWT and audit; background runs; React JS + CSS screens; server PDF. Run `python -m app.db.migrate` (0008) on Neon and create users with `app.api.users_cli` before using it |
| 7 Learning loop, evaluation, observability | Built, committed (`babe29b`) | Open items updated 2026-11-02: OI-1, OI-2, OI-5, OI-6 resolved; OI-3 values, OI-4 live Langfuse check and OI-7 targets wait for the real-model baseline run |
| 8 UI revamp (Pramaan) | Built, committed (`25e6ad6`, `ff177fa`) | 2026-11-02. Tokens and bundled fonts, light/dark/system, login landing, sidebar shell, Home screens, stepper, score ring, 3C strip, Conditions, admin Users (new endpoints, audited). See "Stage 8 build notes". No migration, no scoring change |
| 9 Customer notifications and issue reports | **Built, exit criteria pass (not committed)** | 2026-11-02. Migration 0010 (outbox, issue_reports, `users.phone`, `applicants.email`), `app/notifications/`, message and issue routes, Sent items, draft dialog, Report a problem, admin Issues. See "Stage 9 build notes". Run `python -m app.db.migrate` first |
| 10 Hardening, Docker and demo | **Planned, not started** | Was Stage 8; renumbered 2026-11-02. Starts only after Stages 8 and 9 and the review window (see the plan) |

Next: the user commits Stage 9 and applies migration 0010 on Neon, then the review window (additions and corrections), then Stage 10. Do not start Stage 10 until the user says so.

---

## Decisions log

### 2026-11-02: Stages 8 to 10 planned

- **Name:** the bank and the product are both called **Pramaan** ("proof" in Hindi). It replaces the display name "Sample Bank" in the UI, the customer messages and the docs. The policy and rules files keep their `Sample Bank` identifiers; only the display name changes. The name was not checked for trademarks; check before any public use.
- **Look:** Ampera's purple (`#7C70AF`) as the brand colour, with a darker purple (about `#5E4FA0`) for buttons and links so text passes WCAG AA. Fonts: Outfit (headings) and Inter (body), bundled through `@fontsource` packages. Only the colour feel and fonts are borrowed from amperadei.com; no images, copy or policy are reused. Light, dark and system themes with a three-way toggle (system, dark, light) in the sidebar. Some light animation, all switched off under `prefers-reduced-motion`.
- **Login is the landing.** The app is for bank staff, so there is no public page and no signup. The login page carries the brand and the 5-stage explainer. The admin gets a Users screen (create, disable, reset password) instead of using only `users_cli`.
- **Underwriting frame in the UI:** the 5 banking stages (intake and screening, verification and documents, risk and ratios, decisioning and conditions, officer sign-off) are shown as a stepper. The scored stages map as in `DESIGN_SYSTEM.md` section 8. A Credit / Capacity / Collateral strip is a display-only regrouping of existing scores; Collateral reads "not scored in v1". Scoring and weights do not change.
- **Customer notifications:** the officer sends a short contact request to the customer. It carries **no confidential data and no outcome hint**: no name, score, status, missing items or reason; only an optional case reference, the officer's contact details, and a fixed fraud warning (bank staff never ask for an OTP, PIN or password). It is a no-reply message. Delivery in v1 is **terminal log plus a Sent Items screen**; no real email or SMS. Templates plus a blank option; a content check in code blocks a send that contains forbidden content; the officer reviews, clicks Send and confirms in a second dialog.
- **Order:** Stages 8 and 9 come before Stage 10 (Docker). Which of 8 and 9 goes first is decided at the end. A review window for additions and corrections sits between Stage 9 and Stage 10.

### 2026-11-02: Stage 8 follow-ups agreed (after the Stage 8 build, before commit)

The user reviewed the built Stage 8 and agreed these changes. **Built 2026-11-02 (see the tracking line below); the docs first stated an admin email and phone on the login page, corrected the same day to the plain sentence only.**

- **Login page content:** keep a few lines of "About Pramaan" and the five stages. **Move the score weights and bands off the login page** (they would be confidential for a real bank) to the Help page behind sign-in. The login page gets **no footer**. It gets a plain line, **"Can't sign in? Contact your admin."**, and **nothing else**: no email, no phone, no settings values, no request form, no new endpoint. No self-service forgot-password, no open request form (nothing unauthenticated can write; no real email in v1). Lockout still lifts itself; the admin resets a password in the Users screen. The person uses their own channel (phone or internal mail), not the website.
- **Footer inside the app (not on login):** slim, on every signed-in page: "Pramaan, sample bank, synthetic data only", a Help link and the app version.
- **Help page behind sign-in, by role:** a guide for new or forgetful users. Officer: create a case, upload, read the stepper and report, confirm or override, what each stage and agent does in plain words, what "unverified" means, the score weights and bands. Admin: Users, resetting passwords, the precedent queue. Static content, no database or API change.
- **Issue reports to the admin (confirmed by the user 2026-11-02: built with Stage 9):** an officer files an issue, the admin reads it in an inbox. Recommended to build with Stage 9 because it shares the outbox-style table and migration, the content check and the audit rows, but as a separate task so decision 17 (customer notifications) is not changed. Only a case reference, a category and short text; a warning not to paste personal data; the same code check blocks PAN, Aadhaar, phone and account numbers; an officer sees only their own issues; the admin sees all issues but no case data.

### Stage 8 and 9 questions to ask before coding

Ask the user these at the start of the Stage 8 session (and the Stage 9 ones at the start of Stage 9) if the answer is not already in the docs:

- Which of Stage 8 and Stage 9 first, and are the Stage 9 outbox migration and the new `users.phone` and customer email fields wanted in the same migration?
- Stage 8: confirm the exact darker purple for buttons after seeing it in both themes; whether the sidebar collapses on tablet; whether the typing effect on the report summary is wanted or too much.
- Stage 9: the branch contact lines (email, phone) for `.env.example`; the wording of each template (the user reviews all of them); whether failed sends should be retried by the officer only.

---

## Stage 8 to 10 tracking

Tick items here as they land. The exit criteria are in `IMPLEMENTATION_PLAN.md`.

- [x] Stage 8 UI revamp (2026-11-02)
- [x] Stage 8 follow-ups: login page trim and contact-admin sentence, in-app footer, Help page `/help` (built 2026-11-02; frontend only, no migration, no backend change; tests added; not committed)
- [x] Stage 9 Customer notifications and issue reports (2026-11-02; migration 0010; not committed)
- [ ] Review window: additions and corrections collected by the user before Stage 10
- [ ] Stage 10 Hardening, Docker and demo

---

## Stage 9 build notes (2026-11-02)

- **Questions:** none blocked the build. Defaults taken (change on request): the branch contact lines are optional (`BRANCH_CONTACT_EMAIL`, `BRANCH_CONTACT_PHONE` in `.env.example`, empty = omitted); the **template wording is mine and awaits the user's review** (`app/notifications/templates.py`: three templates, general contact, contact soon, visit the branch, plus blank); only the officer who owns a message can edit, send or retry it; one migration holds the outbox, issue reports and the two contact fields.
- **Data (migration 0010):** `outbox`, `issue_reports`, `users.phone`, `applicants.email`. The customer email lives only in `applicants.email`, so it is never in `cases.form_data` and never reaches the pipeline or a model. Grants for `app_rw` and `migrator` are given when those roles exist.
- **Backend:** `app/notifications/` (`templates.py` fixed subject, footer and `compose`; `check.py` the content check and the issue check; `sender.py` the `Sender` protocol, `ConsoleSender`, `build_sender`), `app/api/messages.py` (templates, officer phone, draft, edit, send/retry, list, read), `app/api/issues.py` (file, own list, admin inbox, read, close). `create_app` takes an optional `sender`. `/admin/summary` also counts open issues and messages sent and failed (counts only). The case view returns the customer email masked; a corrected form that leaves it masked keeps the stored one.
- **Behaviour worth knowing:** the draft is created after confirm, override or stop (409 otherwise); the server composes the text (body, optional case reference, contact lines, fixed footer) and checks it on create, edit and send; a blocked or failed send is returned (422 or 502) with its status and audit row committed; sending needs `second_click: true`; a sent message is final. The check also blocks the customer's name, amounts, links and other email addresses, which the plan did not list (a phishing and leak guard). Audit rows never hold message text.
- **Frontend:** `MessageDialog` (two steps, the second shows the exact text), `CustomerContact` card on the case page, `SentItemsPage`, `IssuesPage`, `AdminIssuesPage`, sidebar links, an Open issues tile on admin Home, a customer email field on the application form, and new Help sections. Details in `DESIGN_SYSTEM.md` 9.1.
- **Measured:** results are in `TESTING.md` section 7d.
- **Not done / left for the review window:** real email or SMS (out of scope for v1); a browser (Playwright) test of the message flow, which is listed in the Stage 10 demo checks; the template wording review.

## Stage 8 build notes (2026-11-02)

- **Questions answered before coding (2026-11-02):** Stage 8 goes first and the Stage 9 outbox table and the new `users.phone` and customer email fields wait for Stage 9, so **Stage 8 adds no migration**. Button purple `#5E4FA0` confirmed. The sidebar collapses to icons on tablet widths. The typing effect on the report summary is wanted.
- **Backend:** `app/api/users.py` (new): `GET /admin/users`, `GET /admin/summary`, `POST /admin/users`, `POST /admin/users/{id}/disable|enable|reset-password`. Temporary passwords are generated on the server (`secrets`), returned once, argon2-hashed, never logged. Audit actions `user_created`, `user_disabled`, `user_enabled`, `user_password_reset`. An admin cannot disable their own account or the last active admin. `UserCreateIn` added to `schemas.py`. Scoring, rules, agents and the confirm/override rules are untouched. The PDF author is now Pramaan.
- **Frontend:** new shell (`Sidebar`, `BrandMark`, `ThemeToggle`, `Icons`), pages `HomePage`, `AdminHomePage`, `AdminUsersPage`, restyled `LoginPage`, `CaseStepper`, score ring (`ScoreBadge`), `CreditStrip`, Conditions block and `TypedText` in the report. `TopBar` was removed. Routes: `/` is Home for both roles; officers get `/cases`; admins get `/admin/precedents` and `/admin/users`. Details in `DESIGN_SYSTEM.md` 8.9.
- **Contrast:** the unit test found two Stage 6 status colours below AA on their tinted backgrounds (approve and refer). They were darkened (`#19703f`, `#8a5700`). All text pairings now pass 4.5:1 in both themes.
- **Fonts:** `@fontsource/inter` and `@fontsource/outfit` are exact-pinned in `frontend/package.json`; no runtime request to Google.
- **Measured:** results are in `TESTING.md` section 7c.
- **Decisions taken:** the 3C strip and Conditions are built in the browser from the report's existing stage scores and document findings (no backend change, no numbers added). Home tiles filter in the browser (`/cases?view=...`) because the list endpoint filters by status only. "Referred" means awaiting confirmation with band refer. The Sent items link arrived with Stage 9. Admin creation of another admin is allowed (the CLI allowed it too).
- **Not done here:** nothing from the Stage 8 task list. Policy and rule file status and the Grafana link (listed as not built in Stage 6) are not in the Stage 8 plan and remain open for the review window.

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

---

## Stage 4 build notes (2026-10-31)

- **Modules:** `app/rag/` (`policy_loader`, `embedder`, `index`, `reindex`, `retrieve`, `precedents`, `grounding`, `schemas`, `config`, `evaluate`) and `app/agents/policy.py`; prompt `backend/prompts/policy.md` (v1). Settings in `data/rag/config.yaml`; migration 0007 adds `checksum` and `indexed_at` to `policy_documents`.
- **Index:** BGE-small (384-d, normalised) and the MiniLM cross-encoder run locally from the venv (`sentence-transformers` on CPU `torch`; models load from the local cache first). `python -m app.rag.reindex` parses the policy files, re-embeds only new or changed clauses, handles new versions (one active per loan type) and removed clauses, reloads the rules file, and writes an `audit_log` row. It refuses to run if a rule cites a clause that is not in `data/policy`.
- **Retrieval:** top 12 by cosine, rerank, keep 5 per query; filters are the active version and `common` + the case's loan type. The agent also fetches the clauses that rule results point at (`via="rule"`, relevance 1.0), so every rule-based finding has its clause available.
- **Precedents:** `find_precedents` returns approved, unexpired, same-loan-type precedents at or above `precedent.similarity_min`, only for a refer-band case with no hard stop. Nothing writes precedents yet (Stage 7); `precedent_text()` defines the text that Stage 7 must embed so both sides match. The score bonus stays 0.
- **Measured (50 dev queries, local Postgres 17 + pgvector):** vector only: hit@1 0.80, recall@5 0.99, MRR 0.888; with rerank: hit@1 0.84, recall@5 1.00, MRR 0.903; citation validity 1.00. Targets are recorded in `data/rag/baseline.json` (recall@5 0.95, hit@3 0.95, hit@1 0.80, MRR 0.88, validity 1.0). The 12 test queries were not run.
- **Live check:** one synthetic personal case through the real Nemotron model gave grounded findings on the first try; another run failed the quote check twice and fell back to code-written findings, which is the designed behaviour. Model wording varies between runs.
- **Environment:** the Neon database was unreachable during this stage (the hostname lookup hung), so the migration, seed, index and tests ran on a private throwaway Postgres 17 cluster with `DATABASE_URL` overridden in the shell. Neon still needs `python -m app.db.migrate` and `python -m app.rag.reindex` before the next stage.
- **Not done here (later stages):** RAGAS faithfulness on the Policy agent and the online judge (Stage 7); wiring into LangGraph gates (Stage 5).

---

## Stage 5 build notes (2026-10-31)

- **Modules:** `app/agents/` (see `AGENTS.md`, "How the pipeline runs"). Prompts `backend/prompts/{supervisor,kyc,risk,decision}.md` (v1). New dependency: `langgraph`, `langgraph-checkpoint-postgres`.
- **Scoring runs once.** The rules engine is called at the end of Extraction; KYC, Risk, Policy and Decision read its result. Models explain and write; every model reply is schema-checked, guardrail-checked (decision words, protected attributes, invented numbers, unknown ids), retried once, then replaced by code-written text and marked `unverified`.
- **Extraction path:** upload checks, intake, duplicate check, masked LLM fill for missing fields only, then the `CaseInput` is built from the form, the mock identity, bureau and GST lookups and the bank-statement analytics. Bank statements and GST returns now carry their month counts (`units`). Cross-document tamper hints are applied here once.
- **Checkpoints:** Postgres schema `langgraph`; `python -m app.agents.run --resume CASE` continues a killed run. `--crash-before STAGE` kills the process as a stage starts, for the resume check. `Pipeline.resume_after_fix` and `Pipeline.officer_action` are the entry points the Stage 6 API will call.
- **Models off:** `--no-llm` skips every model call. Used for the 60-case runs, CI and offline work; the live run is the same code with the router on.
- **Exit criteria** (measured in `docs/TESTING.md` section 2d, dev split, models off): all 60 cases finish and **stop at the expected stage (60 of 60)**; band matches the key for 58 of 60. The 9 cases with an unreadable `poor` ID photograph are expected to stop at KYC (E-27, decided). Kill and resume gives the same result (tests plus a real `exit 137`); a forced 429 on every primary completes through the fallbacks (real Router, mocked providers; a live forced 429 is too slow on the free tiers); injected instructions change nothing (obedient scripted model plus a poisoned payslip).
- **Models on:** tried live on 5 cases; max output tokens were raised (Gemini 3.x and gpt-oss spend part of the limit on reasoning, and 300 to 900 truncated the JSON).
- **Intake changes made here:** an accepted passport-style photograph gets the "good photo" quality (94) instead of a score read from OCR noise (it pulled `kyc_doc_quality` down to 55 to 63 for clean cases); `ExtractedDocument.meta` carries `units`.
- **Decisions taken:** E-18 is left as measured (see `EDGE_CASES.md`); `CM-DOC-11` and `CM-KYC-13` tiers are unchanged. A weak hint counts once per kind, so a round salary on every payslip is one hint (E-28).
- **Not done here (later stages):** Langfuse traces and Prometheus metrics (Stage 7), RAGAS faithfulness for the Policy agent and the offline judge run (Stage 7), the HTTP API and the confirm/override screens (Stage 6; `Pipeline.officer_action` and `officer_actions` rows exist), Neon `migrate` and `reindex` (Neon was unreachable again; see Stage 4 notes).

---

## Stage 6 build notes (2026-11-01)

- **Decision changed by the user:** the frontend is React, plain JavaScript and CSS (no TypeScript, no Tailwind). CLAUDE.md decision 10, CODE_STYLE section 3, ARCHITECTURE, PRD and the diagram script were updated first.
- **Backend:** `app/api/` (`main`, `auth`, `cases`, `admin`, `deps`, `runner`, `security`, `schemas`, `display`, `reportpdf`, `users_cli`) and `app/main.py`. Migration 0008 (lockout columns). New dependencies: fastapi, uvicorn, python-multipart, pyjwt, argon2-cffi. Settings added: `LLM_ENABLED`, `ACCESS_TOKEN_MINUTES`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES`, `CORS_ORIGINS`. Small changes in Stage 5 code: `Pipeline.resume_after_fix` takes the whole current file list (`documents=`) so removed files go away; `store.audit` records the actor; `next_case_no` is public. See ARCHITECTURE section 3b.
- **Frontend:** `frontend/` (Vite, React 18, react-router). See DESIGN_SYSTEM section 6b.
- **PDF:** reportlab on the server (`GET /cases/{id}/report.pdf`); no identifiers are printed.
- **Decisions taken:** admin has no case access at all (least privilege); the document type picked at upload is only a checklist hint; the checklist counts a bank statement as one file; application date defaults to today and can be set (the synthetic cases use 2026-10-20).
- **Scope boundary:** creating a precedent from an override (LLM summary, code hard-rule check, `pending`/`held` rows) is Stage 7 task 1. Stage 6 builds the queue: list, approve (expiry date, embedding, reviewer) and reject, with roles enforced. Tests insert `pending` rows directly.
- **Browser tests:** Playwright 1.64 with the installed Chrome (1.49 hung on Node 24). The user approved the install on 2026-11-01.
- **Not done here:** admin users page and policy/rule status, Grafana link; `Runner.recover` (continue `running` cases at start-up) has no dedicated test; the migration and user creation on Neon are for the user to run (below).
- **Run it:** `cd backend && ../.venv/bin/python -m app.db.migrate`, then `python -m app.api.users_cli create --email ... --name ... --role officer|admin`, then `uvicorn app.main:app --reload` and `npm run dev` in `frontend/` (proxy to port 8000), or `npm run build` and open the API's port to get both from one process.

---

## Review-window additions (2026-11-03)

- **Report:** an "At a glance" card above the Summary (score ring, top 3 reasons ranked hard fail, cap, biggest point loss, and the next step; all taken from existing findings, nothing computed in the UI). The Policy citations block has a text search and a "cited by stage" filter.
- **Admin officer view** (`/admin/users/:id`, `GET /admin/users/{id}/activity`): case counts by status and band, confirm and override counts, precedents proposed by status, last sign-in, and the 10 latest case numbers with status. No applicant data, so the least-privilege rule (admin has no case access) is unchanged.
- **User menu** top right, beside the theme toggle: name, email, role and Sign out (asks first). No separate Profile page. The sidebar keeps only navigation.
- **Not done (waiting on the user):** read-only super admin / auditor role. It changes locked decision 9 and needs a migration for the role check.
- **No schema change** in this batch, so no migration to run.
