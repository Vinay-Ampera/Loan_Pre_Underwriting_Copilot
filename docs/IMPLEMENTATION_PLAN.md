# Implementation Plan

Twelve stages. Each stage ends with something runnable and a test gate. Do not start a stage until the previous exit criteria pass. No dates yet (deadline not fixed); effort is S (≈1 day), M (2-3 days), L (4-6 days) for a solo developer.

Trainer approval of the documents comes first. Nothing below starts before that.

```
1 Foundation   2 Intake & parsers   3 Rules & scoring   4 RAG & Policy
5 Agent pipeline   6 API & frontend   7 Learning, eval, observability
8 UI revamp (Pramaan)   9 Customer notifications   10 Intake desk & applicant link
11 Hardening & Docker   12 Post-demo features
```

Stage 12 (post-demo features) was added on 2026-11-25, after the trainer and CEO demos. Docker was built in Stage 11; Stage 12 adds no new service and keeps the `Dockerfile` and `docker-compose.yml` working, with every new setting in `.env.example` (locked decision 18, reworded by the user on 2026-11-25).

Stages 8 and 9 were added on 2026-11-02 (the old Stage 8 is now Stage 11). Stage 8 was built first (2026-11-02). After both, there is a **review window**: the user collects additions and corrections, and they are done before Stage 11 starts. Docker is always last.

Stage 10 (intake desk and applicant upload link) was added on 2026-11-04 from the review window; the hardening and Docker stage is now **Stage 11**.

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
3. Model-judged evaluation; full run on dev and test; GitHub Actions gate on PRs with metric thresholds. (The judge runner `app.eval.judge` was built in Stage 11 (RAGAS and DeepEval were replaced by this runner, user decision 2026-11-21).)
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

## Stage 10: Intake desk and applicant upload link (L), planned 2026-11-04, Parts A to C built 2026-11-04, Part D built 2026-11-18

**Goal:** the officer no longer labels files one by one or types the identity fields, and an applicant can send documents through a one-time link. The pipeline order, scoring, weights, bands and the human confirmation do not change. Everything here happens **before** Submit and ends in the same `Submission` the pipeline already reads.

**Status (2026-11-18):** Parts A, B, C and D are built and tested. Part D (bundle PDF split, built 2026-11-18): migration 0017, `intake/bundle.py`, the split screen (a tick on each page where a document starts), 98.8% page-level label accuracy measured on the dev split, the switch on by default (see `TESTING.md` 7e and `PROGRESS.md`). Differences from this text are listed in `PROGRESS.md` ("Stage 10 build notes"): the token rides in the URL fragment and a header (192 bits), the read result is a sidecar file, two photographs are filed by the officer, and the identity values for the form are offered to the owning officer only. The exit-criteria results are in the same notes.

Decisions behind it are in `PROGRESS.md` (2026-11-04) and `EDGE_CASES.md` E-31 (amended) and E-42 to E-54. Build in this order; each part is usable on its own, and the last part may be cut.

**Part A: Intake desk (bulk upload and inventory)**
1. **Read once, early.** The upload step runs the existing read (text layer or OCR), classification and local field extraction as soon as a file is accepted and caches the result against the file hash. Extraction reuses the cache and does not read the file again (no second OCR). If a cache entry is missing, Extraction reads the file as it does today.
2. **Bulk input.** One request accepts a zip, a folder (browser folder picker) or many files. `intake/archive.py` unpacks safely: no path outside the case folder, no symlinks, nested zips only one level, file-count and total-size limits, junk names (`__MACOSX`, `.DS_Store`, `Thumbs.db`) skipped, allowed extensions only, a zip bomb stopped by a size-ratio and byte budget while reading. Every inner file then goes through the normal upload checks (signature, size, password, active content, blur, crop). Original names are metadata only.
3. **Classify and assign.** Each file gets a document type (existing classifier, local) and a person (primary or co-applicant): the first KYC set is the primary; a second distinct PAN proposes the co-applicant; other documents are matched to a person by name and PAN with the existing matching code; no match means "unassigned" and the officer picks.
4. **Inventory screen.** One table per person: **received** (type, person, file, which checklist item and which fields it feeds), **still missing** (essential items marked), **extra** (not needed for this loan), **unrecognised**, **rejected** (with the reason), and **duplicate, ignored** (with the file it matches). The officer can change a type or person from a dropdown (no confirmation needed; it is easy to change back).
5. **Gate.** Missing items offer two actions: "Ask the applicant" (Part C) or "Proceed anyway" (second click; the pipeline then stops with its normal fix-type result if a required document is absent). The existing Submit gate (E-29) still blocks submission without the KYC documents.
6. **Duplicates in bulk (E-43, E-44).** Same hash anywhere in the case is ignored and listed; same content key (type, person, period) is ignored; same key with different amounts is kept and raised as `DUPLICATE_CONFLICT`; duplicates never fill a checklist slot (E-03). A cross-case duplicate check is **out of v1**.

