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

## 7. Regression practice

- Every bug gets a failing test first.
- Changing a rule threshold needs the golden set rerun and a note in the PR.
- Changing a prompt bumps its version and reruns the golden set.
- Record baselines in `docs/baselines/` (JSON) so changes are visible.

## 8. Demo checks (Stage 8)

- Clean case per loan type completes with report.
- Hard-fail case stops at the right stage with a short report.
- Password-protected upload rejected.
- Override, admin approval, similar case re-run shows the precedent.
- Forced model failure triggers fallback; case still completes.
