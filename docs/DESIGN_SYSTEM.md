# DESIGN_SYSTEM

Calm, readable, trustworthy. Built for bank staff who review many cases a day. The UI shows what the backend decides; it never computes scores. Brand: **Pramaan** (bank and product). Stage 8 (built 2026-11-02) restyles everything below; section 8 holds the design as built and overrides sections 2 and 6b where they differ. The craft pass of 2026-11-17 (section 8.11) refines section 8 and overrides 8.1, 8.2, 8.3 and 8.7 where they differ. The section 2 table is the Stage 6 palette and is kept for history; the live values are in `frontend/src/styles/tokens.css` and section 8.1.

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
7. **Admin Users.** Table of users with role and status; create officer, disable or enable, reset password (shown once, never logged). The admin opens an officer to see every case they own, and any case from there (2026-11-03).
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
- **Collateral:** has no score of its own. For home and vehicle the cell reads "Checked in Policy fit" with "Loan-to-value limit, scored in Policy fit"; for education "Checked in Policy fit" with "Collateral above a set loan amount, scored in Policy fit"; for personal and business "Not checked" with "No collateral rule for this loan type" (changed 2026-11-21 from "Not scored in v1", which hid the LTV and collateral rules in Policy fit). The words come from `collateralNote` in `lib/conditions.js`; no number is shown.

Scoring weights, bands and hard rules do not change.

### 8.7 Motion

CSS only. Entrance fade and rise, score ring fill, stepper advance, skeleton shimmer, button press, and a one-time typing effect on the report summary (the full text is in the DOM for screen readers and copy). Everything is off under `prefers-reduced-motion`, and no animation carries meaning that is not also in text.

### 8.8 Accessibility

WCAG AA contrast in both themes; visible focus; dialogs trap focus; icons come with text; the theme toggle has labels for screen readers; keyboard operable throughout.

### 8.11 Craft pass (2026-11-17)

A redline pass over every screen, following the **unslop** checklist by Damir Sokolovsky (github.com/heydamir/unslop, CC BY 4.0). It keeps locked decision 16 as it is (user, 2026-11-17): Pramaan purple, Outfit and Inter, light, dark and system, and login as the landing page. No feature, route, role, wording rule or score changes.

- **Direction.** Product: a pre-underwriting desk where bank loan officers check documents stage by stage, see a score computed in code with policy citations, and confirm every case. Character: exact, unhurried, accountable. World: a bank's credit desk (case files, ledgers, stamped papers). Moments: the case verdict (score ring, stepper, 3C strip) and the case file on login. Signature: rule and clause IDs as small mono tags.
- **Colour.** Surfaces, borders and text come from one neutral graphite ramp; purple leaves the surfaces and is the one accent (primary button, selection, the active nav icon, the current stage, the sign-off stage on login). Light: `--bg #F7F7F8`, `--surface #FFFFFF`, `--raised #F2F2F4`, `--chrome #FFFFFF` (sidebar, login panel), `--ink #18181B`, `--muted #52525B`, `--faint #6A6A73` (meta only), `--line` ink at 9%, `--line-strong #D4D4D8` (inputs, secondary buttons). Dark: `--bg #141415`, `--surface #1A1A1C`, `--raised #232326`, `--chrome #0F0F10`, `--ink #EDEDEF`, `--muted #A1A1A8`, `--faint #8A8A92`, `--line-strong #3A3A3F`, no shadows (depth from surface steps). `--brand-soft` is `#EFEDF6` / `#26232F`. Status colours, button purple and danger tokens are unchanged. Removed: `--shimmer`, `--glow-a/b`, `--panel-bg` (the login gradient). New: `--shadow-float` (menus, dialogs), `--focus-ring`, `--radius-sm/panel`, `--fs-13/28`, `--topbar-h`. `tokens.test.js` checks AA for the new pairs and that surfaces carry no visible hue.
- **Type.** Weights 400 and 500 (Inter 500 added); 600 only for the wordmark. Page titles 28 px, Outfit 500. No upper-case tracked labels anywhere (12 places became sentence case). Figures use tabular numbers; the score band reads "Recommend approve / Refer / Recommend reject / Not computed" instead of capitals.
- **Icons.** One line set (`Icons.jsx`, stroke 1.5). The text glyphs used as status marks (✓ ✕ ! ● ■ ⟳ ○ =) became icons in status chips, the stepper, stage progress, checklists, findings, upload results and the applicant page.
- **Shape and spacing.** 4 px grid. Radii: 6 tags and chips, 8 controls, 12 cards, 16 dialogs and the login panels. Chips and tags are no longer pills. Page padding 32 / 24 / 16; content max 1440 px. Sidebar 248 px with 36 px rows and a sticky 56 px top bar; sticky case panels and the Help contents clear it.
- **Screens.** Login: the gradient panel and drifting glow are gone; the five stages are drawn as a case file with the officer sign-off as the one accented step, still without weights or bands; on phones the form comes first. Home: no greeting; stat tiles are label, figure and hint with no coloured top bar. Help header: plain card. Charts: neutral track, 8 px bars, mono values. Tables: quiet header row. The audit timeline marks only the latest entry in purple.
- **Motion.** One curve `cubic-bezier(0.22, 1, 0.36, 1)`, 150 / 200 / 360 ms. Removed: the looping stepper pulse, the login glow drift, the skeleton sheen (now a slow fade), hover lifts on cards and tiles. Only live states loop: a case being assessed, the stage in progress, a loading placeholder. `styles/craft.test.js` guards all of this (no gradients, glows, upper-case labels, weights above 600, catch-all transitions, hover transforms, glyph icons, or loops outside live states).

