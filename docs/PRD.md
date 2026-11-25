# PRD: Loan Pre-Underwriting Copilot

Status: Draft v1.0 for trainer approval · Date: 2026-10-29 · Owner: solo developer (capstone project)

This is the main requirements document. Other docs go deeper on one topic each (see `CLAUDE.md` for the map). Everything we agreed in planning is captured here. Anything not yet confirmed is listed in section 15.

---

## 1. Purpose

A copilot for a bank or NBFC that pre-assesses loan applications. Bank staff upload an applicant's documents; the system checks them stage by stage, scores the case, and writes a report with a recommendation (approve, refer or reject) and policy citations. **A human always confirms the final outcome.** When the human overrides the recommendation, the system learns from the reason by saving it as a reviewed "precedent" in its knowledge base. No model is trained.

Context: capstone project from a training programme. Trainer approves the documents first, then implementation starts. It will be demoed, and may be shown to a company if it is good enough.

## 2. Business problem

Underwriters manually review payslips, bank statements and credit policy for every application. Real-world pain points:

- Documents are messy: scanned payslips, photos, password-protected statements, a different format per bank.
- Policy lives in PDFs and circulars that change often, so people work from memory.
- Manual FOIR calculation is slow and error-prone, and different underwriters decide differently.
- Fraud signals are easy to miss: tampered payslips, window-dressed statements, salary that does not match bank credits.
- RBI expects fair practices, written rejection reasons and an audit trail.

## 3. Users and roles

The users are **bank staff**, not applicants. Applicants never log in and have no account. From Stage 10 an applicant may open one **time-limited upload link** (section 9.8) to send documents; that page can only add files and see a checklist.

| Role | What they do |
|---|---|
| Loan officer | Creates a case, picks the loan type, fills the application form, uploads documents (all at once or one by one), clicks "Submit for assessment", reads the report, confirms or overrides (with a reason). Reads the policy in force (read-only Policies page, Stage 10c). From Stage 12 (planned): sees a counter-offer box on reports where it helps, asks read-only questions about their own case ("Ask this case"), exports their own queue as CSV, and sees their own decision timers and median time to decide |
| Auditor | Read-only (added 2026-11-03, reshaped the same day). Exactly one account, created only from the command line. Sees how many cases there are and in which state, not what a loan is: the Overview charts, a static Cases table with filters and CSV export (no applicant, document, report or message content, no case page), the audit log (masked, filters, CSV) and the users list. From Stage 12 (planned) also the Insights page, counts only, with no case reference or link. Changes nothing |
| Admin | Sits above the loan officers. Manages users (any number of officers) in a Users screen (create, disable, reset password; Stage 8), approves or rejects each proposed precedent, approves any change that touches a hard rule, edits the rules file, changes the policy documents and manages the learnings in the knowledge base (Stage 10c, 2026-11-21), triggers re-indexing. Since 2026-11-03: opens any officer's case (documents, report, audit trail), **corrects** a decision after the officer has decided it (reason, second click, a separate record beside the officer's, never over a hard rule, never a precedent), **reassigns** a case the officer has not decided, reads the messages officers sent (no drafts) and each case's own audit tab. The system-wide audit log is the auditor's alone. From Stage 12 (planned): the Insights page with links to cases and clauses, the export of all cases, the overdue reminders one working day after an officer's, and "Ask this case" on any case |

(Earlier we discussed a separate underwriter and a reviewer. For v1 the loan officer plays the underwriter, and the admin plays the reviewer. Three roles: admin, loan officer and, from 2026-11-03, one read-only auditor.)

## 4. Scope

**In v1**

- Five loan types: personal, home, education, business, vehicle.
- Indian norms based on public SBI, HDFC and ICICI criteria plus RBI rules, merged into one blended policy. The fictional bank and the product are named **Pramaan**; policy and rules files keep their `Sample Bank` identifiers.
- Primary applicant plus optional co-applicant (mandatory for education loans).
- Documents as digital PDFs, scanned PDFs and photos (JPG/PNG). English only.
- Multi-agent pipeline on LangGraph with fixed routing and gates.
- Human confirmation on every case, whatever the score.
- Learning through a precedent store inside RAG.
- Evaluation, guardrails, observability, token and cost tracking.
- A refreshed UI (Stage 8): Pramaan brand, light, dark and system themes, the 5-stage underwriting stepper, a Credit / Capacity / Collateral display strip, admin Users screen.
- Customer contact messages (Stage 9): the officer sends a short no-reply message with no confidential data; v1 logs it in the terminal and a Sent Items screen.
- Intake desk (Stage 10): upload a zip, folder or many files at once; the system reads and classifies each file once, shows what is received, missing, extra, unrecognised and duplicate, and fills the identity fields of the form from the PAN and Aadhaar cards for the officer to confirm. A single PDF holding several documents is split by page (built last, switchable).
- Applicant upload link (Stage 10): a 7-day, revocable, one-case link on which the applicant states the request and uploads documents; the case lands in the chosen officer's queue as "From applicant".
- Synthetic data only. Docker Compose at the final stage (Stage 11).
- Post-demo features (Stage 12, planned 2026-11-25, section 9.12):
  - a counter-offer and alternate-product box on the report, shown only when it helps;
  - an Insights page (time to decide, funnel, officer agreement, override insights, stop reasons, precedent use);
  - a queue export (CSV, no names) and decision timers (2 working days) with reminders;
  - a score breakdown chart;
  - a read-only "Ask this case" chat grounded in the case and its policy.

  Scoring does not change.

**Out of v1**

