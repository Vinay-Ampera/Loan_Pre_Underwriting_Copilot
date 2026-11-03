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
  it('gives the auditor read-only destinations and nothing that creates', () => {
    const items = links('auditor')
    expect(items).toEqual(
      expect.arrayContaining(['Overview', 'Cases', 'Messages', 'Audit log', 'Users']),
    )
    expect(items).not.toContain('New case')
    expect(items).not.toContain('Report a problem')
  })
})
