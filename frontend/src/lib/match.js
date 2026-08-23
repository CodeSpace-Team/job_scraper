/**
 * match.js — matching jobs to what a student actually selected
 * =============================================================
 *
 * Why this exists rather than another filter
 * ------------------------------------------
 * The board used to open with every job on it, sorted by date, and leave the
 * student to work out which ones were for them. The labels it sorted by are
 * not trustworthy enough for that. Measured on a real 66-job board:
 *
 *     29 of 66   no level evidence at all
 *     27 of 66   level worked out from a years figure in the ad
 *     10 of 66   level taken from the company's own word in the title
 *
 * Forty-four percent of the board carries no evidence of its own level, and
 * an employer typing "Junior" into a title is not evidence -- plenty of ads
 * say junior and then describe a job nobody two years in could do.
 *
 * So this module does not ask "is this job junior". It asks "does this job
 * match what this person told us about themselves", and it says out loud
 * what each match rests on.
 *
 * The rules
 * ---------
 * **Track is a filter.** A student who came for software development should
 * not be shown a QA post; that is a choice they made, not a guess we made.
 *
 * **Level is matched on the ad's own number, not its adjective.** An ad
 * asking three years does not match somebody at entry level, whatever its
 * title says. An ad that states no number cannot be ruled out on level, so
 * it stays in -- labelled as unstated, so the student knows to read it.
 *
 * **Skills rank, they never filter.** A seven-day board holds a few dozen
 * jobs. If ticking React and Docker removed everything else, a student would
 * see two results or none, and a student who sees "no matches" concludes
 * there are no jobs. Every job that passes track and level is shown; the
 * ones sharing the most skills come first.
 */

import { jobSkills } from './filters.js'

export const ENTRY = 'entry level'
export const JUNIOR = 'junior'

export const EMPTY_CRITERIA = {
  roleTypes: [],
  levels: [],
  skills: [],
}

/**
 * The most years an ad can ask for and still suit somebody at this level.
 *
 * Read off what the ad states, not what it calls itself. Entry level means
 * no real experience yet, so one year is the outside edge; junior covers the
 * first three, which is the cohort the whole tool is built for.
 */
export const YEARS_CEILING = {
  [ENTRY]: 1,
  [JUNIOR]: 3,
}

/** Why a job came back. Shown on the card, so a match is never a black box. */
export const EVIDENCE = {
  YEARS: 'years',
  TITLE_ONLY: 'title-only',
  UNSTATED: 'unstated',
}

function statedYears(job) {
  const years = job.experience_years
  if (years === null || years === undefined || years === '') return null
  const parsed = Number(years)
  return Number.isNaN(parsed) ? null : parsed
}

/**
 * The highest years figure the selected levels allow.
 *
 * @returns {number|null} null when no level was selected, meaning no cap.
 */
export function ceilingFor(levels) {
  if (!levels || levels.length === 0) return null
  const ceilings = levels
    .map((level) => YEARS_CEILING[level])
    .filter((n) => typeof n === 'number')
  return ceilings.length ? Math.max(...ceilings) : null
}

/**
 * Decide whether a job suits the levels selected, and on what evidence.
 *
 * @returns {{matches: boolean, evidence: string, years: number|null}}
 */
export function matchesLevel(job, levels) {
  const years = statedYears(job)
  const ceiling = ceilingFor(levels)

  // What the match rests on does not depend on what the student selected --
  // an ad either states its requirement or it does not. Working the evidence
  // out first keeps the card honest whether or not a level was picked.
  let evidence = EVIDENCE.UNSTATED
  if (years !== null) {
    evidence = EVIDENCE.YEARS
  } else if (job.level_source === 'title') {
    evidence = EVIDENCE.TITLE_ONLY
  }

  // No level selected means no cap to apply.
  if (ceiling === null) {
    return { matches: true, evidence, years }
  }

  if (years !== null) {
    // The ad's own number decides, and it beats the ad's own adjective. A
    // "Junior Developer" asking five years does not match a junior search.
    return { matches: years <= ceiling, evidence, years }
  }

  // Nothing stated. Silence is not evidence that a job is out of reach, so
  // it stays in -- flagged, because the student has to read it to find out.
  return { matches: true, evidence, years: null }
}

/** Track is the student's own choice, so it filters outright. */
export function matchesTrack(job, roleTypes) {
  if (!roleTypes || roleTypes.length === 0) return true
  return roleTypes.includes(job.role_type || '')
}

/**
 * Which of the student's skills this job asks for.
 *
 * @returns {string[]} the overlap, in the order the student picked them.
 */
export function skillOverlap(job, skills) {
  if (!skills || skills.length === 0) return []
  const asked = new Set(jobSkills(job))
  return skills.filter((skill) => asked.has(skill))
}

/**
 * Match a day's jobs against what a student selected.
 *
 * Ordered by how many of their skills the job asks for, then by ads that
 * state their requirements over ads that do not -- a job that says what it
 * wants is worth more of somebody's afternoon than one that does not -- and
 * then by date.
 *
 * @returns {{job: object, overlap: string[], evidence: string, years: number|null}[]}
 */
