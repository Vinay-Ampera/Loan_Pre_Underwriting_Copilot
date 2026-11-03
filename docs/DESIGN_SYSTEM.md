# DESIGN_SYSTEM

Calm, readable, trustworthy. Built for bank staff who review many cases a day. The UI shows what the backend decides; it never computes scores. Brand: **Pramaan** (bank and product). Stage 8 (built 2026-11-02) restyles everything below; section 8 holds the design as built and overrides sections 2 and 6b where they differ. The section 2 table is the Stage 6 palette and is kept for history; the live values are in `frontend/src/styles/tokens.css` and section 8.1.

## 1. Principles

1. **Clarity over decoration.** Dense but scannable; one primary action per screen.
2. **Never colour alone.** Every status has a text label and an icon.
3. **Say "recommended".** The system never says "approved" or "rejected" as an action taken.
4. **Show the why.** Every score and finding links to its rule ID and policy clause.
5. **Honest states.** Stopped, unverified and low-confidence are shown plainly.

## 2. Tokens

| Token | Value | Use |
|---|---|---|
| `--ink` | `#1F2933` | Body text |
| `--muted` | `#52606D` | Secondary text |
| `--line` | `#D9DEE3` | Borders |
| `--surface` | `#FFFFFF` | Cards |
| `--bg` | `#F6F7F9` | Page background |
| `--primary` | `#2F6FDE` | Primary actions, links |
| `--approve` | `#1E7F4F` on `#E4F4E8` | Recommend approve |
| `--refer` | `#9A6200` on `#FFF1D6` | Refer |
| `--reject` | `#B03A36` on `#FDE3E1` | Recommend reject |
| `--stopped` | `#52606D` on `#EEF0F3` | Stopped, needs correction |
| `--unverified` | `#6B55B5` on `#EEE8FA` | Unverified by the system |

Typography: Inter. Sizes 12, 14 (body), 16, 20, 24. Weights 400, 600. Monospace for IDs (PAN masks, rule IDs).
Spacing: 4-pixel base (4, 8, 12, 16, 24, 32). Radius 8 for cards, 6 for inputs. Contrast at least WCAG AA.

## 3. Components

| Component | Notes |
|---|---|
| `CaseQueueTable` | Case no, applicant, loan type, status chip, score, age of case, assigned officer; filter and search |
| `StatusChip` | Label + icon + colour from tokens above |
| `LoanTypePicker` | Five cards at case creation |
| `ApplicationForm` | Common fields plus loan-specific section; co-applicant section for home and education. Required fields show `*`, optional ones show "(optional)", and a short note at the top explains both |
| `UploadZone` | Multi-file and one by one; per-file result: accepted, warning (blur), rejected (password, blur) |
| `DocumentChecklist` | Required vs uploaded per applicant; missing in amber |
| `DocumentViewer` | PDF and image viewer with extracted fields beside it; low-confidence fields highlighted |
| `StageCard` | Stage name, score out of max, status, expandable findings with rule ID and clause link |
| `ScoreBadge` | Total score and band; "not computed" when stopped |
| `FindingList` | Severity icon, text, evidence, citation |
| `ReportPanel` | Summary, stage cards, citations, rejection reason, export to PDF |
| `ConfirmBar` | "Confirm recommendation" and "Override"; each opens a second confirmation dialog |
| `OverrideDialog` | Required reason (minimum length), shows what the system recommended |
| `PrecedentReviewCard` | Original case summary, officer reason, LLM summary, similar existing precedents, Approve/Reject with expiry date |
| `AuditTimeline` | Chronological actions for a case |
| `EmptyState`, `ErrorState`, `Skeleton` | Consistent loading and failure states |

## 4. Screens

