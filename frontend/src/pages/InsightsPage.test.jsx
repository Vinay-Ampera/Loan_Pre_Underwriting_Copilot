import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), blob: vi.fn() },
}))

import { api } from '../api/client'
import InsightsPage from './InsightsPage'
import HomePage from './HomePage'

const H = 3600
const cases = [{ id: 'c2', case_no: 'CASE-2026-0002' }]
const adminPage = {
  scope: { start: null, end: null, loan_type: null },
  time_to_decide: {
    report_ready: { n: 7, median_s: 4 * H, slowest_s: 8 * H },
    officer_decided: { n: 4, median_s: 13.5 * H, slowest_s: 48 * H },
    by_loan_type: [{ loan_type: 'home', n: 2, median_s: 2 * H }],
    by_officer: [{ officer_id: 'o1', officer: 'Asha Officer', n: 2, median_s: 36 * H }],
  },
  funnel: {
    created: 10, submitted: 9, report_ready: 7, decided: 4, confirmed: 2, changed: 2,
    not_submitted: 1, running: 1, stopped: 1, waiting: 3,
  }, // prettier-ignore
  agreement: {
    confirmed: 2,
    changed: 2,
    admin_corrections: 1,
    by_loan_type: [{ loan_type: 'home', confirmed: 1, changed: 1 }],
    by_band: [{ band: 'refer', confirmed: 1, changed: 1 }],
  },
  changed_rules: [
    {
      rule_id: 'CM-INC-10', clause_id: 'CM-INC-01', clause_title: 'FOIR', clause_doc: 'common',
      from: 'refer', to: 'approve', n: 1, cases,
    }, // prettier-ignore
  ],
  stop_reasons: [
    {
      stage: 'kyc', stage_label: 'KYC', rule_id: 'CM-KYC-03', clause_id: 'CM-KYC-03',
      clause_title: 'Name match', clause_doc: 'common', n: 2, cases,
    }, // prettier-ignore
  ],
  precedents: { reached: 2, moved: 1, cases, moved_cases: cases },
}
const strip = (row) =>
  Object.fromEntries(
    Object.entries(row).filter(([k]) => !['cases', 'moved_cases', 'officer_id'].includes(k)),
  )
const auditorPage = {
  ...adminPage,
  time_to_decide: {
    ...adminPage.time_to_decide,
    by_officer: adminPage.time_to_decide.by_officer.map(strip),
  },
  changed_rules: adminPage.changed_rules.map(strip),
  stop_reasons: adminPage.stop_reasons.map(strip),
  precedents: { reached: 2, moved: 1 },
}

const show = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const lastUrl = () => api.get.mock.calls.at(-1)[0]

beforeEach(() => api.get.mockReset())

