import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), del: vi.fn(), blob: vi.fn() },
  login: vi.fn(),
}))

import { api } from './api/client'
import App from './App'

const signInAs = (role, path) => {
  sessionStorage.setItem(
    'lc.session',
    JSON.stringify({ token: 't', user: { id: 'u', name: 'Sam Test', email: 's@x.test', role } }),
  )
  window.history.pushState({}, '', path)
}

beforeEach(() => {
  sessionStorage.clear()
  api.get.mockReset().mockImplementation(async (path) => {
    if (path === '/auditor/summary')
      return { cases: 7, awaiting_confirmation: 1, overridden: 0, pending_precedents: 0 }
    if (path === '/auditor/charts')
      return {
        cases_by_status: {},
        cases_by_loan_type: {},
        cases_by_band: { approve: 0, refer: 0, reject: 0 },
        score_histogram: [],
        officer_actions_by_loan_type: [],
        cases_per_week: [],
        top_failed_rules: [],
      }
    if (path === '/auditor/fairness')
      return {
        min_group: 5,
        attributes: {
          gender: {
            flag: false,
            gap_pp: null,
            groups: [
              { group: 'F', n: 6, approve_rate: 0.5 },
              { group: 'M', too_few: true },
            ],
          },
        },
      }
    return []
  })
})

describe('routing by role', () => {
  it('opens the auditor on the Overview', async () => {
    signInAs('auditor', '/')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByText('7')).toBeInTheDocument()
    expect(await screen.findByText('too few to show')).toBeInTheDocument()
    expect(screen.getByText('F (6)')).toBeInTheDocument()
    expect(screen.getByText('50')).toBeInTheDocument()
  })

  it('sends the auditor away from the officer-only New case page', async () => {
    signInAs('auditor', '/cases/new')
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/')
  })

  it('sends an officer away from the auditor pages and an admin from the case list', async () => {
    signInAs('officer', '/auditor/audit-log')
    const first = render(<App />)
    await screen.findByRole('heading', { name: 'Home' })
    expect(window.location.pathname).toBe('/')
    first.unmount()

    signInAs('admin', '/cases')
    render(<App />)
    await screen.findByRole('heading', { name: 'Home' })
    expect(window.location.pathname).toBe('/')
  })
})
