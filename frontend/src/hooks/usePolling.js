import { useEffect, useRef } from 'react'

/** Call `tick` every `ms` while `active`. Stops on unmount or when `active` turns false. */
export function usePolling(tick, active, ms = 2000) {
  const saved = useRef(tick)
  useEffect(() => {
    saved.current = tick
  })
  useEffect(() => {
    if (!active) return undefined
    const id = setInterval(() => saved.current(), ms)
    return () => clearInterval(id)
  }, [active, ms])
}