### 8.12 Case page tidy (2026-11-17)

Display only: no route, role, API, scoring or wording-rule change, and the keywords (Recommended, At a glance, Points lost, Next, Conditions) are kept.

- **Two columns.** The case page is the content plus one 300 px rail. The document checklist moved from a third column into a "Required documents" card at the top of the Documents tab (open while anything is missing, closed once all are in, with "N of M received").
- **The score once.** The ring sits in the rail only, as a small ring with the band beside it (`ScoreBadge compact`). At a glance no longer repeats it, and the "Recommended: ..." sentence under the ring shows only on the other tabs because the Report tab already has it as its heading.
- **Nothing stale after a decision.** Once the officer has decided, At a glance drops "Next:" and the summary drops its closing "Awaiting your confirmation." (`ReportPanel`, `AtAGlance`).
- **Readable findings.** `lib/format.js` tidies the rules-engine sentences for display: the rule ID leaves the sentence (it is the tag beside it), field names are capitalised, and money, percentages and months carry a unit ("Earned 0 of 12 points: FOIR 72.6%", "Net monthly income ₹12,800"). Sentences of any other shape are shown as they are. The model-written summary gets the same units on the figures it quotes. At a glance rows are aligned columns: kind, finding, rule tag.
- **Dates** are day, month in words, year ("1 Nov 2026, 12:43 pm") everywhere, not 11/1/2026.
- **Stepper.** Once all five stages are done it is one slim line (the detail text stays in the page for screen readers); in progress it is unchanged.
- **Header.** The status chip sits beside the case number.
- **Fixes found on the way.** The summary's typing effect could stay blank when the page re-rendered while it was typing (`TypedText` now counts a text as seen only when it finishes). The Documents checklist uses the shared document names, so "Sale agreement" and "Title deed" are capitalised like the rest. The sign-in password has a show/hide button; the browser tests match the field with `exact: true` because the button's name also contains "password".

### 8.13 One loader, everything at once (2026-11-17)

A screen used to paint its heading first and fill in over the next second or two (the case page, then its customer messages, then the documents desk). Now each screen mounts hidden, runs all its requests, and is shown in one go.

- **Loader** (`Loader.jsx`): the Pramaan shield draws itself, then the tick that proves it, then it starts over (2.2 s). One stroke weight, brand purple on a faint outline, no gradient or glow; reduced motion shows the finished mark. Its label is spoken to screen readers.
- **First screen after sign-in:** the whole app (sidebar, top bar, page) stays hidden behind a full-screen loader ("Getting your desk ready") until the first screen is ready and the bundled fonts are loaded, so text never appears in one font and then jumps.
- **Later screens:** the sidebar and top bar stay; the content area shows the loader. It appears after 180 ms, so a fast load never flashes it.
- **How it works** (`Loading.jsx`): `Reveal` wraps the page, keyed by route. It mounts the page with `display: none` and counts what is loading. `useAsync` reports its first load automatically; a plain fetch uses `useBusy(flag)`. When nothing has been loading for 80 ms the page is shown, once. It never holds a screen longer than 10 s. Only the first load is held: refreshing a table, changing a filter or opening the Audit tab later does not hide the page again, and a screen without a `Reveal` (a page test) behaves as before.
- **Applicant link page:** the same loader on its own, in place of the brand header followed by "Opening…".
- **Fixed on the way:** the documents desk could show an older inventory after a newer save (a slow refetch answered after the employment change); a save now wins over any refetch in flight.

### 8.14 New case page (2026-11-19)

Display only: the case is still opened the same two ways (documents first, or the form first), with the same calls and button wording.

- **Steps.** Numbered steps (1 Loan type, 2 How do you want to start?, 3 the application form); a step's number becomes a tick once it is answered. Step 2 is shown from the start with its two options switched off and "Choose a loan type first." until a loan is picked.
- **Choice cards** (`ChoiceCard.jsx`): one card radio used for the loan types and the two ways to start: icon tile, name, one line, and a ring that fills with a tick when chosen. Five loan types sit in one row on a wide screen; on phones the icon sits beside the text. New line icons: `wallet`, `cap`, `briefcase`, `car`, `pencil`, `file`.
- **Documents needed** (`RequiredDocsPreview.jsx`): a 320 px rail beside steps 2 and 3, sticky under the top bar, below them on narrow screens. It lists the documents the chosen loan needs, straight from the rules file through `GET /meta/loan-types` (`documents`): Identity, Income and loan (Student for education), Co-applicant, with "If salaried"-style notes, counts as small mono tags, "A or B" for either-or documents, and the co-applicant rule. Nothing is scored or decided here.

## 9. Stage 9 design: customer notifications (planned 2026-11-02, built 2026-11-02)

- **Draft dialog** on the case workspace after confirm, override or a stopped run: a template picker (a few short templates plus **Blank**), the recipient (customer email, masked in lists), the subject (fixed), the body (editable), the fixed fraud footer (shown, locked), and the officer's contact lines. A **Send** button opens a second confirmation that shows the final text. A blocked send shows the exact reason (for example "Contains a number that looks like an account number").
- **Sent items screen:** the officer's own messages with date, case reference, template, status (sent, failed, blocked) and a retry action for failed ones. Open one to read it.
- **Wording rule:** messages never state a score, status, missing item or reason; they only ask the customer to contact the officer, and always carry the fraud warning. The UI never says "approved" or "rejected" to the customer.