- Applicant accounts, logins and a status-tracking page (a coarse status on the same link may come later, never a score or outcome hint).
- Finding the same file in a different case (cross-case duplicate check, E-44).
- Real customer data or real PII anywhere.
- Real UIDAI, NSDL, GST, Udyam or CIBIL calls (mocked with synthetic records, replaceable later).
- Automatic approval or rejection without a human.
- NRI applicants, non-English documents.
- Applicant-facing portal (customer messages in Stage 9 are one-way and carry no case data).
- Real email or SMS delivery (v1 prints to the terminal and keeps Sent Items; a real sender can be added behind the `Sender` interface later).
- Training any model or hosting any local LLM. DPO, TRL, Colab and a tuned Qwen model are **removed** (user decision, 2026-10-31). LLMs are used only through APIs. Local embeddings, reranker and OCR (from the pip venv) are not LLMs and stay.
- Celery and Redis (not needed for v1; can be added later).
- Hosted file storage (local disk in v1).
- ~~Admin UI for policy upload~~: built as the knowledge base in Stage 10c (2026-11-21, decision 12 changed by the user, see 9.5). Editing the rules file from the browser stays out: scoring numbers change only in the file, with a golden-set rerun.

**Later (held by the user on 2026-11-25; not in Stage 12)**

- A policy impact simulator: replay cases against a changed copy of the rules file to see what would move.
- A one-click "request the missing documents" action. "Ask the applicant" on the intake desk mostly covers it.
- A report diff after a correction (what changed between report versions).
- More loan types (gold loan, loan against property) and a guarantor.
- Auto-assignment of cases. Every case already has an owner from the start (the officer who made it, or the officer an upload link belongs to); the admin reassigns undecided cases by hand.
- Precedents as a source for the "Ask this case" chat (left out of its first version).

## 5. End-to-end workflow

1. Loan officer logs in and opens the case queue.
2. Creates a case: picks loan type, enters the request, then uploads (or an applicant sends documents and the request through a link, section 9.8 and Stage 10).
3. Uploads a zip, folder or files all at once (or one by one); the intake desk shows what is received, missing, extra and duplicate; the identity fields of the form are filled from the PAN and Aadhaar cards and the officer confirms them, then fills the claim fields (section 7). **Upload-time checks** run per file (section 9.1).
4. Clicks **Submit for assessment**. The pipeline starts.
5. Pipeline runs (section 8). A hard failure stops it early; a short report is still produced.
6. Report is shown with stage scores, findings, citations and a recommendation worded "recommended, awaiting your confirmation".
7. Officer reviews the report and documents, then confirms or overrides. Both need a second confirming click. An override needs a written reason.
8. For an override, the system creates a **proposed precedent**: officer reason plus an LLM summary of the report.
9. A code check tests the proposal against the hard rules. A proposal that breaches a hard rule is **held** and never enters the knowledge base. Otherwise the admin approves or rejects it; approved precedents enter the knowledge base.
10. Everything is written to the audit log.
11. (Stage 9) After confirm, override or a stopped run, the officer may send the customer a short contact request (section 9.7).


A stopped case can be resumed from the failed stage after the officer corrects data or re-uploads, under the same case ID. Stopped is **not** a final reject.

## 6. Loan types, rules and sources

### 6.1 How rules are organised

- **Policy documents** (Markdown/PDF in plain English with clause IDs such as `PL-ELIG-03`). The Policy agent retrieves and cites them. A company can swap in its own.
- **Rules file** (YAML/table, one row per rule): `rule_id, loan_type, stage, kind, field, operator, threshold, points, policy_clause, source, version`. The scoring code reads it. Changing a limit means editing one row.
- `source` is one of `public`, `RBI`, `sample`.
- Scoring is in code. The LLM never calculates scores.

### 6.2 Common rules for every loan

**Hard rules**

- PAN (or Form 60) present and valid in format. Aadhaar 12 digits with checksum.
- Name and DOB match across PAN, ID, income documents and the application form.
- Indian resident.
- **Age cap: 55 at loan maturity, for every applicant and co-applicant** (see open item OI-1). Minimum age 21 (education loan student: 18).
- All mandatory documents for the loan type present.
- CIBIL at or above the product floor.
- Suspected tampering sends the case to refer, never silent pass.

**Soft rules**

FOIR, job or business stability, salary regularity, cheque and NACH returns, LTV, savings pattern, document quality.

**Hard-fail classes**

- *Fix-type* (missing document, mismatch, invalid ID format): case stops, officer corrects and resumes. Not a final reject.
- *Eligibility-type* (age out of range, CIBIL below floor, non-resident): case stops with recommendation reject; score capped below 60.

**RBI conduct rules the Policy agent cites** (not all are scored)

- KYC: PAN or Form 60 required; Aadhaar voluntary and redacted when submitted.
- Written reason for any rejection. Every report includes a plain-language rejection reason.
- Credit bureau data kept no longer than six months without fresh consent. The retention job is built (Stage 11, `python -m app.db.retention`; SECURITY.md 7).
- Key Fact Statement under the Digital Lending Directions (effective 8 May 2025).
- No foreclosure charges on floating-rate loans to individuals for non-business purposes (new directions apply to loans sanctioned or renewed from 1 Jan 2026). Cited, not scored.
- Our own rule: gender, religion, caste and similar attributes are never used.

### 6.3 Per-loan rules (Sample Bank policy)

| | Personal | Home | Education | Business | Vehicle |
|---|---|---|---|---|---|
| Employment | Salaried | Salaried or self-employed | Co-applicant salaried or self-employed | Self-employed | Salaried or self-employed |
| CIBIL | ≥700; 650-699 refer; <650 hard fail | ≥700 (750 full marks) | Co-applicant ≥700 | ≥650 (700 full marks) | ≥700 |
| Min income | ₹25,000 net/month | ₹25,000/month | Co-applicant income proof | Turnover ≥ ₹36L/yr | Salaried ₹25,000; self-employed income per ITR |
| Age | 21 to 55 at maturity | 21 to 55 at maturity | Student 18+; co-applicant 21 to 55 at maturity | 21 to 55 at maturity | 21 to 55 at maturity |
| FOIR | Cap 50%; full marks ≤40% | Cap 50% | Combined cap 50% | Per bank-statement analysis | Cap 50% |
| Tenure | ≤60 months | ≤30 years | Moratorium course+1 yr; repay ≤15 yrs | Per product | Car new ≤7 yrs, used ≤5 yrs, two-wheeler ≤5 yrs |
| Collateral / value | None | LTV 90% (≤₹30L), 80% (≤₹75L), 75% above | None ≤₹7.5L (RBI: none needed ≤₹4L); above ₹7.5L collateral required; margin 5% India, 15% abroad above ₹4L | Optional | LTV 85% new on-road, 80% used |
| Stability | ≥2 yrs experience, ≥1 yr with employer | Employment or business stability | n/a | Vintage ≥2 yrs; bank credits ≥80% of GST sales; 3+ cheque returns in 12 months = refer | Employment or business stability |
| Extra | | Existing loans count in FOIR only if >12 instalments unpaid | Co-applicant mandatory | GST or Udyam required | Driving licence, invoice |

