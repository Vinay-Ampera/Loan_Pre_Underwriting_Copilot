import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Sidebar from './Sidebar'

const links = (role) => {
  render(
    <MemoryRouter>
      <Sidebar user={{ role }} />
    </MemoryRouter>,
  )
  return within(screen.getByRole('navigation', { name: 'Main' }))
    .getAllByRole('link')
    .map((a) => a.textContent)
}

describe('Sidebar', () => {
  it('gives the auditor overview, cases table, audit log, users and help only', () => {
    expect(links('auditor')).toEqual(['Overview', 'Cases', 'Audit log', 'Users', 'Help'])
  })

  it('gives the admin messages and the audit log but no case list or creating', () => {
    const items = links('admin')
    expect(items).toEqual([
      'Home',
      'Precedents',
      'Messages',
      'Issues',
      'Users',
      'Audit log',
      'Help',
    ])
    expect(items).not.toContain('New case')
  })
})
