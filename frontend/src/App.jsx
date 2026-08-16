import { useMemo, useState } from 'react'
import FilterPanel from './components/FilterPanel.jsx'
import JobCard from './components/JobCard.jsx'
import SearchBar from './components/SearchBar.jsx'
import { useJobs } from './hooks/useJobs.js'
import { EMPTY_FILTERS, extractFacets, filterJobs } from './lib/filters.js'

export default function App() {
  const { jobs, loading, error } = useJobs()
  const [filters, setFilters] = useState(EMPTY_FILTERS)

  const facets = useMemo(() => extractFacets(jobs), [jobs])
  const visible = useMemo(() => filterJobs(jobs, filters), [jobs, filters])

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-neutral-800 bg-codespace-ink">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-6">
          <img
            src="https://codespace-assets.global.ssl.fastly.net/wp/assets/website/codespace-primary-logo-light.svg"
            alt="CodeSpace"
            className="h-8 w-auto"
          />
          <div>
            <h1 className="text-xl font-bold text-codespace-teal">Job Board</h1>
            <p className="text-sm text-neutral-300">
              Tech jobs in South Africa for graduates in their first three years of work.
            </p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {error && (
          <div className="mb-4 rounded-md bg-red-50 p-4 text-sm text-red-700">
            Could not load today's jobs ({error.message}). Try refreshing the page.
          </div>
        )}

        <div className="mb-4">
          <SearchBar
            value={filters.search}
            onChange={(search) => setFilters({ ...filters, search })}
          />
        </div>

        <div className="flex flex-col gap-6 md:flex-row">
          <FilterPanel facets={facets} filters={filters} onChange={setFilters} />

          <div className="flex-1">
            {loading ? (
              <p className="text-sm text-neutral-600">Loading jobs...</p>
            ) : (
              <>
                <p className="mb-3 text-sm text-neutral-600">
                  {visible.length} of {jobs.length} jobs
                </p>
                <div className="space-y-3">
                  {visible.map((job) => (
                    <JobCard key={job.job_url || `${job.title}-${job.company}`} job={job} />
                  ))}
                </div>
                {visible.length === 0 && jobs.length > 0 && (
                  <p className="text-sm text-neutral-600">
                    No jobs match these filters. Try clearing a few.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}