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
| 9 Customer notifications and issue reports | Built, committed (`a91f035`) | 2026-11-02. Migration 0010 (outbox, issue_reports, `users.phone`, `applicants.email`), `app/notifications/`, message and issue routes, Sent items, draft dialog, Report a problem, admin Issues. See "Stage 9 build notes". Run `python -m app.db.migrate` first |
| 10 Intake desk and applicant upload link | Built, committed (A to C `d2bcae7`, D `f3c4a2c`) | Migrations 0014 to 0017; `intake/archive.py`, `readcache.py`, `inventory.py`, `prefill.py`, `bundle.py`; `api/ingest.py`, `intake.py`, `links.py`, `public.py`, `filestore.py`, `ratelimit.py`; desk, split screen, form tick, links page and applicant page in the UI. See "Stage 10 build notes" and "Stage 10 Part D build notes". Run `python -m app.db.migrate` first |
| 10b AI control for the admin | Built, committed (`f521e32`) | Migration 0018; `services/ai_config.py`, `api/ai_control.py`, `agents/prompt_check.py`; models, keys (status only), prompts (editable part) and settings from the browser. See "AI control build notes". Run `python -m app.db.migrate` first |
| 10c Knowledge base (policy documents and learnings) | Built, committed (`d484bff`) | Migration 0021; `rag/policy_admin.py`, `rag/policy_store.py`, `rag/versions.py`, `learning/maintenance.py`, `api/knowledge.py`; admin Knowledge base page and officer Policies page. See "Knowledge base build notes". Run `python -m app.db.migrate` first |
| 11 Hardening, Docker and demo | **Built (2026-11-21; not committed)** | Migrations 0023 (Part 3) and 0024; retention job, log guards, audit-coverage test, dashboards row 6, release manifest, judge runner, final test-split results (models off), `docs/DEMO.md`, README, `requirements.lock`, `Dockerfile`, `docker-compose.yml`. See "Stage 11 build notes". The real-model test run is the user's |

In-app notifications Part 1 and Part 2 (email) are committed (`135b5b1`, `7b96d95`). The post-demo cleanup (2026-11-21, migration 0022) is committed (`319af64`); see "Post-demo cleanup" below.

Notifications Part 3 (hardening and close-out) is built (2026-11-21, migration 0023); see "Notifications Part 3 build notes". Next: Stage 11 (hardening, Docker and demo), asked for by the user on 2026-11-21. Docker stays last.

---

## Decisions log

### 2026-11-21: Notifications Part 3 and Stage 11 started; three Stage 11 choices

The user asked for Notifications Part 3 and then Stage 11 (Docker last), and chose:

1. **RAGAS and DeepEval are replaced by our own judge runner** (`python -m app.eval.judge`): the existing judge model grades the Decision summary and the Policy findings against the masked facts and the cited clause text on the dev split. No new packages. The docs that promised RAGAS and DeepEval are updated to say so (decision 15: the user's word).
2. **Final test-split run:** the models-off results are run and recorded here; the real-model run is one command the user runs with their own keys, and its numbers are recorded when the user pastes them back.
3. **Langfuse stays on the cloud** (or off): the Compose stack does not self-host it (that would need ClickHouse, Redis and MinIO).

### 2026-11-21: Knowledge base planned and built (changes locked decision 12)

The user asked for an admin feature to add, read, change and retire the policy documents behind RAG, see the learnings, handle yearly policy changes (one clause or the whole document) and deal with old-format documents, before Notifications Part 3 and Stage 11. A plan was agreed in chat; the user accepted every recommendation and changed one: uploads accept `.txt` and `.docx` as well as Markdown, converted to Markdown.

1. **Decision 12 changed:** policy text is kept in the database (every version, with its full Markdown); the files in `data/policy` are starting data imported only when their label is new. The rules file is still edited by hand only.
2. Scoring numbers stay in the rules file; a changed number in a clause is a warning naming the rule (E-92).
3. Old-format documents: code-only import, the admin checks every proposed clause ID (no LLM).
4. "Delete" is retire; published versions are never edited or deleted.
5. A published change pauses the approved precedents whose rules use a changed clause, until the admin confirms them again or retires them.
6. Officers get a read-only Policies page; no new notification kind.

### 2026-11-17 (later): one loader, screens appear all at once
UI only (details in `DESIGN_SYSTEM.md` 8.13). New `Loader`, `Reveal`, `useBusy`; `useAsync` reports its first load, so every screen shows once, after all its data. First load after sign-in is full screen and waits for fonts. Also fixed a stale-inventory race on the documents desk. Unit tests 574 pass.

### 2026-11-17: Case page tidy, password toggle, two test fixes
UI only, at the user's request after a review of the case page (details in `DESIGN_SYSTEM.md` 8.12): two-column case page, the score shown once, no stale "awaiting" text after a decision, readable finding sentences and dates, a slim stepper once done, a show/hide password button on sign-in, and a `TypedText` fix. `e2e/auditor.spec.js` now checks `/admin/users` and `/admin/recent-decisions` for 403 (the old `/admin/audit-log` no longer exists; the audit log moved to `/auditor/audit-log`). Unit tests 563 pass; all 29 browser tests pass.

### 2026-11-17: Frontend craft pass (unslop), locked decision 16 kept
The user asked to redo the whole frontend with the unslop skill (github.com/heydamir/unslop) so it reads as a production bank platform. Agreed in conversation: keep Pramaan purple and Outfit + Inter (purple becomes the one accent, surfaces neutral), keep light, dark and system only, keep login as the landing page (no public site), and do every screen in one pass. Frontend only: no route, role, API, wording-rule or scoring change. Details in `DESIGN_SYSTEM.md` 8.11. Tests: `tokens.test.js` updated (new pairs, neutral-surface check, the login-gradient check removed), new `styles/craft.test.js`, `e2e/theme.spec.js` background values updated and the glow check replaced.

### 2026-11-04: Stage 10 planned, Docker becomes Stage 11 (changes locked decisions 16 and 18, amends E-31)
Three automation items from the review window, agreed with the user in conversation. Docs only; no code written.
- **Intake desk:** the officer uploads a zip, folder or files; each file is read once (cached by hash, so no second OCR in Extraction), classified and assigned; an inventory shows received, missing (essential marked), extra, unrecognised, rejected and duplicate. Missing items: "Ask the applicant" or "Proceed anyway" (second click). Cross-case duplicate detection is **out of v1** (E-44).
- **Form filling (middle path, partly reverses E-31):** only name, date of birth, PAN, Aadhaar last four and address are filled from the PAN and Aadhaar cards, marked "from documents", empty when the cards disagree, confirmed by a tick. Loan amount, tenure, purpose, employment and income, mobile, email, residential status, loan-type fields and the relationship are claims entered by the applicant (on the link) or the officer; the system never decides the amount. Scoring is unchanged.
- **Applicant upload link:** a one-time, 7-day, revocable link bound to one officer (created by the officer, or the admin naming one). No applicant account, no status tracking in v1 (a coarse status may come later, never a score or outcome hint). The page shows the checklist; missing items are shown there, never in the Stage 9 message. Locked decision 16 ("no public page") is relaxed for this one page family only. Files stay on local disk behind a `FileStore` interface.
- **Bundle PDF split:** in the same stage, built last, behind `BUNDLE_SPLIT_ENABLED`; the stage can close without it.
- **Second click** on: create/send link, disable link, Send to the bank, Proceed anyway, send "Upload link" message, confirm split (plus the existing ones). None for type/person changes, split moves, drafts, filters, copying or downloading.
- **Numbering:** Stage 10 is this work; hardening and Docker is Stage 11 and stays last.

### 2026-11-03 (later): Auditor reshaped, admin reads and corrects cases (changes locked decision 9 again)

- **Auditor:** no case page, report, document, message or precedent. Sees Overview (counts, charts, cases per officer), a static Cases table (filters, CSV), the audit log (masked, filters, CSV) and the Users list (no buttons). Admin Users screen: the auditor's buttons are greyed out with no tooltip.
- **Admin:** reads every officer's case, documents included, with the same masking as the officer; Users → officer lists their cases. Sees Messages (sent only, no drafts, filters) and each case's own audit tab. The system-wide Audit log is the auditor's alone (the user's call, so the admin does not review their own actions). Home lists recently decided cases.
- **Correction:** after the officer has decided only, never over a hard rule, reason (15+ characters) and a second click, stored as a separate `admin_actions` row beside the officer's; the latest is the decision in force; the officer is told on the case and on Home; it never creates a precedent. May repeat; each is kept.
- **Reassign:** a case the officer has not decided (`draft`, `uploaded`, `stopped`, `awaiting_confirmation`) goes to another active officer, with a reason and a second click, so an officer still decides first. Disabling an officer with undecided cases warns and links to the list.
- **Schema:** migration 0012 adds `admin_actions`. See `SECURITY.md` D3 and D4.

