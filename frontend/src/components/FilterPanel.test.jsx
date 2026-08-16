/**
 * Tests for the filter panel's own interactive behaviour (F6) --
 * specifically the skills search box, since that's the one piece of real
 * logic living inside this component rather than in lib/filters.js.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import FilterPanel from './FilterPanel.jsx'
import { EMPTY_FILTERS } from '../lib/filters.js'

const FACETS = {
  roleTypes: ['Software Development', 'Technical Support'],
  levels: ['entry', 'senior'],
  workPolicies: ['remote'],
  sources: ['indeed'],
  employmentTypes: [],
  skills: ['JavaScript', 'React', 'Python', 'Django'],
}

describe('FilterPanel', () => {
  it('shows every skill option when the search box is empty', () => {
    render(<FilterPanel facets={FACETS} filters={EMPTY_FILTERS} onChange={() => {}} />)
    expect(screen.getByText('JavaScript')).toBeInTheDocument()
    expect(screen.getByText('Python')).toBeInTheDocument()
  })

  it('narrows the skills list as you type in the skills search box', async () => {
    const user = userEvent.setup()
    render(<FilterPanel facets={FACETS} filters={EMPTY_FILTERS} onChange={() => {}} />)

    await user.type(screen.getByLabelText('Filter skills options'), 'py')

    expect(screen.getByText('Python')).toBeInTheDocument()
    expect(screen.queryByText('JavaScript')).not.toBeInTheDocument()
  })

  it('shows a "no matches" message when the skills search matches nothing', async () => {
    const user = userEvent.setup()
    render(<FilterPanel facets={FACETS} filters={EMPTY_FILTERS} onChange={() => {}} />)

    await user.type(screen.getByLabelText('Filter skills options'), 'nonexistent skill')

    expect(screen.getByText('No matches')).toBeInTheDocument()
  })

  it('does not show a "clear all filters" button when nothing is active', () => {
    render(<FilterPanel facets={FACETS} filters={EMPTY_FILTERS} onChange={() => {}} />)
    expect(screen.queryByText('Clear all filters')).not.toBeInTheDocument()
  })

  it('shows a "clear all filters" button once a filter is active, and it resets everything', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <FilterPanel
        facets={FACETS}
        filters={{ ...EMPTY_FILTERS, roleTypes: ['Software Development'] }}
        onChange={onChange}
      />,
    )

    const button = screen.getByText('Clear all filters')
    await user.click(button)

    expect(onChange).toHaveBeenCalledWith(EMPTY_FILTERS)
  })

  it('other checkbox groups are not searchable', () => {
    render(<FilterPanel facets={FACETS} filters={EMPTY_FILTERS} onChange={() => {}} />)
    expect(screen.queryByLabelText('Filter role type options')).not.toBeInTheDocument()
  })
})