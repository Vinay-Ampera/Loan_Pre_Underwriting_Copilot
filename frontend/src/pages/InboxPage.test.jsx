import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import { UnreadProvider } from '../components/UnreadProvider'
import InboxPage from './InboxPage'

const item = (n, over = {}) => ({
  id: `n${n}`,
  kind: 'run_ready',
  title: `Notice ${n}`,
  body: '',
  case_id: `c${n}`,
  case_ref: `CASE-2026-000${n}`,
  created_at: '2026-11-19T10:00:00Z',
  read_at: null,
  path: `/cases/c${n}`,
  ...over,
})

function mount() {
  return render(
    <MemoryRouter initialEntries={['/inbox']}>
      <UnreadProvider user={{ id: 'u1', role: 'officer' }}>
        <Routes>
          <Route path="/inbox" element={<InboxPage />} />
          <Route path="/cases/:id" element={<p>the case page</p>} />
        </Routes>
      </UnreadProvider>
    </MemoryRouter>,
  )
}

const GROUPS = [
  { key: 'applicant', label: 'Applicant and links' },
  { key: 'runs', label: 'Checks' },
]
let all
beforeEach(() => {
  all = [item(1), item(2, { read_at: '2026-11-19T11:00:00Z' }), item(3)]
  api.post.mockReset().mockResolvedValue({})
  api.get.mockReset().mockImplementation(async (path) => {
    if (path.startsWith('/notifications/unread-count')) return { unread: 2 }
    const unread = path.includes('unread=true')
    const items = unread ? all.filter((n) => !n.read_at) : all
    return { items, total: items.length, unread: 2, limit: 30, offset: 0, groups: GROUPS }
  })
})

describe('InboxPage', () => {
  it('lists unread notices first, with the case reference and no applicant detail', async () => {
    mount()
    const list = await screen.findByRole('list', { name: 'Notifications' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Unread: Notice 1')
    expect(rows[0]).toHaveTextContent('CASE-2026-0001')
    expect(screen.getByText('2 unread')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/notifications?limit=30&offset=0&unread=true')
  })

  it('shows read notices too under All', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    await user.click(screen.getByRole('tab', { name: 'All' }))
    expect(await screen.findByText('Notice 2')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/notifications?limit=30&offset=0&unread=false')
    expect(screen.getAllByRole('button', { name: /^Mark read/ })).toHaveLength(2) // not for the read one
  })

  it('marks one read without leaving the page', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    await user.click(screen.getByRole('button', { name: 'Mark read: Notice 1' }))
    expect(api.post).toHaveBeenCalledWith('/notifications/n1/read')
    expect(screen.getByText('Notice 1')).toBeInTheDocument() // stays, now read
    expect(screen.queryByRole('button', { name: 'Mark read: Notice 1' })).toBeNull()
    expect(screen.getByText('Notice 1').closest('li')).toHaveClass('read')
    expect(await screen.findByText('1 unread')).toBeInTheDocument() // the count follows
  })

  it('opens the case on a click, marking the notice read first', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /^(Unread: )?Notice 3/ }))
    expect(api.post).toHaveBeenCalledWith('/notifications/n3/read')
    expect(await screen.findByText('the case page')).toBeInTheDocument()
  })

  it('marks everything read and then disables the button', async () => {
    api.post.mockResolvedValue({ marked: 2, unread: 0 })
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    await user.click(screen.getByRole('button', { name: 'Mark all read' }))
    expect(api.post).toHaveBeenCalledWith('/notifications/read-all')
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeDisabled()
    expect(screen.queryAllByRole('button', { name: /^Mark read/ })).toHaveLength(0)
  })

  it('has a friendly empty state', async () => {
    all = []
    api.get.mockImplementation(async () => ({
      items: [],
      total: 0,
      unread: 0,
      limit: 30,
      offset: 0,
    }))
    mount()
    expect(await screen.findByText('You are all caught up')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeDisabled()
  })

  it('shows an error with a retry', async () => {
    api.get.mockRejectedValue(new Error('The server is down'))
    const user = userEvent.setup()
    mount()
    expect(await screen.findByRole('alert')).toHaveTextContent('The server is down')
    api.get.mockImplementation(async () => ({
      items: [],
      total: 0,
      unread: 0,
      limit: 30,
      offset: 0,
    }))
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('You are all caught up')).toBeInTheDocument()
  })

  it('says what went wrong when marking fails, and keeps the notice unread', async () => {
    api.post.mockRejectedValue(new Error('Notification not found.'))
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    await user.click(screen.getByRole('button', { name: 'Mark read: Notice 1' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Notification not found.')
    expect(screen.getByRole('button', { name: 'Mark read: Notice 1' })).toBeInTheDocument()
  })

  it('pages: Show more appends the next page', async () => {
    const page1 = Array.from({ length: 30 }, (_, i) =>
      item(i + 1, { id: `a${i}`, title: `A ${i}` }),
    )
    api.get.mockImplementation(async (path) =>
      path.includes('offset=30')
        ? {
            items: [item(99, { id: 'z', title: 'Last one' })],
            total: 31,
            unread: 31,
            limit: 30,
            offset: 30,
          }
        : { items: page1, total: 31, unread: 31, limit: 30, offset: 0 },
    )
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Show more' }))
    expect(await screen.findByText('Last one')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Show more' })).toBeNull()
  })

  it('offers the types the server sends, and asks for the chosen one', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    const type = await screen.findByLabelText('Type')
    expect([...type.options].map((o) => o.text)).toEqual([
      'All types',
      'Applicant and links',
      'Checks',
    ])
    await user.selectOptions(type, 'runs')
    expect(api.get).toHaveBeenCalledWith('/notifications?limit=30&offset=0&unread=true&group=runs')
  })

  it('searches by case number after a pause, sending only what a number holds', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    await user.type(screen.getByLabelText('Case number'), 'case-2026 0001!')
    expect(await screen.findByRole('list', { name: 'Notifications' })).toBeInTheDocument()
    await vi.waitFor(() =>
      expect(api.get).toHaveBeenCalledWith(
        '/notifications?limit=30&offset=0&unread=true&case=CASE-20260001',
      ),
    )
    expect(api.get).not.toHaveBeenCalledWith(expect.stringContaining('case=C&'))
  })

  it('says nothing matches, and Clear filters brings everything back', async () => {
    const user = userEvent.setup()
    mount()
    await screen.findByRole('list', { name: 'Notifications' })
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull()
    api.get.mockImplementation(async (path) =>
      path.includes('group=runs')
        ? { items: [], total: 0, unread: 2, limit: 30, offset: 0, groups: GROUPS }
        : {
            items: all.filter((n) => !n.read_at),
            total: 2,
            unread: 2,
            limit: 30,
            offset: 0,
            groups: GROUPS,
          },
    )
    await user.selectOptions(await screen.findByLabelText('Type'), 'runs')
    expect(await screen.findByText('Nothing matches these filters')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByRole('list', { name: 'Notifications' })).toBeInTheDocument()
    expect(screen.getByLabelText('Type')).toHaveValue('')
    expect(screen.queryByRole('button', { name: 'Clear filters' })).toBeNull()
  })
})