### 2026-11-03: Read-only auditor role approved (changes locked decision 9)

- **Role:** `auditor`, UI label "Auditor". Strictly read-only. Reads our own database (cases, scores, decisions, overrides, audit log, precedents, users list, customer messages, counts, charts built in-app from Postgres). Sees **masked** applicant data and **no original documents**. No Grafana or Langfuse link or account. Customer messages are readable with recipient emails masked.
- **Creation:** only by `python -m app.api.users_cli create --role auditor`; exactly one active auditor (the CLI refuses a second). The admin API and Users screen cannot create, disable, enable or reset an auditor.
- **Admin creating an admin** stays allowed; the confirm dialog shows a red "You are creating an admin" warning (second click and audit row kept).
- **Unchanged:** officers see only their own cases (404 on others); an admin cannot disable themselves or the last active admin. (The auditor's case access and the admin's lack of it were changed later the same day; see the entry above.)
- **Schema:** migration 0011 widens the `users.role` check; no new tables.
- **Part 2 (after part 1 works):** aggregate fairness charts for the auditor, groups under 5 cases shown as "too few to show", never case-level rows, from a separate read-only route; the pipeline must still be unable to read the fairness table.

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
- [ ] Review window: additions and corrections collected by the user before Stage 11
- [x] Stage 10 Part A intake desk, Part B identity from the cards, Part C applicant upload link (built 2026-11-04; migrations 0014, 0015; not committed)
- [x] Stage 10 Part D several documents in one PDF (built 2026-11-18; migration 0017; not committed)
- [x] Stage 10b AI control for the admin (built 2026-11-18; migration 0018; not committed)
- [ ] Stage 11 Hardening, Docker and demo

---

## Stage 10 build notes (Parts A, B, C: 2026-11-04)

Built in the order A, B, C as asked; Part D was not started (the user said to go with A, B and C first). One migration per door: **0014** (documents: `role`, `role_source`, `classification`, `type_source`, `duplicate_of`, `duplicate_kind`, status `ignored`; `cases.loan_amount` and `tenure_months` nullable; `documents.applicant_id` now `ON DELETE SET NULL`) and **0015** (`upload_links`, case status `applicant_submitted`, outbox template `upload_link` and `link_id`). Both apply and roll back (`test_migrations`). Run `python -m app.db.migrate`.

**What exists**
- Part A: `intake/archive.py` (in-memory safe unpack), `intake/readcache.py` (read result saved next to the file, no raw text), `intake/inventory.py` (person assignment, inventory), `api/ingest.py` (the one upload step), `api/intake.py` (start a case from documents, bulk upload, inventory, correct a file, state employment, Proceed anyway, files zip), `api/filestore.py` (`FileStore` interface, local disk). UI: New case asks how to start; `BulkUpload`, `Inventory`, `IntakeDesk`, `AskApplicantDialog`.
- Part B: `intake/prefill.py` (five identity fields only), `api/identity.py` (offer and marks), `PUT /cases/{id}/form`, the tick in `ApplicationForm`, `Report.identity_from_documents` and an `evidence.source_note` on identity findings (E-48). Scoring, weights and bands are untouched.
- Part C: `api/links.py`, `api/public.py`, `api/ratelimit.py`; the `/u` applicant page, the Upload links page (officer and admin), the "From applicant" badge and status, `ApplicantRequest`, the "Upload link" message (`SendLinkDialog`). Help page sections added.

**Differences from the plan, and why** (none changes a locked decision)
1. **Token in the URL fragment and a header, 192 bits.** The plan said 128 bits or more; a path token would land in uvicorn's access log, which the plan forbids. `/u#token` never reaches a server.
2. **Read result is a JSON sidecar on the `FileStore`, not a database column,** and Extraction reuses it only if the hash and the application date match; it reads again when the model pass needs the page text (raw text is never saved) or when the date differs (E-59). The synthetic runs use `--no-llm`, so they never read twice.
3. **Photographs with two people are not matched** (no text to match, E-55); the officer drops each on a person. Folder or file names are not used to seat anyone. For education the PAN whose income papers are asked only from the co-applicant is the co-applicant, because a folder arrives alphabetically.
4. **Desk and applicant data live in `form_data`** (origin, request, request_locked, applicant_sent, intake, from_documents, identity_confirmed), not in new `cases` columns; only the status needed a constraint change.
5. **The applicant's request is not echoed back** by the public page ("can never read anything back except the checklist counts"); re-sending it replaces the old one until the officer saves the form.
6. **A link made from a case** ("Ask the applicant") is bound to that case; an open link creates the case when the request arrives (status `draft`, shown to the officer as "From applicant · applicant is still preparing"), and Send to the bank moves it to `applicant_submitted`.
7. **The identity values for the form (`/prefill`) are the owning officer's only** (admin 403), because they include the full PAN.
8. **One file covers many months** for bank statements and GST returns (E-57).
9. **`POST /cases/intake` takes an optional application date** so a dated (synthetic) case reads its files against the right date (E-59).
10. **Console sender prints the upload link in the terminal** (the v1 stand-in for email); the database keeps a placeholder (E-58).
11. Not added in 0014 because they belong to Part D or were not needed: `parent_document_id`, `page_from`, `page_to`, `documents.origin`, `class_confidence`, `class_source`, `source_archive`.

