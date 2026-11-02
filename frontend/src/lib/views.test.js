import { describe, expect, it } from 'vitest'
import { matchesView, tileCounts } from './views'

const cases = [
  { status: 'awaiting_confirmation', band: 'approve' },
  { status: 'awaiting_confirmation', band: 'refer' },
  { status: 'stopped', band: null },
  { status: 'running' },
  { status: 'draft' },
  { status: 'confirmed', band: 'refer' },
]

describe('home tiles', () => {
  it('counts each tile', () => {
    expect(tileCounts(cases)).toEqual({ awaiting: 2, referred: 1, stopped: 1, progress: 2 })
  })
  it('filters by view and ignores an unknown view', () => {
    expect(cases.filter((c) => matchesView(c, 'referred'))).toHaveLength(1)
    expect(cases.filter((c) => matchesView(c, 'nonsense'))).toHaveLength(cases.length)
    expect(cases.filter((c) => matchesView(c, null))).toHaveLength(cases.length)
  })
})
