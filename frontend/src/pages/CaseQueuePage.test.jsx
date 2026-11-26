import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CaseQueuePage from './CaseQueuePage'
import AdminHomePage from './AdminHomePage'
import AdminOfficerPage from './AdminOfficerPage'
import { api } from '../api/client'
import { downloadFile } from '../lib/download'
import { caseAge } from '../lib/format'

vi.mock('../api/client', () => ({ api: { get: vi.fn() } }))
vi.mock('../lib/download', async (importOriginal) => ({
  ...(await importOriginal()),
  downloadFile: vi.fn(),
}))

const HOUR = 3_600_000
const ago = (ms) => new Date(Date.now() - ms).toISOString()
const row = (n, extra) => ({
  id: `c${n}`,
  case_no: `CASE-2026-000${n}`,
  loan_type: 'personal',
  loan_amount: 500000,
  status: 'awaiting_confirmation',
  band: 'refer',
  total_score: 70,
  officer: 'Asha Officer',
  applicant: 'A Person',
  created_at: ago(5 * HOUR),
  due_state: null,
  sla_due_at: null,
  sla_working_days: 2,
  ...extra,
})
const rows = [
  row(1, { due_state: 'overdue', sla_due_at: '2026-11-24T09:30:00Z', created_at: ago(73 * HOUR) }),
  row(2, { due_state: 'due_today', sla_due_at: '2026-11-26T09:30:00Z' }),
  row(3, {}),
]

const show = (page, at = '/cases') =>
  render(<MemoryRouter initialEntries={[at]}>{page}</MemoryRouter>)

describe('the queue and the decision timer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue(rows)
  })

  it('shows each case’s age and its due badge, with the due time for screen readers', async () => {
    show(<CaseQueuePage />)
    const table = await screen.findByRole('table')
    const [, first, second, third] = within(table).getAllByRole('row')
    expect(within(first).getByText('3 days')).toBeInTheDocument()
    expect(within(first).getByText('Overdue')).toBeInTheDocument()
    expect(first).toHaveTextContent(/Decision due 24 Nov 2026.*2 working days after the report/)
    expect(within(second).getByText('Due today')).toBeInTheDocument()
    expect(within(second).getByText('5 hours')).toBeInTheDocument()
    expect(third).not.toHaveTextContent(/Due today|Overdue|Decision due/)
  })

  it('filters by due state and exports with the filters that are set', async () => {
    const user = userEvent.setup()
    show(<CaseQueuePage />, '/cases?view=awaiting')
    await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Due'), 'overdue')
    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith('/cases?due=overdue'))
    await user.selectOptions(screen.getByLabelText('Loan type'), 'home')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(downloadFile).toHaveBeenCalledWith(
      '/cases/export.csv?loan_type=home&due=overdue&view=awaiting',
      expect.stringMatching(/^pramaan-cases-\d{4}-\d{2}-\d{2}\.csv$/),
    )
    expect(screen.queryByRole('dialog')).toBeNull() // a download changes nothing: no second click
    expect(screen.getByText(/No applicant names/)).toBeInTheDocument()
  })

  it('opens already filtered from the address', async () => {
    show(<CaseQueuePage />, '/cases?due=overdue')
    await screen.findByRole('table')
    expect(screen.getByLabelText('Due')).toHaveValue('overdue')
    expect(api.get).toHaveBeenCalledWith('/cases?due=overdue')
  })

  it('says why when a download fails', async () => {
    downloadFile.mockRejectedValue(new Error('Cannot reach the server.'))
    const user = userEvent.setup()
    show(<CaseQueuePage />)
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot reach the server.')
  })

  it('lets the admin export every case from Home', async () => {
    api.get.mockImplementation((url) =>
      Promise.resolve(url === '/admin/summary' ? { pending_precedents: 0 } : []),
    )
    const user = userEvent.setup()
    show(<AdminHomePage />, '/')
    await user.click(screen.getByRole('button', { name: 'Export all cases' }))
    expect(downloadFile).toHaveBeenCalledWith('/admin/cases/export.csv', expect.any(String))
  })

  it('exports only that officer’s cases from the admin’s officer page', async () => {
    api.get.mockResolvedValue({
      user: { name: 'Asha Officer', email: 'asha@example.test', role: 'officer', active: true },
      cases_total: 0,
      cases_by_status: {},
      cases_by_band: {},
      precedents_by_status: {},
      confirmed: 0,
      overridden: 0,
      admin_corrected: 0,
      cases: [],
    })
    const user = userEvent.setup()
    show(
      <Routes>
        <Route path="/admin/users/:id" element={<AdminOfficerPage />} />
      </Routes>,
      '/admin/users/u-7',
    )
    await user.click(await screen.findByRole('button', { name: "Export this officer's cases" }))
    expect(downloadFile).toHaveBeenCalledWith(
      '/admin/cases/export.csv?officer=u-7',
      expect.any(String),
    )
    expect(screen.queryByRole('button', { name: 'Export all cases' })).toBeNull()
  })
})

describe('caseAge', () => {
  const now = Date.parse('2026-11-26T12:00:00Z')
  it.each([
    ['2026-11-26T11:30:00Z', 'under an hour'],
    ['2026-11-26T11:00:00Z', '1 hour'],
    ['2026-11-26T07:00:00Z', '5 hours'],
    ['2026-11-25T12:00:00Z', '1 day'],
    ['2026-11-23T11:00:00Z', '3 days'],
    [undefined, '–'],
  ])('%s reads %s', (created, words) => {
    expect(caseAge(created, now)).toBe(words)
  })
})