### 9.1 Build notes (Stage 9)

- **Case workspace:** a "Contact the customer" card appears in the right column when the case is confirmed, overridden or stopped (`CustomerContact`). It opens `MessageDialog` (step 1: template, recipient, subject locked, editable body with a character count, case-reference checkbox, locked contact lines and fraud footer, optional "your mobile number" field; **Review** saves a draft and the server checks it; a block lists each reason and stays on step 1. Step 2: the exact final text and **Yes, send**, which is the second click). The card also lists the latest three messages and links to Sent items.
- **Sent items** (`/messages`, officer sidebar): date, case link, template, recipient (masked), status chip (Sent, Failed, Blocked, Draft). **Retry** on a failed message opens a dialog with the final text; its **Yes, send again** button is the second click. Drafts and blocked messages have **Edit** and **Delete** (Delete asks "Delete this draft?" and only the **Yes, delete** button removes it; sent and failed messages can never be deleted). A filter bar sits above the table: status buttons (All, Draft, Sent, Failed, Blocked), a case-number search, a From and To date range, **Clear filters** and a "Showing N of M" line. The **Contact the customer** card on a case lists the last three messages (template, date, status chip); when an unsent draft exists, **Write a message** first asks to continue it, start a new message, or delete the draft and start new. Anything that deletes or cannot be undone uses the shared `ConfirmDialog` (Cancel has focus; the red button is the second click), including removing an uploaded document.
- **Report a problem** (`/problems`, officer): category, optional case reference, text with a warning not to paste personal data, and a list of the officer's own reports with their status. **Issues** (`/admin/issues`, admin): tabs Open, Read, Closed, All; opening a report marks it read; Mark as closed finishes it. Admin Home gains an Open issues tile.
- **Customer email** is an optional field on the primary applicant in the application form.
- Help gets sections for officers (Contact the customer, Report a problem) and for admins (Read issue reports).

### 8.9 Build notes (Stage 8)

- **Files:** tokens in `styles/tokens.css` (light default; dark under `:root[data-theme='dark']` and, with no stored choice, `@media (prefers-color-scheme: dark)`; the two dark blocks are kept identical by a test). Fonts in `styles/fonts.css` (`@fontsource/inter` 400 and 600, `@fontsource/outfit` 500 and 600, Latin subset). Theme logic in `lib/theme.js`; `index.html` sets `data-theme` before first paint. The stored key is `lc.theme` in `localStorage` (`system` stores nothing).
- **Routes:** `/` is Home (officer tiles and recent cases, or admin summary), `/cases` the list (a tile opens `/cases?view=awaiting|referred|stopped|progress`, filtered in the browser), `/cases/new`, `/cases/:id`, `/admin/precedents`, `/admin/users`. The old top bar is gone.
- **Stepper (`lib/journey.js`):** derived from the case status, the `stage_runs` rows and `report.stopped_stage`. Officer sign-off is "in progress" while the case awaits confirmation and "done" only after an officer confirms or overrides.
- **3C strip and Conditions (`lib/conditions.js`):** Credit shows the Credit and behaviour stage score and Capacity the Income and FOIR stage score exactly as the report holds them; Collateral says where it is checked for the loan type (8.6). Conditions lists the document-stage findings that are not plain notes. No backend change and no numbers added.
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

- **Auditor screens (2026-11-03, reshaped the same day):** the read-only role has its own sidebar (Overview, Cases, Audit log, Users, Help) and a "Read-only" badge in the user menu. Cases is a static table with filters and Export CSV; its rows are not links, and the auditor has no case page, report, document, messages or precedents. Users lists name, role, status and last sign-in with no buttons. The Audit log (auditor only) has filters for action, user, case reference and dates, paging and Export CSV; it is masked and has no case links. The auditor's disabled buttons on the admin Users screen are greyed out with no tooltip or text.
- **Admin screens (2026-11-03):** sidebar Home, Precedents, Messages, Issues, Users, Help (no system-wide audit log). Home adds "Recently decided by officers" (links into the case, a chip when an admin changed it). Messages lists sent messages only (no drafts, no actions) with filters for officer, template, case and date. Users → officer lists every case the officer owns, filterable (including "Not decided by the officer" and "Changed by an admin"); disabling an officer with undecided cases warns with a link to that list. The case workspace opens in an "Admin view": no Confirm, Override, Upload, Submit, Contact or PDF; instead an Admin panel with **Change the decision** (after the officer has decided, not on a hard-rule case; needs a different decision and a reason of 15+ characters; the dialog button is the second click) and **Reassign to another officer** (undecided cases only). An admin change is shown as its own card beneath the officer's decision ("Changed by an admin", who, when, from and to, reason), to the officer as well, who also gets a notice on Home. Overview charts are CSS bars (`BarChart`) drawn from counts, with the numbers as text; a group under 5 cases reads "too few to show". Creating an admin on the Users screen shows a red "You are creating an admin" warning and needs a second click.

## 11. Stage 10 design: intake desk and applicant link (Parts A to C built 2026-11-04)

