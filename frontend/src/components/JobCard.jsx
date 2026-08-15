import { jobSkills, splitSkills } from '../lib/filters.js'
import { formatLevel, formatSalary, formatYears } from '../lib/format.js'

function Badge({ children }) {
  return (
    <span className="inline-block rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
      {children}
    </span>
  )
}

function SkillChip({ children }) {
  return (
    <span className="inline-block rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">
      {children}
    </span>
  )
}

export default function JobCard({ job }) {
  const level = formatLevel(job.job_level)
  const years = formatYears(job.experience_years)
  const salary = formatSalary(job)
  const mustHave = splitSkills(job.must_have_skills)
  const niceToHave = splitSkills(job.nice_to_have_skills)
  const skillCount = jobSkills(job).length

  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">{job.title}</h2>
          <p className="text-sm text-slate-600">{job.company}</p>
        </div>
        {job.job_url && (
          <a
            href={job.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Apply
          </a>
        )}
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {job.role_type && <Badge>{job.role_type}</Badge>}
        {level && <Badge>{level}</Badge>}
        {job.workplace_policy && <Badge>{job.workplace_policy}</Badge>}
        {job.location && <Badge>{job.location}</Badge>}
      </div>

      {(years || salary) && (
        <p className="mt-2 text-sm text-slate-600">
          {[years, salary].filter(Boolean).join(' · ')}
        </p>
      )}

      {job.blurb && <p className="mt-3 text-sm text-slate-700">{job.blurb}</p>}

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