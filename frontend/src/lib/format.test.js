import { describe, expect, it } from 'vitest'
import { formatLevel, formatSalary, formatYears } from './format.js'

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