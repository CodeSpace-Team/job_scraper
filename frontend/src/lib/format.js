/**
 * format.js — small display-formatting helpers (F6)
 * ====================================================
 *
 * Mirrors the same salary shape the backend's own Sheet writer formats
 * (salary_min/salary_max/salary_currency/salary_period) -- see
 * format_salary() in backend/src/writers/sheets.py.
 */

export function formatSalary(job) {
  const min = job.salary_min
  const max = job.salary_max
  const currency = job.salary_currency || ''
  const period = job.salary_period ? `/${job.salary_period}` : ''

  if (!min && !max) return null

  // A fixed locale, not the runtime's default -- toLocaleString() with no
  // argument formats according to whatever locale Node resolves on the
  // machine it runs on, which is not the same in every browser or CI
  // runner. "en-US" is used only to fix the thousands separator as a
  // comma, matching the same comma the backend's own format_salary()
  // always uses in the Sheet.
  if (min && max) {
    return `${currency} ${Number(min).toLocaleString('en-US')} - ${Number(max).toLocaleString('en-US')}${period}`.trim()
  }
  if (min) {
    return `${currency} ${Number(min).toLocaleString('en-US')}+${period}`.trim()
  }
  return `Up to ${currency} ${Number(max).toLocaleString('en-US')}${period}`.trim()
}

export function formatYears(years) {
  if (years === null || years === undefined || years === '') return null
  const parsed = Number(years)
  if (Number.isNaN(parsed)) return null
  if (parsed === 0) return 'No experience required'
  return `${parsed}+ year${parsed === 1 ? '' : 's'} experience`
}

export function formatLevel(level) {
  if (!level || level === 'unknown') return null
  return level.charAt(0).toUpperCase() + level.slice(1)
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * Formats a "YYYY-MM-DD" date string as "14 Aug 2026".
 *
 * Deliberately not Date/Intl-based -- toLocaleDateString() has the exact
 * same runtime-locale problem toLocaleString() had for salary, and the
 * Date constructor has its own timezone traps parsing a bare date string.
 * Plain string slicing is the only way to guarantee the same output on
 * every machine.
 */
export function formatDate(dateStr) {
  if (!dateStr) return null
  const match = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return null
  const [, year, month, day] = match
  const monthName = MONTHS[Number(month) - 1]
  if (!monthName) return null
  return `${Number(day)} ${monthName} ${year}`
}

/**
 * The date to show on a job card: the ad's own posting date when it
 * states one, falling back to the date the board first added the job --
 * only a date, never a time, since the pipeline runs once a day and every
 * job from the same run would show an identical, meaningless time.
 */
export function formatJobDate(job) {
  const posted = formatDate(job.date_posted)
  if (posted) return `Posted ${posted}`
  const added = formatDate(job.date_added)
  if (added) return `Added ${added}`
  return null
}