import { useCallback, useState } from 'react'
import { loadSession } from '../api/session'

// Text the person is typing (an override reason, a problem report) is kept in sessionStorage as
// they type, so a session that ends (idle, 12 hours) loses nothing. Drafts are per user and per
// page, are dropped when the person cancels or submits, and are wiped on a deliberate sign-out.
const PREFIX = 'lc.draft.'

const keyFor = (name) =>
  `${PREFIX}${loadSession()?.user.id ?? 'anon'}.${name}@${window.location.pathname}`

function read(key) {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key, value) {
  try {
    if (value) sessionStorage.setItem(key, value)
    else sessionStorage.removeItem(key)
  } catch {
    /* storage unavailable: the draft lasts until the page closes */
  }
}

/** Like useState for a string, but remembered. Returns [value, setValue, discard]. */
export function useDraft(name, initial = '') {
  const [key] = useState(() => keyFor(name))
  const [value, setValue] = useState(() => read(key) ?? initial)
  const set = useCallback(
    (next) => {
      setValue(next)
      write(key, next)
    },
    [key],
  )
  const discard = useCallback(() => write(key, ''), [key])
  return [value, set, discard]
}

export function clearDrafts() {
  try {
    Object.keys(sessionStorage)
      .filter((k) => k.startsWith(PREFIX))
      .forEach((k) => sessionStorage.removeItem(k))
  } catch {
    /* nothing to clear */
  }
}
