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