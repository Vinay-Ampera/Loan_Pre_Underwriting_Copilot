import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), del: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import SentItemsPage from './SentItemsPage'

const rows = [
  {
    id: 'a',
    case_id: 'c1',
    case_no: 'CASE-2026-0001',
    template_label: 'Please get in touch',
    recipient: '****@example.test',
    status: 'sent',
    created_at: '2026-11-02T10:00:00Z',
    sent_at: '2026-11-02T10:01:00Z',
  },
  {
    id: 'b',
    case_id: 'c2',
    case_no: 'CASE-2026-0002',
    template_label: 'Please visit the branch',
    recipient: '****@example.test',
    status: 'failed',
    created_at: '2026-11-02T11:00:00Z',
    sent_at: null,
  },
  {
    id: 'd',
    case_id: 'c3',
    case_no: 'CASE-2026-0003',
    template_label: 'Please get in touch',
    recipient: '****@example.test',
    status: 'draft',
    created_at: '2026-11-03T09:00:00Z',
    sent_at: null,
  },
]

beforeEach(() => {
  api.get
    .mockReset()
    .mockImplementation(async (path) =>
      path === '/messages' ? rows : { ...rows[1], text: 'Final text', block_reason: null },
    )
  api.post.mockReset().mockResolvedValue({ status: 'sent' })
  api.del.mockReset().mockResolvedValue(null)
})

const page = () =>
  render(
    <MemoryRouter>
      <SentItemsPage />
    </MemoryRouter>,
  )

describe('SentItemsPage', () => {
  it('lists the officer’s messages with a status each', async () => {
    page()
    expect(await screen.findByText('CASE-2026-0001')).toBeInTheDocument()
    const table = within(screen.getByRole('table'))
    expect(table.getByText('Sent')).toBeInTheDocument()
    expect(table.getByText('Failed')).toBeInTheDocument()
    expect(table.getByText('Draft')).toBeInTheDocument()
  })

  it('retries a failed message only from the dialog button (second click)', async () => {
    page()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /Retry/ }))
    expect(await screen.findByText('Final text')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Yes, send again' }))
    expect(api.post).toHaveBeenCalledWith('/messages/b/send', { second_click: true })
  })

  it('says so when there are no messages', async () => {
    api.get.mockResolvedValue([])
    page()
    expect(await screen.findByText('No messages yet')).toBeInTheDocument()
  })

  it('deletes a draft only after the second click, and never offers it for a sent message', async () => {
    page()
    const user = userEvent.setup()
    await screen.findByText('CASE-2026-0003')
    expect(screen.getAllByRole('button', { name: /^Delete/ })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: /^Delete/ }))
    expect(api.del).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Yes, delete' }))
    expect(api.del).toHaveBeenCalledWith('/messages/d')
  })

  it('cancelling the delete keeps the draft', async () => {
    page()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: /^Delete/ }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(api.del).not.toHaveBeenCalled()
  })

  it('filters by status, case number and date, and clears', async () => {
    page()
    const user = userEvent.setup()
    await screen.findByText('CASE-2026-0001')
    expect(screen.getByRole('status')).toHaveTextContent('Showing 3 of 3')

    await user.click(screen.getByRole('button', { name: 'Draft' }))
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1 of 3')
    expect(screen.queryByText('CASE-2026-0001')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await user.type(screen.getByLabelText('Case number'), '0002')
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1 of 3')

    await user.clear(screen.getByLabelText('Case number'))
    await user.type(screen.getByLabelText('From'), '2999-01-01')
    expect(await screen.findByText('No messages match')).toBeInTheDocument()
  })
})
