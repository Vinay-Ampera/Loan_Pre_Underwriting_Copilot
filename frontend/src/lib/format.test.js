import { describe, expect, it } from 'vitest'
import { formatDay, formatWhen, rupees, tidyFinding, tidySummary } from './format'

describe('format', () => {
  it('writes dates with the month in words', () => {
    expect(formatWhen('2026-11-01T07:13:45Z')).toMatch(/^1 Nov 2026, \d{1,2}:\d{2} (am|pm)$/i)
    expect(formatDay('2026-11-01T07:13:45Z')).toBe('1 Nov 2026')
    expect(formatWhen('not a date')).toBe('')
  })

  it('groups rupees the Indian way', () => {
    expect(rupees(1280000)).toBe('₹12,80,000')
    expect(rupees('12800.0')).toBe('₹12,800')
  })

  it('tidies a rules-engine finding and drops the rule id from the sentence', () => {
    expect(tidyFinding('CM-INC-10 earned 0 of 12 points: foir: 72.6')).toBe(
      'Earned 0 of 12 points: FOIR 72.6%',
    )
    expect(tidyFinding('HL-INC-11 earned 0 of 6 points: net monthly income: 12800.0')).toBe(
      'Earned 0 of 6 points: Net monthly income ₹12,800',
    )
    expect(tidyFinding('CM-CRD-11 earned 0 of 6 points: cheque nach returns 12m: 3')).toBe(
      'Earned 0 of 6 points: Cheque or NACH returns in 12 months: 3',
    )
    expect(tidyFinding('HL-PROD-02 failed: ltv percent: 96.9 (needed 90)')).toBe(
      'Failed: LTV 96.9% (needed 90%)',
    )
    expect(tidyFinding('CM-KYC-01 failed: pan valid: False')).toBe('Failed: PAN valid: no')
  })

  it('leaves any other sentence alone', () => {
    expect(tidyFinding('The PAN does not match.')).toBe('The PAN does not match.')
    expect(tidyFinding(null)).toBe(null)
  })

  it('adds units to the figures a summary quotes, and drops the stale awaiting line once decided', () => {
    const s =
      'A FOIR of 72.6, a net monthly income of 12800.0 and an LTV percentage of 96.9. Awaiting your confirmation.'
    expect(tidySummary(s)).toContain('FOIR of 72.6%')
    expect(tidySummary(s)).toContain('net monthly income of ₹12,800')
    expect(tidySummary(s)).toContain('LTV of 96.9%')
    expect(tidySummary(s)).toContain('Awaiting your confirmation.')
    expect(tidySummary(s, { decided: true })).not.toContain('Awaiting')
  })
})

describe('duration', () => {
  it('reads minutes, hours or days', async () => {
    const { duration } = await import('./format')
    expect(duration(30)).toBe('1 min')
    expect(duration(40 * 60)).toBe('40 min')
    expect(duration(3600)).toBe('1 hour')
    expect(duration(13.5 * 3600)).toBe('13.5 hours')
    expect(duration(36 * 3600)).toBe('36 hours')
    expect(duration(4.2 * 86400)).toBe('4.2 days')
    expect(duration(null)).toBe('–')
  })
})
