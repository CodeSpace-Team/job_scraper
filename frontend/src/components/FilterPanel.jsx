import { useState } from 'react'
import { EMPTY_FILTERS, hasActiveFilters } from '../lib/filters.js'

const MAX_OPTIONS_SHOWN = 20

function toggle(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function CheckboxGroup({ title, options, selected, onChange, searchable = false }) {
  const [search, setSearch] = useState('')

  if (options.length === 0) return null

  const visible = searchable && search.trim()
    ? options.filter((o) => o.toLowerCase().includes(search.trim().toLowerCase()))
    : options.slice(0, MAX_OPTIONS_SHOWN)

  return (
    <fieldset className="border-t border-neutral-200 pt-4 first:border-t-0 first:pt-0">
      <legend className="mb-2 text-sm font-semibold text-codespace-ink">{title}</legend>
      {searchable && (
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Find a ${title.toLowerCase()}...`}
          aria-label={`Filter ${title.toLowerCase()} options`}
          className="mb-2 w-full rounded-md border border-neutral-300 px-2 py-1 text-xs focus:border-codespace-teal focus:outline-none focus:ring-1 focus:ring-codespace-teal"
        />
      )}
      <div className="max-h-48 space-y-1.5 overflow-y-auto">
        {visible.length === 0 ? (
          <p className="text-xs text-neutral-400">No matches</p>
        ) : (
          visible.map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm text-neutral-700">
              <input
                type="checkbox"
                checked={selected.includes(option)}
                onChange={() => onChange(toggle(selected, option))}
                className="h-4 w-4 rounded border-neutral-300 text-codespace-teal focus:ring-codespace-teal"
              />
              {option}
            </label>
          ))
        )}
      </div>
    </fieldset>
  )
}

export default function FilterPanel({ facets, filters, onChange }) {
  const set = (key) => (value) => onChange({ ...filters, [key]: value })

  return (
    <aside className="w-full space-y-4 rounded-lg border border-neutral-200 bg-white p-4 md:w-64">
      {hasActiveFilters(filters) && (
        <button
          type="button"
          onClick={() => onChange(EMPTY_FILTERS)}
          className="text-sm font-medium text-codespace-teal hover:text-codespace-tealDark"
        >
          Clear all filters
        </button>
      )}
      <CheckboxGroup
        title="Role type"
        options={facets.roleTypes}
        selected={filters.roleTypes}
        onChange={set('roleTypes')}
      />
      <CheckboxGroup
        title="Level"
        options={facets.levels}
        selected={filters.levels}
        onChange={set('levels')}
      />
      <CheckboxGroup
        title="Work policy"
        options={facets.workPolicies}
        selected={filters.workPolicies}
        onChange={set('workPolicies')}
      />
      <CheckboxGroup
        title="Skills"
        options={facets.skills}
        selected={filters.skills}
        onChange={set('skills')}
        searchable
      />
      <CheckboxGroup
        title="Source"
        options={facets.sources}
        selected={filters.sources}
        onChange={set('sources')}
      />

      <div className="border-t border-neutral-200 pt-4">
        <label className="mb-2 block text-sm font-semibold text-codespace-ink" htmlFor="max-years">
          Max years of experience asked for
        </label>
        <input
          id="max-years"
          type="number"
          min="0"
          value={filters.maxYears}
          onChange={(e) => set('maxYears')(e.target.value)}
          placeholder="No limit"
          className="w-full rounded-md border border-neutral-300 px-3 py-1.5 text-sm focus:border-codespace-teal focus:outline-none focus:ring-1 focus:ring-codespace-teal"
        />
      </div>
    </aside>
  )
}