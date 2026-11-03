import { clearSession, loadSession } from './session'

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

async function request(method, path, { json, form, raw } = {}) {
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
    if (res.status === 401 && session && !path.startsWith('/auth/login')) {
      clearSession()
      window.dispatchEvent(new Event('lc:signed-out'))
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
  del: (path) => request('DELETE', path),
  upload: (path, form) => request('POST', path, { form }),
  /** A file behind the sign-in (document image, report PDF) as a blob. */
  blob: async (path) => (await request('GET', path, { raw: true })).blob(),
}

export const login = (email, password) => api.post('/auth/login', { email, password })
