import { useEffect, useState } from 'react'

const seen = new Set()
const TICK_MS = 16
export const TYPING_MS = 480 // the whole text, however long: a hint of motion, never a wait

/**
 * Types the text out once per page view, in about half a second whatever its length. The whole
 * text is always in the DOM for screen readers and copy; the visible part grows. Skipped under
 * prefers-reduced-motion and when `id` was already typed in this page view.
 */
export default function TypedText({ id, text }) {
  const reduced =
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const instant = reduced || seen.has(id)
  const [shown, setShown] = useState(instant ? text.length : 0)

  useEffect(() => {
    if (instant) return undefined
    const step = Math.max(1, Math.ceil(text.length / (TYPING_MS / TICK_MS)))
    const timer = setInterval(() => {
      setShown((n) => {
        if (n + step >= text.length) {
          clearInterval(timer)
          seen.add(id) // only a finished text counts as seen, so a re-render mid-typing cannot freeze it
        }
        return Math.min(text.length, n + step)
      })
    }, TICK_MS)
    return () => clearInterval(timer)
  }, [id, text, instant])

  if (shown >= text.length) return <span data-typed="done">{text}</span>
  return (
    <span data-typed="running">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{text.slice(0, shown)}</span>
    </span>
  )
}
