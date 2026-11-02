import { describe, expect, it } from 'vitest'
import { conditionsFrom, threeC } from './conditions'

const report = {
  findings: [
    { stage: 'documents', rule_id: 'CM-DOC-01', severity: 'cap', message: 'Payslip missing' },
    { stage: 'documents', rule_id: 'CM-DOC-09', severity: 'note', message: 'fyi' },
    { stage: 'kyc', rule_id: 'CM-KYC-02', severity: 'points_lost', message: 'Address' },
  ],
  stage_scores: [
    { stage: 'income', score: 24, max: 30, ran: true },
    { stage: 'credit', score: null, max: 25, ran: false },
  ],
}

describe('report helpers', () => {
  it('lists only document findings that are not plain notes', () => {
    expect(conditionsFrom(report).map((f) => f.rule_id)).toEqual(['CM-DOC-01'])
  })
  it('regroups existing stage scores without adding numbers', () => {
    expect(threeC(report)).toEqual({
      capacity: { score: 24, max: 30 },
      credit: null,
      collateral: null,
    })
  })
})