Personal loans are capped at ₹25 lakh and business loans at 30% of annual turnover (sample policy; added in Stage 1 so each can fail independently of FOIR). Tenure is also limited so that age at maturity stays ≤55. Age at maturity is the age on the date `application date + total tenure`, where an education loan's tenure includes the moratorium. Values are a sample policy modelled on public SBI, HDFC and ICICI criteria. They are not any bank's actual policy.

### 6.4 Scoring

Total 100 points.

| Stage | Points | Produced by |
|---|---|---|
| KYC | 20 | KYC & Compliance agent |
| Documents (completeness, quality) | 15 | Extraction agent |
| Income and FOIR | 30 | Risk agent |
| Credit and risk behaviour | 25 | Risk agent |
| Policy fit | 10 | Policy agent |

Bands: **85 and above** recommend approve · **60-84** refer · **below 60** recommend reject. A hard fail overrides the band. If the run stops early, only completed stages show a score and the final score is shown as "not computed". Weights and bands live in the rules file.

### 6.5 Mandatory documents per loan

All loans: PAN, Aadhaar or other OVD, photo, application form data.

- **Personal:** 3 months payslips, 6 months bank statement, Form 16 or ITR (optional).
- **Home:** 3 months payslips and Form 16 (salaried) or 3 years ITR with P&L and balance sheet (self-employed); 6 months bank statement; sale agreement or allotment letter, title deed, encumbrance certificate, approved plan, builder NOC where applicable.
- **Education:** admission letter, fee structure, marksheets; co-applicant KYC, income proof and bank statement.
- **Business:** promoter KYC, business proof, GST registration or Udyam, 12 months bank statement, 12 months GST returns, 2 years ITR, P&L and balance sheet.
- **Vehicle:** income proof (payslips or ITR), 6 months bank statement, dealer proforma invoice, driving licence (two-wheeler); RC and insurance for used vehicles.

Co-applicant: same KYC, income and bank statement set as the primary applicant.

## 7. Application form fields

Entered by the officer at case creation. The system checks documents against these.

- **Common:** applicant name, DOB, PAN, Aadhaar last four digits, address, phone, employment type, employer or business name, declared monthly income, loan amount, tenure, purpose.
- **Home:** property value, property address, seller or builder, owner name.
- **Education:** course, institution, country (India or abroad), course duration, total fee.
- **Business:** business name, constitution type, GSTIN, Udyam number, vintage, annual turnover.
- **Vehicle:** make, model, new or used, on-road price, dealer.
- **Co-applicant:** same identity and income fields plus relationship.
- **Required and optional (changed 2026-11-01):** the form marks required fields with `*` and optional ones with "(optional)", and opens with a short note saying what each means. Optional fields: mobile number, employer or business, months in current job, total experience, residential status (defaults to resident), purpose, application date, relationship (co-applicant); home: property address, seller or builder, owner name; education: institution, course duration; business: Udyam number. No scoring rule reads the loan-type ones. An empty optional field is simply skipped; a filled one is compared with the documents like any other. Everything else is required.
- **Filled from documents (Stage 10, Part B built 2026-11-04, partly reverses E-31):** name, date of birth, PAN, Aadhaar last four and address are filled from the PAN and Aadhaar cards, marked "from documents", left empty when the two cards disagree, and confirmed by the officer with a tick before Submit. Everything else is a **claim** and is never read from a document: loan type, amount, tenure, purpose, employment type, employer, declared income, months in job, experience, mobile, email, residential status, the loan-type fields and the co-applicant relationship. The applicant states the loan request on the upload link, or the officer enters it; the system never decides the amount.
- **Customer email (Stage 9):** optional field on the primary applicant, used only as the recipient of a contact message. Synthetic values only; masked in lists and in any model input.
- **Also collected (added in Stage 1, needed by the rules):** residential status; months in current employment (stability rules); total work experience in months (personal loan only); collateral offered and margin amount (education).

## 8. Agents and pipeline (summary)

Detail is in `AGENTS.md`. Order is **fixed**, with a gate after each stage based on the previous agent's output.

```
Supervisor → Extraction → KYC & Compliance → (Policy ‖ Risk) → Decision → officer review
```

- **Supervisor:** opens the case, builds the document checklist from the rules file, gives each agent its task, handles retries and fallbacks, assembles the final output.
- **Extraction:** classifies documents, masks PII, extracts fields into a fixed schema, gives each field a confidence.
- **KYC & Compliance:** completeness, ID format and checksum, name, PAN, DOB and address matches, mock identity lookup.
- **Policy:** retrieves clauses and similar approved precedents, checks its answer is grounded before citing.
- **Risk:** FOIR and debt-to-income, bounced cheques and NACH returns, salary regularity, tamper hints, business ratios.
- **Decision:** combines stage scores (computed in code), writes the report and the rejection reason.
- Co-applicant runs through the same pipeline with a role tag, and the report has a section per person plus a combined FOIR.
- Gates: a hard fail stops the run; low-confidence extraction is flagged to the officer; a check that fails is retried once, then marked **unverified** and passed to the officer.

## 9. Functional requirements

### 9.1 Upload and parsing

