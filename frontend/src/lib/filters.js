/**
 * filters.js — the board's search and filter rules (F6)
 * =======================================================
 *
 * Kept as plain functions, independent of any component, so the actual
 * matching rules can be tested directly rather than through rendered
 * markup -- the same reasoning the backend's own pipeline modules follow.
 *
 * Rule for combining filters: no selection in a category means that
 * category is inactive (everything passes it). Selecting several values
 * within one category is OR ("React or Python"); different categories
 * combine with AND ("Software track AND entry level AND React or Python").
 */

export const EMPTY_FILTERS = {
  search: '',
  roleTypes: [],
  levels: [],
  skills: [],
  workPolicies: [],
  sources: [],
  employmentTypes: [],
  maxYears: '',
}

export function splitSkills(value) {
  if (!value) return []
  return String(value)
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export function jobSkills(job) {
  return [...splitSkills(job.must_have_skills), ...splitSkills(job.nice_to_have_skills)]
}

function includesCI(haystack, needle) {
  return String(haystack || '').toLowerCase().includes(needle)
}

export function matchesSearch(job, query) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  return (
    includesCI(job.title, q) ||
    includesCI(job.company, q) ||
    includesCI(job.blurb, q) ||
    includesCI(job.description_snippet, q)
  )
}

function matchesAnySelected(value, selected) {
  if (!selected || selected.length === 0) return true
  return selected.includes(value)
}

export function matchesRoleType(job, selectedRoleTypes) {
  return matchesAnySelected(job.role_type || '', selectedRoleTypes)
}

export function matchesLevel(job, selectedLevels) {
  return matchesAnySelected(job.job_level || 'unknown', selectedLevels)
}

export function matchesWorkPolicy(job, selectedPolicies) {
  return matchesAnySelected(job.workplace_policy || '', selectedPolicies)
}

export function matchesSource(job, selectedSources) {
  return matchesAnySelected(job.source || '', selectedSources)
}

export function matchesEmploymentType(job, selectedTypes) {
  return matchesAnySelected(job.employment_type || '', selectedTypes)
}

export function matchesSkills(job, selectedSkills) {
  if (!selectedSkills || selectedSkills.length === 0) return true
  const skills = jobSkills(job)
  return selectedSkills.some((skill) => skills.includes(skill))
}

export function matchesMaxYears(job, maxYears) {
  // No cap set, or the job itself states no number, both pass -- a job
  // that says nothing about years asked for is not evidence it is out of
  // reach, the same rule the backend's own screening (F4) follows.
  if (maxYears === null || maxYears === undefined || maxYears === '') return true
  const years = job.experience_years
  if (years === null || years === undefined || years === '') return true
  const parsed = Number(years)
  if (Number.isNaN(parsed)) return true
  return parsed <= Number(maxYears)
}

export function filterJobs(jobs, filters = EMPTY_FILTERS) {
  return jobs.filter(
    (job) =>
      matchesSearch(job, filters.search) &&
      matchesRoleType(job, filters.roleTypes) &&
      matchesLevel(job, filters.levels) &&
      matchesSkills(job, filters.skills) &&
      matchesWorkPolicy(job, filters.workPolicies) &&
      matchesSource(job, filters.sources) &&
      matchesEmploymentType(job, filters.employmentTypes) &&
      matchesMaxYears(job, filters.maxYears),
  )
}

// ─── Facets: what to actually offer as filter options ──────────────────────

function uniqueSorted(values) {
  return Array.from(new Set(values.filter(Boolean))).sort()
}

/**
 * Work out what filter options are actually worth offering, from the real
 * jobs on the board -- rather than a hand-maintained list that drifts from
 * what is actually there. Skills are ranked by how often they appear, so
 * the most useful ones surface first instead of an alphabetical wall.
 */
export function extractFacets(jobs) {
  const roleTypes = uniqueSorted(jobs.map((j) => j.role_type))
  const levels = uniqueSorted(jobs.map((j) => j.job_level || 'unknown'))
  const workPolicies = uniqueSorted(jobs.map((j) => j.workplace_policy))
  const sources = uniqueSorted(jobs.map((j) => j.source))
  const employmentTypes = uniqueSorted(jobs.map((j) => j.employment_type))

  const skillCounts = new Map()
  for (const job of jobs) {
    for (const skill of jobSkills(job)) {
      skillCounts.set(skill, (skillCounts.get(skill) || 0) + 1)
    }
  }
  const skills = Array.from(skillCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([name]) => name)

  return { roleTypes, levels, workPolicies, sources, employmentTypes, skills }
}