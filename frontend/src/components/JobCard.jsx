import { jobSkills, splitSkills } from '../lib/filters.js'
import { formatJobDate, formatLevel, formatSalary, formatYears } from '../lib/format.js'

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

export default function JobCard({ job }) {
  const level = formatLevel(job.job_level)
  const years = formatYears(job.experience_years)
  const salary = formatSalary(job)
  const jobDate = formatJobDate(job)
  const mustHave = splitSkills(job.must_have_skills)
  const niceToHave = splitSkills(job.nice_to_have_skills)
  const skillCount = jobSkills(job).length

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
          {job.job_url && (
            <a
              href={job.job_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md bg-codespace-teal px-3 py-1.5 text-sm font-medium text-white hover:bg-codespace-tealDark"
            >
              Apply
            </a>
          )}
          {jobDate && <span className="text-xs text-neutral-500">{jobDate}</span>}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {job.role_type && <Badge>{job.role_type}</Badge>}
        {level && <Badge>{level}</Badge>}
        {job.workplace_policy && <Badge>{job.workplace_policy}</Badge>}
        {job.location && <Badge>{job.location}</Badge>}
      </div>

      {(years || salary) && (
        <p className="mt-2 text-sm text-neutral-600">
          {[years, salary].filter(Boolean).join(' · ')}
        </p>
      )}

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
    </article>
  )
}
