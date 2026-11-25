import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  it('gives the auditor overview, insights, cases table, audit log, users and help only', () => {
    expect(links('auditor')).toEqual([
      'Overview',
      'Insights',
      'Cases',
      'Audit log',
      'Users',
      'Help',
    ])
  })

  it('gives the officer the read-only policy library, and the admin the knowledge base', () => {
    const officer = links('officer')
    expect(officer).toContain('Policies')
    expect(officer).not.toContain('Knowledge base')
    cleanup()
    expect(links('auditor')).not.toContain('Policies')
  })

  it('gives the officer upload links next to sent items', () => {
    const items = links('officer')
    expect(items.indexOf('Upload links')).toBeGreaterThan(items.indexOf('New case'))
    expect(items).toContain('Sent items')
  })

  it('gives the officer an Inbox right after Home, and the auditor none', () => {
    expect(links('officer').slice(0, 2)).toEqual(['Home', 'Inbox'])
    cleanup()
    expect(links('auditor')).not.toContain('Inbox')
  })

  it('gives the auditor Insights right after Overview (Stage 12)', () => {
    expect(links('auditor').slice(0, 2)).toEqual(['Overview', 'Insights'])
  })

  it('gives the admin messages but no audit log, case list or creating', () => {
    const items = links('admin')
    expect(items).toEqual([
      'Home',
      'Insights',
      'Inbox',
      'Precedents',
      'Knowledge base',
      'Upload links',
      'Messages',
      'Issues',
      'Users',
      'AI control',
      'Help',
    ])
    expect(items).not.toContain('New case')
  })

  it('has a Menu button for phones that opens and closes the page list', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Sidebar user={{ role: 'officer' }} />
      </MemoryRouter>,
    )
    const menu = screen.getByRole('button', { name: 'Menu' })
    const nav = screen.getByRole('navigation', { name: 'Main' })
    expect(menu).toHaveAttribute('aria-expanded', 'false')
    expect(menu).toHaveAttribute('aria-controls', nav.id)
    expect(nav).not.toHaveClass('open')
    await user.click(menu)
    expect(menu).toHaveAttribute('aria-expanded', 'true')
    expect(nav).toHaveClass('open')
    await user.keyboard('{Escape}')
    expect(nav).not.toHaveClass('open')
    await user.click(menu)
    await user.click(within(nav).getByRole('link', { name: 'Cases' })) // choosing a page closes it
    expect(nav).not.toHaveClass('open')
  })
})
