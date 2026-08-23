/**
 * Unit tests for matching jobs to what a student selected.
 *
 * The rule these are all really testing: the ad's own number beats the ad's
 * own adjective. A company can type "Junior" into a title for free.
 */

import { describe, expect, it } from 'vitest'
import {
  ENTRY,
  EVIDENCE,
  JUNIOR,
  YEARS_CEILING,
  canSearch,
  ceilingFor,
  highlightTerms,
  matchJobs,
  matchesLevel,
  matchesTrack,
  skillOverlap,
  splitOnTerms,
} from './match.js'

function job(overrides = {}) {
  return {
    title: 'Software Developer',
    role_type: 'Software development',
    must_have_skills: 'JavaScript, React',
    ...overrides,
  }
}

describe('matchesLevel', () => {
  it('takes the ad at its number when it states one', () => {
    const result = matchesLevel(job({ experience_years: 2 }), [JUNIOR])
    expect(result.matches).toBe(true)
    expect(result.evidence).toBe(EVIDENCE.YEARS)
    expect(result.years).toBe(2)
  })

  it('rules out an ad asking more years than the level allows', () => {
    expect(matchesLevel(job({ experience_years: 3 }), [ENTRY]).matches).toBe(false)
    expect(matchesLevel(job({ experience_years: 5 }), [JUNIOR]).matches).toBe(false)
  })

  it('lets the number override the title, which is the whole point', () => {
    // The company called it junior. The ad then asks for five years.
    const titledJunior = job({
      title: 'Junior Developer',
      job_level: JUNIOR,
      level_source: 'title',
      experience_years: 5,
    })
    expect(matchesLevel(titledJunior, [JUNIOR]).matches).toBe(false)
  })

  it('keeps an ad that states no years, and says so', () => {
    const result = matchesLevel(job(), [ENTRY])
    expect(result.matches).toBe(true)
    expect(result.evidence).toBe(EVIDENCE.UNSTATED)
  })

  it('marks an ad whose only signal is the word in its own title', () => {
    const result = matchesLevel(
      job({ job_level: JUNIOR, level_source: 'title' }),
      [JUNIOR],
    )
    expect(result.matches).toBe(true)
    expect(result.evidence).toBe(EVIDENCE.TITLE_ONLY)
  })

  it('applies no cap at all when no level was selected', () => {
    expect(matchesLevel(job({ experience_years: 9 }), []).matches).toBe(true)
  })

  it('takes the more generous ceiling when both levels are selected', () => {
    expect(ceilingFor([ENTRY, JUNIOR])).toBe(YEARS_CEILING[JUNIOR])
    expect(matchesLevel(job({ experience_years: 3 }), [ENTRY, JUNIOR]).matches).toBe(true)
  })
})

describe('matchesTrack', () => {
  it('filters on the track the student chose', () => {
    expect(matchesTrack(job(), ['Software development'])).toBe(true)
    expect(matchesTrack(job(), ['QA/Testing'])).toBe(false)
  })

  it('passes everything when no track was chosen', () => {
    expect(matchesTrack(job(), [])).toBe(true)
  })
})

describe('skillOverlap', () => {
  it('returns the skills the student has that the job asks for', () => {
    expect(skillOverlap(job(), ['React', 'Python', 'JavaScript']))
      .toEqual(['React', 'JavaScript'])
  })

  it('counts nice-to-haves as well as must-haves', () => {
    const withNice = job({ must_have_skills: 'React', nice_to_have_skills: 'Docker' })
    expect(skillOverlap(withNice, ['Docker'])).toEqual(['Docker'])
  })

  it('is empty when nothing was picked', () => {
    expect(skillOverlap(job(), [])).toEqual([])
  })
})

describe('matchJobs', () => {
  const jobs = [
    job({ title: 'No skills in common', must_have_skills: 'COBOL', experience_years: 1 }),
    job({ title: 'Two in common', must_have_skills: 'React, JavaScript', experience_years: 1 }),
    job({ title: 'One in common', must_have_skills: 'React, Go', experience_years: 1 }),
  ]

  it('ranks by how many of the student\'s skills the job asks for', () => {
    const results = matchJobs(jobs, {
      roleTypes: [], levels: [JUNIOR], skills: ['React', 'JavaScript'],
    })
    expect(results.map((r) => r.job.title)).toEqual([
      'Two in common', 'One in common', 'No skills in common',
    ])
  })

  it('never removes a job for lacking a skill -- it only reorders', () => {
    const results = matchJobs(jobs, {
      roleTypes: [], levels: [JUNIOR], skills: ['Kubernetes'],
    })
    expect(results).toHaveLength(3)
    expect(results.every((r) => r.overlap.length === 0)).toBe(true)
  })

  it('puts ads that state their requirements above ads that do not', () => {
    const results = matchJobs(
      [
        job({ title: 'Says nothing' }),
        job({ title: 'Says two years', experience_years: 2 }),
      ],
      { roleTypes: [], levels: [JUNIOR], skills: [] },
    )
    expect(results.map((r) => r.job.title)).toEqual(['Says two years', 'Says nothing'])
  })

  it('drops jobs off the chosen track', () => {
    const results = matchJobs(
      [job(), job({ title: 'A QA job', role_type: 'QA/Testing' })],
      { roleTypes: ['Software development'], levels: [], skills: [] },
    )
    expect(results).toHaveLength(1)
  })

  it('reports the overlap so the card can show what matched', () => {
    const [top] = matchJobs(jobs, {
      roleTypes: [], levels: [JUNIOR], skills: ['React', 'JavaScript'],
    })
    expect(top.overlap).toEqual(['React', 'JavaScript'])
  })

  it('is safe on an empty board', () => {
    expect(matchJobs([], { roleTypes: [], levels: [], skills: [] })).toEqual([])
  })
})

