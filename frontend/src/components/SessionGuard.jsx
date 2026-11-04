import { useEffect, useRef, useState } from 'react'
import { ping, renewSession } from '../api/client'
import { loadSession } from '../api/session'
import Dialog from './Dialog'
import './SessionGuard.css'

const ACTIVITY_KEY = 'lc.activity' // shared by tabs, so a busy tab keeps an idle one signed in
const PING_EVERY_MS = 60_000
const RENEW_LEAD_MS = 60_000
const MAX_WARNING_MS = 15 * 60_000
const EVENTS = ['pointerdown', 'keydown', 'wheel', 'touchstart', 'mousemove']

function sharedActivity() {
  try {
    return Number(localStorage.getItem(ACTIVITY_KEY)) || 0
  } catch {
    return 0
  }
}

function shareActivity(at) {
  try {
    localStorage.setItem(ACTIVITY_KEY, String(at))
  } catch {
    /* tabs then track activity on their own */
  }
}

const clock = (seconds) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

/**
 * Keeps a signed-in session healthy without bothering the person: renews the 15-minute token a
 * minute before it runs out, tells the server when they are working, warns two minutes before the
 * idle sign-out and fifteen minutes before the 12-hour limit. The server enforces both limits;
 * these timers only make the end predictable. `onEnd(reason, message)` signs the person out.
 */
export default function SessionGuard({ onEnd }) {
  const [warning, setWarning] = useState(null) // { kind: 'idle' | 'max', left: seconds }
  const last = useRef(Date.now())
  const lastPing = useRef(0)
  const lastShared = useRef(0)
  const warned = useRef(null)
  const maxDismissed = useRef(false)
  const renewing = useRef(false)

  function worked() {
    const now = Date.now()
    last.current = now
    if (now - lastShared.current > 5000) {
      lastShared.current = now
      shareActivity(now)
    }
    if (now - lastPing.current > PING_EVERY_MS) {
      lastPing.current = now
      ping()
    }
  }

  useEffect(() => {
    // While the idle warning is up, passing mouse movement must not count as "still here".
    const onEvent = () => warned.current !== 'idle' && worked()
    EVENTS.forEach((e) => window.addEventListener(e, onEvent, { passive: true }))
    worked()
    return () => EVENTS.forEach((e) => window.removeEventListener(e, onEvent))
  }, [])

  useEffect(() => {
    const tick = () => {
      const s = loadSession()
      if (!s?.info) return
      const now = Date.now()
      const idleMs = now - Math.max(last.current, sharedActivity())
      const idleLimit = s.info.idle_timeout_seconds * 1000
      const maxEnd = Date.parse(s.info.max_ends_at)
      if (idleMs >= idleLimit) return onEnd('idle')
      if (now >= maxEnd) return onEnd('max')

      if (
        now - s.issuedAt >= s.info.access_token_seconds * 1000 - RENEW_LEAD_MS &&
        !renewing.current
      ) {
        renewing.current = true
        renewSession()
          .then((r) => !r.ok && !r.network && onEnd(r.reason, r.message))
          .finally(() => {
            renewing.current = false
          })
      }

      const idleLeft = idleLimit - idleMs
      if (idleLeft <= s.info.idle_warning_seconds * 1000) {
        warned.current = 'idle'
        setWarning({ kind: 'idle', left: Math.ceil(idleLeft / 1000) })
      } else if (maxEnd - now <= MAX_WARNING_MS && !maxDismissed.current) {
        warned.current = 'max'
        setWarning({ kind: 'max', left: Math.ceil((maxEnd - now) / 1000) })
      } else {
        warned.current = null
        setWarning(null)
      }
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [onEnd])

  function stay() {
    warned.current = null
    worked()
    lastPing.current = Date.now()
    ping()
    setWarning(null)
  }

  if (!warning) return null
  if (warning.kind === 'idle') {
    return (
      <Dialog title="Still there?" onClose={stay} labelledBy="idle-title">
        <p>
          You will be signed out in <strong>{clock(warning.left)}</strong> because there has been no
          activity. What you have typed is saved.
        </p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-primary" data-autofocus onClick={stay}>
            Stay signed in
          </button>
        </div>
      </Dialog>
    )
  }
  return (
    <Dialog
      title="Your working day is ending"
      onClose={() => {
        maxDismissed.current = true
        setWarning(null)
      }}
      labelledBy="max-title"
    >
      <p>
        For safety, a session lasts at most 12 hours. Yours ends in{' '}
        <strong>{clock(warning.left)}</strong>. Finish what you are doing; you can sign in again
        straight after, and what you have typed is saved.
      </p>
      <div className="dialog-actions">
        <button
          type="button"
          className="btn btn-primary"
          data-autofocus
          onClick={() => {
            maxDismissed.current = true
            setWarning(null)
          }}
        >
          OK
        </button>
      </div>
    </Dialog>
  )
}
