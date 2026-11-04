import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({ ping: vi.fn(), renewSession: vi.fn() }))

import { ping, renewSession } from '../api/client'
import SessionGuard from './SessionGuard'

const MIN = 60_000

let limit = 0 // the session's hard end, kept across renewals as the server does

function signIn({ issuedAt = Date.now(), maxEndsAt = Date.now() + 12 * 60 * MIN } = {}) {
  limit = maxEndsAt
  sessionStorage.setItem(
    'lc.session',
    JSON.stringify({
      token: 't',
      user: { id: 'u1' },
      issuedAt,
      info: {
        access_token_seconds: 900,
        idle_timeout_seconds: 1800,
        idle_warning_seconds: 120,
        max_ends_at: new Date(maxEndsAt).toISOString(),
      },
    }),
  )
}

const advance = (ms) => act(async () => vi.advanceTimersByTimeAsync(ms))

describe('SessionGuard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(ping).mockReset()
    // a real renewal stores a fresh token, which resets the clock for the next one
    vi.mocked(renewSession)
      .mockReset()
      .mockImplementation(async () => {
        signIn({ maxEndsAt: limit })
        return { ok: true }
      })
  })
  afterEach(() => vi.useRealTimers())

  it('says nothing while the person is active, and renews the token a minute early', async () => {
    signIn()
    const onEnd = vi.fn()
    render(<SessionGuard onEnd={onEnd} />)
    await advance(13 * MIN)
    expect(renewSession).not.toHaveBeenCalled()
    await advance(1.5 * MIN) // past 14 minutes
    expect(renewSession).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(onEnd).not.toHaveBeenCalled()
  })

  it('warns two minutes before the idle sign-out, and Stay signed in cancels it', async () => {
    signIn()
    const onEnd = vi.fn()
    render(<SessionGuard onEnd={onEnd} />)
    await advance(28 * MIN + 5000)
    expect(screen.getByRole('dialog', { name: 'Still there?' })).toBeInTheDocument()
    await act(async () => screen.getByRole('button', { name: 'Stay signed in' }).click())
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(ping).toHaveBeenCalled()
    await advance(5 * MIN)
    expect(onEnd).not.toHaveBeenCalled()
  })

  it('signs out after 30 minutes of no activity', async () => {
    signIn()
    const onEnd = vi.fn()
    render(<SessionGuard onEnd={onEnd} />)
    await advance(30 * MIN + 2000)
    expect(onEnd).toHaveBeenCalledWith('idle')
  })

  it('tells the server when the person works, at most once a minute', async () => {
    signIn()
    render(<SessionGuard onEnd={vi.fn()} />)
    await advance(2 * MIN)
    ping.mockClear()
    await act(async () => window.dispatchEvent(new Event('keydown')))
    await act(async () => window.dispatchEvent(new Event('keydown')))
    expect(ping).toHaveBeenCalledTimes(1)
  })

  it('warns 15 minutes before the 12-hour limit, then signs out at it', async () => {
    signIn({ maxEndsAt: Date.now() + 16 * MIN })
    const onEnd = vi.fn()
    render(<SessionGuard onEnd={onEnd} />)
    await advance(2000)
    expect(screen.queryByRole('dialog')).toBeNull()
    // keep the person active so only the hard limit applies
    for (let i = 0; i < 14; i += 1) {
      await act(async () => window.dispatchEvent(new Event('keydown')))
      await advance(MIN)
    }
    expect(screen.getByRole('dialog', { name: 'Your working day is ending' })).toBeInTheDocument()
    for (let i = 0; i < 2; i += 1) {
      await act(async () => window.dispatchEvent(new Event('keydown')))
      await advance(MIN)
    }
    expect(onEnd).toHaveBeenCalledWith('max')
  })

  it('signs out with the server reason when renewal is refused', async () => {
    signIn({ issuedAt: Date.now() - 14.5 * MIN })
    renewSession.mockResolvedValue({ ok: false, reason: 'reuse', message: 'closed' })
    const onEnd = vi.fn()
    render(<SessionGuard onEnd={onEnd} />)
    await advance(2000)
    expect(onEnd).toHaveBeenCalledWith('reuse', 'closed')
  })
})
