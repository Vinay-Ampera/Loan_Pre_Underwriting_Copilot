import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = { role: 'admin' }
vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), del: vi.fn(), blob: vi.fn() },
}))
vi.mock('../App', () => ({
  useSession: () => ({ session: { user: { id: 'u1', name: 'X', role: state.role } } }),
}))

import { api } from '../api/client'
import CaseWorkspacePage from './CaseWorkspacePage'

const caseData = (status, extra = {}) => ({
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
  officer_id: 'o1',
  applicants: [{ role: 'primary', full_name: 'Test Person', email: '****@example.com' }],
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
      fields: [{ name: 'name', value: 'Test Person', needs_review: false }],
    },
  ],
  checklist: [],
  doc_types: ['pan_card'],
  kyc_ready: true,
  co_applicant: 'not_allowed',
  stages: [],
  report: null,
  officer_action: null,
  admin_actions: [],
  decision_in_force: null,
  admin_block: null,
  last_failure: { error: 'Boom', at: '2026-11-03T10:00:00Z' },
  loan_fields: [],
  ...extra,
})

const decided = (extra = {}) =>
  caseData('confirmed', {
    last_failure: null,
    decision_in_force: 'approve',
    officer_action: {
      action: 'confirm',
      final_decision: 'approve',
      reason: null,
      at: '2026-11-03T10:00:00Z',
      officer: 'Asha Officer',
    },
    ...extra,
  })

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/cases/c1']}>
      <Routes>
        <Route path="/cases/:id" element={<CaseWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  )

// what only the officer does
const OFFICER_ACTIONS = [
  /submit for assessment/i,
  /^confirm/i,
  /^override/i,
  /resume assessment/i,
  /correct details/i,
  /^remove/i,
  /contact the customer/i,
  /export pdf/i,
]

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.blob.mockReset()
  state.role = 'admin'
})

