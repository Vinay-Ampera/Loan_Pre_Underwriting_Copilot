import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TypedText, { TYPING_MS } from './TypedText'

const TEXT = 'Total score 72 of 100. Two findings need review before sign-off.'

function mockMotion(reduce) {
  window.matchMedia = vi.fn().mockImplementation((q) => ({
    matches: reduce && q.includes('reduce'),
    media: q,
    addEventListener() {},
    removeEventListener() {},
  }))
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  delete window.matchMedia
})

describe('TypedText', () => {
  it('keeps the whole text readable at once and grows the visible part', () => {
    mockMotion(false)
    const { container } = render(<TypedText id="a" text={TEXT} />)
    expect(screen.getByText(TEXT, { selector: '.sr-only' })).toBeInTheDocument()
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'running')
    act(() => vi.advanceTimersByTime(5000))
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'done')
    expect(container).toHaveTextContent(TEXT)
  })

  it('finishes a long summary in about half a second', () => {
    mockMotion(false)
    const long = `${TEXT} `.repeat(12) // about 780 characters
    const { container } = render(<TypedText id="long" text={long} />)
    act(() => vi.advanceTimersByTime(TYPING_MS / 2))
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'running')
    act(() => vi.advanceTimersByTime(TYPING_MS / 2 + 40))
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'done')
  })

  it('shows the text straight away under reduced motion', () => {
    mockMotion(true)
    const { container } = render(<TypedText id="b" text={TEXT} />)
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'done')
  })

  it('types a given text only once per page view', () => {
    mockMotion(false)
    const first = render(<TypedText id="c" text={TEXT} />)
    act(() => vi.advanceTimersByTime(5000))
    first.unmount()
    const { container } = render(<TypedText id="c" text={TEXT} />)
    expect(container.querySelector('[data-typed]')).toHaveAttribute('data-typed', 'done')
  })
})
