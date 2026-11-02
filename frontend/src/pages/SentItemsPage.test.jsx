import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
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
]

beforeEach(() => {
  api.get
    .mockReset()
    .mockImplementation(async (path) =>
      path === '/messages' ? rows : { ...rows[1], text: 'Final text', block_reason: null },
    )
  api.post.mockReset().mockResolvedValue({ status: 'sent' })
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
    expect(screen.getByText('Sent')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
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
})
