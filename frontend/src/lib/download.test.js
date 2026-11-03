import { describe, expect, it } from 'vitest'
import { queryOf } from './download'

describe('queryOf', () => {
  it('keeps only the filters that are filled in', () => {
    expect(queryOf({ action: 'login', actor: '', case_no: null, date_from: '2026-11-01' })).toBe(
      'action=login&date_from=2026-11-01',
    )
  })
  it('adds paging next to the filters', () => {
    expect(queryOf({ status: 'confirmed' }, { limit: 100, offset: 0 })).toBe(
      'status=confirmed&limit=100&offset=0',
    )
  })
})
