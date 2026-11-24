import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import Loader from './Loader'

// Everything on a screen appears together. A page mounts hidden, its data requests run, and the
// page is shown once every one of them has finished, with one loader in the meantime. Only the
// first load of a screen is held back; refreshing a table or opening a tab later does not hide the
// page again.

const SETTLE_MS = 80 // quiet time with nothing loading before the page is shown
const MAX_MS = 10000 // never hold a page longer than this, whatever is still loading

const BootContext = createContext({ booted: true, markReady: () => {} })
const BusyContext = createContext(null)

const FONTS = [
  '400 1rem Inter',
  '500 1rem Inter',
  '600 1rem Inter',
  '500 1rem Outfit',
  '600 1rem Outfit',
]

/** Resolves when the bundled fonts are loaded, so text never appears in one font then jumps. */
export function fontsReady() {
  const fonts = typeof document === 'undefined' ? null : document.fonts
  if (!fonts?.load) return Promise.resolve()
  const give = new Promise((resolve) => setTimeout(resolve, 2500))
  return Promise.race([Promise.all(FONTS.map((f) => fonts.load(f).catch(() => []))), give])
}

/** Above the app: remembers that the first screen has been shown, and waits for the fonts. */
export function LoadingProvider({ children }) {
  const [booted, setBooted] = useState(false)
  const fonts = useRef(null)
  if (!fonts.current) fonts.current = fontsReady()
  const markReady = useCallback(() => {
    fonts.current.then(() => setBooted(true))
  }, [])
  const value = useMemo(() => ({ booted, markReady }), [booted, markReady])
  return <BootContext.Provider value={value}>{children}</BootContext.Provider>
}

export const useBooted = () => useContext(BootContext).booted

/** Tell the nearest Reveal that something is still loading while `active` is true. */
export function useBusy(active) {
  const register = useContext(BusyContext)
  useEffect(() => {
    if (!active || !register) return undefined
    return register()
  }, [active, register])
}

/** Loader shown in the content area while the page behind it is not ready. */
export function PageLoader({ label = 'Loading', full = false }) {
  return (
    <div className={`page-loader${full ? ' page-loader-full' : ''}`}>
      <Loader label={label} />
    </div>
  )
}

/**
 * The same loader inside one section of a page (a table being refreshed, a tab opening), sized
 * for the section and shown after a short pause so a quick answer does not flash it.
 */
export function SectionLoader({ label = 'Loading' }) {
  return (
    <div className="section-loader">
      <Loader label={label} size={40} />
    </div>
  )
}

/**
 * Mounts its children hidden, then shows them all at once when nothing inside is loading any more.
 * Children report loading through `useAsync` or `useBusy`. Key it by route so each screen gets
 * its own first load.
 */
export function Reveal({ children, label }) {
  const { markReady } = useContext(BootContext)
  const [ready, setReady] = useState(false)
  const count = useRef(0)
  const timer = useRef(null)
  const done = useRef(false)
  const alive = useRef(false)

  const settle = useCallback(() => {
    if (done.current || !alive.current) return
    done.current = true
    setReady(true)
    markReady()
  }, [markReady])
  const check = useCallback(() => {
    clearTimeout(timer.current)
    if (count.current === 0) timer.current = setTimeout(settle, SETTLE_MS)
  }, [settle])
  const register = useCallback(() => {
    if (done.current) return () => {}
    count.current += 1
    clearTimeout(timer.current)
    return () => {
      count.current = Math.max(0, count.current - 1)
      check()
    }
  }, [check])

  useEffect(() => {
    alive.current = true
    check()
    const cap = setTimeout(settle, MAX_MS)
    return () => {
      alive.current = false
      clearTimeout(timer.current)
      clearTimeout(cap)
    }
  }, [check, settle])

  return (
    <BusyContext.Provider value={register}>
      {!ready && <PageLoader label={label} />}
      <div className={ready ? 'reveal' : 'reveal reveal-wait'}>{children}</div>
    </BusyContext.Provider>
  )
}
