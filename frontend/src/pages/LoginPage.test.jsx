import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({ login: vi.fn() }))
vi.mock('../App', () => ({ useSession: () => ({ signIn: vi.fn() }) }))

import LoginPage from './LoginPage'

describe('LoginPage', () => {
  it('keeps the five stages and the human-confirms line, but no score weights or bands', () => {
    render(<LoginPage />)
    expect(screen.getByRole('list', { name: 'The five underwriting stages' })).toBeInTheDocument()
    expect(screen.getByText('A human confirms every case.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Score weights')).toBeNull()
    expect(screen.queryByText(/recommend approve|recommend reject|refer/i)).toBeNull()
    expect(screen.queryByText(/100 points/)).toBeNull()
  })

  it('shows only the plain contact sentence, with no email, phone or link, and no footer', () => {
    const { container } = render(<LoginPage />)
    expect(screen.getByText("Can't sign in? Contact your admin.")).toBeInTheDocument()
    expect(container.querySelector('a[href^="mailto:"], a[href^="tel:"]')).toBeNull()
    expect(screen.queryByRole('contentinfo')).toBeNull()
  })
})
