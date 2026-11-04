# DATABASE

Neon Postgres with the `pgvector` extension. One database holds relational and vector data. LangGraph checkpoint tables are created by the library in their own schema (`langgraph`, created by `app/agents/checkpoint.py` on first use; one thread per case, `thread_id` = `cases.id`). All data is synthetic.

Conventions: `id` is UUID primary key; `created_at` and `updated_at` are `timestamptz`; enums are Postgres enums or CHECK constraints; embeddings are `vector(384)` (BGE-small) with HNSW indexes.

## 1. Core case data

**users**
`id, name, email (unique), phone (nullable; added in migration 0010), password_hash (argon2), role (officer|admin|auditor; auditor added in migration 0011, one active at most via a unique partial index), active, failed_logins, locked_until, created_at, updated_at`
Migration 0008 added `failed_logins` and `locked_until` (lockout after repeated failures, SECURITY section 4). Users are created with `python -m app.api.users_cli` or, from Stage 8, by the admin in the Users screen (`POST /admin/users`); the CLI password is typed at a prompt and the screen's temporary password is shown once. Neither is stored in a file or the audit log. Stage 8 added no migration.

**cases**
`id, case_no (CASE-YYYY-NNNN, unique), loan_type (personal|home|education|business|vehicle), status (draft|uploaded|running|stopped|awaiting_confirmation|confirmed|overridden), created_by → users, loan_amount, tenure_months, purpose, form_data jsonb (type-specific fields), stopped_stage, stop_class (fix|eligibility|null), total_score (null if stopped), band (approve|refer|reject|null), recommendation, policy_version, rules_version, created_at, updated_at`

**applicants**
`id, case_id → cases, role (primary|co), full_name, dob, pan, aadhaar_last4, address, phone, email (nullable; migration 0010, synthetic; kept only in this column, never in `cases.form_data`), employment_type (salaried|self_employed), employer_or_business, declared_monthly_income, relationship_to_primary, created_at`
Raw PAN and Aadhaar are synthetic. Full Aadhaar is never stored.

**documents**
`id, case_id, applicant_id, doc_type, file_path, original_name, mime, page_count, source_kind (digital_pdf|scanned_pdf|photo), sha256, upload_checks jsonb (blur_score, warnings), status (accepted|rejected), reject_reason, uploaded_at`

Stage 10 (built, migrations 0014 and 0015) adds to `documents`: `role` (primary|co, null until the file is filed to a person; it replaces the old join through `applicants` and is what the pipeline reads), `role_source` (auto|officer), `classification` (what the local classifier found) with `type_source` (detected|officer) beside `doc_type` (what the officer sees), `duplicate_of` (the document it repeats) with `duplicate_kind` (exact|same_document|conflict). `status` also takes `ignored`: a repeat is a row with no stored file. `applicant_id` is now `ON DELETE SET NULL`: saving a corrected form replaces the applicant rows and used to delete every uploaded file's row through the cascade (a bug found while building the desk; files are filed by `role` and re-linked after the save).

Next to each stored file the desk keeps a **read result** (`<file>.read.json`, behind the `FileStore` interface): the upload checks, the extracted fields, quality flags, tamper hints and missing fields, keyed by `sha256` and the application date. Extraction loads it instead of reading the file again. Raw page text is never stored. Not built (Part D, not started): `parent_document_id`, `page_from`/`page_to`.