describe('canSearch', () => {
  it('needs a track or a level', () => {
    expect(canSearch({ roleTypes: ['Software development'], levels: [], skills: [] })).toBe(true)
    expect(canSearch({ roleTypes: [], levels: [JUNIOR], skills: [] })).toBe(true)
  })

  it('is not satisfied by skills alone', () => {
    // Skills only would mean the whole board, sorted -- which is the
    // everything-at-once screen this flow replaces.
    expect(canSearch({ roleTypes: [], levels: [], skills: ['React'] })).toBe(false)
  })

  it('is not satisfied by nothing', () => {
    expect(canSearch({ roleTypes: [], levels: [], skills: [] })).toBe(false)
  })
})

describe('highlightTerms', () => {
  it('unpacks the aliases the canonical names already carry', () => {
    expect(highlightTerms(['SQL (MySQL/Postgres)']))
      .toEqual(expect.arrayContaining(['SQL', 'MySQL', 'Postgres']))
  })

  it('keeps a bracketed acronym but drops a bracketed word', () => {
    expect(highlightTerms(['Google Cloud (GCP)'])).toContain('GCP')
    expect(highlightTerms(['Excel (Advanced)'])).not.toContain('Advanced')
    expect(highlightTerms(['Excel (Advanced)'])).toContain('Excel')
  })

  it('leaves two-letter halves alone so CI/CD and UI/UX stay whole', () => {
    const terms = highlightTerms(['CI/CD', 'UI/UX'])
    expect(terms).toEqual(expect.arrayContaining(['CI/CD', 'UI/UX']))
    expect(terms).not.toContain('CI')
    expect(terms).not.toContain('UX')
  })

  it('keeps short names that carry punctuation', () => {
    expect(highlightTerms(['C#/.NET'])).toEqual(expect.arrayContaining(['C#', '.NET']))
    expect(highlightTerms(['C++'])).toContain('C++')
  })

  it('never highlights Go', () => {
    // The pipeline's own skills list refuses to match it bare for the same
    // reason: "go the extra mile" would light up half the adverts, and a
    // page speckled with yellow teaches a student to ignore the yellow.
    expect(highlightTerms(['Go'])).toEqual([])
  })

  it('puts the longest term first, so MySQL wins over SQL', () => {
    const terms = highlightTerms(['SQL (MySQL/Postgres)'])
    expect(terms.indexOf('MySQL')).toBeLessThan(terms.indexOf('SQL'))
  })
})

describe('splitOnTerms', () => {
  const terms = highlightTerms(['SQL (MySQL/Postgres)', 'Java', 'C#/.NET', 'React'])

  const render = (text) =>
    splitOnTerms(text, terms).map((r) => (r.hit ? `[${r.text}]` : r.text)).join('')

  it('marks the skills and leaves the rest alone', () => {
    expect(render('We use Java and React here.')).toBe('We use [Java] and [React] here.')
  })

  it('does not light up a word that merely contains one', () => {
    expect(render('Java, not JavaScript')).toBe('[Java], not JavaScript')
    expect(render('MySQLdb is not SQLite')).toBe('MySQLdb is not SQLite')
  })

  it('matches names that start or end in punctuation', () => {
    expect(render('C# on .NET')).toBe('[C#] on [.NET]')
  })

  it('is case-insensitive, and keeps the advert\'s own casing', () => {
    expect(render('we use JAVA')).toBe('we use [JAVA]')
  })

  it('loses no text at all', () => {
    const text = 'Java and React and nothing else in particular.'
    expect(splitOnTerms(text, terms).map((r) => r.text).join('')).toBe(text)
  })

  it('returns the text untouched when nothing was picked', () => {
    expect(splitOnTerms('Some advert text', [])).toEqual([
      { text: 'Some advert text', hit: false },
    ])
  })

  it('is safe on nothing at all', () => {
    expect(splitOnTerms('', terms)).toEqual([])
    expect(splitOnTerms(null, terms)).toEqual([])
  })
})