describe('CaseWorkspacePage for the admin', () => {
  it.each(['draft', 'awaiting_confirmation', 'stopped', 'confirmed'])(
    'shows a %s case without any officer action or upload',
    async (status) => {
      api.get.mockResolvedValue(caseData(status))
      renderPage()
      expect(await screen.findByText(/Admin view\./)).toBeInTheDocument()
      expect(screen.getByText(/officer Asha Officer/)).toBeInTheDocument()
      expect(screen.getByText(/Test Person/)).toBeInTheDocument() // names are shown as they are
      for (const name of OFFICER_ACTIONS) expect(screen.queryByRole('button', { name })).toBeNull()
      expect(screen.queryByText(/drop|choose files|browse/i)).toBeNull()
      expect(screen.queryByText(/The assessment failed/)).toBeNull()
    },
  )

  it('offers Change the decision only after the officer has decided', async () => {
    api.get.mockResolvedValue(caseData('awaiting_confirmation'))
    renderPage()
    await screen.findByText(/Admin view\./)
    expect(screen.queryByRole('button', { name: /change the decision/i })).toBeNull()
    expect(screen.getByText(/only after the officer has decided/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reassign to another officer/i })).toBeInTheDocument()
  })

  it('offers no reassign once the officer has decided', async () => {
    api.get.mockResolvedValue(decided())
    renderPage()
    expect(await screen.findByRole('button', { name: /change the decision/i })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /reassign/i })).toBeNull()
  })

  it('explains, and offers no change, when a hard rule failed', async () => {
    api.get.mockResolvedValue(
      decided({ admin_block: 'This case failed a hard rule, which an admin cannot override.' }),
    )
    renderPage()
    expect(await screen.findByText(/failed a hard rule/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /change the decision/i })).toBeNull()
  })

  it('needs a different decision and a written reason, and the dialog button is the second click', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(decided())
    api.post.mockResolvedValue({ decision_in_force: 'reject' })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /change the decision/i }))
    const dialog = screen.getByRole('dialog')
    const go = within(dialog).getByRole('button', { name: /yes, change the decision/i })
    expect(go).toBeDisabled()
    // the decision in force is not offered again
    expect(within(dialog).queryByRole('option', { name: 'approve' })).toBeNull()
    await user.selectOptions(within(dialog).getByLabelText('New decision'), 'reject')
    await user.type(within(dialog).getByLabelText(/reason/i), 'too short')
    expect(go).toBeDisabled()
    await user.type(within(dialog).getByLabelText(/reason/i), ' but now long enough')
    expect(go).toBeEnabled()
    expect(api.post).not.toHaveBeenCalled()
    await user.click(go)
    expect(api.post).toHaveBeenCalledWith('/admin/cases/c1/override', {
      final_decision: 'reject',
      reason: 'too short but now long enough',
      second_click: true,
    })
  })

  it('reassigns to an active officer other than the owner, with a reason', async () => {
    const user = userEvent.setup()
    api.get.mockImplementation(async (path) =>
      path === '/admin/users'
        ? [
            { id: 'o1', name: 'Asha Officer', role: 'officer', active: true },
            { id: 'o2', name: 'Ben Officer', role: 'officer', active: true },
            { id: 'o3', name: 'Cy Officer', role: 'officer', active: false },
            { id: 'a1', name: 'Ada Admin', role: 'admin', active: true },
          ]
        : caseData('awaiting_confirmation'),
    )
    api.post.mockResolvedValue({ officer: 'Ben Officer' })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /reassign to another officer/i }))
    const dialog = screen.getByRole('dialog')
    const options = await within(dialog).findAllByRole('option')
    expect(options.map((o) => o.textContent)).toEqual(['Choose…', 'Ben Officer'])
    await user.selectOptions(within(dialog).getByLabelText('New officer'), 'o2')
    await user.type(within(dialog).getByLabelText(/reason/i), 'Asha is on leave this week')
    await user.click(within(dialog).getByRole('button', { name: /yes, reassign/i }))
    expect(api.post).toHaveBeenCalledWith('/admin/cases/c1/reassign', {
      officer_id: 'o2',
      reason: 'Asha is on leave this week',
      second_click: true,
    })
  })

  it('shows the officer decision and the admin change that replaced it', async () => {
    api.get.mockResolvedValue(
      decided({
        decision_in_force: 'reject',
        admin_actions: [
          {
            admin: 'Ada Admin',
            previous_decision: 'approve',
            final_decision: 'reject',
            reason: 'The income proof does not match.',
            at: '2026-11-03T12:00:00Z',
          },
        ],
      }),
    )
    renderPage()
    expect(await screen.findByText('Recommendation confirmed')).toBeInTheDocument()
    expect(screen.getByText('Changed by an admin')).toBeInTheDocument()
    expect(screen.getByText(/The income proof does not match\./)).toBeInTheDocument()
  })

  it('loads the document file for the admin', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(decided())
    api.blob.mockResolvedValue(new Blob(['x'], { type: 'application/pdf' }))
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    renderPage()
    await user.click(await screen.findByRole('button', { name: 'View' }))
    expect(api.blob).toHaveBeenCalledWith('/cases/c1/documents/d1/file')
  })
})

describe('CaseWorkspacePage for an officer', () => {
  it('still offers the actions (so the checks above can fail)', async () => {
    state.role = 'officer'
    api.get.mockResolvedValue(caseData('draft'))
    renderPage()
    expect(await screen.findByRole('button', { name: /submit for assessment/i })).toBeEnabled()
    expect(screen.queryByText(/Admin view\./)).toBeNull()
    expect(screen.getByRole('button', { name: /^remove/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /change the decision/i })).toBeNull()
  })

  it('is told when an admin changed the decision', async () => {
    state.role = 'officer'
    const data = decided({
      decision_in_force: 'refer',
      admin_actions: [
        {
          admin: 'Ada Admin',
          previous_decision: 'approve',
          final_decision: 'refer',
          reason: 'Needs a branch manager look.',
          at: '2026-11-03T12:00:00Z',
        },
      ],
    })
    api.get.mockImplementation(async (path) => (path.includes('/messages') ? [] : data))
    renderPage()
    expect(await screen.findByText('Changed by an admin')).toBeInTheDocument()
    expect(screen.getByText(/Needs a branch manager look\./)).toBeInTheDocument()
  })
})
