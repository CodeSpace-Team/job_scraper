/**
 * What a CodeSpace graduate leaves the course with.
 *
 * This is the client's own list, in the client's own order, and it exists to
 * fix a specific problem with the skills picker: the picker was ordered by
 * how often a skill appears in the adverts, which is a fact about the South
 * African job market rather than a fact about the students using the board.
 *
 * On the day this was written that ordering put SQL, Data Analysis, Business
 * Analysis, ETL & Data Pipelines and Stakeholder Management in the visible
 * twenty, and pushed HTML/CSS, Node.js, Testing/Debugging, Java, CI/CD,
 * Docker, Angular, Vue.js, PHP, MongoDB and Kubernetes below the fold --
 * eleven of the twenty-two things a graduate actually has, reachable only by
 * somebody who thought to type into the search box. A student opening the
 * page was shown a list of skills they mostly do not have.
 *
 * Frequency still decides the order of everything after these, because for
 * skills nobody was taught here, "what the market asks for most" is as good
 * a guide as any.
 *
 * Every name below is a canonical name in backend/skills.json. That is not a
 * coincidence to be relied on quietly -- graduate.test.js pins it, so a
 * rename on either side fails a test rather than silently emptying a group.
 */
export const GRADUATE_SKILLS = [
  'JavaScript',
  'HTML/CSS',
  'React',
  'Git',
  'REST APIs',
  'Testing/Debugging',
  'Agile/Jira',
  'TypeScript',
  'Python',
  'SQL (MySQL/Postgres)',
  'MongoDB/NoSQL',
  'C#/.NET',
  'Node.js',
  'Java',
  'PHP',
  'Vue.js',
  'Docker',
  'Azure',
  'CI/CD',
  'Angular',
  'AWS',
  'Kubernetes',
]

const TAUGHT = new Set(GRADUATE_SKILLS)

/**
 * Put the taught skills first, in the order they were taught.
 *
 * A skill that is on the list but not in any advert today is left out. The
 * picker only ranks results, so offering a tick that cannot change what comes
 * back would be a control that does nothing -- worse than not offering it.
 *
 * @param {string[]} skills Skill names found on the board, most common first.
 * @returns {{ordered: string[], taughtCount: number}} The same names
 *   reordered, and how many of the leading ones are taught here -- which is
 *   how many the picker shows before it starts hiding things behind a search.
 */
export function orderForGraduates(skills) {
  const onBoard = new Set(skills)
  const taught = GRADUATE_SKILLS.filter((skill) => onBoard.has(skill))
  const rest = skills.filter((skill) => !TAUGHT.has(skill))
  return { ordered: [...taught, ...rest], taughtCount: taught.length }
}