**A bug found on the way (E-56):** saving a corrected form deleted every uploaded file's row (foreign key cascade). It also affected "Correct details" on a fix-stopped case. Fixed in 0014 and covered by the desk tests.

**Exit criteria (Stage 10, Parts A to C; Part D has none built)**

| Criterion | Result |
|---|---|
| A zip, a folder and loose files give the same inventory | Same inventory for the clean personal dev case in all three forms (`test_a_zip_a_folder_and_loose_files_give_the_same_inventory`) |
| Inventory correct against the answer key for all 5 loan types | Type and person of every file match `answer_key.json` for one clean dev case per loan type; nothing missing, extra, unassigned or unrecognised once employment is stated. Education's two photographs are filed by the officer (E-55) |
| Unsafe archives refused, nothing written outside the case folder | `../`, absolute, symlink, password, zip bomb, nested zip, too many files, oversize: 17 unit tests, and over HTTP no row and no file is written and `intake_upload_refused` is audited |
| A file is read once | Counter test: 7 files read at the desk, 0 by Extraction; the case then scores the same total, band and status as the same case entered form first |
| Identity fields only from the cards; disagreement leaves the field empty; no claim filled; mismatch still hard-fails | Prefill unit tests; HTTP test that the stored desk case has no amount, tenure, purpose or applicants until given; the mixed-cards case (a stranger's PAN card among the applicant's documents) offers no name or date of birth and still stops at KYC with CM-KYC-03 |
| Scores, weights, bands and the 40-case results unchanged | `app.scoring.replay --verbose` output is **byte-identical** to the Stage 9 commit for the dev split (60) and the held-out test split (40), checked against a `git archive` of HEAD; `app.eval.run --split dev` gate passes. `app/scoring/` was not edited. The test split's `failed_rules_exact` is 0.775 (below the dev floor of 0.95); it was the same before this stage |
| A link works, stops at expiry and when disabled, same answer for an unknown token, never shows case data, token in no log or audit row | `test_upload_links.py` (15 tests) |
| Roles | Another officer 404, anonymous 401, auditor 403 on links; the admin reads the inventory and the zip but not the identity values (403) and writes nothing |
| Every second-click action needs it; the no-dialog ones do not | Component tests (`IntakeDesk`, `UploadLinksPage`, `ApplicantUploadPage`) |
| Browser | Playwright (`e2e/intake-desk.spec.js`): folder upload, inventory, identity from the cards, tick, submit, report note; and a link used from a fresh browser context with no sign-in, shown in the queue, disabled, then a dead end. Both pass in real Chrome. The five form-first loan-type specs use the unchanged path with one extra click |
| Migrations | 0014 and 0015 apply, roll back to 0013 with data present and apply again (`test_stage_10_migrations_...`). **The configured dev database was at 0013**; run `python -m app.db.migrate` |
| Lint, types, frontend | `ruff check`, `ruff format --check`, `mypy` (134 files), `eslint`, `prettier --check` clean; Vitest 220 of 220 |


## Stage 10 Part D build notes (2026-11-18)

Requested by the user on 2026-11-18 ("complete stage 10 part D as well"). Migration **0017**; run `python -m app.db.migrate`.

