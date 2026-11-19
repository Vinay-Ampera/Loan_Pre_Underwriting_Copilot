import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import UserMenu from './UserMenu'

beforeEach(() => {
  api.get.mockReset().mockResolvedValue({ notice_emails: true })
  api.put.mockReset().mockImplementation(async (_path, body) => body)
})

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

describe('UserMenu notice emails', () => {
  const openMenu = async (role) => {
    render(
      <MemoryRouter>
        <UserMenu user={{ name: 'Asha', email: 'a@x.test', role }} onSignOut={() => {}} />
      </MemoryRouter>,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /asha/i }))
    return user
  }

  it('shows the choice as a checkbox and saves a change', async () => {
    const user = await openMenu('officer')
    const box = await screen.findByRole('menuitemcheckbox', { name: 'Email me about new notices' })
    expect(box).toHaveAttribute('aria-checked', 'true')
    await user.click(box)
    expect(api.put).toHaveBeenCalledWith('/me/preferences', { notice_emails: false })
    expect(box).toHaveAttribute('aria-checked', 'false')
  })

  it('says so when saving fails and keeps the old value', async () => {
    api.put.mockRejectedValue(new Error('offline'))
    const user = await openMenu('admin')
    const box = await screen.findByRole('menuitemcheckbox')
    await user.click(box)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save')
    expect(box).toHaveAttribute('aria-checked', 'true')
  })

  it('is not offered to the auditor, who has no inbox', async () => {
    await openMenu('auditor')
    expect(screen.queryByRole('menuitemcheckbox')).toBeNull()
    expect(api.get).not.toHaveBeenCalled()
  })
})
