import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CaseStepper from './CaseStepper'

const steps = () =>
  within(screen.getByRole('list', { name: 'Underwriting stages' })).getAllByRole('listitem')

describe('CaseStepper', () => {
  it('shows the five stages and marks the current one', () => {
    render(<CaseStepper caseData={{ status: 'draft' }} />)
    expect(steps()).toHaveLength(5)
    expect(steps()[0]).toHaveAttribute('aria-current', 'step')
    expect(steps()[0]).toHaveTextContent('in progress')
    expect(steps()[1]).toHaveTextContent('not started')
  })

  it('stops at the failing stage with the plain-language reason', () => {
    render(
      <CaseStepper
        caseData={{ status: 'stopped', report: { stopped_stage: 'kyc' } }}
        stopText="The PAN does not match."
      />,
    )
    expect(steps()[0]).toHaveTextContent('done')
    expect(steps()[1]).toHaveTextContent('stopped here')
    expect(steps()[2]).toHaveTextContent('not started')
    expect(screen.getByRole('note')).toHaveTextContent(
      'Stopped at “Verification and documents”: The PAN does not match.',
    )
  })

  it('never shows officer sign-off as done by the system', () => {
    render(<CaseStepper caseData={{ status: 'awaiting_confirmation' }} />)
    expect(steps()[3]).toHaveTextContent('done')
    expect(steps()[4]).toHaveTextContent('in progress')
    expect(steps()[4]).not.toHaveTextContent(/done/)
  })
})
