import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BandChip, CaseStatusChip } from './StatusChip'

describe('StatusChip', () => {
  it('always has a text label, not colour alone', () => {
    render(<CaseStatusChip status="stopped" />)
    expect(screen.getByText('Stopped: needs correction')).toBeInTheDocument()
  })

  it('says recommended, never approved', () => {
    render(<BandChip band="approve" />)
    expect(screen.getByText(/Recommended: approve/)).toBeInTheDocument()
  })

  it('shows "Not computed" when there is no band', () => {
    render(<BandChip band={null} />)
    expect(screen.getByText('Not computed')).toBeInTheDocument()
  })

  it('shows the waiting state for a case awaiting the officer', () => {
    render(<CaseStatusChip status="awaiting_confirmation" band="refer" />)
    expect(screen.getByText('Awaiting confirmation')).toBeInTheDocument()
  })
})
