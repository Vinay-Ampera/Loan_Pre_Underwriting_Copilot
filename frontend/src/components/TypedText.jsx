import { useEffect, useState } from 'react'

const seen = new Set()

/**
 * Types the text out once per page view. The whole text is always in the DOM for screen readers
 * and copy; the visible part grows. Skipped under prefers-reduced-motion and when `id` was
 * already typed in this page view.
 */
export default function TypedText({ id, text, speed = 12 }) {
  const reduced =
    typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const instant = reduced || seen.has(id)
  const [shown, setShown] = useState(instant ? text.length : 0)

  useEffect(() => {
    if (instant) return undefined
    seen.add(id)
    const step = Math.max(1, Math.ceil(text.length / 160))
    const timer = setInterval(() => {
      setShown((n) => {
        if (n + step >= text.length) clearInterval(timer)
        return Math.min(text.length, n + step)
      })
    }, speed)
    return () => clearInterval(timer)
  }, [id, text, speed, instant])

  if (shown >= text.length) return <span data-typed="done">{text}</span>
  return (
    <span data-typed="running">
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{text.slice(0, shown)}</span>
    </span>
  )
}