- FR-1 Detect file type per page: digital PDF (text layer), scanned PDF, photo, password-protected PDF.
- FR-2 **Reject password-protected PDFs at upload.** The password is never stored.
- FR-3 Reject badly blurry or cropped images with "please re-upload". Borderline quality is accepted with a warning.
- FR-4 Digital PDFs: PyMuPDF for text, pdfplumber for tables.
- FR-5 Scans and photos: OpenCV deskew and blur score, then local OCR (PaddleOCR; Tesseract fallback).
- FR-6 Classify document type (payslip, bank statement, ITR, Form 16, Aadhaar, PAN, and so on).
- FR-7 Mask PII, then the LLM extracts fields into a fixed schema. Every field has a confidence. Low confidence is flagged, never guessed.
- FR-8 Validate with code: formats, totals (net pay = gross minus deductions), dates, statement running balances.
- FR-9 Tamper hints: PDF metadata showing an editing tool, round-number or arithmetic-inconsistent salary, PF out of line with pay, salary slip with no matching recurring bank credit, odd-date credits from individual accounts with no TDS.
- FR-10 Bank statements: start with digital statements in 3-4 synthetic bank styles (SBI-like, HDFC-like, ICICI-like, one scanned). More scanned formats later.

- FR-28 (Stage 10, built) A zip, a folder or many files can be uploaded at once. Archives are unpacked safely (no paths outside the case folder, no symlinks, one nesting level, count, size and ratio limits, junk files skipped) and every inner file gets the normal upload checks.
- FR-29 (Stage 10, built) Each accepted file is read once (OCR only where needed), classified and assigned to a person; the result is cached against the file hash and reused by Extraction, so nothing is read twice.
- FR-30 (Stage 10, built) An inventory shows, per person, what is received, still missing (essential items marked), extra, unrecognised, rejected and duplicate-ignored. The officer can correct a type or person.
- FR-31 (Stage 10, Part D, built 2026-11-18) A multi-page PDF whose pages are different documents is read page by page: a page with a recognised title starts a new document, a page without one continues the previous document, and an unrecognised first page is "unrecognised". The proposed split is shown with a tick on each page where a document starts and a type for each; the officer moves it and confirms with a second click. The original PDF is kept untouched; each piece is its own file (own checks, own duplicate rules) linked to it by `parent_document_id` and page range. Nothing goes on (proceed, submit, resume) while a PDF waits for its split. A bundle may have up to `BUNDLE_MAX_PAGES` pages (120) and `BUNDLE_MAX_MB` megabytes (25) and every scanned page is checked for blur; the whole feature is off with `BUNDLE_SPLIT_ENABLED=false`, and then a multi-page PDF is one document as before.

### 9.2 ID validation (offline functions, no real lookups)

- **Aadhaar:** 12 digits, first digit 2-9, Verhoeff checksum. Only the last four digits are stored or shown.
- **PAN:** pattern `AAAAA9999A`; 4th letter holder type (P individual, C company, F firm); 5th letter matches surname initial for individuals.
- **GSTIN:** 15 characters, embedded PAN cross-checked against the applicant's PAN, checksum verified.
- **Udyam:** format check.
- Real lookups go through a mock service backed by synthetic records.

### 9.3 Review and confirmation

- FR-11 Every case, at every score, needs an officer confirmation. A report is always generated.
- FR-12 Confirm or override each need a second confirming click.
- FR-13 Override needs a reason. Reports use the wording "recommended", never "approved".
- FR-14 Report export to PDF.

### 9.4 Learning loop (precedents)

- FR-15 On override, store: officer reason, LLM summary of the report, loan type, rules involved, original score and recommendation, final decision, embedding.
- FR-16 Three gates before a precedent is stored: officer override with reason, rule-based hard-rule check in code, admin approval. Any change touching a hard rule needs admin approval. Approved ones get an expiry (revalidation) date.
- FR-17 Precedents are retrieved only for borderline cases (refer band), above a similarity threshold, same loan type, same failing rules.
- FR-18 A precedent **never overrides a hard rule**. A strong approved precedent can lift a borderline case's label (for example "refer → recommend approve, supported by precedent P-0042") by a capped bonus set in the rules file. The officer still confirms.
- FR-19 Main policy files are never modified by learning. Precedents are stored separately.

### 9.5 Policy updates and the knowledge base (Stage 10c, built 2026-11-21; decision 12 changed by the user)

- FR-20 v1: edit policy and rule files, run a re-index command. Policy and rule versions are recorded on each report. **Changed 2026-11-21:** the database now holds every policy version and is the source of truth; the files in `data/policy` are the starting data that the re-index command imports when their version label is new (E-94). The rules file is still edited by hand only.
- FR-52 (built) The admin has a **Knowledge base** page with three tabs: **Policies** (the six policies; for each, Read, Change and History), **Learnings** (approved precedents and what happened to them) and **Search and index** (a search tester, index health, the policy files on the server, a re-index and the retrieval evaluation). Officers get a read-only **Policies** page (the version in force, the rules that use each clause, search); the auditor gets neither (403).
- FR-53 (built) A change always goes through a draft, one per loan type: change, add or remove one clause, edit the whole text, or upload a `.md`, `.txt` or `.docx` file (1 MB at most), which is converted to the Markdown policy format. A document in an old format (headings, no clause IDs) can be imported: headings become clauses, an existing clause ID is reused when the title matches, new IDs are proposed and the admin ticks that every ID was checked (E-97).
- FR-54 (built) Every draft is checked. **Errors** block publishing (front matter, loan type, version label new and later, clause headings, clause prefix, duplicates, empty clauses, a clause a rule cites is missing, instruction-like text, personal data). **Warnings** need a tick (a number a linked rule uses is gone from its clause, E-92; a clause looks renamed; a source tag changed; a very long or short clause; more than half the clauses change; a past or far date). **Auto-fix** offers formatting fixes only (heading form, source tag spelling, spaces, quotes, missing front-matter fields, the next version label), shown before and after, applied only when the admin chooses; it never changes a clause's words or numbers.
- FR-55 (built) Before publishing, the admin sees the clause-by-clause comparison with the version in force (word by word) and must run the **retrieval check**: the development evaluation questions for that policy run against the version in force and the draft. Citation validity below 100% blocks; a lower score is a warning. Publishing needs a written reason and a second click. A future effective date schedules the version; it becomes active on that date (E-95).
- FR-56 (built) A published version is never edited or deleted. History reads and compares any two versions, restores an older text into a new draft (published like any change), and retires a scheduled or replaced version. The version in force cannot be retired (E-99). A case uses the versions in force when it starts (E-91); its report keeps the clause text it cited and records the versions.
- FR-57 (built) When a published change alters a clause that an approved precedent's rules use, the precedent is paused until the admin confirms it again or retires it (E-98). Learnings shows each precedent's status, expiry, use count, last use and the cases it lifted. Retiring and confirming again need a reason and a second click.
- FR-58 (built) Every step is in the audit log: draft saved or discarded, published, activated, retired, re-indexed, precedent paused, confirmed again or retired.