describe('Insights', () => {
  it('shows every panel to the admin with links to the cases and the clause', async () => {
    api.get.mockResolvedValue(adminPage)
    show(<InsightsPage audience="admin" />)
    expect(await screen.findByText('13.5 hours')).toBeInTheDocument()
    expect(lastUrl()).toBe('/admin/insights')
    expect(screen.getByText('No AI is used on this page.', { exact: false })).toBeInTheDocument()
    expect(
      screen.getByText('Confirmed 2 (50%) · Changed by the officer 2 (50%)'),
    ).toBeInTheDocument()
    expect(screen.getByText('Admin corrections: 1')).toBeInTheDocument()
    expect(screen.getByText('Refer → approve (officer)')).toBeInTheDocument()
    expect(
      screen.getByText("A precedent's bonus reached 2 cases; it moved 1 of them to another band."),
    ).toBeInTheDocument()
    const clause = screen.getByRole('link', { name: 'CM-INC-01' })
    expect(clause).toHaveAttribute('href', '/admin/knowledge?doc=common&clause=CM-INC-01')
    const rules = screen.getByRole('region', { name: 'Rules in changed decisions' })
    expect(within(rules).getByRole('link', { name: 'CASE-2026-0002' })).toHaveAttribute(
      'href',
      '/cases/c2',
    )
    expect(document.body.textContent).not.toMatch(/\bapproved\b/i)
  })

  it('gives the auditor the same counts with no link and says so', async () => {
    api.get.mockResolvedValue(auditorPage)
    show(<InsightsPage audience="auditor" />)
    expect(await screen.findByText('13.5 hours')).toBeInTheDocument()
    expect(lastUrl()).toBe('/auditor/insights')
    expect(screen.getByText('Counts only. Cases cannot be opened from here.')).toBeInTheDocument()
    expect(screen.queryAllByRole('link')).toHaveLength(0)
    expect(screen.queryByText(/open the cases/)).toBeNull()
    expect(screen.getByText('CM-INC-01')).toBeInTheDocument() // the clause tag, as text
  })

  it('filters by period and loan type, and clears them', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(adminPage)
    show(<InsightsPage audience="admin" />)
    await screen.findByText('13.5 hours')
    expect(screen.getByText('Showing all cases.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('From'), '2026-11-01')
    await user.type(screen.getByLabelText('To'), '2026-11-25')
    await user.selectOptions(screen.getByLabelText('Loan type'), 'home')
    const q = new URLSearchParams(lastUrl().split('?')[1])
    expect(new Date(q.get('start')).getTime()).toBe(new Date(2026, 10, 1).getTime())
    expect(new Date(q.get('end')).getTime()).toBe(new Date(2026, 10, 26).getTime()) // whole day
    expect(q.get('loan_type')).toBe('home')
    expect(screen.getByText(/Showing home loan cases created 1 Nov 2026 to 25 Nov 2026/i))

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(lastUrl()).toBe('/admin/insights')
    expect(screen.getByText('Showing all cases.')).toBeInTheDocument()
  })

  it('does not ask for a period that ends before it starts', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(adminPage)
    show(<InsightsPage audience="admin" />)
    await screen.findByText('13.5 hours')
    await user.type(screen.getByLabelText('From'), '2026-11-20')
    const calls = api.get.mock.calls.length
    await user.type(screen.getByLabelText('To'), '2026-11-02')
    expect(screen.getByRole('alert')).toHaveTextContent('The end date is before the start date.')
    expect(api.get.mock.calls.length).toBe(calls)
  })

  it('says when no case was created in the period', async () => {
    api.get.mockResolvedValue({ ...adminPage, funnel: { ...adminPage.funnel, created: 0 } })
    show(<InsightsPage audience="admin" />)
    expect(await screen.findByText('No cases in this period')).toBeInTheDocument()
    expect(screen.queryByText('Time to decide')).toBeNull()
  })
})

describe('officer Home', () => {
  const answer = (mine) => (url) => Promise.resolve(url === '/me/insights' ? mine : [])

  it('shows the officer’s own median time to decide', async () => {
    api.get.mockImplementation(
      answer({ decided_30d: 2, median_decision_s: 36 * H, overdue: 3, sla_working_days: 2 }),
    )
    show(<HomePage />)
    const pace = await screen.findByRole('list', { name: 'Case summary' })
    expect(within(pace).getByText('36 hours')).toBeInTheDocument()
    expect(within(pace).getByText('Your median time to decide')).toBeInTheDocument()
    const overdue = within(pace).getByRole('link', { name: /Overdue/ })
    expect(overdue).toHaveTextContent('3')
    expect(overdue).toHaveTextContent('Past the 2 working day target')
    expect(overdue).toHaveAttribute('href', '/cases?due=overdue')
    expect(api.get).toHaveBeenCalledWith('/me/insights')
  })

  it('says when there is no decision yet', async () => {
    api.get.mockImplementation(
      answer({ decided_30d: 0, median_decision_s: null, overdue: 0, sla_working_days: 2 }),
    )
    show(<HomePage />)
    expect(await screen.findByText('No decisions yet')).toBeInTheDocument()
  })
})
