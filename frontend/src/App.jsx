import { useMemo, useState } from 'react'
import FilterPanel from './components/FilterPanel.jsx'
import JobCard from './components/JobCard.jsx'
import SearchBar from './components/SearchBar.jsx'
import { useJobs } from './hooks/useJobs.js'
import { EMPTY_FILTERS, extractFacets, filterJobs } from './lib/filters.js'
import { DEFAULT_SORT, SORT_OPTIONS, sortJobs } from './lib/sort.js'

export default function App() {
  const { jobs, loading, error } = useJobs()
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [sortBy, setSortBy] = useState(DEFAULT_SORT)

  const facets = useMemo(() => extractFacets(jobs), [jobs])
  const filtered = useMemo(() => filterJobs(jobs, filters), [jobs, filters])
  const visible = useMemo(() => sortJobs(filtered, sortBy), [filtered, sortBy])

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

        <div className="mb-4 flex flex-col gap-3 sm:flex-row">
          <div className="flex-1">
            <SearchBar
              value={filters.search}
              onChange={(search) => setFilters({ ...filters, search })}
            />
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            aria-label="Sort jobs"
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-codespace-teal focus:outline-none focus:ring-1 focus:ring-codespace-teal"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-6 md:flex-row">
          <FilterPanel facets={facets} filters={filters} onChange={setFilters} />

          {/* min-w-0 for the same reason as in JobCard: without it this
              column cannot shrink below the widest card it contains, and a
              single long job title pushes the layout past the screen. */}
          <div className="min-w-0 flex-1">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-neutral-600">
                <span
                  className="h-4 w-4 animate-spin rounded-full border-2 border-neutral-300 border-t-codespace-teal"
                  aria-hidden="true"
                />
                Loading jobs...
              </div>
            ) : (
              <>
                <p className="mb-3 text-sm text-neutral-600">
                  {visible.length} of {jobs.length} jobs
                </p>
                {/* The index is part of the key on purpose. Keys have to be
                    unique among siblings, and the apply link is not: the
                    board carried the same Power Platform advert on six rows
                    and the same ABAP advert on five, because a job with no
                    company name matched nothing in the publisher's merge and
                    was appended again every day.

                    React does not error on repeated keys, it mis-reconciles
                    -- on a filter change it left stale cards in the DOM, so
                    the board said "4 of 377 jobs" above thirty-two cards.
                    That is the screen Emma opened and reported.

                    The publisher no longer creates those rows, but a key
                    must not depend on data being clean to work. Appending
                    the index makes it unique whatever arrives. It costs the
                    re-use of a card's DOM node when the list reorders, which
                    on a few hundred cards is not measurable. */}
                <div className="space-y-3">
                  {visible.map((job, i) => (
                    <JobCard
                      key={`${job.job_url || `${job.title}-${job.company}`}#${i}`}
                      job={job}
                    />
                  ))}
                </div>
                {visible.length === 0 && jobs.length > 0 && (
                  <div className="rounded-lg border border-neutral-200 bg-white p-6 text-center">
                    <p className="text-sm text-neutral-600">
                      No jobs match these filters. Try clearing some from the panel on the left.
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
