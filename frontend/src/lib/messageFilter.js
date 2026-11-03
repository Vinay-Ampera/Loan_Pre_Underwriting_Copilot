/** Filters for the Sent items list. Everything runs in the browser on the officer's own rows. */

export const STATUS_FILTERS = [
  ['all', 'All'],
  ['draft', 'Draft'],
  ['sent', 'Sent'],
  ['failed', 'Failed'],
  ['blocked', 'Blocked'],
]

export const NO_FILTER = { status: 'all', query: '', from: '', to: '' }

export const isFiltered = (f) => f.status !== 'all' || Boolean(f.query.trim() || f.from || f.to)

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
    const day = messageDay(m)
    if (f.from && day < f.from) return false
    if (f.to && day > f.to) return false
    return true
  })
}