`cases.loan_amount` and `cases.tenure_months` may be empty for a case opened at the desk (their `> 0` checks still hold for a value). `cases.status` also takes `applicant_submitted`. Desk and applicant data that are not columns live in `form_data`: `origin` (`applicant` when it came through a link), `request` (the applicant's own statement: loan type, amount, tenure, purpose, employment, income, earner role), `request_locked`, `applicant_sent` (`at`, `incomplete`, `reference`), `upload_link_id`, `intake` (`employment` per person, `co`, `proceeded`), `from_documents` (per person, the identity fields still exactly as the cards gave them) and `identity_confirmed`.

**upload_links** (built)
`id, token_hash (unique), officer_id → users, created_by → users, loan_type (nullable preset), case_id (nullable until the applicant sends the request; set at once for a link made from a case), created_at, expires_at, disabled_at, disabled_by, last_used_at, files_count, bytes_total`
The token (192 random bits) is never stored, only its SHA-256. `outbox` gains the template `upload_link` and `link_id` (which link a message carried, never its token). Both tables are granted to `app_rw` and `migrator` like the others.

**extracted_fields**
`id, document_id, field_name, value_masked, value_local (nullable, encrypted at rest later), confidence, source_page, needs_review bool`

## 2. Pipeline results

**stage_runs**
`id, case_id, applicant_id (nullable), stage (extraction|kyc|policy|risk|decision), status (passed|failed|stopped|unverified), score, max_score, hard_fail bool, fail_class, findings jsonb, model_used, prompt_version, retries, fallback_used, started_at, finished_at`
One row per (case, stage); a stage that runs again (resume, correction) replaces its row. `applicant_id` stays null: per-person detail lives in `rule_results.evidence.role` and the report sections. A stage that was not run (after a hard stop, or Policy beside a Risk stop) has no row. The Supervisor has no row (it scores nothing); its calls are in `llm_calls` with a null `stage_run_id`.

**rule_results**
`id, stage_run_id, rule_id, kind (hard|soft), passed, points_awarded, points_max, evidence jsonb, clause_id`

**reports**
`id, case_id, version, summary_md, rejection_reason, report_json jsonb, pdf_path, created_at`
`version` is the run number: 1 for the first run, +1 each time a correction re-runs the case (`Pipeline.resume_after_fix`). A node that runs twice replaces its own row (upsert on `case_id, version`).

**eval_scores**
`id, case_id, stage_run_id, metric, value, method (code|judge), created_at`

**llm_calls**
`id, case_id, stage_run_id, provider, model, tokens_in, tokens_out, cost_usd, latency_ms, langfuse_trace_id, fallback_used, created_at`

## 3. Human actions and learning

**officer_actions**
`id, case_id, officer_id, action (confirm|override), original_recommendation, final_decision, reason (required for override), second_click_at, created_at`

**admin_actions** (migration 0012)
`id, case_id → cases (cascade), admin_id → users, action (override), previous_decision, final_decision (approve|refer|reject), reason (not blank), second_click_at, created_at`
An admin's correction of an officer's decision, next to `officer_actions` (never edited). The latest row per case is the decision in force. Reassigning a case changes `cases.created_by` and is recorded in `audit_log` (`case_reassigned`, before and after officer names, reason). `report_ro` may read the table.

**precedents**
`id, source_case_id (nullable; cleared if the source case is deleted), status (pending|held|approved|rejected|expired), loan_type, rule_ids text[] (rules involved), original_score, original_recommendation, final_decision, officer_reason, report_summary, embedding vector(384), proposed_by, reviewed_by, reviewed_at, valid_until, times_used, created_at`
`held` = failed the code-side hard-rule check; it never reaches the admin or RAG. A CHECK constraint stops a row becoming `approved` without a reviewer, review time, expiry date and embedding.
Index: HNSW on `embedding`; btree on `(loan_type, status)`.

**outbox** (Stage 9, migration 0010)
`id, case_id → cases (cascade), sent_by → users, recipient_email, template (general_contact|contact_soon|visit_branch|blank), subject, body (the officer-editable part), final_text (the full text with contact lines and footer, set at send), case_ref_included bool, status (draft|blocked|sent|failed), block_reason (nullable), error (nullable), created_at, updated_at, sent_at`
`body` never holds case data by design (the content check enforces it); `final_text` is exactly what the customer received. Officers read only their own rows; the admin API returns counts only. Raw customer email is synthetic; every API view shows it masked. Retention: kept with the case.

**issue_reports** (Stage 9, migration 0010)
`id, reported_by → users, case_ref (nullable text CASE-YYYY-NNNN, not a foreign key, so the admin inbox cannot reach case data), category (bug|wrong_result|access|other), body, status (open|read|closed), created_at, read_at, closed_at`
Reports containing PAN, Aadhaar, phone, account number or email patterns are refused and never stored. Officers read their own rows; the admin reads all.

**user_sessions** (migration 0013)
`id, user_id → users (cascade), started_at, last_active, refresh_hash (SHA-256 of the current refresh secret), prev_refresh_hash, rotated_at, revoked_at, revoked_reason (logout|idle|max|reuse|inactive)`
One row per sign-in (SECURITY.md 4a). `last_active` moves only on `POST /auth/ping`, never on polling. Rows older than two days are deleted at the next sign-in; the audit log keeps the history. `app_rw` has full access; `report_ro` has none.

**audit_log**
`id, actor_id, action, entity, entity_id, before jsonb, after jsonb, at`
Append-only; no update or delete grants.

## 4. Policy and rules

**policy_documents**
`id, loan_type (or 'common'), title, version, source_tag (public|RBI|sample), file_path, effective_from, active, checksum (sha256 of the file), indexed_at`. One active version per loan type; a new `version` in a file's front matter adds a row and deactivates the old one. `policy_chunks.metadata` holds `source_tag`, `title` and `text_hash` (a clause is re-embedded only when the hash changes).

**policy_chunks**
`id, policy_document_id, clause_id, text, embedding vector(384), metadata jsonb`
Index: HNSW on `embedding`; btree on `clause_id`.

**rules**
`rule_id (pk), loan_type (or 'common' when a rule spans several), loan_types text[], stage (kyc|documents|income|credit|policy), kind (hard|soft), subject (each|case), roles text[], when_cond jsonb, field, operator ('tiers' for tier-scored rules), threshold, tiers jsonb, points, fail_class (fix|eligibility), on_fail (stop|cap_refer), policy_clause, source_tag, version, active`

**rule_set_versions**
`version, checksum, loaded_at, loaded_by`
Each report stores the policy and rules version used.

## 5. Mock services (synthetic)

- `mock_identity(pan, name, dob, aadhaar_hash, address)`
- `mock_bureau(pan, cibil_score, active_loans jsonb, enquiries jsonb)`
- `mock_gst(gstin, legal_name, pan, turnover_12m, filings jsonb)`
- `mock_udyam(udyam_no, legal_name, pan, registered_on)`

## 6. Evaluation and fairness

**test_cases**
`case_id (text key such as SYN-PL-D01), split (dev|test), loan_type, scenario, expected_band, expected_stop_stage, expected_flags jsonb, target_score, case_ref → cases (set when the golden runner creates a real case)`
Expected band is null for a fix-type stop; target score is null when the run stops early.

**fairness_attributes** (separate and isolated)
`case_id (→ test_cases), applicant_role (primary|co), gender, age_band, city_tier`
Used only by the monitoring report. Agents and the scoring code have no access; enforce with a separate database role and no joins in the pipeline.

## 7. Roles and access

| DB role | Access |
|---|---|
| `app_rw` | Read and write on case, pipeline, policy and precedent tables; no access to `fairness_attributes`; insert-only on `audit_log` |
| `report_ro` | Read-only on `fairness_attributes` and result tables for monitoring |
| `migrator` | Schema changes only, used in CI and setup |

## 8. Retention

- Bureau-derived data (`mock_bureau` snapshots copied into stage results) is deleted after six months unless consent is renewed (nightly job).
- Rejected uploads: file removed at once, row kept with reason.
- Audit log: kept for the life of the project.

## 9. Migrations

Alembic (`python -m app.db.migrate`), one migration per change, applied by CI on a throwaway database before merge. Roles are created `NOLOGIN` by migration 0005; an admin gives them a password by hand. Seed script `python -m app.db.seed` loads rules, policy chunks (embeddings come from `python -m app.rag.reindex`, which also records the policy and rules versions and writes an `audit_log` row), mock data and the answer keys. `python -m app.db.check` prints connection facts without exposing the URL.
