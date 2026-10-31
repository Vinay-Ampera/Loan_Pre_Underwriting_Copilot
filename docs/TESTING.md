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
- Small unit-test fixtures are separate and tiny.
- The **test split is held out**. It is run only at release and for the final report. Never tune on it.
- Each case has an answer key: expected band, expected stop stage, expected flags, target score.
- Score spread covers roughly 30, 40, 55, 67, 85, 98 and 100.
- Special files: password-protected PDFs, blurry and cropped photos, tampered documents, poisoned documents for injection tests.

## 3. Metrics

| Metric | Meaning |
|---|---|
| Band accuracy | Predicted band equals expected band |
| Stop-stage accuracy | Early-stopped cases stop where the key says |
| Score error | Absolute difference between predicted and target score |
| Field accuracy | Extracted fields equal ground truth (per document type) |
| Citation validity | Every cited clause exists in retrieved text (target 100%) |
| Faithfulness | RAGAS: answer supported by retrieved context |
| Retrieval quality | Recall at k and rerank quality on a query-to-clause set |
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
