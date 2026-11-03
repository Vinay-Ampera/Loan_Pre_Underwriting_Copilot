import { describe, expect, it } from 'vitest'
import { filterCitations, topReasons } from './glance'

const report = {
  findings: [
    { stage: 'kyc', rule_id: 'A', severity: 'points_lost', points_lost: 2, clause_id: 'C-1' },
    { stage: 'income', rule_id: 'B', severity: 'points_lost', points_lost: 6, clause_id: 'C-2' },
    { stage: 'kyc', rule_id: 'C', severity: 'note', points_lost: 0 },
    { stage: 'income', rule_id: 'D', severity: 'hard_fail', points_lost: 0, clause_id: 'C-3' },
    { stage: 'credit', rule_id: 'E', severity: 'cap', points_lost: 0 },
  ],
  citations: [
    { clause_id: 'C-1', text: 'Address proof is required' },
    { clause_id: 'C-2', text: 'FOIR must not exceed 50%' },
    { clause_id: 'C-3', text: 'Minimum age is 21' },
  ],
}

describe('glance helpers', () => {
  it('ranks hard fails, then caps, then the biggest point losses; skips notes', () => {
    expect(topReasons(report).map((f) => f.rule_id)).toEqual(['D', 'E', 'B'])
    expect(topReasons(report, 5).map((f) => f.rule_id)).toEqual(['D', 'E', 'B', 'A'])
  })
  it('filters citations by text, clause id and stage', () => {
    expect(filterCitations(report, { q: 'foir' }).map((c) => c.clause_id)).toEqual(['C-2'])
    expect(filterCitations(report, { q: 'c-3' }).map((c) => c.clause_id)).toEqual(['C-3'])
    expect(filterCitations(report, { stage: 'kyc' }).map((c) => c.clause_id)).toEqual(['C-1'])
    expect(filterCitations(report, {})).toHaveLength(3)
  })
})
