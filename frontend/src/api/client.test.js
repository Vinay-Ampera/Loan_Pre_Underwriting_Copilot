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
