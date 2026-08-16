/**
 * Tests for the board's search and filter rules (F6).
 *
 * The things that matter most:
 *   1. An empty selection in any category means that category is
 *      inactive -- everything passes it. A filter panel that starts
 *      with nothing checked should show every job, not none.
 *   2. A job that says nothing about years, or has no level, is never
 *      excluded on the strength of that silence -- the same "don't
 *      guess it away" rule the backend's own screening follows.
 *   3. Skills are read out of the same comma-separated string shape the
 *      backend actually writes, not an array.
 */

import { describe, expect, it } from 'vitest'
import {
  EMPTY_FILTERS,
  extractFacets,
  filterJobs,
  hasActiveFilters,
  jobSkills,
  matchesMaxYears,
  matchesSearch,
  matchesSkills,
  splitSkills,
} from './filters.js'

function makeJob(overrides = {}) {
  return {
    title: 'Junior Developer',
    company: 'Acme',
    role_type: 'Software Development',
    job_level: 'entry',
    workplace_policy: 'remote',
    source: 'indeed',
    employment_type: 'fulltime',
    must_have_skills: 'JavaScript, React',
    nice_to_have_skills: 'Node.js',
    experience_years: 0,
    ...overrides,
  }
}

// ─── splitSkills / jobSkills ────────────────────────────────────────────

describe('splitSkills', () => {
  it('splits a comma-separated string and trims whitespace', () => {
    expect(splitSkills('JavaScript, React,  Node.js')).toEqual(['JavaScript', 'React', 'Node.js'])
  })

  it('is safe on empty, null and undefined', () => {
    expect(splitSkills('')).toEqual([])
    expect(splitSkills(null)).toEqual([])
    expect(splitSkills(undefined)).toEqual([])
  })
})

describe('jobSkills', () => {
  it('combines must-have and nice-to-have skills', () => {
    const job = makeJob({ must_have_skills: 'Python', nice_to_have_skills: 'Django' })
    expect(jobSkills(job)).toEqual(['Python', 'Django'])
  })
})

// ─── matchesSearch ──────────────────────────────────────────────────────

describe('matchesSearch', () => {
  it('matches on title, company, blurb or description, case-insensitively', () => {
    const job = makeJob({ title: 'React Developer', blurb: 'Build things with React.' })
    expect(matchesSearch(job, 'react')).toBe(true)
    expect(matchesSearch(job, 'REACT')).toBe(true)
  })

  it('an empty or whitespace-only query matches everything', () => {
    const job = makeJob()
    expect(matchesSearch(job, '')).toBe(true)
    expect(matchesSearch(job, '   ')).toBe(true)
    expect(matchesSearch(job, undefined)).toBe(true)
  })

  it('does not match unrelated text', () => {
    const job = makeJob({ title: 'React Developer', company: 'Acme' })
    expect(matchesSearch(job, 'mining engineer')).toBe(false)
  })
})

// ─── matchesSkills ──────────────────────────────────────────────────────

describe('matchesSkills', () => {
  it('no skills selected matches everything', () => {
    expect(matchesSkills(makeJob(), [])).toBe(true)
  })

  it('matches a job with at least one of the selected skills (OR within the category)', () => {
    const job = makeJob({ must_have_skills: 'Python, Django' })
    expect(matchesSkills(job, ['Django', 'Rust'])).toBe(true)
  })

  it('does not match a job with none of the selected skills', () => {
    const job = makeJob({ must_have_skills: 'Python, Django' })
    expect(matchesSkills(job, ['Rust', 'Go'])).toBe(false)
  })
})

// ─── matchesMaxYears ────────────────────────────────────────────────────