### 9.6 Customer contact messages (Stage 9, built 2026-11-02)

- FR-21 After a case is confirmed, overridden or stopped, the officer can draft a message to the customer. Templates plus a **blank** option. The officer reviews, clicks Send and confirms in a second dialog.
- FR-22 A message carries **no confidential data and no outcome hint**: no name, score, status, missing item or reason. It has one neutral subject, a short generic body, an optional case reference, the officer's name, email and phone, and a fixed fraud warning (bank staff never ask for an OTP, PIN or password). It is a no-reply message.
- FR-23 A code check blocks a send that contains forbidden content (PAN or Aadhaar patterns, account or phone numbers, scores, rule IDs, outcome words such as approved or rejected, a request for an OTP, PIN or password) or lacks the footer. The block shows the reason.
- FR-24 v1 delivery is a terminal log and a Sent Items list (sent, failed, blocked) per officer. Failed sends can be retried. Every draft, edit, send, block and failure is in the audit log.
- FR-25 The fraud footer is added by code and cannot be edited out.
- FR-26 (issue reports) An officer can report a problem to the admin: case reference (optional text; when given it must be one of that officer's own cases, else 422, the same answer for a number that does not exist and one that belongs to someone else), category and short text. The same personal-data patterns (PAN, Aadhaar, phone, account number, email) refuse the report. The officer sees only their own reports; the admin reads and closes all of them in an inbox that holds no case data. Filed, read, closed and refused reports are audited.
- FR-27 The officer's phone number is optional on the user record (set by the officer in the draft dialog) and the customer email is an optional field on the primary applicant, kept out of the application the pipeline reads.

### 9.7 Guardrails

- Input: upload checks, prompt-injection scan (document text is data, never instructions), PII masking with regex rules (PAN, Aadhaar, phone, account numbers, email).
- Output: strict JSON schema (Pydantic), citations required, banned terms and protected attributes blocked, "recommend" wording enforced.
- Failed check: retry once, then mark unverified. Custom code in v1; NeMo Guardrails or Guardrails AI later if needed.

### 9.8 Applicant upload link (Stage 10, Part C built 2026-11-04)

- FR-32 (built) The officer, or the admin naming an officer, creates a link for one officer. It is valid for 7 days (configurable), the officer can extend it, and the officer or admin can disable it at any time with a second click. The token is random (128 bits or more), stored only as a hash and shown once.
- FR-33 (built) The applicant page needs no account. It collects the request (loan type if not preset, amount, tenure, purpose, employment type, declared income) as the applicant's own statement, shows a live checklist for the loan type, accepts a zip, folder or files, warns when items are missing but allows sending as "incomplete", and finishes with "Send to the bank" behind a second click and a reference number.
- FR-34 (built) The page never reads back a file, a score, a status or an outcome. A wrong, expired or revoked token gets one generic answer. Rate limits and size caps apply per link and per address.
- FR-35 (built) The case appears in the chosen officer's queue as "From applicant". The officer can correct the request (audited) until they open and edit the form; after that the link accepts files only. Missing items are shown to the applicant on the same link; the Stage 9 message never lists them. A new "Upload link" template carries only the link and the usual footer.
- FR-36 (built) Uploaded files stay on local disk with a database reference behind a `FileStore` interface; only the assigned officer and the admin can open them, through the authenticated API.

### 9.9 AI control (admin only, built 2026-11-18)

- FR-37 (built) The admin has an AI control page with four tabs: **Models** (per role a first-choice model and up to three fallbacks, chosen from the providers in `llm_models.yaml`; retries, timeout and cooldown), **Keys** (whether each key is set in `.env`, and a test button), **Prompts** (the editable part of each of the six prompts) and **Settings** (model switch, temperature and output length per role). Officers and the auditor cannot open it.
- FR-38 (built) API keys stay in `.env`. The page shows only "set" or "missing" and the variable name; it never shows, stores or returns a key, and a test returns only ok, latency and the error class.
- FR-39 (built) A model or setting change needs a written reason (10 characters or more) and a second click. Every model that is new for a role is tested with a real call first; a failed test or a missing key refuses the change. The judge may not be the same model as the Decision step. Each change is a new immutable version; rolling back copies an old version into a new one. Every change is in the audit log with what changed (provider ids and numbers only).
- FR-40 (built) A prompt has an **editable part** (role and style) and a **locked part** (data is not instructions, no arithmetic, "recommended" wording, no protected attributes, the reply format) that always comes from the file in git and is added after the editable part. A draft is saved freely, must pass a test on a fixed synthetic sample (the real schema and guardrails) and is then published with a reason and a second click; any edit after the test clears the pass. Older versions, and the original text, can be restored the same way.
- FR-41 (built) A change applies to cases that start after it. A case that is already running keeps the configuration it started with; the report records the configuration version and the prompt versions it used.
- FR-42 (built) The page cannot change scoring weights, bands, hard rules, the age cap, masking, the output schemas or the guardrails. Switching the models off makes every step write its text in code, exactly as an offline run does.

### 9.10 In-app notifications (Notifications Part 1, built 2026-11-19)

- FR-43 (built) Officers and admins have an inbox: a bell with the unread count in the top bar, an Inbox entry in the sidebar with a badge, and a page (`/inbox`, `/admin/inbox`) with an unread filter, a type filter (five groups, only those a role can receive), a case-number search, mark read, mark all read and a click through to the case (or the Issues or Precedents page). The count refreshes every 60 seconds and when the window gets focus; there are no websockets, no Celery and no Redis. The auditor has none (403 on every route).
- FR-44 (built) A notification carries only a kind, a short fixed title and body from a table in code, the case reference (CASE-YYYY-NNNN) and a link to a page of the app. It never carries a name, PAN, Aadhaar, phone, email, amount, score, band, rule or outcome; the personal-data patterns of the message check run over every text as a safety net (loud in dev and tests, logged and dropped in production).
- FR-45 (built) A notification is written in the same transaction as the event it reports, so the two cannot drift apart. The officer is told when: the applicant presses Send (also a second time, with its own title), a request arrives from an upload link, a run is ready for the decision, a run stops on a fix, the admin corrects their decision, a case is reassigned to them, a precedent they proposed is added or not added, an upload link ends within a day while the applicant still owes files, a customer message could not be sent. Every active admin is told when: an issue report is filed, a precedent waits for review, a precedent was held by the code check. Overrides, uploads one by one and failed runs are not notified.
- FR-46 (built) A person reads and changes only their own rows (another person's id is a 404). No delete in v1.

### 9.11 Real email (Notifications Part 2, built 2026-11-19; decision 17 changed by the user)

- FR-47 (built) With `NOTIFICATION_SENDER=smtp` messages really go out by email over SMTP (Resend in the demo, Mailpit while developing; any SMTP server by settings only). `console` stays the default and prints as before. A wrong setup refuses to start and names the variable, never a key.
- FR-48 (built) Only addresses on `EMAIL_ALLOWLIST` receive real email. Any other address goes to `EMAIL_REDIRECT_TO` (a demo inbox, the intended recipient masked in the subject) or, with no redirect, is printed and not sent. The redirect address must itself be on the list. Data is synthetic, so no email can reach a stranger.
- FR-49 (built) The officer's contact request and the upload-link message really send; Sent items shows how each went out (by email, to the demo inbox, printed). The content check, the fraud footer and the second click are unchanged. No receipt email goes to the applicant.
- FR-50 (built) Staff get fixed-text emails with no case details: "you have a new notice, sign in" (at most one per person per 30 minutes, each person can turn them off in the user menu, new accounts start as `STAFF_EMAILS_DEFAULT` says), "your account is ready" and "your password was reset". **A password is never emailed**: the admin still hands it over. The auditor gets none.
- FR-51 (built) Staff email is queued in the transaction of its event and sent after the commit by a loop in the app (no Celery or Redis), three tries, then failed. Every outcome is in the audit log with a masked address.
- FR-59 (built, Notifications Part 3, 2026-11-21) Hardening: staff email is sent one per transaction (one bad email can never cause another to be sent twice), a failed email waits 1 and then 5 minutes before the next try, the SMTP sender refuses a malformed address before connecting, and email outcomes are counted for the dashboards. A browser test covers the inbox and the email choice. A real send to Resend stays a manual check by the user.

### 9.12 Post-demo features (Stage 12, planned 2026-11-25)

Picked by the user from the project manager's and CEO's review. Built in parts A to E (`IMPLEMENTATION_PLAN.md` Stage 12); scoring, weights, bands and hard rules do not change.

**Part A: counter-offer and alternate product**

- FR-60 A report may carry one small **counter-offer box**, shown only when **all** of these hold:
  - the band is reject or refer;
  - the run did not stop on a fix-type rule, or on an eligibility rule other than age at maturity;
  - points were lost on rules that amount or tenure can move (FOIR, tenure, amount, LTV, loan-to-turnover, education repayment, collateral and margin);
  - a changed amount or tenure really moves the band up;
  - the suggested amount is at least half of the amount asked.

  It is never shown on approve cases, on refer cases held by a cap rule (PL-CIBIL-02, CM-FRD-01, BL-CRD-20) when the line would aim at approve, on KYC or fix-type stops, or on eligibility stops other than age.
- FR-61 The box is worked out **in code** (`scoring/counter_offer.py`), never by a model.
  - It rescores the case's own checked input with the normal rules engine, changing only the loan amount and the tenure; everything else (including a precedent bonus the run got) stays as checked.
  - EMI is at the rules-file rate.
  - The tenure never passes the product's tenure rule or age 55 at maturity for any applicant or co-applicant.
  - At most two lines: (a) the same amount over the shortest longer tenure that alone moves the band; (b) the largest smaller amount (₹10,000 steps, at least 50% of the amount asked) at the longest allowed tenure that moves the band further than (a), or at all when there is no (a).
  - Each line gives the amount, tenure, EMI, FOIR and the band it would get.
- FR-62 When the run stopped only because an applicant would be over 55 at maturity, income was never checked, so no band is given. The box shows at most "a tenure up to N months keeps every applicant at 55 or under at maturity" (for education N includes the moratorium).
- FR-63 When the purpose clearly fits **another** of the five loan types, the box adds one line for it. "Clearly fits" means exactly one product's keyword list in the rules file matches, and that product accepts the applicant's employment type. The line gives:
  - the indicative EMI and FOIR at that product's rate and longest tenure;
  - the extra documents a new application needs, from the rules file.

  It is labelled "a new application, not scored" and is shown only if its FOIR is better than the case's, and only inside a box that already shows an amount or tenure line (never on its own).
- FR-64 The box is computed when the report is made and stored with it (audited, the same every time). It is shown on the report screen to the officer and the admin, and in the officer's report PDF (the admin view has no PDF export). It is not part of the model-written summary or any prompt, and it never reaches a customer message: the existing message check blocks its text. Wording: "Pramaan estimates ₹6.2L over 5 years would be recommended for refer (FOIR 39.7%)". Never "approved" or "eligible for".

**Part B: Insights**

- FR-65 An **Insights** page, counted by code (SQL) from the database with no AI. Filters: a date range (cases created in it) and a loan type. It shows:
  - **time to decide:** created → report ready → officer decision; median and slowest; per loan type and per officer;
  - **the funnel:** created → documents complete (submitted) → report ready → decided (confirmed, overridden), and where open cases are stuck;
  - **officer agreement with the recommendation:** confirmed against overridden, by loan type and band; admin corrections counted separately;
  - **override insights:** the rules that failed in overridden cases, with the direction (for example refer → approve) and the rule's policy clause;
  - **top stop reasons**, for example "12 cases stopped at KYC for CM-KYC-03";
  - **precedent use:** how many cases an approved precedent's bonus reached, and how many it moved to another band.
- FR-66 **Access.** The admin sees the full page with links to the cases and to the clauses. The auditor sees the same charts and counts with no case reference or link (decision 9). An officer sees only their own numbers, on Home: their overdue count and their median time to decide. They never see another officer's numbers.

**Part C: queue export and decision timers**

- FR-67 **Queue export as CSV** (opens in Excel; no new package).
  - Officers export their own queue with the filters they have set; the admin exports all cases.
  - Columns: case reference, loan type, status, band, score, officer, created, updated, officer decision, SLA due, overdue. No applicant names.
  - Cells that a spreadsheet would run as a formula are written as text.
  - Every download is in the audit log.
- FR-68 **Decision timer (SLA).**
  - The officer should decide within **2 working days** (Monday to Friday; holidays out of scope) of the report being ready. `SLA_WORKING_DAYS` is one setting.
  - Each new report restarts the clock. Fix-type stops and cases waiting on the applicant are not timed. Reassignment keeps the due time. The officer's decision stops the clock.
  - The queue shows each case's age and "Due today" and "Overdue" badges.
- FR-69 **Reminders.** One in-app notice goes to the officer when a case becomes overdue, and one to the admins one working day later, each once per case. Staff emails follow the existing per-person switch and carry no case data. The check runs inside the app like the retention job (no Celery, no Redis). There is no auto-assignment.

**Part D: score breakdown**

- FR-70 For scored cases the report starts with a **waterfall chart**:
  - it starts at 100 and steps down by the points lost in each stage to the final score;
  - the 85 and 60 band lines are marked, a precedent bonus shows as a step up, and a cap is marked with its rule;
  - the backend sends the numbers and the screen only draws them;
  - it works in light, dark and system themes and has a text and table alternative for screen readers.

  A stopped case, with stages that did not run, shows no chart. The chart is on screen only; the report PDF's stage table gains a "Points lost" column from the same numbers.

**Part E: "Ask this case"**

- FR-71 The case's officer and the admin can **ask questions about one case** in plain words.
  - Retrieval finds the material and the model writes the answer from that material only. The sources are:
    - the case report (findings, rule IDs, stage scores, code-derived facts such as FOIR, EMI, LTV, CIBIL and age at maturity);
    - the masked extracted document fields;
    - the policy clauses for that loan type in the versions the run used, plus the clauses the report cites.
  - Nothing else is used: no internet, no other cases, no general knowledge, no precedents in this version.
  - Role `case_assistant`, Gemini Flash by default with the existing fallbacks, on the AI control page.
- FR-72 Every answer is a validated schema in which **every sentence cites** a rule ID, a clause ID or a document field.
  - Code checks that each clause was retrieved, each rule is the case's, each field exists, each number matches the case's own material, the wording rules hold and no raw identifier is present.
  - A failed check is retried once; then the answer is the fixed text "I can't answer that from this case's documents and policy."
  - The model does no arithmetic. A "what if" question points to the counter-offer box.
  - Citations open the clause, like the report's.
- FR-73 The chat is **read-only**: it cannot change a score, a status or a decision. Access is the case's officer and the admin only (another officer 404, the auditor 403). The question is masked and treated as data, never as instructions. A per-user hourly limit protects the free model tiers. With models off (`LLM_ENABLED=false` or the AI control switch) the page says that chat is off.
- FR-74 Questions and answers are stored per case and person (masked) and deleted by the retention job after `CHAT_RETENTION_DAYS`. Each model call is logged in `llm_calls` (stage `chat`) and traced in Langfuse (metadata only), and each question is in the audit log (never its text).

## 10. Evaluation

- **Online (every agent):** cheap code checks first. LLM judge only if the code checks are inconclusive. Failed check means one retry, then unverified.
- **Offline:** the answer-key runner on the golden set, run in GitHub Actions as a PR gate (band accuracy, stop-stage accuracy, score error, hard-rule integrity), and the judge runner `python -m app.eval.judge` run locally with the keys (faithfulness, citation support) (RAGAS and DeepEval were replaced by this runner, user decision 2026-11-21).
- **Fairness:** monitoring only. Approval rates by gender, age band and city tier are computed from a separate attributes table that agents and scoring cannot read. Never used in a decision.
- Judge model is a lighter model from a different family than the generator.

## 11. Data plan (synthetic)

100 cases, with an answer key per case (expected band, stop stage, flags).

| Loan | Dev | Test | Total |
|---|---|---|---|
| Personal | 13 | 9 | 22 |
| Home | 13 | 9 | 22 |
| Vehicle | 13 | 9 | 22 |
| Business | 13 | 9 | 22 |
| Education | 8 | 4 | 12 |
| **Total** | **60** | **40** | **100** |

- Score targets spread over roughly 30, 40, 55, 67, 85, 98 and 100.
- Scenarios: clean, borderline, hard fail (mismatch, invalid ID, missing KYC), risk (high FOIR, low CIBIL, cheque returns, irregular salary), tampered documents, missing documents, co-applicant cases (home and education).
- Formats: digital PDFs, photos (rendered, then blur, tilt, shadow), a few scans, 3-4 bank statement styles. A few password-protected files for upload tests.
- Indian names, cities and employers, all invented. PAN and Aadhaar generated to pass format and checksum rules. No real numbers.
- Public policy text where it exists; otherwise our own replica text, marked `sample`.
- Small unit-test fixtures are kept separate from the 100 cases.

## 12. Non-functional requirements

- **Security:** synthetic data only, masking before cloud LLM calls, role-based login, audit log, secrets in `.env`, no PII in logs or traces (see `SECURITY.md`).
- **Free-tier limits:** Gemini, Groq and NVIDIA free tiers rate-limit. LiteLLM routes to a fallback model on 429 or errors. Use different providers per agent to spread quota.
- **Performance targets (to be tuned):** a clean case completes in a few minutes; upload checks respond in seconds.
- **Reliability:** pause and resume through LangGraph checkpoints in Postgres.
- **Explainability:** every finding links to a rule ID and a policy clause.
- **Portability:** local development first; Docker Compose at the final stage; hosted Neon database means moving online later is a connection-string change.

## 13. Technology (summary)

| Layer | Choice |
|---|---|
| Frontend | React, JavaScript, CSS (Vite) |
| API | FastAPI |
| Agents | LangGraph (fixed routing, human-in-the-loop, Postgres checkpoints) |
| LLM gateway | LiteLLM (fallback, token and cost logging) |
| Models | Supervisor, Extraction, Decision: Gemini Flash. KYC and Risk: Groq gpt-oss-20b. Policy: NVIDIA Nemotron. Case assistant chat (Stage 12, planned): Gemini Flash. Fallback: another free NVIDIA or similar model. Verify exact model names and free limits at build time. |
| Database | Neon hosted Postgres + pgvector (relational and vector data in one place) |
| Embeddings and rerank | BGE-small (384 dimensions), local; local cross-encoder reranker |
| RAG | Retrieval, rerank, grounding check (Self-RAG style) |
| OCR | PaddleOCR local, Tesseract fallback |
| Parsing | PyMuPDF, pdfplumber, OpenCV |
| Evaluation | Own runners: answer key, retrieval, judge model (RAGAS and DeepEval replaced, 2026-11-21) |
| Observability | Langfuse (cloud if quick, else local), Prometheus, Loki, Tempo, Grafana |
| CI and Git | GitHub Actions, trunk-based, model versions tagged with releases |
| Deployment | Docker Compose at the last stage |

Detail is in `ARCHITECTURE.md`.

## 14. Success criteria

- A loan officer can run all five loan types end to end on synthetic cases.
- Answer-key agreement on the 40 held-out test cases meets the targets set after the dev baseline (see `TESTING.md`).
- Every report cites rule IDs and policy clauses, and every citation is verifiable.
- Hard-fail cases stop at the right stage.
- An override produces a reviewed precedent that is retrieved on a similar later case.
- Token, cost and latency per agent are visible per case.
- Demo script runs without manual fixes.

## 15. Assumptions and open items

| ID | Item | Current handling |
|---|---|---|
| OI-1 | "No applicant above 55": confirmed as a cap for every applicant and co-applicant. The exact meaning (age at application or at maturity) was not stated. | **Resolved 2026-11-02:** user confirmed age at maturity ≤55, including the education parent co-applicant (shorter tenure is intended, see E-35). Value stays configurable in the rules file. |
| OI-2 | DPO, TRL, Colab and tuned Qwen from the original idea | **Resolved 2026-10-31:** removed. No training, no local LLM, API only. Learning is precedent-based with admin approval. |
| OI-3 | Size of the precedent bonus and similarity threshold | Design settled 2026-11-02: the Policy agent only finds matches; code turns them into capped bonus points (see E-36). The values (`bonus_max` 5, `similarity_min` 0.80) are still placeholders; tune on dev data after the real-model baseline, then lock (Stage 7 plan step 6). |
| OI-4 | Langfuse cloud versus self-hosted | **Resolved 2026-11-23:** cloud. User added the keys to `.env` on 2026-11-02 and confirmed on 2026-11-23 that traces appear in Langfuse cloud. Not self-hosted in the Compose stack. |
| OI-5 | Exact free model names and rate limits | **Resolved 2026-10-31** (verified live, see `docs/AGENTS.md` section 7 and `backend/app/services/llm_models.yaml`). Gemini Flash is `gemini-3.6-flash` (2.5 Flash is closed to new users); Groq `openai/gpt-oss-20b` allows 1,000 requests/day but only **8,000 tokens/minute**; NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` at about 40 requests/minute shared across models; fallback OpenRouter free (20 requests/minute, 50/day). |
| OI-6 | Fairness groups | **Resolved 2026-11-02:** gender, age band, city tier, logged in `fairness_attributes` for monitoring only. Never an input to scoring, agents or RAG; a flagged gap is a prompt to review, not proof of bias (see E-37). |
| OI-7 | Targets for evaluation metrics | Deferred by user decision (2026-11-02): no hard accuracy or latency targets until the first real-model baseline run; then lock thresholds. Fixed from day one: citation validity 100%, hard-rule integrity 100%, zero raw PII in LLM inputs (see E-38). |

## 16. Not done yet (by design)

Stages 1 to 9 are built. Stage 10 (intake desk, identity from the cards, applicant upload link, several documents in one PDF) is built; the AI control page for the admin (Stage 10b, 2026-11-18) is built. In-app notifications Part 1 (inbox for officers and admins) and Part 2 (real email over SMTP) are built (2026-11-19); the knowledge base (Stage 10c: policy versions, drafts, checks, learnings) is built (2026-11-21); notifications Part 3 (hardening and close-out) and Stage 11 (hardening, Docker, demo) are built (2026-11-21); the real-model test-split run is left to the user. 2-step verification for the admin and the auditor is built (2026-11-24). Stage 12 (post-demo features, section 9.12) was planned on 2026-11-25; Part A (counter-offer box) is built, Parts B to E are not started. Status is tracked in `PROGRESS.md`.
