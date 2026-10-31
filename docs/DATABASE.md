# DATABASE

Neon Postgres with the `pgvector` extension. One database holds relational and vector data. LangGraph checkpoint tables are created by the library in their own schema. All data is synthetic.

Conventions: `id` is UUID primary key; `created_at` and `updated_at` are `timestamptz`; enums are Postgres enums or CHECK constraints; embeddings are `vector(384)` (BGE-small) with HNSW indexes.

## 1. Core case data

**users**
`id, name, email (unique), password_hash, role (officer|admin), active, created_at`

**cases**
`id, case_no (CASE-YYYY-NNNN, unique), loan_type (personal|home|education|business|vehicle), status (draft|uploaded|running|stopped|awaiting_confirmation|confirmed|overridden), created_by → users, loan_amount, tenure_months, purpose, form_data jsonb (type-specific fields), stopped_stage, stop_class (fix|eligibility|null), total_score (null if stopped), band (approve|refer|reject|null), recommendation, policy_version, rules_version, created_at, updated_at`

**applicants**
`id, case_id → cases, role (primary|co), full_name, dob, pan, aadhaar_last4, address, phone, employment_type (salaried|self_employed), employer_or_business, declared_monthly_income, relationship_to_primary, created_at`
Raw PAN and Aadhaar are synthetic. Full Aadhaar is never stored.

**documents**
`id, case_id, applicant_id, doc_type, file_path, original_name, mime, page_count, source_kind (digital_pdf|scanned_pdf|photo), sha256, upload_checks jsonb (blur_score, warnings), status (accepted|rejected), reject_reason, uploaded_at`

**extracted_fields**
`id, document_id, field_name, value_masked, value_local (nullable, encrypted at rest later), confidence, source_page, needs_review bool`

## 2. Pipeline results

**stage_runs**
`id, case_id, applicant_id (nullable), stage (extraction|kyc|policy|risk|decision), status (passed|failed|stopped|unverified), score, max_score, hard_fail bool, fail_class, findings jsonb, model_used, prompt_version, retries, fallback_used, started_at, finished_at`

**rule_results**
`id, stage_run_id, rule_id, kind (hard|soft), passed, points_awarded, points_max, evidence jsonb, clause_id`

**reports**
`id, case_id, version, summary_md, rejection_reason, report_json jsonb, pdf_path, created_at`

**eval_scores**
`id, case_id, stage_run_id, metric, value, method (code|judge), created_at`

**llm_calls**
`id, case_id, stage_run_id, provider, model, tokens_in, tokens_out, cost_usd, latency_ms, langfuse_trace_id, fallback_used, created_at`

## 3. Human actions and learning

**officer_actions**
`id, case_id, officer_id, action (confirm|override), original_recommendation, final_decision, reason (required for override), second_click_at, created_at`

**precedents**
`id, source_case_id, status (pending|held|approved|rejected|expired), loan_type, rule_ids text[] (rules involved), original_score, original_recommendation, final_decision, officer_reason, report_summary, embedding vector(384), proposed_by, reviewed_by, reviewed_at, valid_until, times_used, created_at`
`held` = failed the code-side hard-rule check; it never reaches the admin or RAG. A CHECK constraint stops a row becoming `approved` without a reviewer, review time, expiry date and embedding.
Index: HNSW on `embedding`; btree on `(loan_type, status)`.

**audit_log**
`id, actor_id, action, entity, entity_id, before jsonb, after jsonb, at`
Append-only; no update or delete grants.

## 4. Policy and rules

**policy_documents**
`id, loan_type (or 'common'), title, version, source_tag (public|RBI|sample), file_path, effective_from, active`

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

Alembic (`python -m app.db.migrate`), one migration per change, applied by CI on a throwaway database before merge. Roles are created `NOLOGIN` by migration 0005; an admin gives them a password by hand. Seed script `python -m app.db.seed` loads rules, policy chunks (embeddings come from the Stage 4 re-index), mock data and the answer keys. `python -m app.db.check` prints connection facts without exposing the URL.
