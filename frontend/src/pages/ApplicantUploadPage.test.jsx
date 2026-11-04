import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const pub = vi.hoisted(() => ({
  link: vi.fn(),
  request: vi.fn(),
  files: vi.fn(),
  send: vi.fn(),
}))
vi.mock('../api/public', async (orig) => ({ ...(await orig()), publicApi: pub }))

import ApplicantUploadPage from './ApplicantUploadPage'

const view = (over = {}) => ({
  active: true,
  loan_type: 'personal',
  expires_on: '2026-11-10',
  request_open: true,
  request_received: true,
  accepting_files: true,
  sent: false,
  checklist: {
    people: [
      {
        who: 'Applicant',
        items: [
          { type: 'pan_card', needed: 1, have: 1 },
          { type: 'payslip', needed: 3, have: 1 },
        ],
      },
    ],
    after_employment: [],
    complete: false,
  },
  ...over,
})

beforeEach(() => {
  Object.values(pub).forEach((f) => f.mockReset())
  window.location.hash = '#a-long-enough-token-0123456789'
})

describe('ApplicantUploadPage', () => {
  it('reads the token from the address fragment and sends it with every call', async () => {
    pub.link.mockResolvedValue(view())
    render(<ApplicantUploadPage />)
    await screen.findByText('What to send')
    expect(pub.link).toHaveBeenCalledWith('a-long-enough-token-0123456789')
  })

  it('shows one neutral page for a link that is not active', async () => {
    pub.link.mockRejectedValue(
      Object.assign(new Error('This link is not active.'), { status: 404 }),
    )
    render(<ApplicantUploadPage />)
    expect(await screen.findByText('This link is not active')).toBeInTheDocument()
    expect(screen.queryByText('What to send')).not.toBeInTheDocument()
  })

  it('shows counts only: never a score, a status, an outcome or a file name', async () => {
    pub.link.mockResolvedValue(view())
    render(<ApplicantUploadPage />)
    await screen.findByText('What to send')
    expect(screen.getByText('(1 of 3)')).toBeInTheDocument()
    const text = document.body.textContent.toLowerCase()
    for (const word of ['score', 'recommend', 'approved', 'rejected', 'status', 'outcome']) {
      expect(text).not.toContain(word)
    }
  })

  it('Send to the bank needs the second click, warns when incomplete, and shows the reference', async () => {
    const user = userEvent.setup()
    pub.link.mockResolvedValue(view())
    pub.send.mockResolvedValue({ reference: 'PRM-0A1B2C3D', incomplete: true })
    render(<ApplicantUploadPage />)
    expect(await screen.findByText(/not in yet/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Send to the bank' }))
    expect(pub.send).not.toHaveBeenCalled() // the first click only opens the dialog
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(pub.send).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Send to the bank' }))
    await user.click(screen.getByRole('button', { name: 'Yes, send' }))
    expect(pub.send).toHaveBeenCalledTimes(1)
    expect(await screen.findByText('PRM-0A1B2C3D')).toBeInTheDocument()
    expect(screen.getByText(/open this same link again/)).toBeInTheDocument()
  })

  it("asks for the request first on a new link and sends it as the applicant's own statement", async () => {
    const user = userEvent.setup()
    pub.link
      .mockResolvedValueOnce(
        view({ loan_type: null, request_received: false, accepting_files: false, checklist: null }),
      )
      .mockResolvedValue(view())
    pub.request.mockResolvedValue({ received: true })
    render(<ApplicantUploadPage />)
    expect(await screen.findByText(/This is your own statement/)).toBeInTheDocument()
    expect(screen.queryByText('What to send')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Kind of loan'), 'personal')
    await user.type(screen.getByLabelText(/Amount you would like/), '250000')
    await user.type(screen.getByLabelText(/For how many months/), '24')
    await user.click(screen.getByRole('button', { name: 'Save my request' }))
    expect(pub.request).toHaveBeenCalledWith(
      'a-long-enough-token-0123456789',
      expect.objectContaining({ loan_type: 'personal', loan_amount: 250000, tenure_months: 24 }),
    )
    expect(await screen.findByText('What to send')).toBeInTheDocument()
  })

  it('says so plainly when the link is not taking files', async () => {
    pub.link.mockResolvedValue(view({ accepting_files: false }))
    render(<ApplicantUploadPage />)
    expect(
      await screen.findByText('This link is not accepting files right now.'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send to the bank' })).not.toBeInTheDocument()
  })

  it('a locked request is not offered again', async () => {
    pub.link.mockResolvedValue(view({ request_open: false }))
    render(<ApplicantUploadPage />)
    await screen.findByText('What to send')
    expect(screen.queryByText('Change my request')).not.toBeInTheDocument()
  })
})
