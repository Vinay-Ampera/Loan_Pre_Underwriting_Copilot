import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const who = vi.hoisted(() => ({ role: 'officer' }))
vi.mock('../api/client', () => ({ api }))
vi.mock('../App', () => ({
  useSession: () => ({ session: { user: { id: 'u1', name: 'A', role: who.role } } }),
}))

import UploadLinksPage from './UploadLinksPage'

const link = (over = {}) => ({
  id: 'l1',
  state: 'active',
  loan_type: 'personal',
  officer: 'Asha Officer',
  created_at: '2026-11-03T10:00:00Z',
  expires_at: '2026-11-10T10:00:00Z',
  files_count: 2,
  case_id: null,
  case_no: null,
  sent: false,
  ...over,
})

function setup(role = 'officer', list = [link()]) {
  who.role = role
  api.get.mockReset().mockImplementation(async (path) => {
    if (path === '/links') return list
    if (path.endsWith('/address')) return { path: '/u#abc' }
    if (path === '/admin/users')
      return [{ id: 'o1', name: 'Ben Officer', role: 'officer', active: true }]
    return null
  })
  api.post.mockReset().mockResolvedValue({})
  render(
    <MemoryRouter>
      <UploadLinksPage />
    </MemoryRouter>,
  )
  return userEvent.setup()
}
beforeEach(() => vi.clearAllMocks())

describe('UploadLinksPage', () => {
  it('creating a link needs the second click and shows the address once', async () => {
    const user = setup()
    await screen.findByText('Open')
    await user.click(screen.getByRole('button', { name: 'Create a link' }))
    expect(api.post).not.toHaveBeenCalled() // the first click only opens the dialog
    api.post.mockResolvedValue({
      id: 'l2',
      token: 'secret-token-0123456789abcdef',
      path: '/u#secret-token-0123456789abcdef',
      expires_at: new Date(Date.now() + 7 * 86400000).toISOString(),
    })
    await user.click(screen.getByRole('button', { name: 'Create the link' }))
    expect(api.post).toHaveBeenCalledWith('/links', { second_click: true })
    const box = await screen.findByLabelText('Upload link address')
    expect(box.value).toMatch(/\/u#secret-token/)
    // the listing never carries the token
    expect(document.body.textContent).not.toContain('secret-token')
  })

  it('an admin must name the officer before the link can be created', async () => {
    const user = setup('admin')
    await user.click(await screen.findByRole('button', { name: 'Create a link' }))
    expect(screen.getByRole('button', { name: 'Create the link' })).toBeDisabled()
    await user.selectOptions(await screen.findByLabelText('Officer this link is for'), 'o1')
    await user.click(screen.getByRole('button', { name: 'Create the link' }))
    expect(api.post).toHaveBeenCalledWith('/links', { second_click: true, officer_id: 'o1' })
  })

  it('disabling needs the second click', async () => {
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Disable' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Disable' }))
    await user.click(screen.getByRole('button', { name: 'Yes, disable it' }))
    expect(api.post).toHaveBeenCalledWith('/links/l1/disable', { second_click: true })
  })

  it('copy link fetches the address again', async () => {
    const user = setup()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue() },
      configurable: true,
    })
    await user.click(await screen.findByRole('button', { name: 'Copy link' }))
    expect(api.get).toHaveBeenCalledWith('/links/l1/address')
  })

  it('a disabled link has no actions and an expired one cannot be disabled twice', async () => {
    setup('officer', [link({ state: 'disabled' })])
    await screen.findByText('Disabled')
    expect(screen.queryByRole('button', { name: 'Set days' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Disable' })).not.toBeInTheDocument()
  })
})
