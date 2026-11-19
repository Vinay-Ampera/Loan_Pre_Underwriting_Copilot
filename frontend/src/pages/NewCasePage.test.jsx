import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('../api/client', () => ({ api }))

import NewCasePage from './NewCasePage'

const kyc = (type) => ({
  type,
  kyc: true,
  min_count: 1,
  applicant: 'primary',
  when: null,
  any_of: null,
})
const doc = (type, over = {}) => ({
  type,
  kyc: false,
  min_count: 1,
  applicant: 'primary',
  when: null,
  any_of: null,
  ...over,
})
const META = {
  fields: { personal: [], home: [], education: [], business: [], vehicle: [] },
  co_applicant: {
    personal: 'not_allowed',
    home: 'optional',
    education: 'required',
    business: 'not_allowed',
    vehicle: 'not_allowed',
  },
  documents: {
    personal: [
      kyc('pan_card'),
      kyc('aadhaar'),
      kyc('photo'),
      doc('payslip', { min_count: 3, when: { employment_type: 'salaried' } }),
      doc('bank_statement', { min_count: 6 }),
    ],
    home: [kyc('pan_card')],
    education: [
      kyc('pan_card'),
      doc('admission_letter'),
      doc('bank_statement', { applicant: 'co', min_count: 6 }),
    ],
    business: [doc('gst_registration', { any_of: ['gst_registration', 'udyam_certificate'] })],
    vehicle: [kyc('pan_card')],
  },
}

function mount() {
  return render(
    <MemoryRouter initialEntries={['/cases/new']}>
      <Routes>
        <Route path="/cases/new" element={<NewCasePage />} />
        <Route path="/cases/:id" element={<p>the case page</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('NewCasePage', () => {
  beforeEach(() => {
    api.get.mockReset().mockResolvedValue(META)
    api.post.mockReset()
  })

  it('keeps the ways to start off until a loan type is chosen', async () => {
    mount()
    const ways = screen.getByRole('radiogroup', { name: 'How to start' })
    for (const r of within(ways).getAllByRole('radio')) expect(r).toBeDisabled()
    expect(screen.getByText('Choose a loan type first.')).toBeInTheDocument()
    expect(
      screen.getByText('Choose a loan type to see the documents it needs.'),
    ).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /Personal loan/ }))
    expect(screen.getByRole('radio', { name: /Personal loan/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    for (const r of within(ways).getAllByRole('radio')) expect(r).toBeEnabled()
    expect(screen.queryByText('Choose a loan type first.')).not.toBeInTheDocument()
  })

  it('shows the documents the chosen loan needs, from the rules', async () => {
    mount()
    await userEvent.click(screen.getByRole('radio', { name: /Personal loan/ }))
    const panel = await screen.findByRole('complementary', { name: 'Documents needed' })
    expect(within(panel).getByText('Personal loan')).toBeInTheDocument()
    expect(within(panel).getByText('PAN card')).toBeInTheDocument()
    expect(within(panel).getByText('Payslips')).toBeInTheDocument()
    expect(within(panel).getByText('If salaried')).toBeInTheDocument()
    expect(within(panel).getByTitle('At least 6')).toHaveTextContent('6')

    await userEvent.click(screen.getByRole('radio', { name: /Education loan/ }))
    const edu = screen.getByRole('complementary', { name: 'Documents needed' })
    expect(within(edu).getByRole('heading', { name: 'Co-applicant' })).toBeInTheDocument()
    expect(within(edu).getByText(/A co-applicant is required/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: /Business loan/ }))
    expect(screen.getByText('GST registration or Udyam certificate')).toBeInTheDocument()
  })

  it('opens a documents-first case and goes to it', async () => {
    api.post.mockResolvedValue({ id: 'c9' })
    mount()
    await userEvent.click(screen.getByRole('radio', { name: /Vehicle loan/ }))
    await userEvent.click(screen.getByRole('radio', { name: /Start with the documents/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Open the case and add documents' }))
    expect(api.post).toHaveBeenCalledWith('/cases/intake', { loan_type: 'vehicle' })
    expect(await screen.findByText('the case page')).toBeInTheDocument()
  })

  it('shows the form as step 3 when the officer types first', async () => {
    mount()
    await userEvent.click(screen.getByRole('radio', { name: /Home loan/ }))
    await userEvent.click(screen.getByRole('radio', { name: /Fill in the form first/ }))
    expect(
      await screen.findByRole('heading', { name: 'Home loan application' }),
    ).toBeInTheDocument()
  })
})
