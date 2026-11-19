import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import Icon from './Icons'
import './Toast.css'

export const TOAST_MS = 7000

/**
 * A message pinned to the top right of the screen, so it is seen whatever part of a long page the
 * person is looking at. A bar under it runs down over `duration`, then the message goes. Give it a
 * new `key` to show a new message. The same text should also stay on the page for later.
 */
export default function Toast({ title, lines = [], tone = 'error', duration = TOAST_MS, onClose }) {
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  })
  // one timer per message: a re-render of the page must not restart it
  useEffect(() => {
    const t = setTimeout(() => close.current(), duration)
    return () => clearTimeout(t)
  }, [duration])
  // on the page body: an animated ancestor would otherwise carry a fixed box away with the scroll
  return createPortal(
    <div className="toast-host">
      <div className={`toast toast-${tone}`} role="status">
        <div className="toast-body">
          <span className="toast-icon" aria-hidden="true">
            <Icon name={tone === 'error' ? 'alert-circle' : 'check'} size={18} />
          </span>
          <div className="toast-text">
            <strong>{title}</strong>
            {lines.map((l, i) => (
              <p key={i} className="small">
                {l}
              </p>
            ))}
          </div>
          <button type="button" className="toast-close" aria-label="Dismiss" onClick={onClose}>
            <Icon name="x" size={16} />
          </button>
        </div>
        <div className="toast-bar" aria-hidden="true">
          <span style={{ animationDuration: `${duration}ms` }} />
        </div>
      </div>
    </div>,
    document.body,
  )
}
