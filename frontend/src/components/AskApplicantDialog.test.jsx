import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import AskApplicantDialog, { modeOf } from './AskApplicantDialog'

const link = (over = {}) => ({
  id: 'l1',
  state: 'active',
  sent: false,
  case_no: 'CASE-2026-0007',
  expires_at: '2026-11-25T10:00:00Z',
  ...over,
})

function open(found) {
  api.get.mockReset().mockResolvedValue({ link: found })
  api.post.mockReset().mockResolvedValue({
    link_id: 'l1',
    token: 'tok',
    path: '/u#tok',
    new_link: false,
  })
  render(
    <MemoryRouter>
      <AskApplicantDialog caseId="c1" recipient="****@example.test" onClose={vi.fn()} />
    </MemoryRouter>,
  )
  return userEvent.setup()
}
beforeEach(() => vi.clearAllMocks())

describe('modeOf', () => {
  it('names the situation from the case link', () => {
    expect(modeOf(null)).toBe('create')
    expect(modeOf(link())).toBe('share')
    expect(modeOf(link({ sent: true }))).toBe('more')
    expect(modeOf(link({ state: 'expired' }))).toBe('expired')
    expect(modeOf(link({ state: 'disabled' }))).toBe('disabled')
  })
})

describe('AskApplicantDialog wording follows what really happens', () => {
  it('no link yet: it says it creates one, after the second click', async () => {
    const user = open(null)
    expect(await screen.findByText('Ask the applicant for the rest?')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Create the link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
  })

  it('an open link the applicant has not sent from: it only shows the address', async () => {
    const user = open(link())
    expect(await screen.findByText("Share the applicant's link?")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create the link' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show the link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
  })

  it('an applicant who already sent: it asks for more, and nothing says a link is created', async () => {
    const user = open(link({ sent: true }))
    expect(await screen.findByText('Ask the applicant for more documents?')).toBeInTheDocument()
    expect(screen.getByText(/what is still needed/)).toBeInTheDocument()
    expect(screen.queryByText(/makes a secure upload link/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ask for more' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
    expect(await screen.findByLabelText('Upload link address')).toBeInTheDocument()
  })

  it('an expired link: reopen the same link, or make a new one, or manage it', async () => {
    const user = open(link({ state: 'expired', sent: true }))
    expect(await screen.findByText("The applicant's link has expired")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Manage this case/ })).toHaveAttribute(
      'href',
      '/links?case=CASE-2026-0007',
    )
    await user.click(screen.getByRole('button', { name: 'Reopen this link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', {
      second_click: true,
      reopen: true,
    })
  })

  it('an expired link: Make a new link does not ask for a reopen', async () => {
    const user = open(link({ state: 'expired' }))
    await user.click(await screen.findByRole('button', { name: 'Make a new link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
  })

  it('a switched-off link cannot be reopened: only a new link is offered', async () => {
    const user = open(link({ state: 'disabled' }))
    expect(await screen.findByText('This link was switched off')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reopen this link' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Make a new link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', { second_click: true })
  })

  it('Cancel records nothing', async () => {
    const user = open(link({ sent: true }))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(api.post).not.toHaveBeenCalled()
  })
})
