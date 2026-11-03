/** Filters for the Sent items lists (the officer's own, and the admin's all-officers view). They
 * run in the browser. `officer` and `template` are used by the admin list only. */

export const STATUS_FILTERS = [
  ['all', 'All'],
  ['draft', 'Draft'],
  ['sent', 'Sent'],
  ['failed', 'Failed'],
  ['blocked', 'Blocked'],
]

export const NO_FILTER = { status: 'all', query: '', from: '', to: '', officer: '', template: '' }

export const isFiltered = (f) =>
  f.status !== 'all' || Boolean(f.query.trim() || f.from || f.to || f.officer || f.template)

/** The day a message is listed under, as local YYYY-MM-DD (the date shown in the table). */
export function messageDay(m) {
  const d = new Date(m.sent_at || m.created_at)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function filterMessages(rows, f) {
  const q = f.query.trim().toLowerCase()
  return rows.filter((m) => {
    if (f.status !== 'all' && m.status !== f.status) return false
    if (q && !m.case_no.toLowerCase().includes(q)) return false
    if (f.officer && m.officer_id !== f.officer) return false
    if (f.template && m.template !== f.template) return false
    const day = messageDay(m)
    if (f.from && day < f.from) return false
    if (f.to && day > f.to) return false
    return true
  })
}
