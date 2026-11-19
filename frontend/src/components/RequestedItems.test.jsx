import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import RequestedItems, { isComplete, toBody } from './RequestedItems'

function Harness({ onValue }) {
  const [value, setValue] = useState({ items: [], note: '' })
  onValue(value)
  return (
    <RequestedItems
      docTypes={['payslip', 'bank_statement', 'unknown', 'other']}
      value={value}
      onChange={setValue}
    />
  )
}

describe('RequestedItems', () => {
  it('ticks kinds with a count and keeps a note, never offering "not recognised"', async () => {
    const seen = vi.fn()
    const user = userEvent.setup()
    render(<Harness onValue={seen} />)
    expect(screen.queryByText('Not recognised')).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: 'Payslips' }))
    const count = screen.getByLabelText('How many Payslips')
    expect(count).toHaveValue(1)
    await user.clear(count) // the box can be emptied while typing
    expect(count).toHaveValue(null)
    await user.type(count, '30') // too many: brought to the most the server takes
    await user.type(screen.getByLabelText(/Note for the applicant/), 'Last months')
    expect(count).toHaveValue(12)
    const last = seen.mock.calls.at(-1)[0]
    expect(toBody(last)).toEqual({ items: [{ type: 'payslip', count: 12 }], note: 'Last months' })
    await user.clear(count)
    await user.type(screen.getByLabelText(/Note for the applicant/), '!')
    expect(toBody(seen.mock.calls.at(-1)[0]).items[0].count).toBe(1) // an empty box means one
    await user.click(screen.getByRole('checkbox', { name: 'Payslips' })) // untick removes it
    expect(screen.queryByLabelText('How many Payslips')).not.toBeInTheDocument()
  })

  it('is complete with a document or a note, not with neither', () => {
    expect(isComplete({ items: [], note: '   ' })).toBe(false)
    expect(isComplete({ items: [{ type: 'payslip', count: 1 }], note: '' })).toBe(true)
    expect(isComplete({ items: [], note: 'Please send more' })).toBe(true)
  })

  it('counts the note and warns not to write personal data', () => {
    render(<Harness onValue={() => {}} />)
    expect(screen.getByText(/0 of 200/)).toBeInTheDocument()
    expect(screen.getByText(/personal numbers/)).toBeInTheDocument()
  })
})
