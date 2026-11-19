import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import IssuesPage from './IssuesPage'

beforeEach(() => {
  api.get.mockReset().mockResolvedValue([])
  api.post.mockReset()
})

describe('IssuesPage', () => {
  it('warns against personal data and needs at least ten characters', async () => {
    render(<IssuesPage />)
    const user = userEvent.setup()
    expect(screen.getByText('Do not paste personal data')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'Send report' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('What happened?'), 'The page froze.')
    expect(send).toBeEnabled()
  })

  it('shows the refusal when personal data is detected', async () => {
    api.post.mockRejectedValue(new Error('Not sent: contains a pan. Remove personal details.'))
    render(<IssuesPage />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText('What happened?'), 'PAN ABCDE1234F is wrong')
    await user.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Remove personal details')
  })

  it('confirms a sent report and lists the status of your own reports', async () => {
    api.get.mockResolvedValue([
      {
        id: '1',
        category: 'bug',
        case_ref: null,
        body: 'Earlier problem',
        status: 'read',
        created_at: '2026-11-02T10:00:00Z',
      },
    ])
    api.post.mockResolvedValue({ id: '2' })
    render(<IssuesPage />)
    const user = userEvent.setup()
    expect(await screen.findByText('Read by admin')).toBeInTheDocument()
    await user.type(screen.getByLabelText('What happened?'), 'Another problem here')
    await user.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByRole('status')).toHaveTextContent('sent to the admin')
    expect(api.post).toHaveBeenCalledWith('/issues', {
      category: 'bug',
      case_ref: null,
      body: 'Another problem here',
    })
  })

  it('lets the thank-you go: after a few seconds, or when a new report is started', async () => {
    api.post.mockResolvedValue({ id: '2' })
    const user = userEvent.setup()
    const send = async () => {
      await user.type(screen.getByLabelText('What happened?'), 'Another problem here')
      await user.click(screen.getByRole('button', { name: 'Send report' }))
      return screen.findByRole('status')
    }
    render(<IssuesPage />)
    await send()
    await user.type(screen.getByLabelText('What happened?'), 'N') // a new report begins
    expect(screen.queryByRole('status')).toBeNull()

    await user.clear(screen.getByLabelText('What happened?'))
    await user.type(screen.getByLabelText('What happened?'), 'Yet another problem')
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      await user.click(screen.getByRole('button', { name: 'Send report' }))
      expect(await screen.findByRole('status')).toBeInTheDocument()
      await act(async () => {
        vi.advanceTimersByTime(6500)
      })
      expect(screen.queryByRole('status')).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it('explains a badly formed case reference in plain words and sends nothing', async () => {
    const user = userEvent.setup()
    render(<IssuesPage />)
    await user.type(screen.getByLabelText(/Case reference/), 'CASE-2026-000')
    await user.type(screen.getByLabelText('What happened?'), 'The page froze today')
    await user.click(screen.getByRole('button', { name: 'Send report' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A case reference looks like CASE-2026-0001',
    )
    expect(screen.getByRole('alert')).not.toHaveTextContent('pattern')
    expect(api.post).not.toHaveBeenCalled()
  })
})
