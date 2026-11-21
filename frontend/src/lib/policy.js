// Words for the knowledge base screens. The backend decides everything; these only describe it.

export const POLICY_TYPES = ['common', 'personal', 'home', 'education', 'business', 'vehicle']
export const LOAN_ONLY = POLICY_TYPES.filter((t) => t !== 'common')

const LABEL = {
  common: 'Common credit policy',
  personal: 'Personal loan',
  home: 'Home loan',
  education: 'Education loan',
  business: 'Business loan',
  vehicle: 'Vehicle loan',
}
export const policyLabel = (lt) => LABEL[lt] ?? lt

export const SOURCES = [
  ['public', 'public (bank criteria)'],
  ['RBI', 'RBI'],
  ['sample', 'sample (this project)'],
]

export const TOPICS = [
  ['ELIG', 'Eligibility'],
  ['PROD', 'Product terms'],
  ['STAB', 'Stability'],
  ['INC', 'Income'],
  ['CRD', 'Credit'],
  ['KYC', 'KYC'],
  ['DOC', 'Documents'],
  ['FRD', 'Fraud'],
  ['GEN', 'General'],
]

const STATUS = {
  active: ['approve', 'In force'],
  scheduled: ['info', 'Scheduled'],
  superseded: ['neutral', 'Replaced'],
  retired: ['stopped', 'Retired'],
  draft: ['neutral', 'Draft'],
}
export const versionTone = (s) => STATUS[s] ?? ['neutral', s]

const ORIGIN = {
  file: 'imported from a file',
  upload: 'uploaded',
  edit: 'edited on this screen',
  restore: 'restored from an older version',
  legacy: 'imported from an old-format document',
}
export const originLabel = (o) => ORIGIN[o] ?? o

const OP = { gte: '≥', lte: '≤', gt: '>', lt: '<', eq: '=', ne: '≠', in: 'is one of' }
const value = (v) =>
  Array.isArray(v)
    ? v.join(', ')
    : typeof v === 'number'
      ? v.toLocaleString('en-IN')
      : v === true
        ? 'yes'
        : v === false
          ? 'no'
          : String(v)

/** One rule from the rules file in plain words, for example "cibil_score ≥ 700 · hard, stops". */
export function ruleText(r) {
  const field = r.field.replaceAll('_', ' ')
  if (r.tiers) {
    const tiers = r.tiers.map((t) => `${OP[t.operator]} ${value(t.threshold)}: ${t.points}`)
    return `${field}: ${tiers.join(', ')} points (of ${r.points})`
  }
  const test = `${field} ${OP[r.operator] ?? r.operator} ${value(r.threshold)}`
  if (r.kind === 'soft') return `${test} · ${r.points} points`
  if (r.on_fail === 'cap_refer') return `${test} · hard, refer at most`
  return `${test} · hard, stops (${r.fail_class === 'fix' ? 'fix' : 'eligibility'})`
}

export const when = (t) => (t ? new Date(t).toLocaleString() : '')
export const day = (d) =>
  d ? new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString() : ''

export const METRICS = [
  ['hit@1', 'Right clause first'],
  ['hit@3', 'Right clause in top 3'],
  ['recall@5', 'Expected clauses in top 5'],
  ['mrr', 'Average rank score'],
  ['citation_validity', 'Results from the right policy'],
]
export const pct = (v) => (v === null || v === undefined ? '' : `${Math.round(v * 100)}%`)
