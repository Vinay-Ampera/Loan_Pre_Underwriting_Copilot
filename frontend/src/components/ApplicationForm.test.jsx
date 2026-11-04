import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ApplicationForm from './ApplicationForm'

const meta = {
  co_applicant: { home: 'optional' },
  fields: {
    home: [
      { name: 'property_value', label: 'Property value (INR)', kind: 'number' },
      { name: 'owner_name', label: 'Property owner name', kind: 'text', required: false },
    ],
  },
}

const setup = () => {
  const onSubmit = vi.fn().mockResolvedValue()
  render(<ApplicationForm loanType="home" meta={meta} submitLabel="Save" onSubmit={onSubmit} />)
  return { onSubmit, user: userEvent.setup() }
}

describe('ApplicationForm required and optional fields', () => {
  it('marks required fields with * and optional ones with (optional)', () => {
    setup()
    expect(screen.getByText('Loan amount (INR)').textContent).toContain('*')
    expect(screen.getByText('Property value (INR)').textContent).toContain('*')
    expect(screen.getByText('Property owner name').textContent).toContain('(optional)')
    expect(screen.getByText('Mobile number').textContent).toContain('(optional)')
    expect(screen.getByLabelText('How to fill this form')).toBeInTheDocument()
  })

  it('shows messages for empty required fields and none for optional ones', async () => {
    const { onSubmit, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('Enter the loan amount.')).toBeInTheDocument()
    expect(screen.getByText('Enter property value (inr).')).toBeInTheDocument()
    expect(screen.queryByText(/mobile number\./i)).not.toBeInTheDocument()
    expect(screen.queryByText(/property owner name\./i)).not.toBeInTheDocument()
  })

  it('has an optional customer email on the primary applicant that must look like an email', async () => {
    const { onSubmit, user } = setup()
    expect(screen.getByText('Customer email').textContent).toContain('(optional)')
    await user.type(screen.getByLabelText(/Customer email/), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/Enter a valid email address/)).toBeInTheDocument()
  })
})

describe('ApplicationForm with identity read from the cards', () => {
  const offer = {
    primary: {
      values: {
        full_name: 'Rahul Rao',
        dob: '1990-01-01',
        pan: 'HOBPR1259X',
        aadhaar_last4: '1234',
        address: '1 Park Rd, Pune',
      },
      notes: {},
    },
  }
  const base = {
    loan_amount: '',
    tenure_months: '',
    purpose: '',
    application_date: '',
    details: { property_value: 5000000 },
    people: {
      primary: {
        role: 'primary',
        ...offer.primary.values,
        phone: '',
        email: '',
        employment_type: 'salaried',
        employer_or_business: '',
        declared_monthly_income: '50000',
        relationship_to_primary: '',
        residential_status: 'resident',
        months_in_current_employment: '',
        total_experience_months: '',
      },
    },
  }
  const setup2 = (o = offer, typed = {}) => {
    const onSubmit = vi.fn().mockResolvedValue()
    render(
      <ApplicationForm
        loanType="home"
        meta={meta}
        initial={{
          ...base,
          loan_amount: 100000,
          tenure_months: 24,
          people: { primary: { ...base.people.primary, ...typed } },
        }}
        offer={o}
        submitLabel="Save"
        onSubmit={onSubmit}
      />,
    )
    return { onSubmit, user: userEvent.setup() }
  }

  it('marks the five identity values "from documents" and never the claims', () => {
    setup2()
    expect(screen.getAllByText('from documents', { selector: '.from-doc' })).toHaveLength(5 + 1) // five tags and the note
    for (const claim of [
      'Loan amount (INR)',
      'Tenure (months)',
      'Declared monthly income (INR)',
      'Mobile number',
    ]) {
      expect(screen.getByText(claim).parentElement.querySelector('.from-doc')).toBeNull()
    }
  })

  it('will not save until the confirmation box is ticked', async () => {
    const { onSubmit, user } = setup2()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/Tick the box to confirm/)).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /I confirmed the details/ }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ identity_confirmed: true }))
  })

  it('a value typed over loses its tag, and with no tag left the box goes away', async () => {
    const { user } = setup2(
      {
        primary: {
          values: { full_name: 'Rahul Rao' },
          notes: { pan: 'The PAN could not be read.' },
        },
      },
      { pan: '', dob: '', aadhaar_last4: '', address: '' },
    )
    expect(screen.getByRole('checkbox', { name: /I confirmed/ })).toBeInTheDocument()
    const name = screen.getByLabelText(/Full name/)
    await user.clear(name)
    await user.type(name, 'Rahul K Rao')
    expect(screen.queryByRole('checkbox', { name: /I confirmed/ })).not.toBeInTheDocument()
    expect(screen.getByText('The PAN could not be read.')).toBeInTheDocument()
  })
})