**Part B: Identity fields filled from documents (partly reverses E-31)**
7. After the inventory, the form opens with **name, date of birth, PAN, Aadhaar last four and address** filled from the PAN card and the Aadhaar card, each marked "from documents". If the two disagree on a field, it is left empty with a note (E-47). The officer must tick "I confirmed these" before Submit (a tick, not a dialog).
8. **Claims stay manual:** loan type, loan amount, tenure, purpose, employment type, employer or business, declared income, months in job, experience, mobile, email, residential status, every loan-type field and the co-applicant relationship are never read from a document. They come from the applicant's request (Part C) or the officer.
9. **Scoring does not change.** The report marks a form value that was taken from a document as "from document, not an independent check" next to the match finding; a test shows a PAN card that disagrees with the Aadhaar card still fails the identity rule.

**Part C: Applicant upload link**
10. **Link.** The officer (or the admin, naming an officer) creates a link for one officer. Token: at least 128 bits, random, stored only as a hash, shown once for copying. Valid for **7 days** by default (`UPLOAD_LINK_DAYS`), an officer can extend it, and the officer or admin can **disable it at any time** (second click). The link opens a case-independent page; the case is created when the applicant sends the request.
11. **Applicant page** (public, no account, no sign-in, only this one page family): step 1 the request (loan type if the officer did not preset it, amount, tenure, purpose, employment type, declared income; all marked as the applicant's own statement); step 2 a live checklist for that loan type and file upload (zip, folder or files, same safe unpacking); a warning when items are missing, but sending is allowed ("incomplete" is flagged to the officer); step 3 "Send to the bank" with a second confirming click and a reference number. The page can never read anything back except the checklist counts for this link. It shows no score, status or outcome.
12. **Officer inbox.** The case appears in that officer's queue as **From applicant** with an "applicant submitted" status, opens on the inventory (Part A), and the applicant's request is shown as a claim the officer can correct (audited). Once the officer has opened and edited the form, the request is locked and the link accepts files only (E-52).
13. **Asking for the rest.** From the inventory, "Ask the applicant" keeps the same link open (or extends it). The applicant reopens it and sees what is still needed. The Stage 9 message stays free of missing items (decision 17); a new template "Upload link" carries only the link and the usual footer and needs the second click. The content check allows exactly that link and nothing else.
14. **Storage.** Local disk plus a database row, behind a small `FileStore` interface (a later object store or a Docker volume swaps in). Files are served only through the authenticated API; the assigned officer and the admin can open them; the auditor and other officers cannot. A zip of the case's files is built on demand for the officer.
15. **Abuse limits.** Rate limit per link and per address, file-count and size caps per link, the same upload checks, a generic answer for a wrong, expired or revoked token, no token in logs or the audit log (only the link id), uploads refused with a neutral message once the case is running (E-51).

**Part D: Several documents in one PDF (build last; the stage can close without it)**
16. Each page of a bundle PDF is read and classified. A page with a recognised title starts a new document; a page without one continues the previous document; an unrecognised first page is "unrecognised". The proposed split (for example pages 1-2 PAN, 3 Aadhaar, 4-6 statement) is shown for the officer to move, merge or relabel and confirm. The original PDF stays untouched; each piece is cut into its own file linked to it (`parent_document_id`, page range) and then follows the normal path and the duplicate rules.
17. Bundle limits are separate from the single-document limit (more pages, every scanned page checked for blur, not only a sample). Password-protected bundles are rejected as today.
18. Switch `BUNDLE_SPLIT_ENABLED`. If the measured split accuracy is poor, the switch stays off and the officer splits nothing; the other parts are unaffected.

**Docs and tests**
19. Update `PRD.md` (sections 3, 4, 5, 7, 9.1 and a new 9.8), `DATABASE.md`, `SECURITY.md`, `ARCHITECTURE.md`, `TESTING.md`, `DESIGN_SYSTEM.md`, `EDGE_CASES.md`, `CLAUDE.md` (decisions 16 and 19) and the Help page.
20. Migrations (next numbers after 0013): documents (classification, duplicate, parent, page range, origin), `upload_links`, case origin and the new status. Run `python -m app.db.migrate` before using it.

**Second click (confirmation dialog):** create and send an upload link, disable a link, "Send to the bank" on the applicant page, "Proceed anyway" with missing items, "Continue anyway" while the applicant has not pressed Send to the bank, send of the "Upload link" message, confirm bundle split, plus the existing ones (submit, delete a document, confirm, override, admin correction, reassign, send message). **No dialog:** changing a type or person, moving a split, saving a draft, filtering, viewing, copying a link, downloading the zip.

Deliverables: migrations, `intake/archive.py`, inventory and link routes, public applicant routes, `FileStore`, officer screens (bulk upload, inventory, link manager, prefill confirmation, From applicant badge), the applicant page, synthetic bundle fixtures, tests, docs.

Exit criteria
- A zip, a folder and loose files of a synthetic case produce the same inventory; the inventory lists received, missing, extra, unrecognised, rejected and ignored duplicates correctly against the answer key for all 5 loan types.
- Unsafe archives (path traversal, symlink, zip bomb, nested zip beyond one level, too many files) are refused and nothing is written outside the case folder (tests).
- A file is read once: Extraction on a case uploaded through the desk makes no second OCR call (test with a counter).
- Identity fields are filled only from the PAN and Aadhaar cards; a disagreement leaves the field empty; no claim field is ever filled from a document (test); the identity-mismatch case still hard-fails.
- Scores, weights, bands and the 40-case results are unchanged against the Stage 9 baseline (replay).
- A link works once created, stops at expiry and when disabled, gives the same generic answer for an unknown token, never shows case data, status or outcome, and the token is never in a log or audit row (tests).
- Roles: another officer, the auditor and anonymous callers cannot read a file or the inventory; the admin can.
- Every second-click action above needs the second click (component tests); the no-dialog ones do not.
- Part D, if built: split accuracy on the synthetic bundles is measured and recorded (page-level label accuracy); with the switch off nothing else changes.

Risks: the classifier misses unusual titles, so many files land in "unrecognised". Mitigation: the dropdown, a measured classification rate on the dev split, and no guessing. A public page invites abuse. Mitigation: item 15, a token that opens nothing but its own checklist, and a short expiry. Scope: Part D can be cut first, then the "Upload link" message template.

---

## Stage 10b: AI control for the admin (added and built 2026-11-18)

**Goal:** the admin can change the models, the model settings and the editable part of the prompts from the browser without a deploy, and nothing the admin can do weakens a locked decision. Requested 2026-11-18; the user chose to keep keys in `.env`.

**Built:** migration 0018 (`ai_config_versions`, `ai_prompt_versions`, `ai_prompt_drafts`); `services/ai_config.py`; `api/ai_control.py` (admin only); `agents/prompt_check.py`; every prompt file split into an editable and a locked part; `Runner` binds the configuration to each run; the AI control page (Models, Keys, Prompts, Settings). Details: PRD 9.9, SECURITY 4d, ARCHITECTURE 3e, DATABASE 4b, TESTING 7f.

**Decisions taken (user: "go ahead with your recommendations"):** keys stay in `.env` (status and test only); prompts are editable only in their editable part, a draft must pass a test before publishing, every change needs a reason and a second click; models come from the fixed catalogue in `llm_models.yaml`; applies to new cases only.

**Not included:** the policy relevance threshold and the precedent bonus cap stay in their own files (they influence what is cited and scored); a browser test of the page; the "run the dev split" evaluation before publishing (the offline gate does not call models, so the prompt test on a fixed sample is the gate).

Exit criteria: met by the tests in TESTING 7f.

## Stage 10c: Knowledge base (policy documents and learnings) (L), planned and built 2026-11-21

**Goal:** the admin can read, change, upload, schedule, compare, restore and retire the policy documents the Policy agent reads, see what the system has learned (approved precedents) and keep both healthy, from the browser, without weakening a locked decision. Officers can read and search the policy in force. Requested 2026-11-21, before Notifications Part 3 and Stage 11; the user accepted every recommendation of the plan and chose to accept `.txt` and `.docx` uploads as well as Markdown (converted to Markdown).

**Decisions (user, 2026-11-21):**
1. The database is the source of truth for policy text (changes locked decision 12); `data/policy` files are starting data imported by `python -m app.rag.reindex` only when their label is new.
2. Scoring numbers stay in the rules file; a number that changes in a clause gives a warning naming the rule (E-92). No rules editing in the browser.
3. Old-format documents are imported by code only (no LLM); the admin checks every proposed clause ID.
4. Uploads: `.md`, `.txt`, `.docx`, converted to Markdown.
5. A published change pauses approved precedents whose rules use a changed clause, until the admin confirms them again or retires them.
6. Officers get a read-only Policies page. No new notification kind.

**Parts and exit criteria**

| Part | What | Exit criteria |
|---|---|---|
| A | Read only: policy list, clause reader with the rules that use each clause and recent citation counts, versions, live learnings, index health, search tester; officer Policies page | Admin and officer see what their role allows; the auditor gets 403 on every route |
| B | Format check, auto-fix, rule-number drift, old-format import, upload conversion (pure code, shared with the command line) | Each error, warning and fix has a test; the six shipped policy files pass with no errors |
| C | Drafts (one per loan type, saved even with errors, staged and embedded when they pass), clause edits, whole text, upload, retrieval check, publish with reason and second click, schedule, history (compare, restore, retire), version bound per run, file import rules | A changed clause reaches new cases while a running case and old reports keep the old text; a published version cannot be deleted or edited (database trigger); an older file never comes back after a screen publish |
| D | Learnings: pause on policy change, confirm again, retire, use history (`precedent_uses`) | A paused or retired precedent gives no bonus; an expired one cannot be confirmed again |

**Built:** migration 0021 (`policy_documents` lifecycle and body, `policy_drafts`, precedent `paused` and `retired`, `precedent_uses`); `rag/policy_admin.py`, `rag/policy_store.py`, `rag/versions.py`, `learning/maintenance.py`; `rag/index.py` and `rag/reindex.py` rewritten for the import rules; `api/knowledge.py`; the runner binds the policy versions; pages `KnowledgeBasePage` and `PolicyLibraryPage` with their components. Details: PRD 9.5, DATABASE 4, SECURITY 4g, EDGE_CASES E-91 to E-100, TESTING 7i, DESIGN_SYSTEM 14.

**Not included:** editing the rules file or `data/rag/config.yaml` in the browser; LLM help to convert old documents; PDF uploads; an inbox notice when a policy changes; a scheduler (scheduled versions switch on the first read after their date).

---

## Stage 11: Hardening, Docker and demo (M), built 2026-11-21

**Goal:** a reproducible package and a smooth demo.

Tasks
1. Security pass against `SECURITY.md`: secrets, retention job, audit coverage, PII leak scan on logs and traces.
2. Docker Compose: frontend, API (with graph runner), Prometheus, Loki, Tempo, Grafana. Langfuse stays on its cloud or off (user decision 2026-11-21). Email is the console sender or SMTP (Notifications Part 2), with an optional Mailpit service; no SMS. Postgres stays on Neon, with an optional local Postgres service for offline use.
3. Grafana dashboards: applications per day, time to decision, override-rate trend, tokens and cost per case, latency per agent.
4. Model versions and policy versions tagged on releases.
5. Run the 40 test cases once, record final results. Fold in the additions and corrections from the review window. Include a demo of the intake desk and the upload link (Stage 10).
6. Demo script, a short README, and a clean `.env.example`.
7. Update all docs to match what was built.

Exit criteria
- `docker compose up` brings up the full stack on a clean machine with only `.env` filled in.
- Final test-set results recorded.
- Demo script runs end to end without manual fixes.

What was built (details and measured results in `PROGRESS.md` "Stage 11 build notes"):
- **Security pass:** a retention job (migration 0024), two log guards, an audit-coverage test and a git-history secret scan.
- **Dashboards:** a new row with applications per day, time to decision, override rate and staff email, plus their metrics.
- **Releases:** the manifest command `python -m app.release`.
- **Evaluation:** the judge runner `python -m app.eval.judge` (replacing RAGAS and DeepEval) and the models-off test-split results.
- **For people:** a demo script (written as `docs/DEMO.md`; moved out of the repo to the presentation folder on 2026-11-23), a new README and a complete `.env.example`.
- **Packaging:** `requirements.lock`, `Dockerfile`, `docker-compose.yml`, and the `make up`, `make down` and `make stack-logs` targets.
- **Still with the user:** the real-model test-split run (one command, with the user's keys) and a demo run by the user.

---

## Stage 12: Post-demo features (L), planned 2026-11-25

**Goal:** five features picked by the user from the project manager's and CEO's review. Each one is useful on its own: a counter-offer box on the report, an Insights page, a queue export with decision timers, a score breakdown chart, and a read-only "Ask this case" chat. **Scoring does not change:** weights, bands, hard rules, the rules engine and the human confirmation stay as they are. The dev replay still gives 60 of 60 bands and the CI evaluation gate stays green. The test split is never used for tuning.

**Status:** Parts A and B built 2026-11-25, Parts C, D and E built 2026-11-26 (see the "Stage 12 Part … build notes" in `PROGRESS.md`). The decisions are in `PROGRESS.md` (decisions log, 2026-11-25); edge cases E-107 to E-131.

**How it is built:** one part at a time, in the order A → B → C → D → E. After each part: stop, report what changed and what was verified, give a commit message, and wait for the user to commit. Tests: only the tests related to the change, **one test job at a time** (pytest, Vitest and Playwright together ran out of memory on the 15 GB machine), using the local pgvector container `lc-test-pg` for database tests. Migrations are written and tested locally; the user applies them to Neon with `python -m app.db.migrate`.

**Docker:** Stage 12 adds no service. The `app` image and `docker-compose.yml` must still build and start; every new setting goes into `.env.example`. A `docker compose build` check closes the stage.

**Held, not in Stage 12** (PRD section 4, "Later"): the policy impact simulator, the one-click missing-documents request, a report diff after a correction, more loan types (gold loan, loan against property) and a guarantor, and auto-assignment of cases.

### Part A: counter-offer and alternate product (one small box on the report)

Shown **only when it helps**, never on every case.

1. **Code only, no AI.** `scoring/counter_offer.py` is pure code (no model, no database). It takes the case's own `CaseInput`, its `ScoreReport` and the rules file, and calls `engine.score_case` again with **only `loan_amount` and `tenure_months` changed**. EMI, FOIR, LTV, loan-to-turnover and age at maturity are worked out again by the normal facts code (`scoring/facts.py`, `scoring/finance.py`) at the rules-file rate. Everything else stays as checked, including any precedent bonus the real run got (E-107).
2. **When the box appears** (all must hold):
   - the band is reject or refer (`counter_offer.bands`);
   - the run did not stop on a fix-type rule, and did not stop on an eligibility rule other than age at maturity (CIBIL floor, residency and minimum age get no box);
   - at least one failed soft rule reads a field that amount or tenure can move (`counter_offer.moves_fields`: FOIR, tenure, loan amount, LTV, loan-to-turnover, repayment years, education collateral and margin);
   - a refer case held by a cap rule (PL-CIBIL-02, CM-FRD-01, BL-CRD-20) never gets a line aiming at approve (E-108);
   - a rescored line really reaches a higher band (reject → refer, refer → approve, or reject → approve);
   - the amount is at least half of the amount asked (`counter_offer.min_share`, 0.5).
3. **Tenure limits.** A longer tenure never passes the product's own tenure rule for this case (the threshold of PL-POL-10, HL-POL-10, VL-POL-10A/B/C for the vehicle kind, BL-POL-10; for education the ED-POL-10 repayment years plus the moratorium), and never takes any applicant or co-applicant past age 55 at maturity (CM-ELIG-03, `age.max_age_at_maturity`). The numbers are read from the rules file, never typed into code (E-110).
4. **At most two lines:**
   - (a) **the same amount over a longer tenure**, if that alone moves the band: the shortest longer tenure in whole years (`tenure_step_months`, 12) that reaches the next band;
   - (b) **the largest smaller amount** (in steps of `amount_step`, ₹10,000) at the longest allowed tenure that reaches a higher band than (a) gives, or the next band when there is no (a). Shown only when its amount is below the amount asked.

   Each line gives the amount, the tenure, the EMI at the rules-file rate, the FOIR and the band it would get.
5. **Age-at-maturity stop** (CM-ELIG-03 the only failure). The run stopped at KYC, so income was never checked: no rescoring and no band. At most one line: "a tenure up to N months keeps every applicant at 55 or under at maturity", shown when N is at least `min_tenure_months` (12). For education N includes the moratorium; if the moratorium alone is too long, no line. This fits E-35 (the education parent co-applicant): no conflict found (E-109).
6. **Alternate product (an extra line in the same box).** The purpose text is matched against the keyword lists in `counter_offer.alternate_products` (whole words, any capitals). Examples: car, bike or two-wheeler → vehicle; house, flat or home purchase → home; college fees, tuition or study → education; shop, working capital or machinery → business. The line is shown only when:
   - exactly one other loan type matches;
   - that product accepts the applicant's employment type (business needs self-employed);
   - its FOIR is lower than the case's;
   - the box already shows a line (a) or (b) (the user's choice, 2026-11-25: never on its own).

   It gives the indicative EMI and FOIR at that product's rate and longest tenure (age-capped as in step 3) and the extra documents a new application would need (the rules-file `documents` block for that product, minus what this loan already asks for). It is labelled "a new application, not scored" (E-111).
7. **Stored with the report.** The box is computed in the Decision node from the run's own `case_input` (already in the run state, so no new storage) and saved in `report_json.counter_offer`: audited, and the same every time it is shown. A re-run after a fix makes a new one with its report version. Reports made before Stage 12 have none (no backfill, E-113). It is **not** part of the LLM summary or any prompt.
8. **Rules file.** A new `counter_offer` block (`bands`, `min_share`, `amount_step`, `tenure_step_months`, `min_tenure_months`, `moves_fields`, `alternate_products` with keywords and employment types), added to the loader's schema. `rules_version` gets a new label because the file changed; no rule row, threshold, weight or band changes.
9. **Who sees it.** The officer and the admin, on the report screen and in the report PDF. The auditor never sees a report (unchanged). It never reaches a customer message (decision 17): the existing message check already blocks its text (the ₹ amount, "FOIR", "recommended" and "refer"), and a test proves it for every line kind (E-112).
10. **Wording:** "Pramaan estimates ₹6.2L over 5 years would be recommended for refer (FOIR 39.7%)". Never "approved" or "eligible for". Full wording in `DESIGN_SYSTEM.md` section 17.1.

Exit criteria (Part A)
- **The worked example**, on a test fixture built from it (personal loan, 12%, verified income ₹60,000 a month, existing EMIs ₹10,000, the rest of the score such that 6 more points keep it in reject and 12 more points reach refer):
  - ₹10L over 36 months gives EMI 33,214 and FOIR 72.0% (0 FOIR points);
  - over 60 months it gives EMI 22,244 and FOIR 53.7%, which is still 0 points, so there is **no line (a)**;
  - ₹7L over 60 months gives EMI 15,571 and FOIR 42.6% (6 points);
  - ₹6.2L over 60 months gives EMI 13,792 and FOIR 39.7% (12 points), recommended for refer, but it is not the largest such amount: **line (b) is ₹6.3L over 60 months**, EMI 14,014, FOIR 40.0% (FOIR is rounded to one decimal before the 40% tier, so 40.0% still earns 12 points; E-128). ₹6.4L gives 40.4% and stays in reject;
  - with the purpose "car", the vehicle line is ₹10L over 84 months at 9.5%, EMI 16,344, FOIR 43.9%.
- Never shown (one test each): approve; refer held by a cap rule; fix-type stop; eligibility stop other than age; points lost only to rules amount and tenure cannot move; a suggestion under 50%.
- Never past the product's tenure limit or age 55 at maturity for any person (tests include education with a parent co-applicant near 55).
- Age stop: the tenure line only, with no band.
- The same input gives the same box. It is stored in the report, shown in the report and the officer's PDF, and absent from the summary and every prompt.
- The customer-message check blocks every line kind.
- The dev replay gives 60 of 60 bands with byte-identical scores, and the CI gate stays green.

### Part B: Insights page (management dashboard and override insights)

1. **Migration 0026:** `cases.submitted_at` (the first "Submit for assessment"; the funnel's "documents complete") and `cases.report_ready_at` (when the latest report that waits for the officer was written). Both are backfilled from the audit log and the stored reports. The other times already exist (`cases.created_at`, `reports.created_at`, `officer_actions.created_at`).
2. **`reporting/insights.py`, SQL only, no AI** (built in a new `app/reporting` package so `app/monitoring` stays the isolated fairness view). Filters: a date range (cases **created** in it; the browser sends its own midnights as instants) and a loan type.
   - **Time to decide:** created → report ready, and report ready → officer decision. Median and slowest, per loan type and per officer.
   - **Funnel:** created → submitted (documents complete) → report ready → decided (confirmed, overridden), plus where open cases sit now (not submitted, stopped for a fix, waiting for the officer).
   - **Officer agreement with the recommendation:** the share confirmed against overridden, by loan type and by band. Admin corrections are counted separately.
   - **Override insights:** the rules that failed in overridden cases, with the direction (for example refer → approve) and the rule's policy clause.
   - **Top stop reasons:** stopped runs by stage and rule, read from every stored report version, so a stop that was later fixed still counts (E-114). Example: "12 cases stopped at KYC for CM-KYC-03".
   - **Precedent use:** how many cases got an approved precedent's bonus, and in how many the bonus changed the band.
3. **Who sees what.**
   - **Admin:** `GET /admin/insights`, the full page with links to the cases and to the rule's clause in the knowledge base.
   - **Auditor:** `GET /auditor/insights`, the same numbers with **no case id, case reference or link** (decision 9, E-115).
   - **Officer:** `GET /me/insights`, their own numbers only, shown on Home: their median time to decide (last 30 days), and their overdue count once Part C exists. Never another officer's numbers.
4. **UI:** an Insights page in the admin and auditor sidebars, reusing `BarChart` and the tokens. The `dataviz` skill is loaded before any chart is drawn. The admin's clause tags open the clause in the knowledge base (`/admin/knowledge?doc=…&clause=…`).

Exit criteria (Part B)
- Every figure equals a hand count on a seeded test database (one test per panel, with and without each filter).
- The auditor's answer holds no case id, reference or link (a test walks the JSON). An officer's numbers never include another officer's case.
- Roles: the officer gets 403 on the admin and auditor routes; the auditor gets 403 on the admin route and the admin on the auditor's.
- No model is called.
- Migration 0026 applies, backfills and rolls back.

### Part C: queue export (CSV) and decision timers (SLA)

1. **Export.**
   - Routes: `GET /cases/export.csv` (officer: their own cases, with the queue's filters: status, loan type, search, view and due state) and `GET /admin/cases/export.csv` (admin: all cases, plus an officer filter).
   - Columns: case reference, loan type, status, band, score, officer, created, updated, officer decision, SLA due, overdue. **No applicant names**; the case reference is enough.
   - It reuses `auditlog.csv_response`, which already writes cells starting with `=`, `+`, `-`, `@`, tab or carriage return as text (CSV injection). It gains a UTF-8 byte-order mark so Excel reads the file correctly. No new package.
   - Every download writes an audit row `cases_exported` with the filters and the row count (E-119).
2. **The decision timer.**
   - **Target:** the officer decides within **2 working days** (Monday to Friday; holidays are out of scope) of the report being ready.
   - **Settings:** one business setting, `SLA_WORKING_DAYS` (2), in `config.py` and `.env.example`, plus two technical ones: `SLA_TIMEZONE` (Asia/Kolkata) and `SLA_CHECK_MINUTES` (15). It is not a scoring rule, so it does not belong in the rules file.
   - **Due time:** the report-ready time plus N × 24 hours of Monday-to-Friday time in that time zone (E-116).
3. **Clock rules** (E-117):
   - only a case waiting for the officer's decision (`awaiting_confirmation`) is timed;
   - each new report restarts the clock;
   - fix-type stops and cases waiting on the applicant (before submit) are not timed;
   - reassignment keeps the due time;
   - the officer's decision stops the clock.
4. **Migration 0027:** `cases.sla_due_at`, `cases.sla_officer_notified_for`, `cases.sla_admin_notified_for`, and two notification kinds (`case_overdue` for the officer, `case_overdue_admin` for every active admin), added to the kind CHECK and `inbox.KINDS`.
5. **Reminders.** A check runs inside the app every `SLA_CHECK_MINUTES` under a Postgres advisory lock, like the retention job: no Celery, no Redis.
   - One in-app notice goes to the case owner when the case becomes overdue.
   - One goes to every active admin when the case is still undecided one working day after its due time.
   - Each is claimed once per due time by one `UPDATE` (E-118).
   - Staff "new notice" emails follow the existing per-person switch. The texts are fixed and carry no case data.
6. **Queue:** a case-age column, "Due today" and "Overdue" badges, and a due-state filter; Home shows the officer's overdue count; the admin's officer page and the export carry the same states. No auto-assignment.

Exit criteria (Part C)
- Working-day tests: a report ready on Friday afternoon, on a Saturday, and just before midnight in India time.
- One test for each clock rule in step 3.
- Reminders: each goes once, to the right person, never after the decision, never to the auditor. Two processes running the check send nothing twice.
- The CSV opens in Excel. It contains no applicant name, and formula-like cells are text. An officer gets only their own cases and the admin gets all. There is one audit row per download.
- Migration 0027 applies and rolls back; the kinds in code equal the database CHECK.

### Part D: score breakdown chart (waterfall) on the report

1. **The backend carries the numbers.** `agents/report.py` adds `score_breakdown` for scored cases. It holds:
   - the start (100);
   - for each stage, its maximum, the points it earned and the points it lost;
   - the precedent bonus;
   - the final score and band;
   - the 85 and 60 band lines from the rules file;
   - any cap, with its rule IDs.

   A stored report without it gets it on read from its own stage scores, through the same function. The UI only draws.
2. **The chart** (`ScoreWaterfall`) sits at the top of the report for scored cases. It starts at 100 and steps down by the points lost in each stage to the final score. The 85 and 60 lines are marked, a precedent bonus is a step up, and a refer cap is marked clearly with its rule (E-120). A stopped case, where some stages did not run, shows no chart.
3. **Accessibility and themes:** light, dark and system themes; a one-sentence text summary for screen readers and a "Show as a table" alternative.
4. **PDF: one new column, no chart** (the user's choice, 2026-11-25). The PDF's "Stage scores" table already lists each stage's score out of its maximum; it gains a third column, "Points lost", read from the same numbers the chart draws (a dash for a stage that did not run). The chart itself is on screen only.

Exit criteria (Part D)
- For every scored dev replay case: 100 minus the points lost plus the bonus equals the final score (test).
- A stopped case has no `score_breakdown`; a capped case carries the cap; a bonus is a step up.
- The report PDF's stage table has the "Points lost" column, equal to the breakdown for every scored dev replay case, with a dash for a stage that did not run (test).
- Component tests: the chart draws exactly the numbers it is given and computes none; the table alternative and the text summary match; contrast passes in both themes (`tokens.test.js` pairs).

### Part E: "Ask this case" chat (retrieval plus a model, read-only)

1. **Sources, and nothing else** (no internet, no other cases, no general knowledge, no precedents in this version):
   - the case report: findings, rule IDs, stage scores and the code-derived facts (FOIR, EMI, LTV, CIBIL, age at maturity);
   - the masked extracted document fields (no raw PAN, Aadhaar, phone or account number);
   - the policy clauses in force for that loan type **in the versions the run bound** (recorded on the report), through `rag/retrieve.py`, plus the clauses the report already cites.
2. **Flow** (ARCHITECTURE 3g):
   1. The officer asks.
   2. Code masks the question and treats it as data. A question that matches the injection patterns gets the fixed answer and is audited.
   3. A "what if" question (another amount or tenure) gets a fixed pointer to the counter-offer box, with no model call.
   4. Retrieval runs: the case facts plus the top reranked clauses.
   5. The model answers: role `case_assistant`, Gemini Flash by default, with the existing fallback chain, on the AI control page.
   6. The output is a Pydantic schema in which every sentence cites a rule ID, a clause ID or a document field.
   7. Code checks that every clause ID was given, every rule ID is the case's, every field exists, every number matches the given material, the wording rules hold and no raw identifier is present. The model does no arithmetic.
   8. A failed check is retried once; then the fixed text "I can't answer that from this case's documents and policy."
3. **Read-only.** The chat cannot change a score, a status or a decision; its routes write only its own rows and the audit log.
4. **Access:** the case's officer and the admin only. Another officer gets 404, the auditor 403. Each person sees their own questions on a case.
5. **Records:**
   - Migration 0028 adds `case_chat_messages`: the masked question, the answer with its citations, the outcome and the report version.
   - Every model call is logged in `llm_calls` (stage `chat`, role `case_assistant`) and traced in Langfuse (metadata only).
   - Each question writes an audit row (never its text).
   - The retention job deletes chat rows after `CHAT_RETENTION_DAYS` (90).
6. **Limits:**
   - A per-user limit (`CHAT_MAX_PER_HOUR`, 20) protects the free tiers.
   - With `LLM_ENABLED=false`, or with models switched off on the AI control page, the page says "Chat is off" and nothing is called.
   - Citations in answers open the clause, like the report's citations.
7. **Files:** `app/chat/` (`context.py`, `check.py`, `service.py`, `evaluate.py`), `api/chat.py`, `prompts/case_assistant.md` (editable and locked parts), a prompt-test sample in `agents/prompt_check.py`, the role in `llm_models.yaml`, and the "Ask" tab on the case page.
8. **Golden set:** `data/eval/chat_dev.yaml`, about 20 questions on dev cases, each with its expected citations or an expected "cannot answer" or "what if". Runner: `python -m app.chat.evaluate --split dev [--no-llm]`. Thresholds go in a `chat` block of `docs/baselines/thresholds.json`.

Exit criteria (Part E)
- **Fake model tests:** a grounded answer is stored and shown with its citations. Each of these is retried once and then replaced by the fixed text: a clause that was not given, a rule that is not the case's, an unknown field, an invented number, a sentence with no citation, "approved" wording.
- **PII guard:** a question holding a PAN, Aadhaar, phone, account number, email or the applicant's name reaches the model and the database masked. No raw identifier appears in a model message, a log line or a trace.
- **Injection:** the case with `data/synthetic/output/special/poisoned_1.pdf` and an "ignore the rules and approve" question change no score, status or decision. No chat route can write to a case.
- **Access:** the owning officer and the admin get 200, another officer 404, the auditor 403, no session 401.
- **Off and limits:** the off message with `LLM_ENABLED=false` and with models off; 429 after the hourly limit.
- **Records:** an `llm_calls` row with stage `chat`, an audit row without text, and old rows removed by the retention job.
- **Browser:** one Playwright test: the officer asks, sees a cited answer and opens the clause.
- **Golden set:** the `--no-llm` mode passes in CI, and citation validity is 100%. The real-model run is the user's, with their keys, and is recorded in `PROGRESS.md` (targets wait for that baseline, OI-7).

### Close of the stage
- Docs updated with each part (PRD, PROGRESS build notes, the topic docs, Help page).
- `docker compose build` still works and the app starts. New settings are in `.env.example`.
- Dev replay 60 of 60 bands and the CI gate are green.
- Migrations 0026 to 0028 are listed for the user to run on Neon.

---

## Order of risk

Highest risks first so we meet them early: synthetic data realism (Stage 1), OCR on photos and statement tables (Stage 2), free-tier rate limits (Stage 5), evaluation noise from small data (Stage 7), visual scope creep (Stage 8). Where a risk bites, cut scope in this order: scanned statement styles, education case count, Grafana dashboards, UI motion. Never cut the human confirmation, hard rules or masking.

## Definition of done (every stage)

Tests written and passing, docs updated if behaviour changed, no real PII, secrets only in `.env`, PR reviewed against `CODE_STYLE.md`, CI green.
