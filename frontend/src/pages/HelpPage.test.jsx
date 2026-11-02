import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

const state = { role: 'officer' }
vi.mock('../App', () => ({ useSession: () => ({ session: { user: { role: state.role } } }) }))

import HelpPage from './HelpPage'

const renderAs = (role) => {
  state.role = role
  return render(
    <MemoryRouter>
      <HelpPage />
    </MemoryRouter>,
  )
}

describe('HelpPage', () => {
  it('has a section menu and quick links that point at real sections', () => {
    renderAs('officer')
    const toc = screen.getByRole('navigation', { name: 'On this page' })
    expect(toc).toHaveTextContent('Score weights and bands')
    for (const a of screen.getByRole('list', { name: 'Quick links' }).querySelectorAll('a')) {
      expect(document.querySelector(a.getAttribute('href'))).not.toBeNull()
    }
  })

  it('shows the officer guide, with the weights and bands, to an officer', () => {
    renderAs('officer')
    expect(screen.getByText('Guide for loan officers')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Score weights' })).toHaveTextContent('Income and FOIR')
    expect(screen.getByRole('list', { name: 'Score bands' })).toHaveTextContent('60 to 84: refer')
    expect(screen.getByRole('heading', { name: 'Confirm or override' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'The precedent queue' })).toBeNull()
  })

  it('shows the admin guide, without the officer guide, to an admin', () => {
    renderAs('admin')
    expect(screen.getByText('Guide for admins')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'The precedent queue' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Reset a password' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Score weights' })).toBeNull()
  })
})
