import { afterEach, describe, expect, it, vi } from 'vitest'
import { publicApi, tokenFromHash } from './public'

afterEach(() => vi.unstubAllGlobals())

describe('public api', () => {
  it('reads the token from the fragment', () => {
    expect(tokenFromHash('#abc_DEF-123')).toBe('abc_DEF-123')
    expect(tokenFromHash('')).toBe('')
  })

  it('sends the token in a header, never in the address, and carries no sign-in', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ active: true }) })
    vi.stubGlobal('fetch', fetchMock)
    await publicApi.link('tok-0123456789abcdefghij')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/public/link')
    expect(url).not.toContain('tok-')
    expect(init.headers['X-Upload-Token']).toBe('tok-0123456789abcdefghij')
    expect(init.headers.Authorization).toBeUndefined()
    expect(init.cache).toBe('no-store')
  })

  it('turns the generic refusal into a plain error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'This link is not active.' }),
      }),
    )
    await expect(publicApi.link('x'.repeat(30))).rejects.toMatchObject({ status: 404 })
  })

  it('the second click on send is explicit', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ reference: 'PRM-1' }) })
    vi.stubGlobal('fetch', fetchMock)
    await publicApi.send('t'.repeat(30))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ second_click: true })
  })
})
