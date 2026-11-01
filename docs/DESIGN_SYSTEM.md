# DESIGN_SYSTEM

Calm, readable, trustworthy. Built for bank staff who review many cases a day. The UI shows what the backend decides; it never computes scores.

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
- Not built yet: admin users page, policy and rule file status, Grafana link (Stages 7 and 8). The Inter font is used if installed; no web font is loaded.

## 7. Responsive

Desktop first (bank workstation). Tablet works; phone shows read-only queue and report.
