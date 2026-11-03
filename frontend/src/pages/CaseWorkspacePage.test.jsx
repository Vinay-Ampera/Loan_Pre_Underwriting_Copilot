import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = { role: 'auditor' }
vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), del: vi.fn(), blob: vi.fn() },
}))
vi.mock('../App', () => ({
  useSession: () => ({ session: { user: { id: 'u1', name: 'X', role: state.role } } }),
}))

import { api } from '../api/client'
import CaseWorkspacePage from './CaseWorkspacePage'

const caseData = (status) => ({
  id: 'c1',
  case_no: 'CASE-2026-0001',
  loan_type: 'personal',
  status,
  loan_amount: 100000,
  tenure_months: 24,
  total_score: null,
  band: null,
  recommendation: null,
  stopped_stage: null,
  stop_class: null,
  officer: 'Asha Officer',
  applicants: [{ role: 'primary', full_name: 'T*** P***', email: '****@example.com' }],
  documents: [
    {
      id: 'd1',
      role: 'primary',
      doc_type: 'pan_card',
      name: 'pan.pdf',
      mime: 'application/pdf',
      status: 'accepted',
      warnings: [],
      message: '',
      fields: [{ name: 'name', value: 'masked', needs_review: false }],
    },
  ],
  checklist: [],
  doc_types: ['pan_card'],
  kyc_ready: true,
  co_applicant: 'not_allowed',
  stages: [],
  report: null,
  officer_action: null,
  last_failure: { error: 'Boom', at: '2026-11-03T10:00:00Z' },
  loan_fields: [],
})

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/cases/c1']}>
      <Routes>
        <Route path="/cases/:id" element={<CaseWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  )

const ACTIONS = [
  /submit for assessment/i,
  /^confirm/i,
  /override/i,
  /resume assessment/i,
  /correct details/i,
  /^remove/i,
  /contact the customer/i,
  /export pdf/i,
]

beforeEach(() => {
  api.get.mockReset()
  api.blob.mockReset()
  state.role = 'auditor'
})

describe('CaseWorkspacePage for the auditor', () => {
  it.each(['draft', 'awaiting_confirmation', 'stopped', 'confirmed'])(
    'shows a %s case view-only: no action buttons, no upload',
    async (status) => {
      api.get.mockResolvedValue(caseData(status))
      renderPage()
      expect(await screen.findByText(/Read-only\./)).toBeInTheDocument()
      expect(screen.getByText(/officer Asha Officer/)).toBeInTheDocument()
      for (const name of ACTIONS) expect(screen.queryByRole('button', { name })).toBeNull()
      expect(screen.queryByText(/drop|choose files|browse/i)).toBeNull()
      expect(screen.queryByText(/The assessment failed/)).toBeNull()
    },
  )

  it('never requests a document file and says documents are not shown', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(caseData('confirmed'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'View' }))
    expect(await screen.findByText(/does not see the original document/i)).toBeInTheDocument()
    expect(api.blob).not.toHaveBeenCalled()
    expect(api.get.mock.calls.every(([path]) => !path.includes('/file'))).toBe(true)
  })
})

describe('CaseWorkspacePage for an officer', () => {
  it('still offers the actions (so the checks above can fail)', async () => {
    state.role = 'officer'
    api.get.mockResolvedValue(caseData('draft'))
    renderPage()
    expect(await screen.findByRole('button', { name: /submit for assessment/i })).toBeEnabled()
    expect(screen.queryByText(/Read-only\./)).toBeNull()
    expect(screen.getByRole('button', { name: /^remove/i })).toBeInTheDocument()
  })
})
