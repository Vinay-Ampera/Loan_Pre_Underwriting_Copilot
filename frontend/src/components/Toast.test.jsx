import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Toast from './Toast'

describe('Toast', () => {
  afterEach(() => vi.useRealTimers())

  it('shows the message and goes after the time is up, even if the page re-renders', () => {
    vi.useFakeTimers()
    const onClose = vi.fn()
    const { rerender } = render(
      <Toast title="Not accepted" lines={['index.json']} onClose={onClose} />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('index.json')
    act(() => vi.advanceTimersByTime(5000))
    rerender(<Toast title="Not accepted" lines={['index.json']} onClose={onClose} />)
    act(() => vi.advanceTimersByTime(1999))
    expect(onClose).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(2))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('can be dismissed by hand', async () => {
    const onClose = vi.fn()
    render(<Toast title="Not accepted" onClose={onClose} />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onClose).toHaveBeenCalled()
  })
})
