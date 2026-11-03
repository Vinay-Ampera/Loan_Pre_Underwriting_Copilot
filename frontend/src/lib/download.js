import { api } from '../api/client'

/** Save a file the server sends behind the sign-in (a CSV export) through the browser. */
export async function downloadFile(path, filename) {
  const blob = await api.blob(path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** A query string from the filters that are filled in. */
export function queryOf(filters, extra = {}) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries({ ...filters, ...extra })) {
    if (v !== '' && v != null) p.set(k, v)
  }
  return p.toString()
}
