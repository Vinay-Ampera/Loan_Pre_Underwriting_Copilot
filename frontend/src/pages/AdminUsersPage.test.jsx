import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
vi.mock('../App', () => ({ useSession: () => ({ session: { user: { id: 'me' } } }) }))

import { api } from '../api/client'
import AdminUsersPage from './AdminUsersPage'

const users = [
  { id: 'me', name: 'Ada Admin', email: 'ada@x.test', role: 'admin', active: true, locked: false },
  {
    id: 'u2',
    name: 'Ben Officer',
    email: 'ben@x.test',
    role: 'officer',
    active: true,
    locked: false,
  },
  {
    id: 'u3',
    name: 'Cy Officer',
    email: 'cy@x.test',
    role: 'officer',
    active: false,
    locked: false,
  },
]

beforeEach(() => {
  api.get.mockReset().mockResolvedValue(users)
  api.post.mockReset()
})

const renderPage = () =>
  render(
    <MemoryRouter>
      <AdminUsersPage />
    </MemoryRouter>,
  )

describe('AdminUsersPage', () => {
  it('lists users, and does not let an admin disable their own account', async () => {
    renderPage()
    expect(await screen.findByText('Ben Officer')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disable Ada Admin' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Disable Ben Officer' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Enable Cy Officer' })).toBeInTheDocument()
  })

  it('shows a new temporary password once, after create', async () => {
    const user = userEvent.setup()
    api.post.mockResolvedValue({
      id: 'u9',
      email: 'new@x.test',
      temporary_password: 'abcd-efgh-ijkl',
    })
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Add user' }))
    await user.type(screen.getByLabelText('Full name'), 'New Person')
    await user.type(screen.getByLabelText('Email'), 'new@x.test')
    await user.click(screen.getByRole('button', { name: 'Create user' }))
    expect(api.post).toHaveBeenCalledWith('/admin/users', {
      name: 'New Person',
      email: 'new@x.test',
      role: 'officer',
    })
    expect(await screen.findByTestId('temp-password')).toHaveTextContent('abcd-efgh-ijkl')
    await user.click(screen.getByRole('button', { name: 'I have copied it' }))
    expect(screen.queryByTestId('temp-password')).not.toBeInTheDocument()
  })

  it('needs a second click to disable', async () => {
    const user = userEvent.setup()
    api.post.mockResolvedValue({})
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Disable Ben Officer' }))
    expect(api.post).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Yes, disable' }))
    expect(api.post).toHaveBeenCalledWith('/admin/users/u2/disable')
  })

  it('shows a plain message when the server refuses', async () => {
    const user = userEvent.setup()
    api.post.mockRejectedValue(new Error('This is the last active admin account.'))
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Disable Ben Officer' }))
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Yes, disable' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('last active admin')
  })
})
