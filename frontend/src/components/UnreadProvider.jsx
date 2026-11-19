import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'

const POLL_MS = 60_000

const UnreadContext = createContext({ count: 0, refresh: () => {}, setCount: () => {} })

/** The number of unread notifications for the signed-in officer or admin (`useUnread`). */
export const useUnread = () => useContext(UnreadContext)

/**
 * Keeps the unread count fresh: once on sign-in, every 60 seconds while the tab is visible and
 * when the window gets focus. No websockets. The auditor has no inbox, so nothing is asked for
 * them. A failed read keeps the last count (a 401 is handled by the API client, which ends the
 * session; the person is then gone and so is this timer, so it cannot loop).
 */
export function UnreadProvider({ user, children }) {
  const [count, setCount] = useState(0)
  const enabled = Boolean(user) && user.role !== 'auditor'
  const alive = useRef(true)

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      const { unread } = await api.get('/notifications/unread-count')
      if (alive.current) setCount(unread)
    } catch {
      /* keep the count we have */
    }
  }, [enabled])

  const userId = user?.id
  useEffect(() => {
    alive.current = true
    if (!enabled) {
      setCount(0)
      return undefined
    }
    refresh()
    const tick = () => document.visibilityState !== 'hidden' && refresh()
    const id = setInterval(tick, POLL_MS)
    window.addEventListener('focus', refresh)
    return () => {
      alive.current = false
      clearInterval(id)
      window.removeEventListener('focus', refresh)
    }
  }, [enabled, userId, refresh])

  const value = useMemo(() => ({ count, refresh, setCount }), [count, refresh])
  return <UnreadContext.Provider value={value}>{children}</UnreadContext.Provider>
}
