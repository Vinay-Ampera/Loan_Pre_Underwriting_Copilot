import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import Breadcrumbs from './Breadcrumbs'

const show = (items) =>
  render(
    <MemoryRouter>
      <Breadcrumbs items={items} />
    </MemoryRouter>,
  )

describe('Breadcrumbs', () => {
  it('links the parents, marks the current page and gives a back link for small screens', () => {
    show([{ label: 'Cases', to: '/cases' }, { label: 'CASE-2026-0007' }])
    const nav = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(nav).toBeInTheDocument()
    expect(screen.getByText('CASE-2026-0007')).toHaveAttribute('aria-current', 'page')
    const links = screen.getAllByRole('link', { name: /Cases/ })
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/cases', '/cases'])
    expect(screen.getByRole('link', { name: '← Cases' })).toBeInTheDocument()
  })

  it('walks three levels and goes back to the nearest parent', () => {
    show([
      { label: 'Users', to: '/admin/users' },
      { label: 'Ben Officer', to: '/admin/users/u2' },
      { label: 'CASE-2026-0007' },
    ])
    expect(screen.getByRole('link', { name: 'Ben Officer' })).toHaveAttribute(
      'href',
      '/admin/users/u2',
    )
    expect(screen.getByRole('link', { name: '← Ben Officer' })).toBeInTheDocument()
  })

  it('shows an item with no address as plain text and no back link when nothing links', () => {
    show([{ label: 'Case CASE-1' }, { label: 'Upload links' }])
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('Upload links')).toHaveAttribute('aria-current', 'page')
  })
})