1. **Login**
2. **Case queue** (officer): filters, new-case button.
3. **New case:** loan type, application form, co-applicant section.
4. **Case workspace:** tabs for Documents, Extracted fields, Report, Audit. Upload happens here; "Submit for assessment" enabled once KYC documents are present.
5. **Report and confirm:** stage cards, citations, confirm bar at the bottom.
6. **Admin precedent queue:** pending precedents.
7. **Admin:** users; policy and rule file status, last re-index, version.
8. **Monitoring link:** opens Grafana (applications per day, time to decision, override trend, tokens and cost).

```
┌ Case workspace ─────────────────────────────────────────────┐
│ CASE-2026-0012  Personal loan   [Awaiting confirmation]      │
├──────────────┬───────────────────────────────┬──────────────┤
│ Documents    │ Report                        │ Score 72     │
│ ✓ PAN        │  KYC            18 / 20       │ REFER        │
│ ✓ Payslips   │  Documents      13 / 15       │              │
│ ! Statement  │  Income & FOIR  20 / 30       │ Recommended: │
│   (blurry)   │  Credit & risk  14 / 25       │ refer        │
│              │  Policy fit      7 / 10       │              │
│              │  Findings, citations …        │ [Confirm]    │
│              │                               │ [Override]   │
└──────────────┴───────────────────────────────┴──────────────┘
```

## 5. Content rules

- Recommendation text: "Recommended: refer. Awaiting your confirmation."
- Stopped: "Stopped at KYC: name on PAN does not match application. Correct the details and resume."
- Unverified: "Could not be verified automatically. Please check manually."
- Low confidence field: "Read with low confidence. Please verify against the document."
- Always show masked identifiers (for example `ABCDE****F`, Aadhaar last four).

## 6. Interaction rules

- Confirm and override each need a second click in a dialog.
- Override cannot be submitted without a reason.
- Destructive or irreversible actions use plain-language confirmation text.
- Long operations show progress by stage, not a spinner alone.
- Keyboard accessible; focus visible; dialogs trap focus.

## 6b. Stage 6 build notes

- Plain JavaScript and CSS (one `.css` beside each component; tokens in `frontend/src/styles/tokens.css`). Animation is CSS only (rise, shimmer, chip spin, a slow login glow) and switched off by `prefers-reduced-motion`. Three.js was not used.
- Built: login, case queue (search, status and loan-type filters), new case (loan type cards, form, co-applicant section), case workspace (checklist, Documents with upload and per-file results, Extracted fields with the document beside it, Report, Audit), confirm and override dialogs, admin precedent queue.
- Not built in Stage 6: the admin users page (built in Stage 8), policy and rule file status, Grafana link. The Stage 6 UI used Inter only if installed; Stage 8 bundles Outfit and Inter (section 8).

## 7. Responsive

Desktop first (bank workstation). Tablet works; phone shows read-only queue and report.

## 8. Stage 8 design: Pramaan (built 2026-11-02)

Built in Stage 8 of `IMPLEMENTATION_PLAN.md`. Inspired by the colour feel and fonts of amperadei.com (the training company); no images, copy or policy from that site are used. The section 2 status colours and the "never colour alone" rule stay.

### 8.1 Tokens

Colours are tokens for light and dark; components use variables only. Contrast passes WCAG AA (4.5:1) for every text pairing in both themes; `frontend/src/styles/tokens.test.js` checks it from the CSS file. Buttons use `#5E4FA0` (confirmed 2026-11-02) with white text in light, and `#B3A9DD` with dark text in dark.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--brand` | `#7C70AF` | `#9A8FCB` | Accents, icons, focus ring tint, charts |
| `--brand-strong` | `#5E4FA0` | `#B3A9DD` | Buttons, links (text on it must pass AA) |
| `--brand-soft` | `#E4E1EE` | `#2A2540` | Soft surfaces, selected rows, sidebar highlight |
| `--bg` | `#F7F6FA` | `#141220` | Page background |
| `--surface` | `#FFFFFF` | `#1E1B2E` | Cards |
| `--ink` | `#1F2933` | `#ECEAF4` | Body text |
| `--muted` | `#5A6472` | `#A9A6BD` | Secondary text |
| `--line` | `#DDDAE8` | `#35314A` | Borders |

