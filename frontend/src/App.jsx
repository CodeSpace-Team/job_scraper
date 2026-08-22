import { useMemo, useState } from 'react'
import JobCard from './components/JobCard.jsx'
import SearchBar from './components/SearchBar.jsx'
import SearchForm from './components/SearchForm.jsx'
import { useJobs } from './hooks/useJobs.js'
import { extractFacets, matchesSearch } from './lib/filters.js'
import { EMPTY_CRITERIA, matchJobs } from './lib/match.js'
import { DEFAULT_SORT, SORT_OPTIONS, sortJobs } from './lib/sort.js'

/**
 * Skill names that are not things a student ticks to say what they can build.
 *
 * The pipeline's skills list is categorised, and most of it is technologies.
 * These few come from its "ways of working" and support categories and read
 * as filler in a picker -- nobody chooses their next job by whether the ad
 * mentions Documentation. Git, Agile/Jira and Code Review are deliberately
 * not here: those are real things somebody has or has not done.
 */
const NOT_A_TECH_SKILL = new Set([
  'Problem Solving',
  'Communication',
  'Documentation',
  'Customer Service',
])

export default function App() {
  const { jobs, loading, error } = useJobs()
  const [criteria, setCriteria] = useState(EMPTY_CRITERIA)

  // null until the student has actually searched. The board opens empty on
  // purpose: 44% of jobs carry no evidence of their own level, so listing
  // them up front would be presenting labels we do not trust as though we
  // did. Nothing is shown until somebody has said what they are looking for.
  const [results, setResults] = useState(null)

  // Both of these narrow what is already on screen, so they live with the
  // results rather than in the form -- there is nothing to keyword-search
  // or re-order before a search has happened.
  const [keyword, setKeyword] = useState('')
  const [sortBy, setSortBy] = useState(DEFAULT_SORT)

  const facets = useMemo(() => {
    const found = extractFacets(jobs)
    return {
      ...found,
      levels: found.levels.filter((l) => l === 'entry level' || l === 'junior'),
      skills: found.skills.filter((s) => !NOT_A_TECH_SKILL.has(s)),
    }
  }, [jobs])

  const search = () => {
    setKeyword('')
    setSortBy(DEFAULT_SORT)
    setResults(matchJobs(jobs, criteria))
  }

  // sortJobs works on jobs; the results carry a job plus why it matched, so
  // it is applied to the jobs and the results put back in that order.
  const shown = useMemo(() => {
    if (results === null) return []
    const narrowed = results.filter((r) => matchesSearch(r.job, keyword))
    const order = sortJobs(narrowed.map((r) => r.job), sortBy)
    return order.map((job) => narrowed.find((r) => r.job === job))
  }, [results, keyword, sortBy])

  const changeCriteria = (next) => {
    setCriteria(next)
    // A changed selection makes the results on screen stale. Clearing them
    // is more honest than leaving a list that no longer answers the form
    // above it.
    setResults(null)
  }

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

        <div className="flex flex-col gap-6 md:flex-row">
          <SearchForm
            facets={facets}
            criteria={criteria}
            onChange={changeCriteria}
            onSearch={search}
            resultCount={results === null ? null : results.length}
          />

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
            ) : results === null ? (
              <div className="rounded-lg border border-dashed border-neutral-300 bg-neutral-50 p-8 text-center">
                <h2 className="text-base font-semibold text-codespace-ink">
                  Tell us what you are looking for
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-neutral-600">
                  Pick the kind of work you want and where you are in your career,
                  then add the skills you already have. We match on what each advert
                  actually asks for, not on what it calls itself.
                </p>
                <p className="mt-3 text-xs text-neutral-500">
                  {jobs.length} jobs open right now.
                </p>
              </div>
            ) : (
              <>
                <div className="mb-4 flex flex-col gap-3 sm:flex-row">
                  <div className="min-w-0 flex-1">
                    <SearchBar value={keyword} onChange={setKeyword} />
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

                <p className="mb-3 text-sm text-neutral-600">
                  {shown.length} of {jobs.length} jobs match
                </p>
                <div className="space-y-3">
                  {shown.map((result, i) => (
                    <JobCard
                      key={`${result.job.job_url || result.job.title}#${i}`}
                      job={result.job}
                      match={result}
                      pickedSkills={criteria.skills.length}
                    />
                  ))}
                </div>
                {shown.length === 0 && (
                  <div className="rounded-lg border border-neutral-200 bg-white p-6 text-center">
                    <p className="text-sm text-neutral-600">
                      Nothing open matches that today. Try another kind of work, or
                      widen where you are.
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
