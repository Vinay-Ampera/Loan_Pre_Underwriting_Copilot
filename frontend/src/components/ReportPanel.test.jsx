import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import ReportPanel from './ReportPanel'

const report = {
  status: 'awaiting_confirmation',
  recommendation: 'refer',
  recommendation_text: 'Recommended: refer for manual review',
  awaiting: 'Awaiting your confirmation.',
  stop_text: null,
  summary: 'Total score 72 of 100.',
  summary_source: 'code',
  rejection_reason: null,
  stage_scores: [
    { stage: 'kyc', label: 'KYC', score: 18, max: 20, ran: true },
    { stage: 'policy', label: 'Policy fit', score: null, max: 10, ran: false },
  ],
  findings: [
    {
      stage: 'kyc',
      rule_id: 'PL-KYC-02',
      clause_id: 'PL-KYC-02A',
      role: 'primary',
      severity: 'points_lost',
      message: 'Address differs',
      explanation: null,
      points_lost: 2,
      evidence: {},
    },
  ],
  sections: { primary: [0], co: [], case: [] },
  citations: [{ clause_id: 'PL-KYC-02A', text: 'Address on the application must match.' }],
  precedents: [],
  unverified: [{ stage: 'policy', reason: 'findings not grounded' }],
  versions: { rules: '2026.10.31-2' },
}

describe('ReportPanel', () => {
  it('shows the recommendation wording and the awaiting line', () => {
    render(<ReportPanel caseId="c1" caseNo="CASE-2026-0001" report={report} officerAction={null} />)
    expect(screen.getByText('Recommended: refer for manual review')).toBeInTheDocument()
    expect(screen.getByText('Awaiting your confirmation.')).toBeInTheDocument()
    expect(screen.queryByText(/\bapproved\b/i)).not.toBeInTheDocument()
  })

  it('shows unverified stages plainly and a stage that did not run', () => {
    render(<ReportPanel caseId="c1" caseNo="CASE-2026-0001" report={report} officerAction={null} />)
    expect(screen.getByText('Could not be verified automatically')).toBeInTheDocument()
    expect(screen.getByText('Not run')).toBeInTheDocument()
  })

  it('links a finding to its rule id and opens the clause text', async () => {
    const user = userEvent.setup()
    render(<ReportPanel caseId="c1" caseNo="CASE-2026-0001" report={report} officerAction={null} />)
    await user.click(screen.getByRole('button', { name: /KYC/ }))
    expect(screen.getAllByText('PL-KYC-02').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: 'PL-KYC-02A' }))
    expect(screen.getAllByText('Address on the application must match.').length).toBeGreaterThan(1)
  })
})
