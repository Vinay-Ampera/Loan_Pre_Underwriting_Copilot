// Display-only formatting. Nothing here changes a value: it only changes how a stored number,
// date or code-written sentence is shown (Indian digit grouping, day-month-year dates).

const WHEN = {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true,
}
const DAY = { day: 'numeric', month: 'short', year: 'numeric' }

const valid = (v) => {
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "1 Nov 2026, 12:43 pm": unambiguous, unlike 11/1/2026. */
export function formatWhen(v) {
  const d = valid(v)
  return d ? d.toLocaleString('en-IN', WHEN) : ''
}

/** "1 Nov 2026". */
export function formatDay(v) {
  const d = valid(v)
  return d ? d.toLocaleDateString('en-IN', DAY) : ''
}

/** How old a case is: "under an hour", "5 hours", "3 days" (the queue's Age column). */
export function caseAge(createdAt, now = Date.now()) {
  const d = valid(createdAt)
  if (!d) return '–'
  const hours = Math.floor((now - d.getTime()) / 3_600_000)
  if (hours < 1) return 'under an hour'
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'}`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? '' : 's'}`
}

/** A span of seconds in words: "40 min", "13.5 hours", "1.3 days" (Insights). */
export function duration(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '–'
  const one = (n, unit) => {
    const v = Number(n.toFixed(1))
    return `${v} ${unit}${v === 1 ? '' : 's'}`
  }
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min`
  if (seconds < 48 * 3600) return one(seconds / 3600, 'hour')
  return one(seconds / 86400, 'day')
}

const num = (s) => Number(String(s).replaceAll(',', ''))

/** 12800.0 becomes "12,800"; 72.6 stays "72.6". */
export function plainNumber(v) {
  const n = num(v)
  if (!Number.isFinite(n)) return String(v)
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

/** 12800 becomes "₹12,800". */
export function rupees(v) {
  const n = num(v)
  return Number.isFinite(n) ? `₹${plainNumber(n)}` : String(v)
}

// How each rule field is named and shown. Unlisted fields fall back to a tidy version of the name.
const FIELD = {
  foir: { label: 'FOIR', kind: 'percent' },
  'ltv percent': { label: 'LTV', kind: 'percent' },
  'net monthly income': { label: 'Net monthly income', kind: 'money' },
  'loan amount': { label: 'Loan amount', kind: 'money' },
  'annual turnover': { label: 'Annual turnover', kind: 'money' },
  'cheque nach returns 12m': { label: 'Cheque or NACH returns in 12 months', kind: 'plain' },
  'cibil score': { label: 'CIBIL score', kind: 'plain' },
  'tenure months': { label: 'Tenure', kind: 'months' },
  'stability months': { label: 'Stability', kind: 'months' },
  'business vintage months': { label: 'Business vintage', kind: 'months' },
  'months with current employer': { label: 'With current employer', kind: 'months' },
  'total experience months': { label: 'Total experience', kind: 'months' },
  'age at application': { label: 'Age at application', kind: 'plain' },
  'age at maturity': { label: 'Age at maturity', kind: 'plain' },
  'bureau dpd max 12m': { label: 'Worst delay in 12 months (days)', kind: 'plain' },
  'enquiries 6m': { label: 'Credit enquiries in 6 months', kind: 'plain' },
}
const ACRONYMS = new Set(['pan', 'kyc', 'gst', 'cibil', 'foir', 'ltv', 'dob', 'nach', 'dpd', 'itr'])

function tidyName(field) {
  const words = field.split(' ')
  return words
    .map((w, i) =>
      ACRONYMS.has(w) ? w.toUpperCase() : i === 0 ? w[0].toUpperCase() + w.slice(1) : w,
    )
    .join(' ')
}

function showValue(kind, raw) {
  const t = String(raw).trim()
  if (/^true$/i.test(t)) return 'yes'
  if (/^false$/i.test(t)) return 'no'
  if (!/^-?[\d,]*\.?\d+$/.test(t)) return t
  if (kind === 'money') return rupees(t)
  if (kind === 'percent') return `${plainNumber(t)}%`
  if (kind === 'months') return `${plainNumber(t)} months`
  return plainNumber(t)
}

// "CM-INC-10 earned 0 of 12 points: foir: 72.6 (needed 40)", as the rules engine wrote it.
const RULE_LINE =
  /^[A-Z]{2,3}-[A-Z]+-\d+\s+(earned [\d.]+ of [\d.]+ points|passed|failed):\s+(.+?):\s+(.+?)(?:\s+\(needed\s+(.+)\))?$/

/**
 * The same finding, easier to read: the rule ID is dropped (it is shown beside the sentence),
 * field names are capitalised and money, percentages and months carry their unit.
 * A sentence in any other shape is returned unchanged.
 */
export function tidyFinding(message) {
  const m = RULE_LINE.exec(message ?? '')
  if (!m) return message
  const [, verdict, rawField, value, needed] = m
  const meta = FIELD[rawField] ?? { label: tidyName(rawField), kind: 'plain' }
  const head = verdict[0].toUpperCase() + verdict.slice(1)
  const tail = needed ? ` (needed ${showValue(meta.kind, needed)})` : ''
  const shown = showValue(meta.kind, value)
  const sep = meta.kind === 'plain' ? ': ' : ' ' // a bare number or yes/no reads better after a colon
  return `${head}: ${meta.label}${sep}${shown}${tail}`
}

/** The summary written by a model: same sentence, with units on the figures it quotes. */
export function tidySummary(text, { decided = false } = {}) {
  let out = String(text ?? '')
  out = out.replace(
    /\b(net monthly income of )(\d[\d,]*(?:\.\d+)?)/gi,
    (_, lead, n) => `${lead}${rupees(n)}`,
  )
  out = out.replace(/\bFOIR of (\d+(?:\.\d+)?)(?!\d|%)/g, (_, n) => `FOIR of ${plainNumber(n)}%`)
  out = out.replace(
    /\bLTV percentage of (\d+(?:\.\d+)?)(?!\d|%)/gi,
    (_, n) => `LTV of ${plainNumber(n)}%`,
  )
  if (decided) out = out.replace(/\s*Awaiting your confirmation\.?\s*$/i, '')
  return out
}
