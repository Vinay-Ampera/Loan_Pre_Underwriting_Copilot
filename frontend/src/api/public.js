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

/** The applicant's own file as a Blob. The token is a header, so a plain link cannot fetch it. */
async function blob(path, token) {
  let res
  try {
    res = await fetch(BASE + path, { headers: { 'X-Upload-Token': token }, cache: 'no-store' })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection and try again.')
  }
  if (!res.ok) throw new ApiError(res.status, 'This file cannot be shown.')
  return res.blob()
}

export const publicApi = {
  link: (token) => call('GET', '/link', token),
  request: (token, json) => call('POST', '/request', token, { json }),
  files: (token, form) => call('POST', '/files', token, { form }),
  send: (token) => call('POST', '/send', token, { json: { second_click: true } }),
  myFiles: (token) => call('GET', '/my-files', token),
  fileBlob: (token, id) => blob(`/files/${encodeURIComponent(id)}`, token),
  removeFile: (token, id) =>
    call('POST', `/files/${encodeURIComponent(id)}/remove`, token, {
      json: { second_click: true },
    }),
}

/** The token from the page address (`/u#TOKEN`). */
export const tokenFromHash = (hash) => decodeURIComponent((hash || '').replace(/^#/, '')).trim()
