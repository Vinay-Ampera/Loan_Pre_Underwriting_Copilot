import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import NotificationBell from './NotificationBell'
import Sidebar from './Sidebar'
import { UnreadProvider } from './UnreadProvider'

const officer = { id: 'u1', role: 'officer', name: 'Asha' }
const mount = (user = officer, ui = <NotificationBell user={user} />) =>
  render(
    <MemoryRouter>
      <UnreadProvider user={user}>
        <Routes>
          <Route path="/" element={ui} />
          <Route path="/inbox" element={<p>officer inbox</p>} />
          <Route path="/admin/inbox" element={<p>admin inbox</p>} />
        </Routes>
      </UnreadProvider>
    </MemoryRouter>,
  )

const NOTICES = [
  {
    id: 'n1',
    title: 'A new problem report',
    body: 'Open the Issues page to read it.',
    case_ref: null,
    path: '/inbox',
    created_at: '2026-11-24T10:00:00Z',
    read_at: null,
  },
  {
    id: 'n2',
    title: 'Assessment finished',
    body: null,
    case_ref: 'CASE-2026-0007',
    path: '/admin/inbox',
    created_at: '2026-11-24T09:00:00Z',
    read_at: '2026-11-24T09:05:00Z',
  },
]

beforeEach(() => {
  api.get
    .mockReset()
    .mockImplementation((path) =>
      Promise.resolve(path.startsWith('/notifications?') ? { items: NOTICES } : { unread: 3 }),
    )
  api.post.mockReset().mockResolvedValue({ unread: 0 })
})
afterEach(() => vi.useRealTimers())

describe('NotificationBell', () => {
  it('is a button whose name carries the unread count', async () => {
    mount()
    const bell = await screen.findByRole('button', { name: 'Notifications, 3 unread' })
    expect(bell).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/notifications/unread-count')
  })

  it('says none unread, and shows no badge, at zero', async () => {
    api.get.mockImplementation(() => Promise.resolve({ unread: 0, items: [] }))
    mount()
    const bell = await screen.findByRole('button', { name: 'Notifications, none unread' })
    expect(bell.querySelector('.bell-count')).toBeNull()
  })

  it('caps the badge but not the accessible count', async () => {
    api.get.mockImplementation(() => Promise.resolve({ unread: 140 }))
    mount()
    const bell = await screen.findByRole('button', { name: 'Notifications, 140 unread' })
    expect(bell).toHaveTextContent('99+')
  })

  it('opens a dropdown with the latest notices instead of leaving the page', async () => {
    const user = userEvent.setup()
    mount()
    const bell = await screen.findByRole('button', { name: /Notifications/ })
    expect(bell).toHaveAttribute('aria-expanded', 'false')
    await user.click(bell)
    expect(bell).toHaveAttribute('aria-expanded', 'true')
    const panel = screen.getByRole('dialog', { name: 'Latest notifications' })
    expect(await within(panel).findByText('A new problem report')).toBeInTheDocument()
    expect(within(panel).getByText(/CASE-2026-0007/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/notifications?limit=8&offset=0&unread=false')
    expect(screen.queryByText('officer inbox')).toBeNull() // still on the same page
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('marks a notice read and goes where it points', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(await screen.findByRole('button', { name: /A new problem report/ }))
    expect(api.post).toHaveBeenCalledWith('/notifications/n1/read')
    expect(screen.getByText('officer inbox')).toBeInTheDocument() // the test route for /inbox
  })

  it('marks all read from the dropdown', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await screen.findByText('A new problem report')
    await user.click(screen.getByRole('button', { name: 'Mark all read' }))
    expect(api.post).toHaveBeenCalledWith('/notifications/read-all')
    expect(screen.getByRole('button', { name: 'Notifications, none unread' })).toBeInTheDocument()
  })

  it('links to the officer inbox for an officer and the admin inbox for an admin', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(screen.getByRole('button', { name: 'Open the inbox' }))
    expect(screen.getByText('officer inbox')).toBeInTheDocument()
  })

  it('opens the admin inbox for an admin', async () => {
    const admin = { id: 'a1', role: 'admin', name: 'Ada' }
    const user = userEvent.setup()
    mount(admin)
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await user.click(screen.getByRole('button', { name: 'Open the inbox' }))
    expect(screen.getByText('admin inbox')).toBeInTheDocument()
  })

  it('shows the same count as a badge on the Inbox link in the sidebar', async () => {
    mount(officer, <Sidebar user={officer} />)
    const link = await screen.findByRole('link', { name: /Inbox.*3 unread/ })
    expect(link).toHaveAttribute('href', '/inbox')
  })
})

describe('UnreadProvider', () => {
  it('asks again every minute and when the window gets focus', async () => {
    vi.useFakeTimers()
    mount()
    await act(async () => {})
    expect(api.get).toHaveBeenCalledTimes(1)
    api.get.mockResolvedValue({ unread: 5 })
    await act(async () => {
      vi.advanceTimersByTime(60_000)
    })
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('button', { name: 'Notifications, 5 unread' })).toBeInTheDocument()
    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })
    expect(api.get).toHaveBeenCalledTimes(3)
  })

  it('keeps the last count when a read fails, and never asks for the auditor', async () => {
    vi.useFakeTimers()
    mount()
    await act(async () => {})
    api.get.mockRejectedValue(new Error('offline'))
    await act(async () => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByRole('button', { name: 'Notifications, 3 unread' })).toBeInTheDocument()
  })

  it('does not ask at all for an auditor or when nobody is signed in', async () => {
    vi.useFakeTimers()
    api.get.mockClear()
    render(
      <UnreadProvider user={{ id: 'x', role: 'auditor' }}>
        <p>child</p>
      </UnreadProvider>,
    )
    render(
      <UnreadProvider user={null}>
        <p>child</p>
      </UnreadProvider>,
    )
    await act(async () => {
      vi.advanceTimersByTime(180_000)
      window.dispatchEvent(new Event('focus'))
    })
    expect(api.get).not.toHaveBeenCalled()
  })

  it('stops asking once the person is gone (a ended session cannot loop)', async () => {
    vi.useFakeTimers()
    const { rerender } = render(
      <UnreadProvider user={officer}>
        <p>child</p>
      </UnreadProvider>,
    )
    await act(async () => {})
    expect(api.get).toHaveBeenCalledTimes(1)
    rerender(
      <UnreadProvider user={null}>
        <p>child</p>
      </UnreadProvider>,
    )
    await act(async () => {
      vi.advanceTimersByTime(300_000)
    })
    expect(api.get).toHaveBeenCalledTimes(1)
  })
})
