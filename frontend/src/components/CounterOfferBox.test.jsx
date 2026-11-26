import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CounterOfferBox from './CounterOfferBox'

// the sentences as app/scoring/counter_offer.py writes them for the worked example
const box = {
  rules_version: '2026.11.25-1',
  lines: [
    {
      kind: 'amount',
      loan_type: 'personal',
      band: 'refer',
      scored: true,
      text: 'Pramaan estimates ₹6.3L over 5 years would be recommended for refer (FOIR 40.0%).',
      tags: ['EMI ₹14,014'],
    },
    {
      kind: 'alternate',
      loan_type: 'vehicle',
      band: null,
      scored: false,
      text: 'The stated purpose fits a vehicle loan: ₹10L over 7 years at 9.5%, EMI ₹16,344, FOIR 43.9%. A new application, not scored. It would also need: dealer invoice.',
      tags: ['Not scored'],
    },
  ],
}

describe('CounterOfferBox', () => {
  it('shows each line with its tags, the intro and the footer', () => {
    render(<CounterOfferBox box={box} />)
    const card = screen.getByRole('region', { name: 'Other amounts or tenures (estimate)' })
    const rows = within(card).getAllByRole('listitem')
    expect(rows).toHaveLength(2)
    expect(
      within(rows[0]).getByText(/₹6\.3L over 5 years would be recommended for refer/),
    ).toBeInTheDocument()
    expect(within(rows[0]).getByText('EMI ₹14,014')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Not scored')).toBeInTheDocument()
    expect(
      within(card).getByText(/does not change the score or the recommendation/),
    ).toBeInTheDocument()
    expect(within(card).getByText(/Not for customer messages/)).toBeInTheDocument()
  })

  it('never says approved, eligible or that the applicant qualifies', () => {
    const { container } = render(<CounterOfferBox box={box} />)
    expect(container.textContent).not.toMatch(/\bapproved\b|\beligible\b|you qualify/i)
  })

  it('shows nothing when the report has no box', () => {
    const { container, rerender } = render(<CounterOfferBox box={null} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<CounterOfferBox box={{ lines: [] }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
