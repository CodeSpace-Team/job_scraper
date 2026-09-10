/**
 * Unit tests for the taught-skills list and the ordering it drives.
 *
 * The bug this exists to prevent is a quiet one. Both halves of the project
 * name skills as free text -- the pipeline writes canonical names into
 * jobs.json, the picker matches on those names -- so a rename on either side
 * does not throw. It just stops matching, and the skill drops out of the top
 * of the picker with nothing to show it ever went missing.
 */

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { GRADUATE_SKILLS, orderForGraduates } from './graduate.js'

function canonicalSkillNames() {
  // Relative to the working directory rather than import.meta.url: under
  // jsdom that URL is an http: one, and fileURLToPath refuses it.
  const path = resolve(process.cwd(), '../backend/skills.json')
  const { skills } = JSON.parse(readFileSync(path, 'utf8'))
  return new Set(skills.map((s) => s.name))
}

describe('GRADUATE_SKILLS', () => {
  it('is the client\'s list, at the client\'s length', () => {
    expect(GRADUATE_SKILLS).toHaveLength(22)
  })

  it('names only skills the pipeline can actually write', () => {
    // If this fails, either skills.json renamed something or this list has a
    // typo. Either way a skill has silently stopped matching any advert.
    const canonical = canonicalSkillNames()
    const unknown = GRADUATE_SKILLS.filter((skill) => !canonical.has(skill))
    expect(unknown).toEqual([])
  })

  it('lists nothing twice', () => {
    expect(new Set(GRADUATE_SKILLS).size).toBe(GRADUATE_SKILLS.length)
  })
})

describe('orderForGraduates', () => {
  it('brings what is taught to the front, in the order it was given', () => {
    const { ordered } = orderForGraduates(['Power BI', 'React', 'JavaScript'])
    // JavaScript is first on the client's list, React third; Power BI is not
    // on it at all, however often the adverts ask for it.
    expect(ordered).toEqual(['JavaScript', 'React', 'Power BI'])
  })

  it('leaves everything else in the order it arrived', () => {
    const { ordered } = orderForGraduates([
      'SQL (MySQL/Postgres)', 'Data Analysis', 'Stakeholder Management', 'Power BI',
    ])
    expect(ordered).toEqual([
      'SQL (MySQL/Postgres)', 'Data Analysis', 'Stakeholder Management', 'Power BI',
    ])
  })

  it('counts the taught ones, which is how many the picker shows', () => {
    const { taughtCount } = orderForGraduates(['Power BI', 'React', 'Docker'])
    expect(taughtCount).toBe(2)
  })

  it('skips a taught skill no advert asks for', () => {
    // A tick that cannot change the results is worse than no tick: skills
    // only reorder, so selecting one nothing asks for does nothing at all.
    const { ordered, taughtCount } = orderForGraduates(['React'])
    expect(ordered).toEqual(['React'])
    expect(taughtCount).toBe(1)
  })

  it('loses nothing and invents nothing', () => {
    const input = ['Power BI', 'React', 'Data Analysis', 'Kubernetes', 'ETL & Data Pipelines']
    const { ordered } = orderForGraduates(input)
    expect([...ordered].sort()).toEqual([...input].sort())
  })

  it('is safe on an empty board', () => {
    expect(orderForGraduates([])).toEqual({ ordered: [], taughtCount: 0 })
  })
})
