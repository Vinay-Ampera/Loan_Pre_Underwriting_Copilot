import { render, screen } from '@testing-library/react'
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
})