- **New case** asks "How do you want to start?": *Start with the documents* (opens the desk) or *Fill in the form first* (the old path, unchanged).
- **Bulk upload** (`BulkUpload`): one drop area, "Choose files or a zip", "Choose a folder" (computers only), "Take a photo" (applicant page, phones and tablets only), a one-line summary ("12 received · 1 not accepted · 2 repeats ignored") and a result chip per file (received, received with a note, not accepted with the reason, repeat ignored). The same component serves the applicant's page.
- **Inventory** (`Inventory`) on the Documents tab, one card per person: employment statement (a select), Received (table: File, Type, Person, Used for), Still missing (a list; identity papers carry an "Essential" chip), Extra. Below: Depends on employment type, Needs your attention (Whose is it? / Not recognised), Same document different amounts, Not accepted, Repeats ignored. Type and person are dropdowns that save at once. On a phone the tables stack as label/value rows.
- **Actions** at the foot: *Download all files (zip)*, *Ask the applicant*, *Proceed anyway* (off while identity papers are missing), *Continue to the application form* (on only when nothing is missing or the officer chose Proceed anyway).
- **Application form after the desk:** the five identity fields carry a small purple "from documents" tag while they are exactly what the card gave; a field the cards disagree on or could not read is empty with a note; one tick "I confirmed the details marked from documents against the cards" above Save. Claim fields have no tag. A case that came from a link shows the applicant's request above (`ApplicantRequest`): their own statement, not checked, with the reference they were given and a Sent complete / Sent, incomplete chip.
- **Upload links page** (`/links` for officers, `/admin/links` for admins): table with Created, Officer (admin), Loan, Case (link to it, "sent"), Files, Expires, State chip (Open, Expired, Disabled), Extend and Disable. "Create a link" opens the second-click dialog; the address then appears once with a Copy button.
- **Queue:** a purple "From applicant" badge beside the case number; an "Applicant submitted" status chip; "Details not entered yet" where the name is not known.
- **Report:** a "Identity details read from the cards" note and, on an identity finding, "The form value here is from document, not an independent check".
- **Applicant page** (`/u`, public, no sidebar, brand and theme only): *1 Your request* (own statement), *What to send* (counts), *2 Your documents*, *3 Send to the bank*. A calm "Some items on the list are not in yet" line; the send dialog is the second click; the reference number on finish; the fraud line in the footer. No score, status or outcome wording (a test scans the page text).
- **Second click:** create a link, disable a link, Ask the applicant (creates a link), Send to the bank, Proceed anyway, Continue before the applicant has sent (intake desk), send the "Upload link" message. Type, person and employment changes, extend, copy and the zip save or run without a dialog. All reuse `ConfirmDialog`.
- **Bundle split view (Part D, built 2026-11-18):** `BundleSplit` is a card in the inventory for each PDF that waits. It lists every page with a checkbox "A new document starts on page N" (page 1 is always a start), a type select for each start page and "continues the document from page N" for the others. Ticking, unticking and choosing a type save at once with no dialog. "Confirm the split" and "Remove this PDF" open the confirmation dialog; "Back to the proposed split" appears only after an edit; "Open the PDF" shows the original. The desk's Continue and Proceed anyway are disabled while a PDF waits.

## 12. AI control page (2026-11-18)

Admin only, route `/admin/ai`, sidebar entry "AI control" (icon `sliders`). One page with four tabs (`role="tablist"`): **Models** (a card per role: first choice, fallbacks with Add and Remove, then one card for retries and timeouts, then the history of versions), **Keys** (a table of providers with the variable name, "Key is set" or "Key is missing" and a Test button), **Prompts** (one tab per prompt: the editable text in a monospace textarea, the locked rules in a dashed read-only block, a line diff against the text in use, Save draft, Test the draft, Publish, Discard, and the version list with Restore), **Settings** (the model switch and a table of temperature and length limit per step). Edits to models and settings are held in the page and a bar offers Discard and "Review and save". Every save, publish and restore opens `ReasonDialog`: a reason of at least ten characters and a confirm button, the second click. Nothing here shows a key value. Tokens and components are the existing ones; no new colours.
- **Breadcrumbs** (`Breadcrumbs.jsx`, added 2026-11-19): only on deep pages, never on the sidebar pages. Case page: officer *Cases › CASE-no*; admin *Users › officer › CASE-no*. Upload links filtered by a case: *Case CASE-no › Upload links*. Admin officer page: *Users › name*. A `nav` labelled Breadcrumb, `aria-current="page"` on the last item; under 560px only a single "← parent" link shows.
- **Ask the applicant dialog** names what really happens (Create the link, Show the link, Ask for more, Reopen this link, Make a new link); see E-75.
- **Asking for more** (`RequestedItems.jsx`, 2026-11-19): after the applicant has sent, the Ask dialog shows *What do you need?* (document kinds with a count of 1 to 12, and a note of up to 200 characters); the button stays off until one is given. The applicant's page then reads *Your loan officer has asked for* followed by exactly that, with no general checklist; after the officer confirms, the dialog says the request is saved and does not show the address again.

## 13. Notifications: bell and inbox (2026-11-19)

