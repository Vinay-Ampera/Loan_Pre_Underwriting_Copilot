import { useCallback, useEffect, useRef, useState } from 'react'

/** Load something on mount (and on `reload`). Returns { data, error, loading, reload, setData }. */
export function useAsync(loader, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const alive = useRef(true)
  const latest = useRef(0)
  const run = useCallback(
    async (quiet = false) => {
      const mine = ++latest.current // a slower, older request must not overwrite a newer one
      if (!quiet) setState((s) => ({ ...s, loading: true, error: null }))
      try {
        const data = await loader()
        if (alive.current && mine === latest.current)
          setState({ data, error: null, loading: false })
      } catch (error) {
        if (alive.current && mine === latest.current) {
          setState((s) => ({ data: quiet ? s.data : null, error, loading: false }))
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    deps,
  )
  useEffect(() => {
    alive.current = true
    run()
    return () => {
      alive.current = false
    }
  }, [run])
  const setData = useCallback((data) => setState((s) => ({ ...s, data })), [])
  return { ...state, reload: () => run(true), setData }
}
