import { useEffect, useState } from 'react'

/**
 * Loads the board's jobs.json once on mount.
 *
 * jobs.json is committed by the daily GitHub Action, not generated at
 * request time -- this just fetches whatever the last run published.
 */
export function useJobs() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    fetch('/jobs.json')
      .then((response) => {
        if (!response.ok) {
          throw new Error(`jobs.json returned ${response.status}`)
        }
        return response.json()
      })
      .then((data) => {
        if (!cancelled) {
          setJobs(Array.isArray(data) ? data : data.jobs || [])
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { jobs, loading, error }
}