describe('matchesMaxYears', () => {
  it('no cap set matches everything', () => {
    expect(matchesMaxYears(makeJob({ experience_years: 5 }), '')).toBe(true)
    expect(matchesMaxYears(makeJob({ experience_years: 5 }), null)).toBe(true)
  })

  it('a job within the cap matches', () => {
    expect(matchesMaxYears(makeJob({ experience_years: 2 }), 3)).toBe(true)
  })

  it('a job over the cap does not match', () => {
    expect(matchesMaxYears(makeJob({ experience_years: 5 }), 3)).toBe(false)
  })

  it('the boundary is exact', () => {
    expect(matchesMaxYears(makeJob({ experience_years: 3 }), 3)).toBe(true)
  })

  it('a job stating no years at all is never excluded by the cap', () => {
    expect(matchesMaxYears(makeJob({ experience_years: null }), 0)).toBe(true)
    expect(matchesMaxYears(makeJob({ experience_years: undefined }), 0)).toBe(true)
    expect(matchesMaxYears(makeJob({ experience_years: '' }), 0)).toBe(true)
  })
})

// ─── filterJobs: categories combine with AND ───────────────────────────

describe('filterJobs', () => {
  it('the default (empty) filters return every job', () => {
    const jobs = [makeJob({ title: 'A' }), makeJob({ title: 'B' })]
    expect(filterJobs(jobs, EMPTY_FILTERS)).toHaveLength(2)
  })

  it('is safe on an empty job list', () => {
    expect(filterJobs([], EMPTY_FILTERS)).toEqual([])
  })

  it('combines role type and level with AND', () => {
    const jobs = [
      makeJob({ title: 'Match', role_type: 'Software Development', job_level: 'entry' }),
      makeJob({ title: 'Right role, wrong level', role_type: 'Software Development', job_level: 'senior' }),
      makeJob({ title: 'Right level, wrong role', role_type: 'Technical Support', job_level: 'entry' }),
    ]
    const result = filterJobs(jobs, {
      ...EMPTY_FILTERS,
      roleTypes: ['Software Development'],
      levels: ['entry'],
    })
    expect(result.map((j) => j.title)).toEqual(['Match'])
  })

  it('a job with an unset level is filtered under "unknown"', () => {
    const jobs = [makeJob({ job_level: '' })]
    expect(filterJobs(jobs, { ...EMPTY_FILTERS, levels: ['unknown'] })).toHaveLength(1)
    expect(filterJobs(jobs, { ...EMPTY_FILTERS, levels: ['entry'] })).toHaveLength(0)
  })
})

// ─── hasActiveFilters ───────────────────────────────────────────────────

describe('hasActiveFilters', () => {
  it('is false for the empty filters', () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false)
  })

  it('is true when search text is set', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, search: 'react' })).toBe(true)
  })

  it('is true when any checkbox category has a selection', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, roleTypes: ['Software Development'] })).toBe(true)
    expect(hasActiveFilters({ ...EMPTY_FILTERS, skills: ['Python'] })).toBe(true)
  })

  it('is true when a max-years cap is set', () => {
    expect(hasActiveFilters({ ...EMPTY_FILTERS, maxYears: '3' })).toBe(true)
  })
})

// ─── extractFacets ──────────────────────────────────────────────────────

describe('extractFacets', () => {
  it('collects the distinct values actually present on the board', () => {
    const jobs = [
      makeJob({ role_type: 'Software Development' }),
      makeJob({ role_type: 'Technical Support' }),
      makeJob({ role_type: 'Software Development' }),
    ]
    expect(extractFacets(jobs).roleTypes).toEqual(['Software Development', 'Technical Support'])
  })

  it('ranks skills by how often they appear, most common first', () => {
    const jobs = [
      makeJob({ must_have_skills: 'Python', nice_to_have_skills: '' }),
      makeJob({ must_have_skills: 'Python, React', nice_to_have_skills: '' }),
      makeJob({ must_have_skills: 'React', nice_to_have_skills: '' }),
    ]
    const { skills } = extractFacets(jobs)
    expect(skills.indexOf('Python')).toBeLessThan(skills.indexOf('React'))
  })

  it('is safe on an empty job list', () => {
    const facets = extractFacets([])
    expect(facets.roleTypes).toEqual([])
    expect(facets.skills).toEqual([])
  })

  it('missing fields do not appear as a blank option', () => {
    const jobs = [makeJob({ workplace_policy: '' }), makeJob({ workplace_policy: undefined })]
    expect(extractFacets(jobs).workPolicies).toEqual([])
  })
})