Status colours keep their meaning (approve green, refer amber, reject red, stopped grey) with dark-theme variants. Two light values were darkened to pass AA: approve `#19703f` (was `#1E7F4F`) and refer `#8A5700` (was `#9A6200`). **Unverified** is teal (`#0B6A72` on `#DDF3F4` light, `#6FD6DB` on `#0F3336` dark), off the brand purple. Danger buttons use their own tokens (`--danger-bg`, `--danger-ink`) because the dark-theme red is light and needs dark text. Extra tokens: `--primary` (= `--brand-strong`), `--primary-hover`, `--primary-ink`, `--overlay`, `--shimmer`, `--glow-a/b`, `--panel-bg`, `--font-head`.

### 8.2 Typography

Outfit for headings (500, 600) and Inter for body and tables (400, 600), bundled with the `@fontsource` npm packages (no runtime request to Google Fonts). Sizes 12, 14 (body), 16, 20, 24, 32 (landing headline). Monospace stays for IDs and rule IDs. A fallback of `system-ui` keeps text readable while fonts load.

### 8.3 Theme

A three-way pill in the sidebar: **system** (default), **dark**, **light**, shown as monitor, moon and sun icons with the active one ringed. The choice is stored in the browser (`localStorage`, with a safe fallback) and set on `<html data-theme>`. Without a stored choice the theme follows `prefers-color-scheme`. No flash on load: the theme is set before first paint.

### 8.4 Screens

1. **Login (the landing page).** No public page and no signup; staff accounts are created by the admin. Split layout: a brand panel on the left (the 5-stage journey, the 20/15/30/25/10 score bar with the three bands, "A human confirms every case", a "Pramaan is a sample bank; synthetic data only" note) and the sign-in form on the right. The panel stacks above the form on small screens.
   **Follow-up (built 2026-11-02):** the panel keeps the five stages, "A human confirms every case", the sample-bank note and a few lines of About; the score bar and band wording are on the Help page behind sign-in. Under the form: "Can't sign in? Contact your admin." (plain sentence only). No footer on the login page and no request form.
2. **App shell.** Sidebar with the Pramaan mark, navigation (officer: Home, Cases, New case, Sent items, Report a problem, Help; admin: Home, Precedents, Users, Issues, Help), the theme toggle and the user menu (avatar, name, role; the menu shows name, email and role and has Sign out) sit top right, the signed-in user and role, sign out, and the theme toggle. It collapses to icons on tablet widths (up to 1024 px, confirmed 2026-11-02; the names stay for screen readers) and becomes a bar across the top on phones. The Sent items, Report a problem (officer) and Issues (admin) links arrived with Stage 9.
3. **Home (officer).** Summary tiles (awaiting confirmation, referred, stopped, in progress) and recent cases. Tiles filter the case list.
4. **Case workspace.** The 5-stage stepper (8.5) above the existing tabs.
5. **Report.** Score ring with band and "Recommended: ..." wording; the 3C strip (8.6); Conditions (missing or unverified items to fix or ask for); existing stage cards with rule IDs and clause links; confirm bar. The summary text appears with a one-time typing effect (confirmed 2026-11-02).
6. **Admin Home.** Pending precedents, active officers and disabled accounts.
7. **Admin Users.** Table of users with role and status; create officer, disable or enable, reset password (shown once, never logged). Admin still has no access to case data.
8. **Sent items and notification draft** (Stage 9, see section 9).

### 8.5 The 5 underwriting stages in the UI

Shown as a stepper on the case workspace and as the journey strip on the login page. Labels use plain banking terms; agent names appear only as small detail text.

