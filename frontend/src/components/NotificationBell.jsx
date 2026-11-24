import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { formatWhen } from '../lib/format'
import Icon from './Icons'
import { SectionLoader } from './Loading'
import { useUnread } from './UnreadProvider'
import './NotificationBell.css'

export const inboxPath = (role) => (role === 'admin' ? '/admin/inbox' : '/inbox')

const label = (n) => (n === 0 ? 'Notifications, none unread' : `Notifications, ${n} unread`)
const SHOWN = 8 // the latest notices in the dropdown; the inbox has the rest and the filters

/**
 * The bell in the top bar. A click opens a dropdown with the latest notices (read ones greyed),
 * "Mark all read" and a link to the full inbox. Opening a notice marks it read and goes where it
 * points, as in the inbox. The button's name carries the real unread count.
 */
export default function NotificationBell({ user }) {
  const { count, setCount } = useUnread()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState(null) // null while loading
  const [problem, setProblem] = useState(null)
  const [busy, setBusy] = useState(false)
  const root = useRef(null)

  // fresh every time it opens
  useEffect(() => {
    if (!open) return undefined
    let live = true
    setItems(null)
    setProblem(null)
    api
      .get(`/notifications?limit=${SHOWN}&offset=0&unread=false`)
      .then((d) => live && setItems(d.items))
      .catch((e) => {
        if (!live) return
        setItems([])
        setProblem(e.message)
      })
    return () => {
      live = false
    }
  }, [open])

  useEffect(() => {
    if (!open) return undefined
    const away = (e) => !root.current?.contains(e.target) && setOpen(false)
    const esc = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  async function openNotice(n) {
    setProblem(null)
    if (!n.read_at) {
      try {
        await api.post(`/notifications/${n.id}/read`)
        setCount((c) => Math.max(0, c - 1))
      } catch (e) {
        setProblem(e.message)
        return
      }
    }
    setOpen(false)
    if (n.path) navigate(n.path)
  }

  async function markAll() {
    setBusy(true)
    setProblem(null)
    try {
      const done = await api.post('/notifications/read-all')
      const now = new Date().toISOString()
      setItems((list) => list?.map((n) => ({ ...n, read_at: n.read_at || now })) ?? list)
      setCount(done.unread)
    } catch (e) {
      setProblem(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="bell-wrap" ref={root}>
      <button
        type="button"
        className="bell"
        aria-label={label(count)}
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Notifications"
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="bell" size={18} />
        {count > 0 && (
          <span className="bell-count" aria-hidden="true">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <div className="bell-panel card" role="dialog" aria-label="Latest notifications">
          <div className="bell-head">
            <strong>Notifications</strong>
            <button
              type="button"
              className="btn btn-ghost bell-mark"
              disabled={busy || count === 0}
              onClick={markAll}
            >
              Mark all read
            </button>
          </div>
          {problem && (
            <p className="field-error small bell-note" role="alert">
              {problem}
            </p>
          )}
          {items === null ? (
            <SectionLoader label="Loading notifications" />
          ) : items.length === 0 ? (
            !problem && (
              <p className="bell-empty muted">
                No notifications yet. New notices appear here when something needs you.
              </p>
            )
          ) : (
            <ul className="bell-list" aria-label="Latest notifications">
              {items.map((n) => (
                <li key={n.id} className={n.read_at ? 'read' : 'unread'}>
                  <button type="button" className="bell-item" onClick={() => openNotice(n)}>
                    <span className="bell-dot" aria-hidden="true" />
                    <span className="bell-text">
                      <span className="bell-title">
                        {!n.read_at && <span className="sr-only">Unread: </span>}
                        {n.title}
                      </span>
                      {n.body && <span className="small muted">{n.body}</span>}
                      <span className="small muted">
                        {n.case_ref && `${n.case_ref} · `}
                        {formatWhen(n.created_at)}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="bell-all"
            onClick={() => {
              setOpen(false)
              navigate(inboxPath(user.role))
            }}
          >
            Open the inbox
            <Icon name="inbox" size={16} />
          </button>
        </div>
      )}
    </div>
  )
}
