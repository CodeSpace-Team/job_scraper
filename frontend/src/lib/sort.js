/**
 * sort.js — ordering rules for the board's job list (F6)
 * ==========================================================
 *
 * Kept separate from filters.js on purpose: filtering decides which jobs
 * show, sorting decides what order they show in -- two different
 * questions, easier to reason about and test apart.
 */

export const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'years-asc', label: 'Fewest years required first' },
]

export const DEFAULT_SORT = 'newest'

function sortDate(job) {
  return job.date_posted || job.date_added || ''
}

function byDate(a, b) {
  return sortDate(a).localeCompare(sortDate(b))
}

function byYearsAscending(a, b) {
  const ay = a.experience_years
  const by = b.experience_years
  const aMissing = ay === null || ay === undefined || ay === ''
  const bMissing = by === null || by === undefined || by === ''

  // A job that states no years at all is not "zero years required" --
  // it is unknown, so it sorts after every job with a real number rather
  // than winning a race it never entered.
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  return Number(ay) - Number(by)
}

/**
 * Order a job list without mutating the input.
 *
 * @param {object[]} jobs
 * @param {string} sortBy - one of SORT_OPTIONS' values.
 */
export function sortJobs(jobs, sortBy = DEFAULT_SORT) {
  const sorted = [...jobs]

  if (sortBy === 'oldest') return sorted.sort(byDate)
  if (sortBy === 'years-asc') return sorted.sort(byYearsAscending)
  return sorted.sort((a, b) => byDate(b, a))
}