---
doc_id: policy-common
loan_type: common
title: Sample Bank Common Credit Policy
version: "2026.10.31-1"
effective_from: 2026-11-01
---

# Sample Bank: Common Credit Policy

Sample policy for a synthetic bank. Modelled on public criteria of large Indian banks and on RBI rules. It is not any bank's actual policy. Each clause has an ID and a source tag: `public`, `RBI` or `sample`.

## CM-KYC-01 | RBI | PAN or Form 60
Every applicant and co-applicant must give a PAN in the valid format, or Form 60 where the person has no PAN. A PAN that fails the format check is a fix-type failure: the case stops and the officer corrects the data.

## CM-KYC-02 | RBI | Aadhaar
Aadhaar is voluntary and is accepted only in redacted form. When given, it must be 12 digits, start with 2 to 9 and pass the Verhoeff checksum. Only the last four digits are stored or shown.

## CM-KYC-03 | sample | Name and date of birth must agree
The name must match across PAN, the identity proof, the income documents and the application form, with a fuzzy match score of at least 85. The date of birth must match on every document. A mismatch is a fix-type failure. A higher match score earns more KYC points.

## CM-KYC-04 | sample | Identity lookup
The applicant's PAN, name and date of birth are checked against the identity service. A confirmed match earns KYC points. The lookup uses synthetic records in this project.

## CM-KYC-05 | sample | Address match
The address on the application form is compared with the address on the identity proof. A close match earns KYC points; a weak match is flagged for the officer.

## CM-DOC-01 | sample | KYC documents must be present
PAN, Aadhaar (or another officially valid document) and a photograph are required for every applicant and co-applicant. A missing KYC document is a fix-type failure: the case stops until it is uploaded.

## CM-DOC-02 | sample | Mandatory documents per loan type
Each loan type lists mandatory documents in the rules file. A missing non-KYC document does not stop the run; it is flagged and lowers the Documents score.

## CM-DOC-03 | sample | Document quality
Documents must be legible. Badly blurry or cropped images are rejected at upload with a request to re-upload. Borderline quality is accepted with a warning. Low-confidence extracted fields are flagged to the officer and never guessed.

## CM-DOC-04 | sample | Totals must tie out
Net pay equals gross pay minus deductions. Bank statement running balances must be consistent. Documents whose totals do not tie out lose Documents points and are checked for tampering.

## CM-ELIG-01 | public | Indian resident
The applicant must be an Indian resident. A non-resident application is out of scope and the recommendation is to reject.

## CM-ELIG-02 | public | Minimum age
The minimum age at application is 21 years for every applicant and co-applicant. Below this, the recommendation is to reject.

## CM-ELIG-03 | sample | Maximum age at maturity
The age of every applicant and co-applicant at loan maturity must not exceed 55. The tenure may be shortened so that this holds. Above 55 at maturity the recommendation is to reject. The exact reading (age at application or at maturity) is open item OI-1 and is configurable.

## CM-FRD-01 | sample | Suspected tampering
Signs of tampering include a PDF edited with an editing tool, round-number or arithmetic-inconsistent salary, provident fund out of line with pay, a payslip with no matching recurring bank credit, and odd-date credits from individual accounts with no TDS. Suspected tampering sends the case to refer. It is never passed silently.

## CM-INC-01 | sample | Fixed obligations to income ratio (FOIR)
FOIR is the total monthly obligations including the proposed instalment divided by net monthly income, computed by the scoring code. The cap is 50 percent. At 40 percent or below the case earns full marks; between 40 and 50 percent it earns partial marks; above 50 percent it earns none and is flagged. For co-applicant cases the FOIR is combined.

## CM-INC-02 | sample | Income by employment type
Salaried income is verified from payslips, Form 16 and salary credits in the bank statement. Self-employed income is verified from income tax returns and bank statement credits.

## CM-INC-03 | sample | Declared versus verified income
The verified income is compared with the declared income on the application form. A close match earns points; a large gap is flagged.

## CM-INC-04 | sample | Income regularity
Regular monthly salary or business credits earn points. Missing or irregular months lose points.

## CM-CRD-01 | public | Credit bureau score
The credit score comes from the credit bureau service. Higher scores earn more points; each product has a floor below which the recommendation is to reject.

## CM-CRD-02 | sample | Cheque and NACH returns
Returned cheques and NACH mandates in the last 12 months are counted from the bank statement. No returns earn full marks; each further return lowers the points.

## CM-CRD-03 | sample | Repayment behaviour
The worst days-past-due on existing loans in the last 12 months is taken from the bureau record. No delay earns full marks.

## CM-CRD-04 | sample | Recent credit enquiries
Many credit enquiries in the last six months suggest credit hunger and lose points.

## CM-RBI-01 | RBI | Written reason for rejection
Whenever the recommendation is to reject, the report includes a plain-language written reason. The final decision is made by a human.

## CM-RBI-02 | RBI | Bureau data retention
Credit bureau data is kept for no longer than six months without fresh consent from the applicant. A nightly job removes expired snapshots.

## CM-RBI-03 | RBI | Key Fact Statement
Under the Digital Lending Directions in force from 8 May 2025, the borrower is given a Key Fact Statement with the loan terms, the annual percentage rate and all charges before the loan is sanctioned.

## CM-RBI-04 | RBI | Foreclosure charges
For loans sanctioned or renewed from 1 January 2026, no foreclosure charges apply on floating-rate loans to individuals for non-business purposes. This clause is cited in reports and is not scored.

## CM-RBI-05 | sample | Fair treatment
Gender, religion, caste and similar attributes are never used in any assessment. Reports use the word "recommended" and never "approved" for an action the system takes. A human confirms every case.
