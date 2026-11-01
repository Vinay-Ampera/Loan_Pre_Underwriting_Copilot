import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ConfirmBar from './ConfirmBar'

const setup = () => {
  const onConfirm = vi.fn().mockResolvedValue()
  const onOverride = vi.fn().mockResolvedValue()
  render(
    <ConfirmBar
      recommendation="refer"
      recommendationText="Recommended: refer for manual review"
      onConfirm={onConfirm}
      onOverride={onOverride}
    />,
  )
  return { onConfirm, onOverride, user: userEvent.setup() }
}

describe('ConfirmBar', () => {
  it('needs a second click to confirm', async () => {
    const { onConfirm, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Confirm recommendation' }))
    expect(onConfirm).not.toHaveBeenCalled() // the first click only opens the dialog
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Yes, confirm' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('cancelling the dialog records nothing', async () => {
    const { onConfirm, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Confirm recommendation' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onConfirm).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes the dialog with Escape', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'Override' }))
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('blocks an override without a decision and a written reason', async () => {
    const { onOverride, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Override' }))
    const submit = screen.getByRole('button', { name: 'Submit override' })
    expect(submit).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Your decision'), 'reject')
    expect(submit).toBeDisabled() // a decision alone is not enough
    await user.type(screen.getByLabelText('Reason (required)'), 'too short')
    expect(submit).toBeDisabled()
    expect(onOverride).not.toHaveBeenCalled()
  })

  it('overrides with a different decision and a reason', async () => {
    const { onOverride, user } = setup()
    await user.click(screen.getByRole('button', { name: 'Override' }))
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options).not.toContain('refer') // cannot override to what the system recommended
    await user.selectOptions(screen.getByLabelText('Your decision'), 'approve')
    await user.type(
      screen.getByLabelText('Reason (required)'),
      'Salary verified with the employer by phone.',
    )
    await user.click(screen.getByRole('button', { name: 'Submit override' }))
    expect(onOverride).toHaveBeenCalledWith({
      final_decision: 'approve',
      reason: 'Salary verified with the employer by phone.',
    })
  })

  it('shows the server message when the action fails', async () => {
    const onConfirm = vi
      .fn()
      .mockRejectedValue(new Error('This case is not waiting for your confirmation.'))
    render(
      <ConfirmBar
        recommendation="refer"
        recommendationText="Recommended: refer"
        onConfirm={onConfirm}
        onOverride={vi.fn()}
      />,
    )
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Confirm recommendation' }))
    await user.click(screen.getByRole('button', { name: 'Yes, confirm' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('not waiting')
  })
})
