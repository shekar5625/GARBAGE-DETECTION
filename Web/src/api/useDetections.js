import { useState, useEffect, useCallback } from 'react'

// Loads a detection listing and re-polls it on an interval, since detections
// arrive from main.py at any time with no push channel. Returns the rows plus
// a reload() the pages call after a verify/remove so the table reflects the
// toggle immediately rather than waiting for the next poll.
//
// `fetcher` must be a stable reference (the methods on `api` are) — it is a
// dependency of the polling effect, so an inline arrow would restart the
// interval on every render.
export function useDetections(fetcher, area, { pollMs = 5000 } = {}) {
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(
    async ({ quiet = false } = {}) => {
      if (!area) return
      if (!quiet) setLoading(true)
      try {
        setRows(await fetcher(area))
        setError(null)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    },
    [fetcher, area]
  )

  useEffect(() => {
    let cancelled = false
    const run = (opts) => !cancelled && load(opts)

    run()
    if (!pollMs) return () => { cancelled = true }

    const id = setInterval(() => run({ quiet: true }), pollMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [load, pollMs])

  return { rows, error, loading, reload: load }
}
