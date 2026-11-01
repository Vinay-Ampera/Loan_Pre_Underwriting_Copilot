import { useEffect, useRef } from 'react'
import './Dialog.css'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** A modal that traps focus, closes on Escape, and returns focus to what opened it. */
export default function Dialog({ title, children, onClose, labelledBy = 'dialog-title' }) {
  const box = useRef(null)

  useEffect(() => {
    const opener = document.activeElement
    const first =
      box.current?.querySelector('[data-autofocus]') || box.current?.querySelector(FOCUSABLE)
    first?.focus()
    return () => opener?.focus?.()
  }, [])

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }
    if (e.key !== 'Tab') return
    const items = [...box.current.querySelectorAll(FOCUSABLE)]
    if (!items.length) return
    const [first, last] = [items[0], items[items.length - 1]]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={box}
        className="dialog card"
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onKeyDown={onKeyDown}
      >
        <h2 id={labelledBy} className="dialog-title">
          {title}
        </h2>
        {children}
      </div>
    </div>
  )
}
