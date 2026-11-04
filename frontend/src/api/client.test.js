import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, messageFrom } from './client'

describe('messageFrom', () => {
  it('passes a plain message through', () => {
    expect(messageFrom('KYC documents are missing: pan_card (primary).', 422)).toContain('pan_card')
  })

  it('turns validation errors into one readable line', () => {
    const detail = [
      { loc: ['body', 'applicants', 0, 'pan'], msg: 'String should match pattern' },
      { loc: ['body'], msg: 'Value error, a education loan needs a co-applicant' },
    ]
    expect(messageFrom(detail, 422)).toBe(
      'applicants > 0 > pan: String should match pattern; a education loan needs a co-applicant',
    )
  })

  it('falls back to the status code', () => {
    expect(messageFrom(undefined, 500)).toBe('The request failed (500).')
  })
})

describe('api verbs', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('has put and del as real functions that send the right method', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    expect(typeof api.put).toBe('function')
    await api.put('/messages/m1', { body: 'x' })
    await api.del('/messages/m1')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT', body: '{"body":"x"}' })
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' })
  })
})

describe('token renewal', () => {
  const stored = () =>
    sessionStorage.setItem(
      'lc.session',
      JSON.stringify({ token: 'old', user: { id: 'u1', role: 'officer' }, info: {} }),
    )
  const reply = (status, body) => ({ ok: status < 400, status, json: async () => body })

  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it('renews an expired token once and repeats the request, with no sign-out', async () => {
    stored()
    const signedOut = vi.fn()
    window.addEventListener('lc:signed-out', signedOut)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(401, { detail: 'expired' }))
      .mockResolvedValueOnce(
        reply(200, {
          access_token: 'new',
          user: { id: 'u1' },
          session: { idle_timeout_seconds: 1800 },
        }),
      )
      .mockResolvedValueOnce(reply(200, { cases: [] }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await api.get('/cases')).toEqual({ cases: [] })
    expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/auth/refresh')
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe('Bearer new')
    expect(signedOut).not.toHaveBeenCalled()
    window.removeEventListener('lc:signed-out', signedOut)
  })

  it('signs out, with the server reason, when the session cannot be renewed', async () => {
    stored()
    const signedOut = vi.fn()
    window.addEventListener('lc:signed-out', signedOut)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(reply(401, { detail: 'expired' }))
        .mockResolvedValueOnce(reply(401, { detail: 'You were signed out.', reason: 'idle' })),
    )
    await expect(api.get('/cases')).rejects.toMatchObject({ status: 401 })
    expect(signedOut.mock.calls[0][0].detail).toMatchObject({
      message: 'You were signed out.',
      userId: 'u1',
    })
    expect(sessionStorage.getItem('lc.session')).toBeNull()
    window.removeEventListener('lc:signed-out', signedOut)
  })

  it('stays signed in when the server cannot be reached during renewal', async () => {
    stored()
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(reply(401, { detail: 'expired' }))
        .mockRejectedValueOnce(new TypeError('offline')),
    )
    await expect(api.get('/cases')).rejects.toMatchObject({ status: 0 })
    expect(sessionStorage.getItem('lc.session')).not.toBeNull()
  })
})
