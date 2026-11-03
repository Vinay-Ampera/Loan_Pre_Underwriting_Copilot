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

  it('shows the auditor but does not let an admin manage it', async () => {
    api.get.mockResolvedValue([
      ...users,
      { id: 'a1', name: 'Aud Auditor', email: 'aud@x.test', role: 'auditor', active: true },
    ])
    renderPage()
    expect(await screen.findByText('Aud Auditor')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disable Aud Auditor' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reset password for Aud Auditor' })).toBeDisabled()
    expect(screen.getByText('Auditor')).toBeInTheDocument()
    // greyed out and silent: no tooltip explaining why
    expect(screen.getByRole('button', { name: 'Disable Aud Auditor' })).not.toHaveAttribute('title')
    expect(
      screen.getByRole('button', { name: 'Reset password for Aud Auditor' }),
    ).not.toHaveAttribute('title')
  })

  it('warns when disabling an officer who still has undecided cases', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(users.map((u) => (u.id === 'u2' ? { ...u, open_cases: 2 } : u)))
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Disable Ben Officer' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('alert')).toHaveTextContent('2 cases')
    expect(within(dialog).getByRole('link', { name: /reassign them/ })).toHaveAttribute(
      'href',
      '/admin/users/u2?status=open',
    )
  })

  it('shows no warning for an officer with nothing waiting', async () => {
    const user = userEvent.setup()
    api.get.mockResolvedValue(users.map((u) => (u.id === 'u2' ? { ...u, open_cases: 0 } : u)))
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Disable Ben Officer' }))
    expect(within(screen.getByRole('dialog')).queryByRole('alert')).toBeNull()
  })

  it('warns in red and asks again before creating an admin', async () => {
    const user = userEvent.setup()
    api.post.mockResolvedValue({
      id: 'u9',
      email: 'n@x.test',
      temporary_password: 'abcd-efgh-ijkl',
    })
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Add user' }))
    const dialog = screen.getByRole('dialog')
    await user.type(within(dialog).getByLabelText('Full name'), 'New Admin')
    await user.type(within(dialog).getByLabelText('Email'), 'n@x.test')
    expect(within(dialog).queryByText(/You are creating an admin/)).toBeNull()
    await user.selectOptions(within(dialog).getByLabelText('Role'), 'admin')
    expect(within(dialog).getByText(/You are creating an admin/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Create user' }))
    expect(api.post).not.toHaveBeenCalled() // the first click only asks
    await user.click(within(dialog).getByRole('button', { name: 'Yes, create an admin' }))
    expect(api.post).toHaveBeenCalledWith(
      '/admin/users',
      expect.objectContaining({ role: 'admin' }),
    )
  })

  it('has no auditor option in the role list', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Ben Officer')
    await user.click(screen.getByRole('button', { name: 'Add user' }))
    const options = within(screen.getByLabelText('Role')).getAllByRole('option')
    expect(options.map((o) => o.value)).toEqual(['officer', 'admin'])
  })
})
