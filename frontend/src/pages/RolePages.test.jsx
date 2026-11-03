import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), blob: vi.fn() },
}))

import { api } from '../api/client'
import AdminHomePage from './AdminHomePage'
import AdminMessagesPage from './AdminMessagesPage'
import AdminOfficerPage from './AdminOfficerPage'
import AuditLogPage from './AuditLogPage'
import AuditorCasesPage from './AuditorCasesPage'
import AuditorUsersPage from './AuditorUsersPage'

const at = (day) => new Date(`${day}T12:00:00`).toISOString()
const page = (ui, path = '/') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/admin/users/:id" element={ui} />
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>,
  )

beforeEach(() => {
  api.get.mockReset()
  api.blob.mockReset()
})

describe('admin Messages', () => {
  const rows = [
    {
      id: 'm1',
      case_id: 'c1',
      case_no: 'CASE-2026-0001',
      officer_id: 'o1',
      officer: 'Asha Officer',
      template: 'blank',
      template_label: 'Blank',
      recipient: '****@example.com',
      text: 'Please call me.',
      sent_at: at('2026-11-02'),
    },
    {
      id: 'm2',
      case_id: 'c2',
      case_no: 'CASE-2026-0002',
      officer_id: 'o2',
      officer: 'Ben Officer',
      template: 'call_me',
      template_label: 'Call me',
      recipient: '****@example.com',
      text: 'Call the branch.',
      sent_at: at('2026-11-04'),
    },
  ]

  it('lists sent messages and filters by officer, template and date', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(rows)
    page(<AdminMessagesPage />)
    expect(await screen.findByText('Showing 2 of 2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit|delete|send/i })).toBeNull()
    expect(screen.queryByText('Draft')).toBeNull()

    await user.selectOptions(screen.getByLabelText('Officer'), 'o2')
    expect(screen.getByText('Showing 1 of 2')).toBeInTheDocument()
    expect(screen.getByText('CASE-2026-0002')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await user.selectOptions(screen.getByLabelText('Template'), 'blank')
    expect(screen.getByText('CASE-2026-0001')).toBeInTheDocument()
    expect(screen.queryByText('CASE-2026-0002')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await user.type(screen.getByLabelText('From'), '2026-11-03')
    expect(screen.getByText('Showing 1 of 2')).toBeInTheDocument()
  })

  it('opens a message to read it, and nothing else', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(rows)
    page(<AdminMessagesPage />)
    await user.click((await screen.findAllByRole('button', { name: /^Open/ }))[0])
    expect(within(screen.getByRole('dialog')).getByText('Please call me.')).toBeInTheDocument()
  })
})

describe('AuditLogPage', () => {
  const log = {
    total: 1,
    rows: [
      {
        at: at('2026-11-03'),
        actor: 'Ada Admin',
        actor_role: 'admin',
        action: 'admin_override',
        case_no: 'CASE-2026-0001',
        case_id: 'c1',
        after: { final: 'reject' },
      },
    ],
  }
  const serve = async (path) => {
    if (path.includes('/audit-log/actions')) return ['admin_override', 'login']
    if (path.endsWith('/users')) return [{ id: 'u1', name: 'Ada Admin' }]
    return log
  }

  it('filters by user and case reference', async () => {
    const user = userEvent.setup()
    api.get.mockImplementation(serve)
    page(<AuditLogPage />)
    await screen.findByText('CASE-2026-0001')
    await user.selectOptions(screen.getByLabelText('User'), 'u1')
    await user.type(screen.getByLabelText('Case reference'), 'CASE-2026')
    const urls = api.get.mock.calls.map(([p]) => p).filter((p) => p.includes('/auditor/audit-log?'))
    const last = new URLSearchParams(urls.at(-1).split('?')[1])
    expect(last.get('actor')).toBe('u1')
    expect(last.get('case_no')).toBe('CASE-2026')
  })

  it('shows masked entries with no link into a case', async () => {
    api.get.mockImplementation(async (path) =>
      path.includes('/audit-log?')
        ? { ...log, rows: [{ ...log.rows[0], case_id: null }] }
        : serve(path),
    )
    page(<AuditLogPage />)
    expect(await screen.findByText('CASE-2026-0001')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'CASE-2026-0001' })).toBeNull()
    expect(screen.getByText(/Identifiers are masked/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/auditor/users')
  })

  it('exports the filtered rows as CSV', async () => {
    const user = userEvent.setup()
    api.get.mockImplementation(serve)
    api.blob.mockResolvedValue(new Blob(['x']))
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    page(<AuditLogPage />)
    await screen.findByText('CASE-2026-0001')
    await user.selectOptions(screen.getByLabelText('Action'), 'login')
    await user.click(screen.getByRole('button', { name: 'Export CSV' }))
    expect(api.blob).toHaveBeenCalledWith('/auditor/audit-log.csv?action=login')
  })
})

describe('auditor Cases and Users', () => {
  const cases = {
    total: 1,
    rows: [
      {
        case_no: 'CASE-2026-0001',
        loan_type: 'personal',
        officer: 'Asha Officer',
        status: 'confirmed',
        band: 'approve',
        score: 88,
        officer_decision: 'override',
        admin_corrected: true,
        created_at: at('2026-11-01'),
        updated_at: at('2026-11-02'),
      },
    ],
  }

  it('is a static table: no links into a case, filters, and an export', async () => {
    api.get.mockImplementation(async (path) =>
      path.startsWith('/auditor/users')
        ? [{ id: 'o1', name: 'Asha Officer', role: 'officer' }]
        : cases,
    )
    page(<AuditorCasesPage />, '/auditor/cases?overridden=admin')
    expect(await screen.findByText('CASE-2026-0001')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /CASE-2026-0001/ })).toBeNull()
    const table = within(screen.getByRole('table'))
    expect(table.getByText('Overridden')).toBeInTheDocument()
    expect(table.getByText('Yes')).toBeInTheDocument()
    expect(screen.getByLabelText('Changed')).toHaveValue('admin') // from the Overview tile link
    expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument()
    const sent = api.get.mock.calls.map(([p]) => p).find((p) => p.startsWith('/auditor/cases?'))
    expect(sent).toContain('overridden=admin')
  })

  it('lists users with their last sign-in and no buttons', async () => {
    api.get.mockResolvedValue([
      {
        id: 'u1',
        name: 'Ada Admin',
        role: 'admin',
        active: true,
        locked: false,
        last_login: at('2026-11-03'),
      },
      {
        id: 'u2',
        name: 'Cy Officer',
        role: 'officer',
        active: false,
        locked: false,
        last_login: null,
      },
    ])
    page(<AuditorUsersPage />)
    expect(await screen.findByText('Ada Admin')).toBeInTheDocument()
    expect(screen.getByText('Never')).toBeInTheDocument()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('admin Home and officer page', () => {
  it('lists recent decisions with a link to the case and a corrected flag', async () => {
    api.get.mockImplementation(async (path) =>
      path === '/admin/summary'
        ? { pending_precedents: 0, active_officers: 1, disabled_accounts: 0, open_issues: 0 }
        : [
            {
              id: 'c1',
              case_no: 'CASE-2026-0001',
              loan_type: 'personal',
              status: 'confirmed',
              officer: 'Asha Officer',
              decided_at: at('2026-11-03'),
              corrected: true,
            },
          ],
    )
    page(<AdminHomePage />)
    expect(await screen.findByRole('link', { name: 'CASE-2026-0001' })).toHaveAttribute(
      'href',
      '/cases/c1',
    )
    expect(screen.getByText('Changed by an admin')).toBeInTheDocument()
  })

  const activity = {
    user: { id: 'o1', name: 'Asha Officer', email: 'a@x.test', role: 'officer', active: true },
    last_login: null,
    cases_total: 2,
    cases_by_status: {},
    cases_by_band: {},
    confirmed: 0,
    overridden: 0,
    admin_corrected: 1,
    precedents_by_status: {},
    cases: [
      {
        id: 'c1',
        case_no: 'CASE-2026-0001',
        loan_type: 'personal',
        status: 'awaiting_confirmation',
        band: 'refer',
        applicant: 'Test Person',
        loan_amount: 100000,
        corrected: false,
        updated_at: at('2026-11-03'),
      },
      {
        id: 'c2',
        case_no: 'CASE-2026-0002',
        loan_type: 'home',
        status: 'confirmed',
        band: 'approve',
        applicant: 'Other Person',
        loan_amount: 500000,
        corrected: true,
        updated_at: at('2026-11-02'),
      },
    ],
  }

  it('lists the officer’s cases as links and filters to the ones not yet decided', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(activity)
    page(<AdminOfficerPage />, '/admin/users/o1')
    expect(await screen.findByRole('link', { name: 'CASE-2026-0002' })).toHaveAttribute(
      'href',
      '/cases/c2',
    )
    await user.selectOptions(screen.getByLabelText('Show'), 'open')
    expect(screen.getByText('CASE-2026-0001')).toBeInTheDocument()
    expect(screen.queryByText('CASE-2026-0002')).toBeNull()
  })

  it('opens already filtered when the disable warning links here', async () => {
    api.get.mockResolvedValue(activity)
    page(<AdminOfficerPage />, '/admin/users/o1?status=open')
    expect(await screen.findByLabelText('Show')).toHaveValue('open')
    expect(screen.queryByText('CASE-2026-0002')).toBeNull()
  })

  it('filters to the cases an admin changed', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(activity)
    page(<AdminOfficerPage />, '/admin/users/o1')
    await user.selectOptions(await screen.findByLabelText('Show'), 'corrected')
    expect(screen.getByText('CASE-2026-0002')).toBeInTheDocument()
    expect(screen.queryByText('CASE-2026-0001')).toBeNull()
  })
})
