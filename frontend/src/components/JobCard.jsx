import { useId, useMemo, useState } from 'react'
import { jobSkills, splitSkills } from '../lib/filters.js'
import { highlightTerms, splitOnTerms } from '../lib/match.js'
import {
  descriptionSegments,
  formatJobDate,
  formatSalary,
  formatYears,
} from '../lib/format.js'

function Badge({ children }) {
  return (
    <span className="inline-block rounded-full bg-neutral-100 px-2.5 py-0.5 text-xs font-medium text-neutral-700">
      {children}
    </span>
  )
}

function SkillChip({ children }) {
  return (
    <span className="inline-block rounded-md bg-codespace-mint px-2 py-0.5 text-xs font-medium text-codespace-tealDark">
      {children}
    </span>
  )
}

/**
 * What this job's match rests on, said out loud.
 *
 * The reason the board asks before it shows anything is that its labels are
 * not worth presenting on their own -- 44% of jobs carry no evidence of
 * their own level, and "Junior" in a title costs an employer nothing. Having
 * matched on the ad's own number where there is one, the card has to say
 * which of those it was, or it is asking to be trusted on the same footing
 * as the labels it just worked around.
 */
function MatchNote({ match, pickedSkills }) {
  if (!match) return null

  const level = {
    years: match.years === 0
      ? 'Asks for no prior experience'
      : `Asks for ${match.years} ${match.years === 1 ? 'year' : 'years'}`,
    'title-only': 'Titled for this level — the ad gives no other detail',
    unstated: 'The ad does not say what level it wants',
  }[match.evidence]

  const solid = match.evidence === 'years'

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <span className={solid ? 'font-medium text-codespace-tealDark' : 'text-neutral-500'}>
        {level}
      </span>
      {pickedSkills > 0 && (
        <span className="text-neutral-600">
          Matches {match.overlap.length} of your {pickedSkills} skills
          {match.overlap.length > 0 && (
            <span className="text-neutral-500">: {match.overlap.join(', ')}</span>
          )}
        </span>
      )}
    </div>
  )
}

export default function JobCard({ job, match = null, pickedSkills = 0 }) {
  const years = formatYears(job.experience_years)
  const salary = formatSalary(job)
  const jobDate = formatJobDate(job)
  const mustHave = splitSkills(job.must_have_skills)
  const niceToHave = splitSkills(job.nice_to_have_skills)
  const skillCount = jobSkills(job).length

  // Reading the ad before opening it is the point. Without this a student
  // has only the one-line blurb to go on, so the way to find out what a job
  // actually asks for is to click Apply and land on the employer's site --
  // and discover there that it wanted five years and a degree they do not
  // have. The description is on the card already; it just was not shown.
  const [showDescription, setShowDescription] = useState(false)
  const descriptionId = useId()
  const description = (job.description_snippet || '').trim()

  // The skills a student picked that this job also asks for. Highlighting
  // those in the advert is the difference between reading three thousand
  // characters and glancing at where the yellow is.
  const terms = useMemo(
    () => highlightTerms(match?.overlap || []),
    [match?.overlap],
  )

  return (
    <article className="rounded-lg border border-neutral-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        {/*
          min-w-0 matters more than it looks. A flex item defaults to
          min-width:auto, so it refuses to shrink below its content's own
          minimum width -- and for a job title with no spaces to break at,
          that minimum is the entire string. One such title dragged the whole
          page out to 768px on a 320px phone, which is what made the board
          look zoomed out and unusable. break-words then lets the title wrap
          mid-word instead of demanding the space.
        */}
        <div className="min-w-0">
          <h2 className="break-words text-base font-semibold text-codespace-ink">
            {job.title}
          </h2>
          <p className="break-words text-sm text-neutral-600">{job.company}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <div className="flex items-center gap-2">
            {description && (
              <button
                type="button"
                onClick={() => setShowDescription((open) => !open)}
                aria-expanded={showDescription}
                aria-controls={descriptionId}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm font-medium text-neutral-700 hover:border-codespace-teal hover:text-codespace-tealDark focus:outline-none focus:ring-2 focus:ring-codespace-teal focus:ring-offset-1"
              >
                {showDescription ? 'Hide description' : 'View description'}
              </button>
            )}
            {job.job_url && (
              <a
                href={job.job_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-md bg-codespace-teal px-3 py-1.5 text-sm font-medium text-white hover:bg-codespace-tealDark focus:outline-none focus:ring-2 focus:ring-codespace-teal focus:ring-offset-1"
              >
                Apply
              </a>
            )}
          </div>
          {jobDate && <span className="text-xs text-neutral-500">{jobDate}</span>}
        </div>
      </div>

      {/*
        No level badge. It used to sit here, and it was the pipeline's own
        guess -- on a real board 44% of jobs have no evidence for it at all.
        Worse, it contradicted the search that found the job: a student who
        asked for junior work saw "Mid" stamped on the first result, above a
        line saying the ad asks for three years. The line is the true thing;
        the badge was the guess. Only the badge went.
      */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {job.role_type && <Badge>{job.role_type}</Badge>}
        {job.workplace_policy && <Badge>{job.workplace_policy}</Badge>}
        {job.location && <Badge>{job.location}</Badge>}
      </div>

      {(years || salary) && (
        <p className="mt-2 text-sm text-neutral-600">
          {[years, salary].filter(Boolean).join(' · ')}
        </p>
      )}

      <MatchNote match={match} pickedSkills={pickedSkills} />

      {job.blurb && <p className="mt-3 text-sm text-neutral-700">{job.blurb}</p>}

      {skillCount > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {mustHave.map((skill) => (
            <SkillChip key={skill}>{skill}</SkillChip>
          ))}
          {niceToHave.map((skill) => (
            <SkillChip key={skill}>{skill} (nice to have)</SkillChip>
          ))}
        </div>
      )}

      {showDescription && description && (
        <div id={descriptionId} className="mt-4 border-t border-neutral-200 pt-3">
          {/*
            whitespace-pre-line keeps the ad's own paragraph breaks, and the
            segments carry its `**` headings through as real bold. Rendered
            as segments rather than as HTML: the text is scraped, so putting
            it through dangerouslySetInnerHTML would put whatever an employer
            typed straight into the page.
          */}
          <p className="whitespace-pre-line break-words text-sm leading-relaxed text-neutral-700">
            {descriptionSegments(description).map((segment, i) => {
              const runs = splitOnTerms(segment.text, terms).map((run, j) =>
                run.hit ? (
                  <mark
                    key={j}
                    className="rounded-sm bg-yellow-200 px-0.5 font-medium text-codespace-ink"
                  >
                    {run.text}
                  </mark>
                ) : (
                  run.text
                ),
              )
              return segment.bold ? (
                <strong key={i} className="font-semibold text-codespace-ink">
                  {runs}
                </strong>
              ) : (
                <span key={i}>{runs}</span>
              )
            })}
          </p>
          <p className="mt-2 text-xs text-neutral-500">
            {terms.length > 0 && (
              <span className="text-neutral-600">
                Your skills are{' '}
                <mark className="rounded-sm bg-yellow-200 px-0.5">highlighted</mark>.{' '}
              </span>
            )}
            {/*
              We store the first 3000 characters of an ad, which is the whole
              thing for most and the bulk of it for the longest. Saying so is
              better than letting somebody assume they have read everything.
            */}
            The start of the advert as we captured it. Open the job to read it in full.
          </p>
        </div>
      )}
    </article>
  )
}