| Banking stage | What the pipeline does | Score points |
|---|---|---|
| 1 Application intake and screening | Upload checks, extraction, duplicate check | none |
| 2 Verification and documents | KYC, document checks | KYC 20, Documents 15 |
| 3 Risk and ratios | Income and FOIR (code), credit and behaviour | Income and FOIR 30, Credit 25 |
| 4 Decisioning and conditions | Policy fit, recommendation, conditions list | Policy fit 10 |
| 5 Officer sign-off | Human confirms or overrides | none |

A stopped case shows the stepper stopped at the failing stage with the plain-language reason. Stage 5 is always the human; the stepper never shows it as done by the system.

### 8.6 Credit, Capacity and Collateral strip

A display-only regrouping on the report, computed from existing stage scores by the backend (the UI does not add numbers):

- **Credit:** the Credit and behaviour stage score.
- **Capacity:** the Income and FOIR stage score.
- **Collateral:** not scored in v1. Shown as "Not scored in v1" for every loan type; for home, vehicle and education the existing collateral and margin facts may be listed as notes, with no points.

Scoring weights, bands and hard rules do not change.

### 8.7 Motion

CSS only. Entrance fade and rise, score ring fill, stepper advance, skeleton shimmer, button press, and a one-time typing effect on the report summary (the full text is in the DOM for screen readers and copy). Everything is off under `prefers-reduced-motion`, and no animation carries meaning that is not also in text.

### 8.8 Accessibility

WCAG AA contrast in both themes; visible focus; dialogs trap focus; icons come with text; the theme toggle has labels for screen readers; keyboard operable throughout.

## 9. Stage 9 design: customer notifications (planned 2026-11-02, built 2026-11-02)

- **Draft dialog** on the case workspace after confirm, override or a stopped run: a template picker (a few short templates plus **Blank**), the recipient (customer email, masked in lists), the subject (fixed), the body (editable), the fixed fraud footer (shown, locked), and the officer's contact lines. A **Send** button opens a second confirmation that shows the final text. A blocked send shows the exact reason (for example "Contains a number that looks like an account number").
- **Sent items screen:** the officer's own messages with date, case reference, template, status (sent, failed, blocked) and a retry action for failed ones. Open one to read it.
- **Wording rule:** messages never state a score, status, missing item or reason; they only ask the customer to contact the officer, and always carry the fraud warning. The UI never says "approved" or "rejected" to the customer.

### 9.1 Build notes (Stage 9)

- **Case workspace:** a "Contact the customer" card appears in the right column when the case is confirmed, overridden or stopped (`CustomerContact`). It opens `MessageDialog` (step 1: template, recipient, subject locked, editable body with a character count, case-reference checkbox, locked contact lines and fraud footer, optional "your mobile number" field; **Review** saves a draft and the server checks it; a block lists each reason and stays on step 1. Step 2: the exact final text and **Yes, send**, which is the second click). The card also lists the latest three messages and links to Sent items.
- **Sent items** (`/messages`, officer sidebar): date, case link, template, recipient (masked), status chip (Sent, Failed, Blocked, Draft). **Retry** on a failed message opens a dialog with the final text; its **Yes, send again** button is the second click. Drafts and blocked messages have **Edit**.
- **Report a problem** (`/problems`, officer): category, optional case reference, text with a warning not to paste personal data, and a list of the officer's own reports with their status. **Issues** (`/admin/issues`, admin): tabs Open, Read, Closed, All; opening a report marks it read; Mark as closed finishes it. Admin Home gains an Open issues tile.
- **Customer email** is an optional field on the primary applicant in the application form.
- Help gets sections for officers (Contact the customer, Report a problem) and for admins (Read issue reports).

### 8.9 Build notes (Stage 8)