export function matchJobs(jobs, criteria = EMPTY_CRITERIA) {
  const results = []

  for (const job of jobs) {
    if (!matchesTrack(job, criteria.roleTypes)) continue

    const level = matchesLevel(job, criteria.levels)
    if (!level.matches) continue

    results.push({
      job,
      overlap: skillOverlap(job, criteria.skills),
      evidence: level.evidence,
      years: level.years,
    })
  }

  const evidenceRank = {
    [EVIDENCE.YEARS]: 0,
    [EVIDENCE.TITLE_ONLY]: 1,
    [EVIDENCE.UNSTATED]: 2,
  }

  return results.sort((a, b) => {
    if (b.overlap.length !== a.overlap.length) return b.overlap.length - a.overlap.length
    const rank = evidenceRank[a.evidence] - evidenceRank[b.evidence]
    if (rank !== 0) return rank
    const dateOf = (r) => String(r.job.date_posted || r.job.date_added || '')
    return dateOf(b).localeCompare(dateOf(a))
  })
}

// ─── Finding those skills inside the advert ────────────────────────────────

const NEVER_ALONE = new Set(['Go', 'R', 'C'])
/**
 * Skill names too common as ordinary words to highlight on their own.
 *
 * The pipeline's own skills list refuses to match "Go" bare for the same
 * reason -- "go the extra mile", "go-getters who close deals" -- and a
 * highlight is worse than a missed match here, because a page speckled with
 * yellow on every "go" teaches a student to ignore the yellow.
 */

const PUNCTUATED = /[^A-Za-z0-9]/
const ACRONYM = /^[A-Z0-9]{2,}$/

/**
 * Turn canonical skill names into the words to look for in an advert.
 *
 * The names are canonical, and adverts are not: a job that wants Postgres
 * says "Postgres", not "SQL (MySQL/Postgres)". The names bundle their own
 * aliases with slashes, ampersands and brackets, so most of what is needed
 * is already in them.
 *
 *     SQL (MySQL/Postgres)  ->  SQL (MySQL/Postgres), SQL, MySQL, Postgres
 *     C#/.NET               ->  C#/.NET, C#, .NET
 *     Excel (Advanced)      ->  Excel (Advanced), Excel
 *     CI/CD                 ->  CI/CD
 *
 * Two things get dropped. A bracketed part that reads as an ordinary word
 * ("Advanced") rather than a name ("GCP"), and any part of two letters or
 * fewer that is all letters -- which is why CI/CD and UI/UX stay whole
 * instead of lighting up every "CI" and "UX" in the page.
 *
 * @returns {string[]} longest first, so "MySQL" wins over "SQL".
 */
export function highlightTerms(skills) {
  const terms = new Set()

  for (const skill of skills || []) {
    const name = String(skill).trim()
    if (!name) continue
    if (NEVER_ALONE.has(name)) continue

    terms.add(name)

    const bracketed = name.match(/\(([^)]+)\)/)
    const withoutBrackets = name.replace(/\s*\([^)]*\)/g, '').trim()

    const parts = withoutBrackets.split(/[/&]/)
    if (bracketed) {
      const inside = bracketed[1]
      // "GCP" is worth finding; "Advanced" is a word that happens to be
      // in brackets and would light up half the adverts on the board.
      if (ACRONYM.test(inside) || inside.includes('/')) {
        parts.push(...inside.split('/'))
      }
    }

    for (const raw of parts) {
      const part = raw.trim()
      if (!part) continue
      if (part.length <= 2 && !PUNCTUATED.test(part)) continue
      if (NEVER_ALONE.has(part)) continue
      terms.add(part)
    }
  }

  return [...terms].sort((a, b) => b.length - a.length)
}

function escapeForRegex(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Split text into runs, marking the ones that name a skill.
 *
 * Boundaries are checked against letters and digits rather than with \b,
 * because \b does nothing useful at the edges of "C++", "C#" or ".NET".
 * Matching "SQL" must not light up the middle of "MySQL", and this is what
 * stops it.
 *
 * @returns {{text: string, hit: boolean}[]}
 */
export function splitOnTerms(text, terms) {
  const source = String(text || '')
  if (!source || !terms || terms.length === 0) {
    return source ? [{ text: source, hit: false }] : []
  }

  const pattern = new RegExp(
    `(?<![A-Za-z0-9])(${terms.map(escapeForRegex).join('|')})(?![A-Za-z0-9])`,
    'gi',
  )

  const runs = []
  let cursor = 0
  let match

  while ((match = pattern.exec(source)) !== null) {
    if (match.index > cursor) {
      runs.push({ text: source.slice(cursor, match.index), hit: false })
    }
    runs.push({ text: match[0], hit: true })
    cursor = match.index + match[0].length
  }

  if (cursor < source.length) {
    runs.push({ text: source.slice(cursor), hit: false })
  }

  return runs
}


/**
 * True once a student has told us enough to search on.
 *
 * A track or a level is enough. Skills alone are not: without one of those
 * two, the "match" is the whole board sorted by skills, which is the
 * everything-at-once screen this flow exists to replace.
 */
export function canSearch(criteria) {
  return Boolean(
    (criteria.roleTypes && criteria.roleTypes.length > 0) ||
    (criteria.levels && criteria.levels.length > 0),
  )
}
