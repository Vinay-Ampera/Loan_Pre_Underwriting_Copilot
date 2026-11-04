import { clearSession, loadSession, saveSession, sessionFrom } from './session'

const BASE = '/api/v1'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

/** FastAPI sends `detail` as text, or as a list of {loc, msg} for form validation. */
export function messageFrom(detail, status) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const where = (d.loc || []).filter((p) => p !== 'body').join(' > ')
        const msg = String(d.msg || '').replace(/^Value error, /, '')
        return where ? `${where}: ${msg}` : msg
      })
      .join('; ')
  }
  return `The request failed (${status}).`
}

let renewing = null

/**
 * Ask the server for a new 15-minute token using the refresh cookie. One call at a time: a burst
 * of 401s waits on the same renewal. Resolves { ok } or { ok: false, reason, message }, or
 * { ok: false, network: true } when the server cannot be reached (the person stays signed in).
 */
export function renewSession() {
  renewing ||= fetchRenewal().finally(() => {
    renewing = null
  })
  return renewing
}

async function fetchRenewal() {
  const before = loadSession()
  let res
  try {
    res = await fetch(`${BASE}/auth/refresh`, { method: 'POST' })
  } catch {
    return { ok: false, network: true }
  }
  if (res.ok) {
    const body = await res.json()
    if (!before || before.user.id !== body.user.id) {
      return { ok: false, reason: 'other_user', message: 'This tab was signed in as someone else.' }
    }
    saveSession(sessionFrom(body))
    return { ok: true }
  }
  let body = {}
  try {
    body = await res.json()
  } catch {
    /* no body */
  }
  return { ok: false, reason: body.reason || 'ended', message: body.detail }
}

function endedByServer(message) {
  const userId = loadSession()?.user.id
  clearSession()
  window.dispatchEvent(new CustomEvent('lc:signed-out', { detail: { message, userId } }))
}

async function request(method, path, { json, form, raw } = {}, retried = false) {
  const headers = {}
  const session = loadSession()
  if (session?.token) headers.Authorization = `Bearer ${session.token}`
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form
  }
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  if (!res.ok) {
    let detail
    try {
      detail = (await res.json()).detail
    } catch {
      detail = undefined
    }
    if (res.status === 401 && session && !path.startsWith('/auth/')) {
      // The 15-minute token ran out: renew it quietly and repeat the request once.
      if (!retried) {
        const renewed = await renewSession()
        if (renewed.ok) return request(method, path, { json, form, raw }, true)
        if (renewed.network)
          throw new ApiError(0, 'Cannot reach the server. Try again in a moment.')
        endedByServer(renewed.message)
        throw new ApiError(401, renewed.message || 'Your session has ended. Sign in again.')
      }
      endedByServer()
    }
    throw new ApiError(res.status, messageFrom(detail, res.status))
  }
  if (raw) return res
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, json) => request('POST', path, { json }),
  put: (path, json) => request('PUT', path, { json }),
  patch: (path, json) => request('PATCH', path, { json }),
  del: (path) => request('DELETE', path),
  upload: (path, form) => request('POST', path, { form }),
  /** A file behind the sign-in (document image, report PDF) as a blob. */
  blob: async (path) => (await request('GET', path, { raw: true })).blob(),
}

/** Tell the server the person is working. Failures are ignored: the next real request retries. */
export const ping = () => api.post('/auth/ping').catch(() => {})

/** End the session on the server and drop the refresh cookie. Fire and forget. */
export const logout = () =>
  fetch(`${BASE}/auth/logout`, { method: 'POST', keepalive: true }).catch(() => {})

export const login = (email, password) => api.post('/auth/login', { email, password })
