import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import UserMenu from './UserMenu'

const setup = () => {
  const onSignOut = vi.fn()
  render(
    <MemoryRouter>
      <UserMenu user={{ name: 'Asha', email: 'a@x.test', role: 'officer' }} onSignOut={onSignOut} />
    </MemoryRouter>,
  )
  return { onSignOut, user: userEvent.setup() }
}

const openSignOut = async (user) => {
  await user.click(screen.getByRole('button', { name: /asha/i }))
  await user.click(screen.getByRole('menuitem', { name: 'Sign out' }))
}

describe('UserMenu', () => {
  it('shows name, email and role', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: /asha/i }))
    expect(screen.getByText('a@x.test')).toBeInTheDocument()
    expect(screen.getByText('Loan officer')).toBeInTheDocument()
  })
  it('asks first and signs out only on the second click', async () => {
    const { onSignOut, user } = setup()
    await openSignOut(user)
    expect(onSignOut).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(onSignOut).toHaveBeenCalledOnce()
  })
  it('stays signed in when cancelled', async () => {
    const { onSignOut, user } = setup()
    await openSignOut(user)
    await user.click(screen.getByRole('button', { name: 'Stay signed in' }))
    expect(onSignOut).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('UserMenu for the auditor', () => {
  it('shows a Read-only badge', async () => {
    render(
      <MemoryRouter>
        <UserMenu user={{ name: 'Aud', email: 'a@x.test', role: 'auditor' }} onSignOut={() => {}} />
      </MemoryRouter>,
    )
    expect(screen.getAllByText('Read-only').length).toBeGreaterThan(0)
    await userEvent.setup().click(screen.getByRole('button', { name: /aud/i }))
    expect(screen.getByText(/this account changes nothing/i)).toBeInTheDocument()
  })
})
