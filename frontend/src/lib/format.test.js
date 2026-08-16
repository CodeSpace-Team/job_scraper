import { describe, expect, it } from 'vitest'
import { formatDate, formatJobDate, formatLevel, formatSalary, formatYears } from './format.js'

describe('formatSalary', () => {
  it('formats a full range', () => {
    expect(formatSalary({ salary_min: 50000, salary_max: 80000, salary_currency: 'ZAR' }))
      .toBe('ZAR 50,000 - 80,000')
  })

  it('formats a minimum only', () => {
    expect(formatSalary({ salary_min: 50000, salary_currency: 'ZAR' })).toBe('ZAR 50,000+')
  })

  it('formats a maximum only', () => {
    expect(formatSalary({ salary_max: 80000, salary_currency: 'ZAR' })).toBe('Up to ZAR 80,000')
  })

  it('includes the period when the ad states one', () => {
    expect(formatSalary({ salary_min: 50000, salary_currency: 'ZAR', salary_period: 'month' }))
      .toBe('ZAR 50,000+/month')
  })

  it('returns null when neither figure is present', () => {
    expect(formatSalary({})).toBeNull()
    expect(formatSalary({ salary_min: null, salary_max: null })).toBeNull()
  })
})

describe('formatYears', () => {
  it('formats zero as "no experience required"', () => {
    expect(formatYears(0)).toBe('No experience required')
  })

  it('pluralises correctly', () => {
    expect(formatYears(1)).toBe('1+ year experience')
    expect(formatYears(3)).toBe('3+ years experience')
  })

  it('returns null when the ad states no number at all', () => {
    expect(formatYears(null)).toBeNull()
    expect(formatYears(undefined)).toBeNull()
    expect(formatYears('')).toBeNull()
  })
})

describe('formatLevel', () => {
  it('capitalises the level', () => {
    expect(formatLevel('entry')).toBe('Entry')
    expect(formatLevel('senior')).toBe('Senior')
  })

  it('returns null for unknown or unset', () => {
    expect(formatLevel('unknown')).toBeNull()
    expect(formatLevel('')).toBeNull()
    expect(formatLevel(null)).toBeNull()
  })
})

describe('formatDate', () => {
  it('formats a plain date string', () => {
    expect(formatDate('2026-08-14')).toBe('14 Aug 2026')
  })

  it('does not pad the day with a leading zero', () => {
    expect(formatDate('2026-08-05')).toBe('5 Aug 2026')
  })

  it('reads only the date prefix, ignoring any time component', () => {
    expect(formatDate('2026-08-14T10:30:00')).toBe('14 Aug 2026')
  })

  it('returns null for missing or malformed input', () => {
    expect(formatDate(null)).toBeNull()
    expect(formatDate('')).toBeNull()
    expect(formatDate('not-a-date')).toBeNull()
  })
})

describe('formatJobDate', () => {
  it('prefers the ad\'s own posting date, labelled "Posted"', () => {
    expect(formatJobDate({ date_posted: '2026-08-14', date_added: '2026-08-16' }))
      .toBe('Posted 14 Aug 2026')
  })

  it('falls back to the board\'s own add date, labelled "Added", when the ad states no posting date', () => {
    expect(formatJobDate({ date_posted: null, date_added: '2026-08-16' })).toBe('Added 16 Aug 2026')
  })

  it('returns null when neither date is present', () => {
    expect(formatJobDate({})).toBeNull()
  })
})