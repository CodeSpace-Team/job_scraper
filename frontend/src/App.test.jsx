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
  },
  {
    title: 'IT Support Technician',
    company: 'Widgets Inc',
    role_type: 'Technical Support',
    job_level: 'entry',
    must_have_skills: 'Windows, Networking',
    job_url: 'https://example.com/2',
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
})