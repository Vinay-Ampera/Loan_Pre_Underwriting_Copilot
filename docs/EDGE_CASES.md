# EDGE_CASES

Only real edge cases live here: situations where the obvious behaviour is wrong or a naive
implementation fails. Routine features belong in the stage docs, not in this file. Add a row when
a new edge case is found or decided; do not re-implement a case already marked `done`.

Status: `done` (built and tested), `planned` (a later stage owns it; the stage is named), `open` (decision needed).

| ID | Edge case | Handling | Where | Status |
|---|---|---|---|---|
| E-01 | The same document is uploaded more than once | Hash the file (exact repeat, ignored). Then compare a content key of type + person + period (rescan or re-export, ignored). Same key but different amounts: keep both and raise `DUPLICATE_CONFLICT` as a tamper hint. File names are never used. | `intake/duplicates.py` | done (Stage 2) |
| E-02 | Payslips for different months, or a co-applicant's documents, look alike | The key includes the period and the person's PAN, so they are never duplicates. A document whose key cannot be built (OCR missed a part) is never called a duplicate. | `intake/duplicates.py` | done (Stage 2) |
| E-03 | Duplicates must not fill a missing-document slot | Completeness counts `CaseDocuments.unique_count`, not uploads. | `scoring/facts.py` (`_docs`) | done (Stage 3 counts one document per `content_key`; Stage 5 supplies the key from `CaseDocuments`) |
| E-04 | Storing the hash and ignoring a duplicate across requests | Save `sha256` in `documents` (column already exists) and rebuild `CaseDocuments` from accepted rows for the case. | case storage | planned (Stage 6 API) |
| E-05 | Officer replaces a rejected or wrong file | Explicit "replace": old row kept in the audit log, new row becomes active. A rejected upload is never recorded, so re-uploading the fixed file is not a duplicate. | API + audit log | planned (Stage 6) |
| E-06 | Password-protected PDF | Rejected at upload; the password is never requested or stored. | `intake/upload.py` | done (Stage 2) |
| E-07 | Applicant photo (passport size) has no text and almost no edges | Images under 500 px on the short side get no blur or crop verdict, so they are not rejected as blurry. | `intake/upload.py` | done (Stage 2) |
| E-08 | Photographed page is cut off | Page aspect ratio outside 1.30 to 1.55 is rejected as cropped. | `intake/quality.py` | done (Stage 2) |
| E-09 | OCR misreads digits and separators ("10.600.00", "07:08/1987", "O" for 0) | Tolerant money and date parsers; PAN/Aadhaar checksums cap the confidence of any misread id. | `intake/fields.py`, `checks.py` | done (Stage 2) |
| E-10 | Badly degraded photo: labels not found | Fields stay empty and the officer sees `missing_required_fields`; nothing is guessed. About 30% field accuracy on the generator's "poor" photos. | `intake/pipeline.py` | done (Stage 2) |
| E-11 | Prompt injection inside a document | Flagged `possible_prompt_injection`; text goes to the model only as masked data; scores are code. | `intake/injection.py` | done (Stage 2) |
| E-12 | Payslip net pay vs bank credits, odd large credits | Functions exist; the Risk agent calls them with both documents. | `intake/tamper.py` | planned (Stage 5) |
| E-13 | Payslip whose totals do not tie out (net printed higher than gross minus deductions) | That payslip is left out of the income average (used only if every payslip is like that); `totals_tie_out` is false, so the Documents score drops. | `scoring/facts.py` | done (Stage 3) |
| E-14 | A KYC document is missing, so PAN or Aadhaar checks have nothing to check | Reported once, by CM-DOC-01 (fix-type). The checks that need the document are not run, so the officer is not shown the same gap three times. | `scoring/engine.py` | done (Stage 3) |
| E-15 | Payslip or ITR income higher than the bank credits support | The lower, bank-supported figure is used for income and FOIR, and `INCOME_EXCEEDS_BANK_CREDITS` is raised as a strong tamper hint (CM-FRD-01 caps the case at refer). | `scoring/facts.py` | done (Stage 3) |
| E-16 | No bureau record for the earner | Treated as unverified: the CIBIL floor rule fails (eligibility-type), never a crash and never a silent pass. | `scoring/evaluate.py` | done (Stage 3) |
| E-17 | Inflated ITR income on a business loan | Bank credits for a business are far above profit, so the bank cross-check cannot expose it; only intake's PDF-metadata hint does. The case is still capped at refer, but income verification (CM-INC-12) can overstate. Known gap, found by SYN-BL-D13. | `scoring/facts.py` | open (accepted for v1) |
| E-18 | Intake's measured quality for mild photos (80) lands in a better scoring tier than the generator's design target (72) | The replay uses the key's design values. Before Stage 5, either recalibrate `CM-DOC-11` / `CM-KYC-13` tiers or the quality score, then rerun the dev replay. | `scoring/replay.py` | open (decide at Stage 5) |
