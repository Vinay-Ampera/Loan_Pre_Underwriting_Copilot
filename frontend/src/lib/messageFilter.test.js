import { describe, expect, it } from 'vitest'
import { filterMessages, isFiltered, NO_FILTER } from './messageFilter'

const at = (day) => new Date(`${day}T12:00:00`).toISOString()
const rows = [
  {
    id: 1,
    case_no: 'CASE-2026-0001',
    status: 'sent',
    created_at: at('2026-11-01'),
    sent_at: at('2026-11-02'),
  },
  {
    id: 2,
    case_no: 'CASE-2026-0002',
    status: 'draft',
    created_at: at('2026-11-03'),
    sent_at: null,
  },
  {
    id: 3,
    case_no: 'CASE-2026-0002',
    status: 'failed',
    created_at: at('2026-11-05'),
    sent_at: null,
  },
]
const ids = (f) => filterMessages(rows, { ...NO_FILTER, ...f }).map((m) => m.id)

describe('filterMessages', () => {
  it('returns everything with no filter', () => {
    expect(ids({})).toEqual([1, 2, 3])
    expect(isFiltered(NO_FILTER)).toBe(false)
  })

  it('filters by status', () => {
    expect(ids({ status: 'draft' })).toEqual([2])
    expect(ids({ status: 'sent' })).toEqual([1])
  })

  it('matches a case number by part, ignoring case and spaces', () => {
    expect(ids({ query: ' case-2026-0002 ' })).toEqual([2, 3])
    expect(ids({ query: '0001' })).toEqual([1])
  })

  it('filters by an inclusive date range using the sent date when there is one', () => {
    expect(ids({ from: '2026-11-02', to: '2026-11-03' })).toEqual([1, 2])
    expect(ids({ from: '2026-11-04' })).toEqual([3])
    expect(ids({ to: '2026-11-01' })).toEqual([])
  })

  it('combines filters', () => {
    expect(ids({ status: 'failed', query: '0002', from: '2026-11-05' })).toEqual([3])
    expect(isFiltered({ ...NO_FILTER, from: '2026-11-05' })).toBe(true)
  })
})
