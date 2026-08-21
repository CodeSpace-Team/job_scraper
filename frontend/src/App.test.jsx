/**
 * Integration test for the board's top-level page (F6).
 *
 * Exercises the real wiring -- fetch, filtering, rendering -- together,
 * the way a person actually uses the page, rather than each piece in
 * isolation.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

const SAMPLE_JOBS = [
  {
    title: 'Junior React Developer',
    company: 'Acme',
    role_type: 'Software Development',
    job_level: 'entry',
    must_have_skills: 'JavaScript, React',
    job_url: 'https://example.com/1',
    date_posted: '2026-08-01',
  },
  {
    title: 'IT Support Technician',
    company: 'Widgets Inc',
    role_type: 'Technical Support',
    job_level: 'entry',
    must_have_skills: 'Windows, Networking',
    job_url: 'https://example.com/2',
    date_posted: '2026-08-14',
  },
]

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ jobs: SAMPLE_JOBS }),
    }),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('App', () => {
  it('loads and shows every job by default', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())
    expect(screen.getByText('Junior React Developer')).toBeInTheDocument()
    expect(screen.getByText('IT Support Technician')).toBeInTheDocument()
  })

  it('narrows results as you type in the search box', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Search jobs'), 'react')

    await waitFor(() => expect(screen.getByText('1 of 2 jobs')).toBeInTheDocument())
    expect(screen.getByText('Junior React Developer')).toBeInTheDocument()
    expect(screen.queryByText('IT Support Technician')).not.toBeInTheDocument()
  })

  it('shows a message when fetching jobs.json fails', async () => {
    global.fetch = vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText(/Could not load today's jobs/)).toBeInTheDocument(),
    )
  })

  it('shows a friendly message when no jobs match the filters', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Search jobs'), 'no such job anywhere')

    await waitFor(() =>
      expect(screen.getByText(/No jobs match these filters/)).toBeInTheDocument(),
    )
  })

  it('defaults to newest first, and re-orders when the sort is changed', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())

    const titlesInOrder = () =>
      screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)

    expect(titlesInOrder()).toEqual(['IT Support Technician', 'Junior React Developer'])

    await user.selectOptions(screen.getByLabelText('Sort jobs'), 'oldest')

    expect(titlesInOrder()).toEqual(['Junior React Developer', 'IT Support Technician'])
  })

  it('the filter panel\'s "clear all filters" button resets search and shows every job again', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())

    await user.type(screen.getByLabelText('Search jobs'), 'no such job anywhere')
    await waitFor(() => expect(screen.getByText('Clear all filters')).toBeInTheDocument())

    await user.click(screen.getByText('Clear all filters'))

    await waitFor(() => expect(screen.getByText('2 of 2 jobs')).toBeInTheDocument())
  })
  it('draws exactly as many cards as the count claims, even when two jobs share an apply link', async () => {
    /*
     * The defect Emma reported: the board said "4 of 377 jobs" with
     * thirty-two cards under it, the first of them nothing to do with what
     * she had filtered for.
     *
     * The cause was not the filtering -- filterJobs had it right all along.
     * It was the card key. Twenty-one rows on the live board shared an apply
     * link with another row, React does not error on repeated keys but
     * mis-reconciles them, and on a filter change it left stale cards in the
     * DOM. The count read from the filtered array and told the truth; the
     * cards did not.
     */
    const user = userEvent.setup()
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            jobs: [
              ...SAMPLE_JOBS,
              { ...SAMPLE_JOBS[1], title: 'IT Support Technician (Cape Town)' },
              { ...SAMPLE_JOBS[1], title: 'IT Support Technician (Durban)' },
            ],
          }),
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText('4 of 4 jobs')).toBeInTheDocument())
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4)

    await user.type(screen.getByLabelText('Search jobs'), 'React')

    await waitFor(() => expect(screen.getByText('1 of 4 jobs')).toBeInTheDocument())
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1)
    expect(screen.getByText('Junior React Developer')).toBeInTheDocument()
  })
})
