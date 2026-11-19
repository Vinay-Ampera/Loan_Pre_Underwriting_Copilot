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
      <AskApplicantDialog
        caseId="c1"
        recipient="****@example.test"
        docTypes={['pan_card', 'payslip', 'bank_statement', 'other']}
        onClose={vi.fn()}
      />
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

  it('an applicant who already sent: it asks what is needed first, and nothing says a link is created', async () => {
    const user = open(link({ sent: true }))
    expect(await screen.findByText('Ask the applicant for more documents?')).toBeInTheDocument()
    expect(screen.getByText(/what is still needed/)).toBeInTheDocument()
    expect(screen.queryByText(/makes a secure upload link/)).not.toBeInTheDocument()
    // nothing can be sent until something is ticked or a note is written
    expect(screen.getByRole('button', { name: 'Ask for more' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Payslips' }))
    await user.clear(screen.getByLabelText('How many Payslips'))
    await user.type(screen.getByLabelText('How many Payslips'), '2')
    await user.type(screen.getByLabelText(/Note for the applicant/), 'Last two months.')
    await user.click(screen.getByRole('button', { name: 'Ask for more' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', {
      second_click: true,
      items: [{ type: 'payslip', count: 2 }],
      note: 'Last two months.',
    })
    // the applicant already has this address: say the page shows the request, not "copy this"
    expect(await screen.findByText('Your request is saved')).toBeInTheDocument()
    expect(screen.getByText(/open the link they already have/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Upload link address')).not.toBeInTheDocument()
  })

  it('a note alone is enough to ask for more', async () => {
    const user = open(link({ sent: true }))
    await user.type(await screen.findByLabelText(/Note for the applicant/), 'Three months please.')
    await user.click(screen.getByRole('button', { name: 'Ask for more' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', {
      second_click: true,
      items: [],
      note: 'Three months please.',
    })
  })

  it('a server refusal of the note is shown in the dialog', async () => {
    const user = open(link({ sent: true }))
    api.post.mockRejectedValue(
      new Error('The note cannot be shown to the applicant: contains a pan.'),
    )
    await user.type(await screen.findByLabelText(/Note for the applicant/), 'ABCDE1234F')
    await user.click(screen.getByRole('button', { name: 'Ask for more' }))
    expect(await screen.findByText(/cannot be shown to the applicant/)).toBeInTheDocument()
  })

  it('an open link before the applicant has sent asks for nothing', async () => {
    open(link())
    await screen.findByText("Share the applicant's link?")
    expect(screen.queryByText('What do you need?')).not.toBeInTheDocument()
  })

  it('an expired link: reopen the same link, or make a new one, or manage it', async () => {
    const user = open(link({ state: 'expired', sent: true }))
    expect(await screen.findByText("The applicant's link has expired")).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Manage this case/ })).toHaveAttribute(
      'href',
      '/links?case=CASE-2026-0007',
    )
    expect(screen.getByRole('button', { name: 'Reopen this link' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Bank statement' }))
    await user.click(screen.getByRole('button', { name: 'Reopen this link' }))
    expect(api.post).toHaveBeenCalledWith('/cases/c1/ask-applicant', {
      second_click: true,
      reopen: true,
      items: [{ type: 'bank_statement', count: 1 }],
      note: '',
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
