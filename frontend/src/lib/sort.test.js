import { describe, expect, it } from 'vitest'
import { sortJobs } from './sort.js'

function makeJob(overrides = {}) {
  return { title: 'Job', company: 'Co', ...overrides }
}

describe('sortJobs', () => {
  it('sorts newest first by default', () => {
    const jobs = [
      makeJob({ title: 'Older', date_posted: '2026-08-01' }),
      makeJob({ title: 'Newer', date_posted: '2026-08-14' }),
    ]
    expect(sortJobs(jobs).map((j) => j.title)).toEqual(['Newer', 'Older'])
  })

  it('sorts oldest first when asked', () => {
    const jobs = [
      makeJob({ title: 'Newer', date_posted: '2026-08-14' }),
      makeJob({ title: 'Older', date_posted: '2026-08-01' }),
    ]
    expect(sortJobs(jobs, 'oldest').map((j) => j.title)).toEqual(['Older', 'Newer'])
  })

  it('falls back to date_added when a job states no posting date', () => {
    const jobs = [
      makeJob({ title: 'StatesDate', date_posted: '2026-08-01' }),
      makeJob({ title: 'NoPostingDate', date_added: '2026-08-14' }),
    ]
    expect(sortJobs(jobs, 'newest').map((j) => j.title)).toEqual(['NoPostingDate', 'StatesDate'])
  })

  it('sorts by fewest years required first', () => {
    const jobs = [
      makeJob({ title: 'Five', experience_years: 5 }),
      makeJob({ title: 'Zero', experience_years: 0 }),
      makeJob({ title: 'Two', experience_years: 2 }),
    ]
    expect(sortJobs(jobs, 'years-asc').map((j) => j.title)).toEqual(['Zero', 'Two', 'Five'])
  })

  it('sorts jobs with no stated years after every job with a real number', () => {
    const jobs = [
      makeJob({ title: 'Unknown', experience_years: null }),
      makeJob({ title: 'Three', experience_years: 3 }),
    ]
    expect(sortJobs(jobs, 'years-asc').map((j) => j.title)).toEqual(['Three', 'Unknown'])
  })

  it('does not mutate the input array', () => {
    const jobs = [makeJob({ title: 'A', date_posted: '2026-08-01' }), makeJob({ title: 'B', date_posted: '2026-08-14' })]
    const original = [...jobs]
    sortJobs(jobs, 'oldest')
    expect(jobs).toEqual(original)
  })

  it('is safe on an empty list', () => {
    expect(sortJobs([], 'newest')).toEqual([])
  })
})