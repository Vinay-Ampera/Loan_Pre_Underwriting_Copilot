# Demo script

A walk-through of Pramaan for a live demo, about 25 minutes. Every case is synthetic (`data/synthetic/output/cases`). Each scene lists what to click and what the audience should see. Scenes 1 to 4 are the core; the rest can be dropped to fit the time.

## Before the demo (once)

With Docker (README "Run with Docker"):

```
cp .env.example .env            # fill DATABASE_URL, JWT_SECRET and the model keys
docker compose up -d --build    # app on http://localhost:8000, Grafana on http://localhost:3000
docker compose exec app python -m app.api.users_cli create --email officer@pramaan.test --name "Asha Officer" --role officer
docker compose exec app python -m app.api.users_cli create --email admin@pramaan.test --name "Ravi Admin" --role admin
docker compose exec app python -m app.api.users_cli create --email auditor@pramaan.test --name "Meera Auditor" --role auditor
```

Without Docker: `make migrate`, `python -m app.db.seed`, `python -m app.rag.reindex`, the same `users_cli` commands from `backend/`, then `make backend` (it serves the built frontend; `cd frontend && npm run build` first).

Check before going live:

- `python -m app.services.llm_probe`: every model answers (or set `LLM_ENABLED=false` and say the text is written by code).
- One dry run of scene 1, so the local embedding and OCR models are warm (the first case of a fresh process is slower).
- Two browser windows: a normal one for staff, a private one for the applicant (scene 5).

## 1. Officer: a clean case, from files to a recommendation (5 min)

1. Sign in as the officer. Home shows the case tiles; the sidebar has New case, Cases, Upload links, Sent items, Inbox, Policies, Help.
2. **New case**: choose *Personal loan*, then *Start with the documents*. Drop the folder `data/synthetic/output/cases/SYN-PL-D02/documents/primary` (or *Choose a folder*).
3. The **intake desk** lists each file as received, with its type read from the content, and the checklist shows nothing missing. Point out that every file is read once and that the applicant's identity comes only from the PAN and Aadhaar cards.
4. **Continue to the application form**: name, date of birth, PAN, Aadhaar last four and address are filled *from documents*. Tick that they match the cards. Every claim field (amount, tenure, income, employer) is typed by the officer: copy them from `SYN-PL-D02/application.json`.
5. **Submit**. The stepper moves through KYC, Documents, Income and FOIR, Credit, Policy fit. Expected result: **Recommended: approve**, score about 85.
6. On the report, show:
   - the score ring;
   - the Credit, Capacity and Collateral strip ("Collateral: not checked" for a personal loan);
   - findings with rule ids, and a citation that opens the clause text;
   - "Awaiting your confirmation".
7. **Confirm** asks for a second click. The case is now confirmed. Nothing is ever approved without the officer.

## 2. Officer overrides a borderline case; the learning loop (5 min)

1. New case `SYN-PL-D03` (form first, then the files). Expected: **refer**, about 67.
2. **Override** to approve, with a written reason (for example "Stable employer for ten years; the dip in balance was a one-off medical bill"), and a second click.
3. The override becomes a **proposed precedent**. A code check runs first: an override over a hard rule would be *held* and never reach the admin.
4. Sign in as the admin (other window). The **bell** shows a new notice. **Precedents** lists the proposal with the model's masked summary. Approve it with an expiry date.
5. Point out the limits on a precedent:
   - it is used only for refer-band cases of the same loan type, above a similarity threshold;
   - its bonus is capped, it is never used over a hard rule, and it expires.

## 3. Stops: one the officer can fix, one that is final (3 min)

1. New case `SYN-PL-D10`, filling the form from `application.json`: the name typed on the form does not match the name on the PAN card. The run **stops at KYC (fix)** and names the mismatch.
2. In **Correct the details**, change the name to the one on the card, then choose **Save and resume assessment**. The run starts again at Extraction and finishes.
3. `SYN-PL-D09` has no PAN card in its folder. The intake desk lists it as missing, and the officer can choose **Ask the applicant for more** (scene 5 shows the link).
4. `SYN-PL-D12` stops for eligibility (credit score below the floor). The report recommends reject, with a written reason that cites the rule and clause.

## 4. Safety: masking and injected text (2 min)

1. Upload `data/synthetic/output/special/poisoned_1.pdf` to any case. The document asks the model to approve and set the score to 100. The score does not change, because scoring is code and document text is data.
2. On the case's audit tab, show that only ids and counts are recorded. Say why no model ever sees a raw PAN, Aadhaar, phone or account number: the text is masked before any model call, and the guard refuses the call otherwise.

## 5. Applicant upload link and a customer message (4 min)

1. As the officer, **Upload links** → create a link (a second click, because it is outward-facing); send it as a customer message (the template carries no name, status or outcome, plus the fraud warning) with a second click. With `NOTIFICATION_SENDER=console` it prints in the app log; with SMTP it goes to the demo inbox.
2. In the private window, open the link: the applicant fills in the short request, uploads the files of `SYN-VL-D02` and presses **Send to the bank**. There is no account and no status page.
3. Back as the officer, the **Inbox** has "The applicant sent their files". The case is on the intake desk, ready for the form.

## 6. Admin: policies, AI control and users (4 min)

1. **Knowledge base** → Business loan → **Change** clause `BL-ELIG-04` (turnover 36 lakh → 40 lakh). The check warns that rule `BL-INC-11` in the rules file still says 36 lakh (scoring numbers change only in the rules file, by hand).
2. Run the **retrieval check**, then publish with a reason and a second click. History keeps every version; nothing is deleted. Cases already running keep the version they started with.
3. **AI control**: the models per role and the key status (set or missing, never the key). Prompts have a locked part that the page cannot change.
4. **Users**: add an officer. The account email never carries a password.

## 7. Auditor and dashboards (2 min)

1. Sign in as the auditor: Overview counts, the Cases table and the audit log. The auditor sees no case, document, report or message, and can change nothing.
2. Grafana (http://localhost:3000), dashboard *Loan Copilot*:
   - cases and recommendations;
   - AI cost and tokens per case, time per step and per agent;
   - backup-model use;
   - row 6: applications per day, time to decision, override rate and staff email.

## If something goes wrong

- **A model is slow or rate limited:** the run uses the fallback models; the report says which. With `LLM_ENABLED=false` every text is written by code, and scores do not change.
- **The first OCR file is slow:** the local OCR model loads once per process.
- **A case is stuck as running after a restart:** the app continues it from its checkpoint on start.

## Numbers to quote

From `docs/PROGRESS.md` "Stage 11 build notes": the final test-split results (40 held-out cases), the dev-split baselines and the test counts.