**What exists**
- `intake/bundle.py` (pure): `propose` classifies every page with the same local classifier, `validate` checks the officer's split, `cut` makes each piece's PDF with PyMuPDF; `intake/upload.py` has the bundle mode of the upload checks (more pages, every scanned page measured for blur, the bad page named); `intake/reader.py` keeps tables per page and can hand a piece its pages (`subset`) so nothing is read twice; `intake/pipeline.process_file` takes that read and marks a piece `from_bundle`.
- `api/ingest.py` was reshaped into a `Desk` class (state of one upload step on one case); `ingest()` and the new `confirm_split()` both use it. A multi-page PDF is looked at first: several documents means a stored row with status `bundle`; one document means the read is handed on and it is filed as before.
- `api/intake.py`: `PUT /cases/{id}/documents/{doc}/split` (the officer's edit, no dialog, audited), `POST .../split/confirm` (second click), `bundles` and `splits` in the inventory; proceed, submit and resume are refused with 409 while a bundle waits.
- UI: `BundleSplit` (a tick on each page where a document starts, a type for each, Confirm the split, Remove this PDF, Back to the proposed split), shown at the top of the inventory; the desk cannot continue while a PDF waits; the case page lists bundle and split rows.
- `python -m app.intake.evaluate_bundles --split dev [--mode digital|all] [--workers N]` measures the split.

**Measured (dev split, 60 bundles, all documents including photographs and scans):** page label accuracy **98.8%** (640 of 648), documents exactly right **98.3%** (527 of 536), 0 bundles refused; text-layer only: 100%. Every miss is an Aadhaar photograph whose title OCR did not read. The switch stays on (`BUNDLE_SPLIT_ENABLED=true`). The test split was not used.

**Differences from the plan, and why** (none changes a locked decision)
1. The bundle is read twice (to propose, then to cut) because raw page text is never saved between the two steps (E-54).
2. A piece's PDF metadata is not judged for tamper hints (E-61); the piece carries `from_bundle`.
3. `bundle` and `split` are document statuses rather than a separate table; the proposal and the officer's edit live in `upload_checks.bundle`.
4. The applicant's link also accepts a bundle (it goes through the same ingest) but only the officer can split it; the applicant sees it as "received".
5. The split screen is a tick per page, not draggable boundaries; moving a boundary is unticking one page and ticking another.
6. The applicant photograph is left out of the measurement (no title; E-62).

**Not done:** a Playwright run of the split screen; the cross-case duplicate check stays out of v1 (decision 19e).

## AI control build notes (2026-11-18)

Requested 2026-11-18 ("let the admin have an AI control page"); the user answered the plan with "keep keys in .env, go ahead with your recommendations". Built after Stage 10 Parts A to C, in the same working tree as Part D.

- **Migration 0018** (`ai_config_versions`, `ai_prompt_versions`, `ai_prompt_drafts`); run `python -m app.db.migrate`. Without it the API still starts (it logs a warning and uses the file defaults) and the page fails until migrated.
- **Backend:** `services/ai_config.py` (defaults, validation, snapshot bound per run, `ConfiguredRouter`, model probe), `api/ai_control.py` (admin only, `/api/v1/admin/ai/...`), `agents/prompt_check.py`, `prompts/*.md` split into editable and locked parts, `AgentContext.models()`, `Runner` binds the configuration to each run, `complete()` reads temperature and length per role, report `versions.ai_config`.
- **Frontend:** `pages/AdminAiControlPage` (tabs Models, Keys, Prompts, Settings), `components/ReasonDialog`, sidebar entry "AI control" for the admin, a `sliders` icon.
- **Differences from the suggestion:** (1) the "run the dev split before publishing" gate became a test of the prompt on a fixed synthetic sample with the real schema and guardrails, because the offline evaluation gate never calls a model; (2) the policy relevance threshold is not on the page (it sits in `rag.yaml` and decides which clauses are cited); (3) a model is tested only when it is new for a role, not at every save.
- **Locked decisions touched:** decision 11 (models) is now the file default, changeable by the admin within the catalogue; decision 9 (roles) gains an admin-only page. Wording for CLAUDE.md is left to the user.
- **Verified:** `test_ai_control.py` 31 tests, `AdminAiControlPage.test.jsx` 10 tests; see TESTING 7f. Not run: a real model call from the page and a Playwright run.

## Stage 9 build notes (2026-11-02)

- **Questions:** none blocked the build. Defaults taken (change on request): the branch contact lines are optional (`BRANCH_CONTACT_EMAIL`, `BRANCH_CONTACT_PHONE` in `.env.example`, empty = omitted); the **template wording is mine and awaits the user's review** (`app/notifications/templates.py`: three templates, general contact, contact soon, visit the branch, plus blank); only the officer who owns a message can edit, send or retry it; one migration holds the outbox, issue reports and the two contact fields.
- **Data (migration 0010):** `outbox`, `issue_reports`, `users.phone`, `applicants.email`. The customer email lives only in `applicants.email`, so it is never in `cases.form_data` and never reaches the pipeline or a model. Grants for `app_rw` and `migrator` are given when those roles exist.
- **Backend:** `app/notifications/` (`templates.py` fixed subject, footer and `compose`; `check.py` the content check and the issue check; `sender.py` the `Sender` protocol, `ConsoleSender`, `build_sender`), `app/api/messages.py` (templates, officer phone, draft, edit, delete of drafts and blocked messages only, send/retry, list, read), `app/api/issues.py` (file, own list, admin inbox, read, close). `create_app` takes an optional `sender`. `/admin/summary` also counts open issues and messages sent and failed (counts only). The case view returns the customer email masked; a corrected form that leaves it masked keeps the stored one.
- **Behaviour worth knowing:** the draft is created after confirm, override or stop (409 otherwise); the server composes the text (body, optional case reference, contact lines, fixed footer) and checks it on create, edit and send; a blocked or failed send is returned (422 or 502) with its status and audit row committed; sending needs `second_click: true`; a sent message is final. The check also blocks the customer's name, amounts, links and other email addresses, which the plan did not list (a phishing and leak guard). Audit rows never hold message text.
- **Frontend:** `MessageDialog` (two steps, the second shows the exact text), `CustomerContact` card on the case page, `SentItemsPage`, `IssuesPage`, `AdminIssuesPage`, sidebar links, an Open issues tile on admin Home, a customer email field on the application form, and new Help sections. Details in `DESIGN_SYSTEM.md` 9.1.
- **Measured:** results are in `TESTING.md` section 7d.
- **Not done / left for the review window:** real email or SMS (out of scope for v1); a browser (Playwright) test of the message flow, which is listed in the Stage 11 demo checks; the template wording review.

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

## Auditor role build notes (2026-11-03)

- **Migration 0011:** widens the `users.role` check to include `auditor`, and adds a unique partial index so only one *active* auditor can exist (the CLI checks first; the index holds under a race). The downgrade turns an auditor into a disabled officer with an unusable password, because `audit_log` is append-only and references users.
- **Backend:** `deps.py` (`auditor_only`, `case_reader` = officer or auditor, `any_reader`); `cases.py` read routes (list, read, status, audit, report) accept the auditor, who sees every case with masked name, DOB, address, PAN, phone, email and extracted fields; `display.scrub_for_auditor` masks identifiers and every part of the applicant names in the report and loan text. The document file route, the PDF export and every write stay officer-only (403 for the auditor). `api/auditor.py`: summary, charts, audit log (filter, paging), users, precedents, messages (recipient masked). `users.py` refuses disable, enable and reset of an auditor (403) and creating one (422). `users_cli --role auditor` refuses a second active auditor.
- **Part 2:** `monitoring/auditor_view.py` serves `GET /auditor/fairness`, aggregate only, groups under 5 cases as `too_few`, no totals. `REPORT_DATABASE_URL` (optional) gives it a read-only login.
- **Frontend:** auditor routes and sidebar (Overview, Cases, Messages, Precedents, Audit log, Users, Help); case workspace and report in view-only mode with a Read-only note and badge; BarChart component; Users screen shows the auditor with actions disabled and a red "You are creating an admin" warning plus a second click; auditor Help guide.
- **Verified:** `tests/test_auditor.py` (403 on every non-GET route found in the OpenAPI schema, other officers' cases readable and masked, officers still get 404, admin cannot manage the auditor, one-auditor rule in CLI and database, migration up and down, group view aggregate only), frontend tests (view-only case page for four statuses, routing by role, admin warning, sidebar, badge), Playwright `e2e/auditor.spec.js`.
- **Run it:** `cd backend && ../.venv/bin/python -m app.db.migrate` (0011), then `python -m app.api.users_cli create --email E --name N --role auditor`.
- **Choices to confirm:** the auditor gets no PDF export (it writes an audit row, and the role changes nothing); `GET /cases/{id}/messages` stays officer-only (messages are read in the Messages screen); Precedents was added to the auditor sidebar beside the five screens the user listed.

---

## Session handling build notes (2026-11-04)

- **Decided with the user:** access token 15 minutes, renewed silently while the person works; idle sign-out after 30 minutes with a two-minute "Still there?" warning; hard stop 12 hours after sign-in with a 15-minute notice; nothing typed is lost; banks need safety, so the server enforces every limit. Replaces the old single 60-minute token (changes only the token lifetime in `.env.example`; no locked decision changes).
- **Migration 0013:** `user_sessions`. **Run `cd backend && ../.venv/bin/python -m app.db.migrate` before using it.** Old tokens carry no session id, so everyone signs in once more after the update.
- **Backend:** `/auth/login` creates the session and sets the HttpOnly cookie; new `/auth/refresh` (rotation, 10-second second-tab grace, reuse closes the session), `/auth/ping`, `/auth/logout`; `deps.current_user` checks the session (revoked, idle, 12 hours). New settings `IDLE_TIMEOUT_MINUTES`, `IDLE_WARNING_MINUTES`, `SESSION_MAX_HOURS`, `REFRESH_GRACE_SECONDS`; `LOGIN_LOCK_MINUTES` unchanged (15).
- **Frontend:** `api/client.js` renews on 401 and retries once; `SessionGuard` (activity, ping, silent renewal, idle and 12-hour dialogs); `lib/drafts.js` (`useDraft`) used by both override dialogs and the problem report; the sign-in page shows why the session ended; the same person returns to the page they left.
- **Scope note:** instead of a re-login pop-up that replays the failed action, an ended session returns the person to the same page after sign-in with their typed text restored. Say if the pop-up is wanted.
- **Verified:** see the commit summary for the test results.

---

## Review-window additions (2026-11-03)

- **Report:** an "At a glance" card above the Summary (score ring, top 3 reasons ranked hard fail, cap, biggest point loss, and the next step; all taken from existing findings, nothing computed in the UI). The Policy citations block has a text search and a "cited by stage" filter.
- **Admin officer view** (`/admin/users/:id`, `GET /admin/users/{id}/activity`): case counts by status and band, confirm and override counts, precedents proposed by status, last sign-in, and the 10 latest case numbers with status. No applicant data, so the least-privilege rule (admin has no case access) is unchanged.
- **User menu** top right, beside the theme toggle: name, email, role and Sign out (asks first). No separate Profile page. The sidebar keeps only navigation.
- **Auditor role:** approved by the user 2026-11-03 and built next (see the decision below).
- **No schema change** in this batch, so no migration to run.

---

## Auditor and admin reshape build notes (2026-11-03, later)

- **Migration 0012:** `admin_actions` (case, admin, previous and final decision, reason, second click time); grants for `app_rw`, `report_ro` and `migrator` when those roles exist. Downgrade drops it.
- **Backend:** `deps.case_reader` is now officer or admin (the auditor gets 403 on every case route). `api/decisions.py` (decision in force, hard-rule check, override block), `api/admin_cases.py` (override, reassign, recent decisions, sent messages), `api/auditlog.py` (the audit query with masking, CSV with formula-safe cells; used by the auditor). `api/auditor.py` rewritten: summary, charts (cases per officer), `/auditor/cases` and CSV, audit log and CSV, users with last sign-in; `/auditor/messages` and `/auditor/precedents` removed. `users.py`: `open_cases` per user, the officer page lists every case. `cases.py`: admin reads every case and document, `admin_actions` and `decision_in_force` in the case and report, `admin_corrected` in the list.
- **Frontend:** sidebars and routes per role; shared `AuditLogPage`; `AuditorCasesPage`; `AdminMessagesPage`; `AdminCorrection` (change the decision, reassign) and `AdminChanges` (the card shown to admin and officer); case workspace in an Admin view; Home notice for the officer; Help guides for admin and auditor rewritten. Removed: auditor messages, precedents and case-page pages.
- **Verified:** backend `test_auditor.py` (403 on every route outside `/auditor`, no case route for the auditor, table content and CSV, audit log filters and masking), `test_admin_cases.py` (reading, override rules, hard-rule refusal, reassign rules, lists, audit log), `test_migrations.py` (0012); frontend tests for each screen; Playwright `auditor.spec.js` and `roles.spec.js` updated.
- **Run it:** `cd backend && ../.venv/bin/python -m app.db.migrate` (0012).
- **Not built:** an admin UI test in the browser that corrects a case end to end (the browser test database seeds a case without a report; the API and component tests cover it).

---

## Soft gate before the applicant has sent (2026-11-19)

- **Decision (user, 2026-11-19):** files from an upload link are stored as they arrive (unchanged), but the officer may not go on to the form or submit while the applicant has an open link and has not pressed Send to the bank, unless they choose "Continue anyway" behind a second click. Option 2 of three offered (keep as is, soft gate, hard gate). Part 1 and Part 2 of the inbox and email plan were **not** built.
- **Backend:** `ingest.waiting_for_applicant` (link for the case open, not sent, no acknowledgement); inventory field `waiting_for_applicant`; `POST /cases/{id}/intake/continue-unsent` (second click, owner only, one audit row `continued_before_applicant_sent`, stored as `form_data.intake.unsent_ack`); `POST /cases/{id}/submit` returns 409 while waiting. No migration.
- **Frontend:** `IntakeDesk` shows a note and a "Continue before the applicant has sent?" dialog; "Proceed anyway" for missing items ends in the same dialog when the applicant has not sent. Help page line added.
- **Edge case:** E-72.

---

## Applicant page after Send and the expired-link warning (2026-11-19)

- **Decision (user, 2026-11-19):** after the applicant presses Send to the bank the page stays on the thank-you screen with the reference, also after a refresh; the applicant cannot see the checklist or add files until the officer asks for more; when the officer asks, the page shows what is submitted and what is still needed. If the link has expired or been switched off while the applicant still owes documents, the officer is warned with a button to the Upload links page. The inbox and email plan (Parts 1 and 2) is still **not built**.
- **Backend (no migration):** `public._view` returns `reference`, `more_requested` and no checklist once sent; `_accepting` refuses files and a changed request after the first send until `form_data.more_requested`; Send again is idempotent; a second send keeps the reference and clears `more_requested`. `links._reopen_for_more` (called by Ask the applicant) sets `more_requested`, clears `intake.unsent_ack` and writes `applicant_more_requested`. `ingest.waiting_for_applicant` treats a pending request for more as waiting. The case payload carries `more_requested`.
- **Frontend:** `ApplicantUploadPage` (thank-you from the server state, "Send the rest of your documents" when asked for more), `LinkWarning` (case page, officer only) and an Upload links page filtered by `?case=`.
- **Edge cases:** E-73, E-74, E-75.
- **Fix (2026-11-19):** saving the application form after the applicant pressed Send to the bank erased `form_data.applicant_sent` (and `more_requested`), because `cases._form_data` keeps only `KEPT_FORM_KEYS`. Submit was then blocked with "has not pressed Send to the bank yet" and the applicant's link showed the upload form again. Both keys added to `KEPT_FORM_KEYS`; test `test_saving_the_form_after_the_applicant_sent_keeps_the_send` in `test_upload_links.py`.

---

## State-aware Ask dialog and breadcrumbs (2026-11-19)

- **Decision (user, 2026-11-19):** the Ask the applicant dialog says what really happens for each link state, an expired link can be reopened (same address) or replaced, a switched-off link only replaced, and deep pages get breadcrumbs. Built, not committed. Inbox and email (Parts 1 and 2) still **not built**.
- **Backend (no migration):** `POST /cases/{id}/ask-applicant` takes `reopen` (expired link: extend it by the standard period and reuse it, audit `upload_link_reopened`; switched-off: 409; no link: creates one). `GET /cases/{id}/link` prefers an open link over a newer ended one.
- **Frontend:** `AskApplicantDialog` (fetches the case link, `modeOf`), `Breadcrumbs` on the case page, the admin officer page and the filtered Upload links page.
- **Edge case:** E-75 updated.

---

## Ask for more says what is needed (2026-11-19)

- **Decision (user, 2026-11-19):** a request for more must state what is needed, as ticked document kinds with counts and/or a short note; the applicant's page shows only that. Built, not committed. Inbox and email (Parts 1 and 2) still **not built**.
- **Backend (no migration):** `POST /cases/{id}/ask-applicant` takes `items` (`{type, count}`, types from the document list) and `note` (max 200, screened by `check_request_note`); after the applicant has sent, at least one is required (422), and nothing is written on a refusal. `form_data.more_requested` is `{at, items, note}`. The public link read returns `requested` and no general checklist while it is open (also not in the upload answer). The audit row records the items and note.
- **Frontend:** `RequestedItems` (count box can be emptied while typing), `AskApplicantDialog` (fields, "Your request is saved" without re-showing the address), `ApplicantUploadPage` ("Your loan officer has asked for"), `ApplicantReview` (what was asked).
- **Edge case:** E-74 updated.

---

## Notifications Part 1 build notes (2026-11-19)

- **Scope (user, 2026-11-19):** notifications and email in three parts; **only Part 1 (the in-app inbox for officers and admins) is built.** Part 2 (real email, which needs decision 17 lifted: provider, candidate receipt, staff emails, recipient allow-list) and Part 3 (hardening and close-out) are **not started** and wait for the user. Decisions 17 and 9 are unchanged. Built, not committed.
- **Migration 0019** (run `python -m app.db.migrate`): table `notifications` (kind CHECK list of 13, fixed `title` and `body`, nullable `case_id` with `ON DELETE CASCADE`, nullable `case_ref` with the `CASE-YYYY-NNNN` check, `read_at`; index on `(user_id, read_at, created_at DESC)`; grants for `app_rw` and `migrator`, none for `report_ro`) and `upload_links.expiry_notified_for`. Downgrade drops both.
- **Backend:** `notifications/inbox.py` holds `KINDS`, the one reviewable table (recipient, event, title, body, click target) and `notify`, `notify_admins`, `notify_owner`, `sweep_expiring_links`. `notify` runs in the caller's transaction beside `write_audit`, takes a kind (and one variant, for the second Send) and **never free text**; `check_notification_text` is the safety net (raises in dev and tests, logs and drops in production; `inbox.configure` is set in `create_app`); the insert only matches users whose role the kind names, so the auditor is never a recipient. `api/notifications.py` (`case_reader`, so 403 for the auditor): `GET /notifications` (unread filter, `limit` and `offset`), `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`; another person's id is a 404; no delete.
- **Triggers wired:** `api/public.py` (request arrived, Send and Send again), `agents/graph.py` (run ready, run stopped on a fix, in the transaction that sets the status), `api/admin_cases.py` (correction, reassignment), `api/admin.py` (precedent added or not added), `learning/proposal.py` (precedent pending or held, every active admin), `api/issues.py` (issue filed, every active admin), `api/messages.py` (message failed), and the link-expiry check on read in `api/notifications.py` (no scheduler, no Celery, no Redis).
- **Deviation from the brief, on purpose:** `notify(conn, user_id, kind, case=None, variant=None)` has no `title` or `body` argument. The titles come from the table by kind, so a caller cannot build one from a name or a number. "Sent files or pressed Send" is one trigger (the Send); single uploads are not announced (noise). A failed run (`pipeline_failed`) is not in the brief's list and is not notified; say if it should be.
- **Frontend:** `UnreadProvider` (count on sign-in, every 60 s while visible, on focus; keeps the last count on failure; nothing for the auditor or after sign-out), `NotificationBell` (a button named "Notifications, N unread", left of the theme toggle), an `Inbox` item with a badge in the officer and admin sidebars, `InboxPage` at `/inbox` and `/admin/inbox` (unread and all tabs, mark read, mark all read, open the case, show more, empty and error states), the `bell` icon, Help sections for the officer and the admin.
- **Verified:** see the summary at the end of the session for the exact counts (backend `test_inbox.py`, frontend tests, ruff, mypy, eslint, prettier).
- **After first review (2026-11-19):** the inbox gained filters (`group` and `case` query parameters, `groups` in the answer; `inbox.GROUPS`), the row hover now fills the whole row and the tabs line up with the heading; a problem report's optional case reference must be the officer's own (E-85), a badly formed one is explained in plain words, and the thank-you note goes after 6 seconds or when a new report is started.
- **Edge cases:** E-76 to E-85. **Docs:** PRD FR-43 to FR-46 (section 9.10), DATABASE 4c, SECURITY 4e, DESIGN_SYSTEM 13, TESTING 7g.
- **Left for Parts 2 and 3:** real email, a browser (Playwright) run of the inbox, the full backend run, the docs sweep and the demo script.

---

## Notifications Part 2 build notes: real email (2026-11-19)

- **Decisions (user, 2026-11-19):** decision 17's "no real email in v1" is lifted; provider Resend, reached over **SMTP** (chosen over Resend's own API: no new package, Mailpit locally, any provider by settings); no verified domain yet, so `onboarding@resend.dev`; allow-list plus a demo redirect (the suggestion taken); contact request and upload link really send; **no** applicant receipt; staff "new notice" emails with a per-person switch; an email when an account is created or a password is reset, **never with the password**. Built, not committed.
- **Migration 0020** (run `python -m app.db.migrate`): `email_outbox`, `users.notice_emails`, `outbox.delivery`.
- **Backend:** `notifications/sender.py` (`SmtpSender`, `GuardedSender` with allow-list and redirect, `check_email_settings` at start-up, `build_sender(settings)`); `notifications/mailer.py` (fixed texts, `queue_notice_email` with a 30-minute gap and the person's choice, `queue_account_email`, `deliver_pending` with row locks, three tries and audit, `run_worker` started by the app every `EMAIL_WORKER_SECONDS`); `inbox.notify` queues the notice email; `api/users.py` queues account and reset emails; `api/messages.py` records `delivery`; `api/preferences.py` (`GET`/`PUT /me/preferences`, officer and admin, audited). Settings: `SMTP_*`, `EMAIL_FROM`, `EMAIL_ALLOWLIST`, `EMAIL_REDIRECT_TO`, `STAFF_EMAILS_DEFAULT`, `EMAIL_WORKER_SECONDS`, `NOTICE_EMAIL_GAP_MINUTES` (`.env.example`). Tests set `EMAIL_WORKER_SECONDS=0` and send by calling `deliver_pending`.
- **Frontend:** the user menu's *Email me about new notices* checkbox; Sent items shows how a message went out; Help lines.
- **Not emailed (by design):** the auditor; a password; case details in staff email; an account made from the command line (the operator typed its password).
- **Turn it on:** set `NOTIFICATION_SENDER=smtp` in `.env` and restart the backend. A wrong setup stops the start with the variable named.
- **Edge cases:** E-86 to E-90. **Docs:** PRD FR-47 to FR-51 (9.11), DATABASE 4d, SECURITY 4f, DESIGN_SYSTEM 13, TESTING 7h, CLAUDE.md decision 17 and status.
- **Left for Part 3:** a real send checked by hand against Resend, the browser run, the full backend run, the docs sweep, the demo script.

## Stage 11 build notes: hardening, Docker and demo (2026-11-21)

- **Asked for by the user** (2026-11-21), with three choices (decisions log): our own judge runner instead of RAGAS and DeepEval, models-off results run here with the real-model run left to the user, Langfuse not self-hosted.
- **Security pass:**
  - **Retention job** (`app/db/retention.py`, migration 0024 `cases.bureau_removed_at`). It runs daily in the app and by hand.
    - Bureau values leave rule results and report findings after six months.
    - A decided case's run checkpoints go too.
    - Old staff email goes after 90 days.
    - Each run that changes something writes one audit row with counts (E-103, E-105).
  - **Log guards.** A new test ran a whole case at DEBUG and found that pdfminer prints raw document text (names, PAN, Aadhaar, account numbers) and that LiteLLM prints model replies. Those libraries are now held at WARNING, and the formatter replaces identifier patterns in every text field (E-104). Normal INFO runs never showed it.
  - **Log path.** `make backend` wrote logs to `backend/logs`, where Promtail never looked; they now go to the repository's `logs/`.
  - **Audit coverage.** A test lists all 72 write routes. Each one audits, names the code that does, or is on the short list of routes not audited by design.
  - **Secrets.** A git-history secret scan found nothing, and `.env` was never committed.
- **Dashboards:** Grafana row 6:
  - applications today and per day (`lc_new_cases_total` by origin);
  - time to decision, median and 90th percentile (`lc_time_to_decision_seconds`, timed from case creation);
  - override rate, as a number and over time;
  - staff email by outcome (`lc_emails_total`).

  Tokens and cost per case and latency per agent were already there.
- **Releases:** `python -m app.release --tag vX.Y.Z` writes `docs/releases/<tag>.json` and prints the `git tag` command for the user. The manifest holds:
  - the commit, the migration head, and the rules version and checksum;
  - the policy versions in force, from the database or the files;
  - the models per role (provider ids), the AI configuration version and the prompt versions;
  - the local models.
- **Judge runner** (`python -m app.eval.judge`): the judge model grades the stored reports of a models-on run. It checks how faithful the summary is to the report's own result, findings and clauses, and whether each Policy finding is supported by its cited clause. Everything is masked first, and code-written summaries are skipped. A `judge` block in `thresholds.json` can set floors (none yet: they wait for the first real-model baseline, OI-7).
- **Final test split (40 held-out cases), recorded and not tuned on** (`docs/baselines/test-final.json`):

  | Run | Band | Stop stage | Total score exact | Failed rules exact | Mean score error | Other |
  |---|---|---|---|---|---|---|
  | Code-side (`app.eval.run --split test --allow-test`) | 100% | 100% | 95% | 77.5% (below the dev floor of 95%) | 0.27 | hard-rule integrity 100% |
  | Pipeline, models off (`app.agents.run --split test --allow-test --no-llm`), real files through intake and OCR | 97.5% (39/40) | 100% | | | 2.0 points over 21 scored cases | 40/40 completed; 0 unverified; 21.9 s per case |

  The differences, for the user to judge (fixing them must be checked on the dev split, never tuned on these):
  - Seven cases that stop for a missing identity document also list CM-KYC-10 as failed.
  - SYN-BL-T09 and SYN-HL-T09 pass CM-INC-12 where the key expects a fail.
  - SYN-HL-T01, in the pipeline only: an OCR reading of a payslip gave a net-pay mismatch, the tamper rule capped the case to refer, and the key says approve.
- **Real-model run (the user's, with their keys):**
  ```
  python -m app.agents.run --split test --allow-test --out test-models.json
  python -m app.eval.judge --split test --allow-test
  ```
  Paste the two summaries back to record them here; they also give the OI-3, OI-4 and OI-7 baseline.
- **For people:**
  - `docs/DEMO.md`, a 25-minute script with the case for each scene (scenes 1, 2, 5 and 6 follow the browser tests `intake-desk`, `roles`, `inbox` and `knowledge-base`);
  - a new README (Docker, no Docker, tests, documents);
  - `.env.example`, which now lists every setting (seven were missing) with up-to-date comments.
- **Packaging:**
  - `requirements.lock` holds the exact versions, frozen from the working venv.
  - The `Dockerfile` builds one image: the frontend built with Node 22, then Python 3.12 slim with CPU torch. It generates the synthetic data, bakes in the embedding, reranker and OCR models (offline at run time) and runs as a non-root user with one worker.
  - `docker/entrypoint.sh` waits for the database, then migrates, seeds and re-indexes; each step is safe to repeat.
  - `docker-compose.yml` brings up app, Prometheus, Loki, Promtail, Tempo and Grafana, with the profiles `local-db` and `mail`; ports are bound to 127.0.0.1.
  - Makefile: `make up`, `make down`, `make stack-logs`.
- **Docker, checked on this machine (2026-11-21).** The image built from the repository; that also caught a bug in my warm-up script, now fixed. It is 4.76 GB, mostly CPU torch and the local models. The stack ran as a separate project (`pramaan-check`) with the `local-db` profile and a test-only override (local database, models off, console email, Langfuse off), so the user's Neon database was not touched. Results:
  - The app turned healthy after it migrated, seeded (69 clauses, 100 answer keys) and indexed (67 embedded) by itself.
  - `/` served the frontend, `/api/health` answered, a sign-in worked, and a new case moved `lc_new_cases_total`, which Prometheus scraped from `app:8000`.
  - Grafana provisioned the "Loan Copilot" dashboard.
  - Loki and Tempo were ready, and a log line reached Loki with its level label and the PAN replaced by `<PAN>`.
  - `SYN-PL-D02` and `SYN-PL-D09` ran through the pipeline inside the container with the baked-in models and no network downloads, and both matched their keys.
  - The test stack and its volumes were removed afterwards.
  - **Not checked:** a fresh `git clone` on another machine, the `mail` profile, and the stack against Neon (the container migrates the database it is given, so the user starts it against Neon when ready).
- **To do on Neon:** `python -m app.db.migrate` (0022 to 0024).

## Notifications Part 3 build notes: hardening and close-out (2026-11-21)

- **Asked for by the user** (2026-11-21) together with Stage 11.
- **Email queue (`notifications/mailer.py`, migration 0023):** one email per transaction. Before, a whole pass (up to 20 rows) was one transaction while the emails went out, so one unexpected error rolled back the outcomes of emails already sent and they went again on the next pass (E-101). Any unexpected error now counts as a failed try (only its type is kept); a failed row waits 1 minute, then 5 minutes (`next_attempt_at`), so a short outage no longer uses all three tries in a minute (E-102). Delivery is at least once.
- **SMTP sender:** the recipient is checked before a connection is opened (one plain address; no line breaks, commas or angle brackets) and any other error becomes a plain `SendError`, so a customer message fails cleanly instead of answering 500.
- **Metrics:** `lc_emails_total{kind,status}` for the Stage 11 dashboards.
- **Browser test:** `frontend/e2e/inbox.spec.js` (problem report to the admin's inbox, count, Mark read, click through, notice-email choice kept, no bell for the auditor).
- **Docs:** PRD FR-59 and status, SECURITY 4f, DATABASE (`email_outbox.next_attempt_at`), TESTING 7g and 7h, EDGE_CASES E-101 and E-102; the CI comment no longer names `app.eval.judge`.
- **Left to the user:** a real send to Resend, `python -m app.notifications.email_check --to ADDR` (it needs the key in `.env`).
- **To do on Neon:** `python -m app.db.migrate` (0023).

## New case page redesign (2026-11-19)

- Display only, asked for by the user: numbered steps, card radios with icons (`ChoiceCard`), and a "Documents needed" rail for the chosen loan (`RequiredDocsPreview`). Details in `DESIGN_SYSTEM.md` 8.14.
- `GET /meta/loan-types` now also returns `documents` per loan type from the rules file (read only; no rule, score or route change).
- Tests: `NewCasePage.test.jsx` (4), `test_api.py::test_case_form_rules_follow_the_loan_type` extended. The e2e selectors (radio names, button names) are unchanged.
- **Fix found on the way (upload buttons):** "Take a photo" showed on laptops and "Choose a folder" on phones, because the shared `.btn` rule loads after `BulkUpload.css` and won the tie. The rules are now `.btn.bulk-camera` / `.btn.bulk-folder`, and a phone is `(hover: none) and (pointer: coarse)` so a touchscreen laptop counts as a computer. Checked in Chrome (desktop and Pixel 7 emulation); guarded in `BulkUpload.test.jsx`.

## Knowledge base build notes (2026-11-21)

- **Database (migration 0021):** `policy_documents` gains `status` (draft, scheduled, active, superseded, retired), `body`, `origin`, who published or retired it and why; `active` becomes a computed column; partial unique indexes allow one active, one scheduled and one draft per loan type; a trigger keeps published versions (no delete, no text change, retired stays retired). New `policy_drafts` (the working text, saved even with errors) and `precedent_uses`; precedents gain `paused` and `retired`. Downgrade tested to the base.
- **Pure code (`rag/policy_admin.py`):** upload conversion (`.md`, `.txt` with a Windows-1252 fallback, `.docx` through the zip and its XML with DTDs refused), auto-fix (formatting only), the check (errors, warnings, fixes with line numbers), clause comparison word by word, rule-number drift (lakh, crore, percent and years understood; a number is reported only when the old text mentioned it), old-format import (Markdown, numbered and all-capital headings; IDs reused by title), and one-clause edits that leave the rest of the text unchanged.
- **Service (`rag/policy_store.py`) and API (`api/knowledge.py`, 23 routes):** drafts, clause edits, the retrieval check (the dev evaluation questions for that policy, in force against draft), publish or schedule, restore, retire, compare, search, index health, re-index, evaluation, learnings. `rag/versions.py`: the in-force set, scheduled versions switched in on the first read after their date under one advisory lock, and the per-run binding. `Runner` binds the policy versions beside the AI configuration; `PolicyRetriever` and the report's version stamp read the bound set.
- **Import (`rag/index.py`, `rag/reindex.py`):** a file is imported only when its label sorts after every label in the database; a file-imported active version may still be edited under its label (E-20); a screen-published or older version is never touched or made active again. A clause whose text is already stored copies that vector (two shipped clauses share text, so a fresh index embeds 67 clauses for 69). The command line still refuses and rolls back when a rule would lose its clause; `seed_policy` uses the same import without embeddings.
- **Frontend:** `KnowledgeBasePage` (Policies with Read, Change and History; Learnings; Search and index) and `PolicyLibraryPage` for officers; components `PolicyList`, `PolicyReader`, `PolicyEditor`, `CheckReport`, `ClauseDiff`, `PolicyHistory`, `LearningsPanel`, `PolicySearch`, `IndexTools`; `lib/policy.js`; icon `book`; `ReasonDialog` gained `blocked`. Help has an admin section and an officer section.
- **Choices made while building (please review):** (1) while a version is scheduled, publishing another for that loan type is refused (the scheduled one would otherwise replace a newer one on its date), E-95; (2) a retired version's text can still be restored into a draft; (3) the retrieval check is required before publishing, and a lower score is a warning, not a block; (4) a change to the common policy pauses matching precedents of every loan type; (5) `rag/*` and `learning/maintenance.py` are exempt from the line-length rule like `api/*` (long messages and SQL).
- **Measured:** backend `test_knowledge_base.py` 48 passed; `test_rag.py`, `test_rules_and_policy.py`, `test_migrations.py` 38 passed after the change; frontend 780 tests passed (vitest), lint and Prettier clean, build clean; browser test `knowledge-base.spec.js` passed in Chrome. The files that run whole cases through the runner and graph (`test_api`, `test_pipeline`, `test_learning`, `test_policy_agent`, `test_inbox`) 88 passed; `test_admin_cases`, `test_agent_units` and `test_ai_control` passed in a full run that was stopped at about 12% because it was too slow against the remote test database. The rest of the suite (email, notifications, intake, scoring, uploads and others) was not re-run; this change does not touch those modules.
- **To do on Neon:** `python -m app.db.migrate` (0021). No re-index is needed: existing versions keep their rows; their Markdown is filled in the next time `python -m app.rag.reindex` runs (until then it is rebuilt from the stored clauses).


## Post-demo cleanup (2026-11-21)

Small fixes noted while preparing the trainer demo (2026-11-20), done at the user's request. No scoring, rule or route change.

- **Intake desk wording:** after the officer asks for more, the desk, the confirm dialog and the submit refusal say "You asked the applicant for more files and they have not sent them yet" instead of "has not pressed Send" (the applicant had already sent once). `ingest.asked_for_more` / `unsent_message`; the inventory carries `asked_for_more`. Help updated.
- **3C strip, Collateral:** says where collateral is checked instead of "Not scored in v1": home and vehicle "Checked in Policy fit" (loan-to-value limit), education "Checked in Policy fit" (collateral above a set amount), personal and business "Not checked" (no collateral rule). Words only (`collateralNote` in `lib/conditions.js`), no number. `DESIGN_SYSTEM.md` 8.6.
- **LLM call log (migration 0022):** `llm_calls` gains `stage` and `role`, so the Supervisor's rows (no stage row, null `stage_run_id`) can be told apart. The judge model's calls are now written (`stage = decision`, `role = judge`) and so is the precedent summary at an override (`stage = precedent`); a run that writes its logs again keeps the `precedent` rows. Old rows get the stage of their stage row.
- **Judge input masked (found on the way):** the judge was given the raw report JSON, which can hold names and document evidence; it now gets the same masked facts the Decision writer saw, and the claim is masked again.
- **Leak check:** `find_leaks` / `assert_masked` now also catch phone and account numbers that stand alone (not inside a word, a hex id or a UUID). The shipped policy files pass the policy check unchanged.
- **Docs:** `app/eval/run.py` docstring no longer names `app.eval.judge` (it does not exist; no RAGAS or DeepEval suite is built yet, see the open question below). `AGENTS.md`: Supervisor (checklist in code, model writes a short briefing only, no retries or report assembly), Extraction (model only for missing fields or unknown types; OCR is RapidOCR first, then PaddleOCR, then Tesseract), KYC (model explains, code decides every match). Status table and `CLAUDE.md` show Stages 9 to 10c as committed.
- **Question answered by the user (2026-11-21):** RAGAS and DeepEval are replaced by our own judge runner, built in Stage 11 (see the decisions log).
- **Measured:** frontend 783 tests passed (3 new), lint, Prettier and build clean; ruff, ruff format and mypy clean. Backend: the new and changed tests in `test_pipeline`, `test_learning` and `test_upload_links` passed (6), and `test_observability`, `test_migrations` (0022 up and down), `test_agent_units`, `test_intake` and `test_knowledge_base` passed (115). The rest of the backend suite was not re-run here; CI runs it.
- **To do on Neon:** `python -m app.db.migrate` (0022).
