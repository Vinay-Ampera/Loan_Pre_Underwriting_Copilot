import { useLayoutEffect, useRef, useState } from 'react'
import './FitPanes.css'

const MIN_HEIGHT = 420 // on a very short window the panes keep this much and the page scrolls

/** Where `el` starts on the page, ignoring transforms (the page's entrance animation). */
function pageTop(el) {
  let y = 0
  for (let node = el; node; node = node.offsetParent) y += node.offsetTop
  return y
}

/** Height of everything laid out below `el` up to the end of the page (padding, the footer). */
function spaceBelow(el) {
  let total = 0
  for (let node = el; node.parentElement && node !== document.body; node = node.parentElement) {
    const parent = node.parentElement
    const ps = getComputedStyle(parent)
    const gap = /flex|grid/.test(ps.display) ? parseFloat(ps.rowGap) || 0 : 0
    for (let s = node.nextElementSibling; s; s = s.nextElementSibling) {
      const ss = getComputedStyle(s)
      if (ss.display === 'none' || ss.position === 'fixed' || ss.position === 'absolute') continue
      total +=
        s.getBoundingClientRect().height +
        (parseFloat(ss.marginTop) || 0) +
        (parseFloat(ss.marginBottom) || 0) +
        gap
    }
    total += (parseFloat(ps.paddingBottom) || 0) + (parseFloat(ps.borderBottomWidth) || 0)
  }
  return total
}

/**
 * Side-by-side panes that fill the rest of the window on wide screens, so the page itself stays
 * still and each pane scrolls on its own (`.fit-scroll` inside marks what scrolls). Below
 * `minWidth`, or with `enabled` false, the panes stack or sit side by side and the page scrolls
 * as usual. Layout only: nothing else changes.
 */
export default function FitPanes({ minWidth, enabled = true, className = '', children, ...rest }) {
  const ref = useRef(null)
  const [height, setHeight] = useState(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!enabled) {
      setHeight(null) // the page scrolls as one, as on a narrow screen
      return undefined
    }
    if (!el || typeof window.matchMedia !== 'function') return undefined
    const wide = window.matchMedia(`(min-width: ${minWidth}px)`)
    let frame = 0
    const fit = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (!wide.matches || el.offsetParent === null) {
          setHeight(null)
          return
        }
        const room = Math.floor(window.innerHeight - pageTop(el) - spaceBelow(el))
        const next = Math.max(MIN_HEIGHT, room)
        setHeight((old) => (old === next ? old : next))
      })
    }
    fit()
    const watch = typeof ResizeObserver === 'function' ? new ResizeObserver(fit) : null
    watch?.observe(document.body) // the header wrapping, fonts arriving, the page being shown
    watch?.observe(el)
    window.addEventListener('resize', fit)
    wide.addEventListener?.('change', fit)
    return () => {
      cancelAnimationFrame(frame)
      watch?.disconnect()
      window.removeEventListener('resize', fit)
      wide.removeEventListener?.('change', fit)
    }
  }, [minWidth, enabled])

  return (
    <div
      ref={ref}
      className={`${className}${height ? ' fit-on' : ''}`}
      style={height ? { height } : undefined}
      {...rest}
    >
      {children}
    </div>
  )
}
