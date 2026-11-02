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
