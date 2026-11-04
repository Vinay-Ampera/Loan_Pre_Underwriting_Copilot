import { ApiError, messageFrom } from './client'

const BASE = '/api/v1/public'

/**
 * The applicant's side. It has no session and never touches the officer's sign-in: the link's
 * token travels in a header (the page keeps it in the URL fragment, which a browser never sends),
 * and nothing here is cached or stored.
 */
async function call(method, path, token, { json, form } = {}) {
  const headers = { 'X-Upload-Token': token }
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form) {
    body = form
  }
  let res
  try {
    res = await fetch(BASE + path, { method, headers, body, cache: 'no-store' })
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
    throw new ApiError(res.status, messageFrom(detail, res.status))
  }
  return res.json()
}

export const publicApi = {
  link: (token) => call('GET', '/link', token),
  request: (token, json) => call('POST', '/request', token, { json }),
  files: (token, form) => call('POST', '/files', token, { form }),
  send: (token) => call('POST', '/send', token, { json: { second_click: true } }),
}

/** The token from the page address (`/u#TOKEN`). */
export const tokenFromHash = (hash) => decodeURIComponent((hash || '').replace(/^#/, '')).trim()