- **Files:** tokens in `styles/tokens.css` (light default; dark under `:root[data-theme='dark']` and, with no stored choice, `@media (prefers-color-scheme: dark)`; the two dark blocks are kept identical by a test). Fonts in `styles/fonts.css` (`@fontsource/inter` 400 and 600, `@fontsource/outfit` 500 and 600, Latin subset). Theme logic in `lib/theme.js`; `index.html` sets `data-theme` before first paint. The stored key is `lc.theme` in `localStorage` (`system` stores nothing).
- **Routes:** `/` is Home (officer tiles and recent cases, or admin summary), `/cases` the list (a tile opens `/cases?view=awaiting|referred|stopped|progress`, filtered in the browser), `/cases/new`, `/cases/:id`, `/admin/precedents`, `/admin/users`. The old top bar is gone.
- **Stepper (`lib/journey.js`):** derived from the case status, the `stage_runs` rows and `report.stopped_stage`. Officer sign-off is "in progress" while the case awaits confirmation and "done" only after an officer confirms or overrides.
- **3C strip and Conditions (`lib/conditions.js`):** Credit shows the Credit and behaviour stage score and Capacity the Income and FOIR stage score exactly as the report holds them; Collateral reads "Not scored in v1". Conditions lists the document-stage findings that are not plain notes. No backend change and no numbers added.
- **Users screen:** create (name, email, role), disable and reset each behind a second dialog, enable directly. The temporary password is shown once in a dialog.
- **Login:** brand panel (headline, the five stages, the 20/15/30/25/10 bar, bands, "A human confirms every case", sample-bank note) beside the sign-in form; the theme toggle sits top right. The panel stacks above the form under 900 px.
- **Motion:** rise, ring fill, stepper pulse, score-bar grow, drifting login glow, typing effect. The global `prefers-reduced-motion` override in `base.css` zeroes every animation and transition; the typing effect also checks the media query.

### 8.10 Follow-ups agreed 2026-11-02 (built; issue reports are Stage 9)

- **Footer (signed-in pages only):** one slim line under the page content: "Pramaan, sample bank, synthetic data only", a Help link and the app version. Not shown on the login page.
- **Help page** (`/help`, both roles, in the sidebar and the footer): content depends on the role. Officer guide: new case, uploading, the stepper, reading the report (stage cards, rule IDs, conditions, unverified), confirm and override with the second click, what each stage and agent does in plain words, and the score weights and bands. Admin guide: adding and disabling users, resetting passwords (the temporary password is shown once), the precedent queue. Static text; the same wording rules apply (never "approved" as an action taken).
  **Layout (built 2026-11-02):** a hero card (icon, title, role line), three quick-link cards, then one `card` per section with a round icon and an anchor, and a sticky "On this page" menu that highlights the section on screen (hidden below 1100px). Reuses tokens, `StatusChip` and the login journey's numbered badges. New components: `HelpSection`, `Callout` (info, warn, ok tones, left accent bar plus icon), `ScoreBar` (proportional weights, a 0 to 100 band scale and band chips), `AgentCard` (agent, the points it feeds, a "More" fold). The admin guide shows the three precedent gates (officer, code check, admin) as a flow.
- **Can't sign in:** the login page shows only the plain sentence "Can't sign in? Contact your admin." under the form. No email, no phone, no settings values, no request form, no endpoint. The person contacts the admin by their own channel.
- **Issue reports (Stage 9, confirmed):** a "Report a problem" action for officers and an admin inbox. Confirmed 2026-11-02 to be built with Stage 9 (task 9 in `IMPLEMENTATION_PLAN.md`); screens are designed at the start of Stage 9.

## 10. Review-window additions (2026-11-03)

- **At a glance** (`AtAGlance`): a card above the report Summary with the score ring, the top three reasons (hard fails first, then band caps, then the biggest point losses, each with its rule ID) and a "Next:" line. Built from existing findings; the UI computes no score.
- **Policy citations filter:** a text search (clause ID or wording) and a "cited by stage" select above the list, with a "Showing X of Y" count.
- **Admin officer view** (`/admin/users/:id`, reached from the officer's name in Users): counts and the latest case numbers only; no applicant data.
- **User menu** (top right, beside the theme toggle): name, email, role and Sign out; there is no separate Profile page. Sign-out opens a small dialog ("Stay signed in" / "Sign out").
