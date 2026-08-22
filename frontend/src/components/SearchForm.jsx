import { useState } from 'react'
import { ENTRY, JUNIOR, canSearch } from '../lib/match.js'

const MAX_OPTIONS_SHOWN = 20

const LEVEL_HELP = {
  [ENTRY]: 'No commercial experience yet — ads asking up to a year',
  [JUNIOR]: 'Up to three years in — ads asking up to three',
}

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function Group({ title, hint, options, selected, onChange, findLabel, help }) {
  const [search, setSearch] = useState('')

  if (options.length === 0) return null

  const visible = findLabel && search.trim()
    ? options.filter((o) => o.toLowerCase().includes(search.trim().toLowerCase()))
    : options.slice(0, MAX_OPTIONS_SHOWN)

  return (
    <fieldset className="border-t border-neutral-200 pt-4 first:border-t-0 first:pt-0">
      <legend className="text-sm font-semibold text-codespace-ink">{title}</legend>
      {hint && <p className="mb-2 mt-0.5 text-xs text-neutral-500">{hint}</p>}
      {findLabel && (
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={findLabel}
          aria-label={findLabel}
          className="mb-2 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs focus:border-codespace-teal focus:outline-none focus:ring-1 focus:ring-codespace-teal"
        />
      )}
      <div className="max-h-48 space-y-1.5 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="text-xs text-neutral-400">No matches</p>
        ) : (
          visible.map((option) => (
            <label key={option} className="flex items-start gap-2 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={selected.includes(option)}
                onChange={() => onChange(toggle(selected, option))}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-neutral-300 text-codespace-teal focus:ring-codespace-teal"
              />
              <span className="min-w-0">
                {option}
                {help?.[option] && (
                  <span className="block text-xs text-neutral-500">{help[option]}</span>
                )}
              </span>
            </label>
          ))
        )}
      </div>
    </fieldset>
  )
}

/**
 * What a student tells us about themselves, before any jobs are shown.
 *
 * The board used to open with everything on it. It no longer does, and the
 * reason is in the data: 44% of jobs carry no evidence of their own level,
 * and an employer typing "Junior" into a title costs them nothing. Opening
 * with a list means presenting those labels as though we believed them.
 * Asking first means the matching runs on what somebody actually told us.
 */
export default function SearchForm({ facets, criteria, onChange, onSearch, resultCount }) {
  const set = (key) => (value) => onChange({ ...criteria, [key]: value })
  const ready = canSearch(criteria)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (ready) onSearch()
      }}
      className="w-full space-y-4 rounded-lg border border-neutral-200 bg-white p-4 md:w-72"
      aria-label="Find jobs that match you"
    >
      <Group
        title="What kind of work"
        hint="The track you are looking for."
        options={facets.roleTypes}
        selected={criteria.roleTypes}
        onChange={set('roleTypes')}
      />
      <Group
        title="Where you are"
        hint="Matched against the years an ad asks for, not the word in its title."
        options={facets.levels}
        selected={criteria.levels}
        onChange={set('levels')}
        help={LEVEL_HELP}
      />
      <Group
        title="Skills you have"
        hint="These order the results. Nothing is hidden for a skill you lack."
        options={facets.skills}
        selected={criteria.skills}
        onChange={set('skills')}
        findLabel="Find a skill..."
      />

      <div className="space-y-2 border-t border-neutral-200 pt-4">
        <button
          type="submit"
          disabled={!ready}
          className="w-full rounded-md bg-codespace-teal px-4 py-2 text-sm font-semibold text-white hover:bg-codespace-tealDark focus:outline-none focus:ring-2 focus:ring-codespace-teal focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-neutral-300"
        >
          Search for jobs
        </button>
        {!ready && (
          <p className="text-xs text-neutral-500">
            Pick what kind of work you want, or where you are, to search.
          </p>
        )}
        {resultCount !== null && (
          <button
            type="button"
            onClick={() => onChange({ roleTypes: [], levels: [], skills: [] })}
            className="w-full text-xs font-medium text-codespace-teal hover:text-codespace-tealDark"
          >
            Start again
          </button>
        )}
      </div>
    </form>
  )
}