- **Bell** (`NotificationBell`): a 36px icon button in the top bar, left of the theme toggle, for officers and admins only (the auditor has none). It is a `button` whose accessible name carries the count ("Notifications, 3 unread", "Notifications, none unread"); the purple count badge (99+ at most) is `aria-hidden`. A click opens the inbox of the role.
- **Sidebar:** an `Inbox` entry (icon `inbox`) right after Home for the officer and the admin, with a purple count badge (hidden text ", 3 unread" for screen readers); on tablet widths the badge sits on the icon.
- **Inbox page** (`InboxPage`, `/inbox`, `/admin/inbox`, top level so no breadcrumbs): title, one line, tabs *Unread* and *All* (the first tab lines up with the heading), a filter bar (*Type*: groups the server sends for the role, such as Applicant and links, Checks, Decisions and cases, Precedents, Messages and problems; *Case number*: a search that waits 300 ms and sends only letters, digits and hyphens; *Clear filters* while one is active), a line "3 unread" and *Mark all read*, then one card of rows. A row is a button (a dot, the fixed title, an optional second line, the case reference and the time) and, while unread, a *Mark read* button. The whole row is the hover target (it fills to the card's edges); the open button is flat. Unread rows have a purple dot and a heavier title; a row marked read here stays in the list, greyed, until the page is reloaded. Opening a row marks it read and goes to the case (or to Issues or Precedents). *Show more* loads the next 30. Empty state "You are all caught up" (or "No notifications yet"), the usual error state with Try again.
- **Wording:** notices say what happened, never who the applicant is or what the outcome is, and never "approved"; the precedent notices say "added to" or "not added to" the knowledge base.
- **Refresh:** `UnreadProvider` reads `/notifications/unread-count` on sign-in, every 60 seconds while the tab is visible and on window focus; a failed read keeps the last count; nothing is read for the auditor or after the session ended. Tokens and components are the existing ones; no new colour.
- **Email (Part 2):** the user menu of an officer or an admin has a checkbox item *Email me about new notices* (`menuitemcheckbox`, a check or a dash icon; saved at once, an error line if it fails); the auditor has none. Sent items shows under the status how a sent message went out: *Sent by email*, *Sent to the demo inbox* or *Printed in the terminal, not emailed*, and the same line in the message dialog.

## 14. Knowledge base and Policies (2026-11-21)

- **Admin page** `KnowledgeBasePage` (`/admin/knowledge`, sidebar "Knowledge base", icon `book`, after Precedents). Tabs (`role="tablist"`, the same underline tabs as AI control): *Policies*, *Learnings*, *Search and index*. Policies is a two-column grid (stacked under 860px): `PolicyList` on the left (one card button per policy with its version, clause count and chips *Draft*, *From date*, *Not fully indexed*; the selected one has the brand outline and soft fill) and a panel with *Read*, *Change* (marked "· draft" while a draft exists) and *History*.
- **Reader** (`PolicyReader`): title, version (mono), effective date, a status chip (*In force*, *Scheduled*, *Replaced*, *Retired*), then one card per clause: the clause ID in the `ref-id` style, the title, the source tag in a small outline, the text, and the rules that use it on a left rule line in muted text ("cibil score ≥ 700 · hard, stops (eligibility)"). The admin also sees who published it and why, and "Cited in N cases in the last 30 days".
- **Change** (`PolicyEditor`): a grey bar while a draft exists (who saved it, when, "Officers and cases still use the version in force", *Discard the draft*); three tabs *One clause at a time* (clause rows with *Change* and *Remove*, an inline form, *Add a clause* with topic, optional ID and position), *Whole text* (a monospace textarea), *Upload a file*. Below: `CheckReport` (errors with a red left rule, warnings amber, fixes with before → after and *Apply these fixes to the draft*), `ClauseDiff` (changed amber, added green, removed red; words shown with `ins` and `del` on the approve and reject tints), the retrieval check table (in force against draft; a worse figure in the reject colour) and the Publish card (the blockers listed, the button off until they are gone). Publishing opens `ReasonDialog` with a checkbox "I have read the N warnings" that must be ticked; `ReasonDialog` gained a `blocked` prop for this.
- **History** (`PolicyHistory`): one card per version with *Read*, *Compare with the version in force*, *Restore as a draft* (off while a draft exists) and *Retire…* (scheduled or replaced only).
- **Learnings** (`LearningsPanel`): counts in a line (in use, paused, waiting in the queue, uses in 30 days), filter tabs, one card per precedent with a status chip (*In use*, *Paused* in the refer colour with the reason, *Expired*, *Retired*), its use and cases, and *Confirm again…* or *Retire…*; a link to the Precedents queue.
- **Search and index:** `PolicySearch` (question, loan type, *Compare with drafts* for the admin; results in two columns) and `IndexTools` (index table, the policy files on the server, *Re-index from the files…* with an "embed every clause again" checkbox in the dialog, the retrieval evaluation against its targets).
- **Officer page** `PolicyLibraryPage` (`/policies`, sidebar "Policies", icon `book`, before Report a problem): search card on top, then the list and the reader. No drafts, history, citation counts or buttons that change anything.
- Tokens and components are the existing ones; no new colour. The new icon `book` follows the 1.5 stroke line set.

## 15. 2-step verification screens (2026-11-24)

All inside the existing sign-in card (`components/TwoStep.jsx`, `TwoStep.css`); the brand panel on the left is unchanged.

- **Enter your code:** one sentence naming the authenticator app (Google Authenticator, Microsoft Authenticator or another), a large mono "6-digit code" box (numeric keyboard on phones, `one-time-code` autofill), "Verify and sign in", then quiet buttons "Lost your phone? Use a recovery code" (switches the box to "Recovery code") and "Use a different account".
- **Set up 2-step verification:** three numbered steps (install an authenticator app such as Google or Microsoft Authenticator; tap + and scan; type the code), the QR code always black on white in both themes so any camera reads it, and a fold "Cannot scan it? Type the key instead" with the key in groups of four. Button "Turn on and sign in".
- **Save your recovery codes:** eight codes in a two-column mono grid, Copy and Download, a tick "I have saved these codes"; "Continue to Pramaan" stays off until it is ticked.
- **Signed in with a recovery code:** how many are left (amber note when two or fewer) and what to do about a lost phone.
- **Users screen:** a 2-step column (On, Set up at next sign-in, Not needed) and a "Reset 2-step" button on rows that have it on (greyed out on your own row; not shown for the auditor), opening the shared reason dialog.
- Wording: "2-step verification" everywhere (never "MFA" on screen); errors say what to do ("Use the newest code in the app, or a recovery code").

## 16. Panes that scroll on their own, one loader, the bell dropdown (2026-11-24)

Asked for by the user; layout and loading only, no change to what any screen does.

- **Side-by-side screens keep the page still** (`components/FitPanes.jsx`). On wide windows the two-pane area is sized to the rest of the window (measured, so the header, the footer and the page padding all fit), and each pane scrolls by itself; the page does not move. Narrower windows stack the panes and the page scrolls as before. Used on:
  - **Knowledge base, Policies tab** (from 861 px): the policy list scrolls on the left; on the right the Read, Change and History tabs stay put and only the text under them scrolls.
  - **Policies** (officer, from 861 px): the list and the policy text scroll separately.
  - **Case page** (from 1001 px, once the case has a report; see 16.3): the case header, stepper and tabs stay put; the open tab (Documents, Extracted fields, Report, Audit) scrolls, and so does the side panel. On Extracted fields the document stays in view while the fields scroll. While the case is put together, or a form is corrected, the page scrolls as one.
  - Left as page scroll on purpose: Help (a long document with its own sticky contents list), New case (a form with a sticky summary), and single-column lists and tables.
- **One loader everywhere.** Every loading state uses the Pramaan shield loader: the full-page one on first load, and `SectionLoader` (the same mark, smaller, shown after a short pause so quick answers do not flash it) inside a section. Each one says what is loading ("Loading the policy", "Loading cases"). The grey skeleton bars are no longer used.
- **The bell opens a dropdown** instead of going to the inbox: the eight latest notices (unread ones bold with a dot), "Mark all read", and "Open the inbox". Opening a notice marks it read and goes where it points, as in the inbox. Escape or a click outside closes it.
- **Account menu:** wider, with left-aligned items, so "Email me about new notices" reads as one line.
- **Status chips never shrink below their label** (`min-width: max-content`): a table squeezing its columns used to cut the end off "Active" and similar chips.
- **Users screen:** the Status and 2-step chips stay whole, and below 900 px wide the table becomes one card per person (it was 720 px; six columns no longer fit beside the sidebar on a tablet). The name and "(you)" stay together.
- **Text inside its box:** the Help page's agent cards wrap their points line, and on a phone the score-weight bar keeps each number inside its segment. Checked on every screen at 1920, 1440, 1280, 1024, 820 and 390 px wide.
- **The 2-step screens name no single app:** "your authenticator app (for example Google Authenticator or Microsoft Authenticator)".

### 16.1 Four UX fixes after the full review (2026-11-24)

- **Case tabs never collapse:** in a FitPanes column the fixed parts (tab strip, notes, the progress card) keep their full height; before, a long Documents or Report tab squeezed the tab strip to a line.
- **Slim stepper earlier:** the stepper becomes one line as soon as the system's four stages are done (awaiting the officer, or decided), with Officer sign-off still marked as the current step; it stays full while the system works and when a case stops. This gives the report about 80 px more height.
- **Phone menu:** at 720 px and below the sidebar is a bar with the Pramaan name and a **Menu** button (with the unread badge); the button opens the pages as a labelled list, and choosing a page, Escape or a tap outside closes it. Tablets keep the icon rail.
- **Long file names** in the document list stay on one line and end in "…", with the whole name on hover, instead of breaking mid-word.

### 16.2 Five finishing fixes after the second review (2026-11-24)

- **One page header shape:** every page puts its one line of context under the title. Knowledge base and Policies used to put it top-right beside the title; their title and text now sit in one block like the other pages.
- **Faster typing effect:** the report summary still types itself once per page view (decided 2026-11-02), but the whole text now takes about half a second whatever its length (it took up to two seconds). Reduced motion still shows it at once.
- **Compact score chart (auditor Overview):** empty score ranges at either end are left out, and a line under the bars says which ("No case scored below 40 or above 89."). Empty ranges in between stay, because a gap in the middle is part of the picture. With no scored case the chart says "No case has a score yet."
- **AI control opens in one wait:** the settings and the change history are asked for together (the history used to wait for the settings), and the server reads the saved settings once instead of twice. The page appears about 0.15 s after the slower of the two answers.
- **Login:** the sign-in form sits on its own plain sheet (`--chrome`) instead of a card floating in an empty grey area, and the case file lies on the page grey (`--bg`) on the left. Same content, wording, order on phones and themes.

### 16.3 Case intake layout (2026-11-24)

The documents desk and the application form were squeezed into a pane about a third of the screen high, with their own scroll bar, under a full stepper, and the same files were listed three times. Layout only: every button and action is still there.

- **One page scroll while the case is put together.** The case page fills the window with side-by-side panes (`FitPanes`) only when there is a report to read. While the documents and the form are being worked on, and while a form is being corrected, the page scrolls as one and the side panel (score, Submit) stays in view.
- **Slim stepper during intake.** Draft, uploaded and applicant-submitted cases show the one-line stepper with intake as the current step. The full stepper shows while the system works and where a case stopped.
- **Slim upload bar.** Once files are in, the big drop box becomes one bar ("Add more: drop a zip, a folder or files here", the two choose buttons, the format note). "Add one file and label it yourself" sits right under it.
- **Each file listed once in view.** The upload result is one line ("7 received · show each file") that opens the list; a file that was not accepted, was a repeat or carries a note stays in view. The inventory table is the working list. "All files" (with View and Remove) is folded behind one line on the desk; with no desk it is shown as before.
- **Next-step bar.** At the bottom of the desk, kept at the bottom of the window while the list scrolls past (in place on phones): why a button is off ("State the employment type above…", "Some documents are still missing…", "Add the applicant's documents above first."), then "Download all files (zip)" on the left and Ask the applicant, Proceed anyway and Continue on the right.
- **Back and Cancel beside Save.** On the application form, "Back to the documents" (and "Cancel" when correcting) sit next to the save button instead of alone under the form. "Edit the application form" is not offered while that form is already open.


## 17. Stage 12 design: post-demo features (planned 2026-11-25)

Built with the existing tokens and components only (no new colour unless named below, and any new colour pair is added to `tokens.test.js`). Icons named below that do not exist yet (`clock`, `chat`) are added to `Icons.jsx` in the same 1.5 stroke line set. The `dataviz` skill is loaded before the Insights charts and the waterfall are drawn. Wording rules hold everywhere: "recommended", never "approved" or "eligible for"; no outcome words to a customer.

### 17.1 Counter-offer box (Part A)

- **Where:** on the report, under "At a glance" and above the stage cards, for the officer and the admin. It is shown only when `report.counter_offer` exists. There is no empty state: no box at all when it does not help.
- **Look:** a plain card with a thin `--line` border and no status colour, because it is an estimate, not a result. The title is "Other amounts or tenures (estimate)". Each line is a row: a small icon (`clock` for a longer tenure, `wallet` for a smaller amount, `car`, `cap`, `briefcase` or `home` for another product), the sentence, and mono tags for EMI and FOIR. Amounts are in Indian short form (₹6.2L, ₹1.25Cr). Tenures are in years when whole ("5 years"), otherwise in months.
- **Wording:**
  - Intro: "Worked out in code from this case's checked figures. For you to discuss with the applicant; it does not change the score or the recommendation."
  - Line (a), for example a vehicle loan asked over 4 years: "Pramaan estimates ₹10L over 7 years would be recommended for refer (FOIR 43.9%)." The EMI follows as a tag: "EMI ₹16,344".
  - Line (b): "Pramaan estimates ₹6.2L over 5 years would be recommended for refer (FOIR 39.7%)." The EMI follows as a tag: "EMI ₹13,792".
  - Approve band: "… would be recommended for approve (FOIR 35.2%)."
  - Age stop: "A tenure of up to 96 months keeps every applicant at 55 or under at maturity. Not scored: the assessment stopped before income was checked."
  - Alternate product: "The stated purpose fits a vehicle loan: ₹10L over 7 years at 9.5%, EMI ₹16,344, FOIR 43.9%. A new application, not scored. It would also need: dealer invoice." The tag reads "Not scored".
  - Footer (muted): "Rate from the bank's rules file. Your decision is still needed. Not for customer messages."
- **Never:** "approved", "eligible", "you qualify", "offer" as a promise, or the score.
- **PDF:** the same sentences, under an "Other amounts or tenures (estimate)" heading after the stage scores table, with the tags in square brackets. The PDF's built-in font has no rupee sign, so the PDF writes "Rs 6.3L" where the screen shows "₹6.3L". The PDF export is the officer's (the admin view has none), so the admin sees the box on screen only.
- **Where the words come from:** the sentences and tags are written by code (`app/scoring/counter_offer.py`) and stored with the report, so the screen and the PDF say the same thing; the title, intro and footer are fixed text in `CounterOfferBox.jsx` and the PDF builder.

### 17.2 Insights page (Part B)

- **Where:** the sidebar entry "Insights" (icon `chart`) for the admin (after Home) and the auditor (after Overview). The routes are `/admin/insights` and `/auditor/insights`. The officer gets no page, only Home tiles (17.3).
- **Header:** "Insights", with the line "Counted from the case records. No AI is used on this page." Filters: From, To (cases created in this period), Loan type, and Clear filters. A "Showing cases created 1 Nov to 25 Nov 2026" line.
- **Panels** (cards on a two-column grid that stacks under 1000 px; each chart is `BarChart` with its numbers as text):
  1. **Time to decide:** two stat tiles ("Report ready after", "Officer decided after", each a median with "slowest: 4.2 days" under it), then bars per loan type and per officer.
  2. **Where cases are:** a funnel as horizontal bars (Created, Submitted, Report ready, Decided, split Confirmed and Changed by the officer), then "Open now": Not submitted, Stopped for a fix, Waiting for the officer.
  3. **Officer agreement:** "Confirmed 41 (82%) · Changed by the officer 9 (18%)", bars by loan type and by band, and a separate line "Admin corrections: 2".
  4. **Rules in changed decisions:** a table (rule tag, clause tag, direction chip such as "Refer → approve (officer)", count). For the admin the clause tag opens the clause in the knowledge base and the count opens the list of cases.
  5. **Why runs stopped:** a table (stage, rule tag, a plain label from the clause title, count), for example "KYC · CM-KYC-03 · Name match · 12 cases".
  6. **Precedents:** "A precedent's bonus reached 6 cases; it moved 2 of them to another band."
- **Auditor version:** the same panels. No links, no case references, no "open the cases" counts, and a line "Counts only. Cases cannot be opened from here."
- **States:** the shared `SectionLoader` while loading; "No cases in this period" when empty; the usual error state with Try again.
- **Wording:** "Changed by the officer" (not "overridden" alone) and "Admin correction". The direction chips use the officer's own decision words ("approve", "refer", "reject") with "(officer)", never "approved".

### 17.3 Case age, due badges, export and Home tiles (Part C)

- **Queue columns:** a new "Age" column ("3 days", "5 hours"), and a due badge beside the status chip:
  - **Due today:** the refer (amber) status tokens, a `clock` icon, the text "Due today".
  - **Overdue:** the reject (red) status tokens, an `alert` icon, the text "Overdue".
  - Hovering the badge, or a screen reader, gives "Decision due 27 Nov 2026, 3:00 pm (2 working days after the report)".
  - There is no badge when the case is not timed (before submit, stopped for a fix, decided).
- **Filter:** "Due" select (Any, Due today, Overdue) beside the status and loan filters.
- **Export:** an "Export CSV" secondary button at the top right of the queue, with no dialog. The line under it reads "Exports the cases shown, with your filters. No applicant names." The admin's "Export all cases" sits on the admin officer page and on Home's recent-decisions card. Files are named `pramaan-cases-YYYY-MM-DD.csv`.
- **Home (officer):** two tiles: "Overdue" (count, hint "Past the 2 working day target", opens the queue filtered) and "Your median time to decide" (for example "1.3 days", hint "Report ready to your decision, last 30 days"; "No decisions yet" when empty).
- **Notices (fixed text, no digits):**
  - Officer: title "A case is past its decision time", body "Open the case to make your decision."
  - Admin: title "A case is still waiting for its officer", body "It passed its decision time a working day ago."
  - Both open the case.
- **Help:** officer and admin sections explaining the 2-working-day target, the badges and the export.

### 17.4 Score breakdown chart (Part D)

- **Where:** the first card of the report for scored cases, titled "How the score was reached", with the line "Starts at 100. Each step is the points lost in a stage."
- **Chart (`ScoreWaterfall`, inline SVG):**
  - Bars:
    - a full bar at 100;
    - one floating bar per stage, dropping by its points lost and labelled "KYC −2", "Income and FOIR −18" (a stage that lost nothing shows "−0" as a thin tick);
    - a rising bar for a precedent bonus ("Precedent +3");
    - the final bar, labelled "Score 72 · Refer".
  - Colours: the bars use `--brand` for the start and end bars and `--muted` for the drops; the bonus uses the approve token. The band lines are dashed `--line-strong` lines labelled "85 recommend approve" and "60 refer".
  - Cap: a mono tag on the final bar, "Capped at refer · CM-FRD-01", in the refer tokens, with a note under the chart: "The score is above 85, but a rule keeps this case at refer."
  - Values use tabular numbers. Every label is text, so colour is never the only signal.
- **No chart** when any stage did not run. The report's existing stopped wording is shown instead.
- **Accessibility:** the SVG is `role="img"` with an `aria-label` sentence ("Score breakdown: starts at 100; KYC lost 2, Documents lost 0, Income and FOIR lost 18, Credit lost 6, Policy fit lost 2; final score 72, refer"). A "Show as a table" toggle shows the table (Stage, Out of, Earned, Lost), which is always in the DOM for screen readers.
- **Themes:** light, dark and system from tokens; no hard-coded colour.
- **PDF:** no chart. The report PDF's "Stage scores" table gets a third column, "Points lost" (right-aligned, like the Score column), with a dash for a stage that did not run. The column headings read "Stage", "Score" and "Points lost".

### 17.5 "Ask this case" panel (Part E)

- **Where:** a case tab "Ask" (label "Ask this case", icon `chat`) after Report, for the case's officer and the admin. In the fitted case layout it is a pane that scrolls on its own, with the input pinned to the bottom. Before a report exists the tab reads "Chat opens when the report is ready."
- **Top line (muted):** "Answers come only from this case's report, its documents (personal numbers hidden) and the policy in force for this case. Chat cannot change the score or decide anything."
- **Conversation:**
  - the person's question in a soft (`--brand-soft`) block;
  - the answer as plain sentences, each followed by its citation chips: rule tags and clause tags in the `ref-id` style (a clause chip opens the clause, as in the report's citations), and field chips such as "Payslip · employer";
  - under the answer, in muted text, "Check the cited source before relying on an answer."
  - an answer about an older report version carries "About report version 1".
- **Input:** a textarea ("Ask about this case, for example: Why did Income and FOIR lose points?"), at most 500 characters with a counter, and an **Ask** button (Enter sends, Shift+Enter makes a new line). No second click: asking changes nothing. While waiting, the shared `SectionLoader` reads "Reading the case".
- **Fixed texts:**
  - Cannot answer: "I can't answer that from this case's documents and policy."
  - What if: "Chat does not work out other amounts or tenures. If a change would help, the report shows it under Other amounts or tenures."
  - Off: "Chat is off because the AI models are switched off. The report and its citations are still here."
  - Limit: "You have asked many questions in the last hour. Please try again a little later."
  - Masked note, when the question held a personal number: "Personal numbers in your question were hidden before it was sent."
- **Never:** "approved", a new score, or advice to the customer.
- **Help:** officer and admin sections "Ask this case" (what it reads, what it cannot do, why some answers are the fixed text).
