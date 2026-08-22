/**
 * Integration test for the board's top-level page (F6).
 *
 * Exercises the real wiring -- fetch, matching, rendering -- together, the
 * way a person actually uses the page, rather than each piece in isolation.
 *
 * The flow it tests is a gate, not a feed. The board shows nothing until a
 * student has said what they are looking for, because its labels are not
 * worth presenting on their own: 44% of jobs on a real board carry no
 * evidence of their own level, and an employer typing "Junior" into a title
 * costs them nothing.
 */

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

const SAMPLE_JOBS = [
  {
    title: 'Junior React Developer',
    company: 'Acme',
    role_type: 'Software development',
    job_level: 'junior',
    level_source: 'years',
    experience_years: 2,
    must_have_skills: 'JavaScript, React',
    job_url: 'https://example.com/1',
    date_posted: '2026-08-01',
  },
  {
    title: 'Graduate Data Analyst',
    company: 'Widgets Inc',
    role_type: 'Data & BI',
    job_level: 'entry level',
    level_source: 'title',
    must_have_skills: 'SQL (MySQL/Postgres), Python',
    job_url: 'https://example.com/2',
    date_posted: '2026-08-14',
  },
]

function mockJobs(jobs) {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ jobs }) }),
  )
}

async function searchFor(user, { work, level } = {}) {
  if (work) await user.click(screen.getByRole('checkbox', { name: new RegExp(work) }))
  if (level) await user.click(screen.getByRole('checkbox', { name: new RegExp(level) }))
  await user.click(screen.getByRole('button', { name: 'Search for jobs' }))
}

beforeEach(() => {
  mockJobs(SAMPLE_JOBS)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('App', () => {
  it('shows no jobs at all until the student has searched', async () => {
    render(<App />)

    await waitFor(() =>
      expect(screen.getByText('Tell us what you are looking for')).toBeInTheDocument(),
    )

    expect(screen.queryByRole('heading', { level: 2, name: 'Junior React Developer' }))
      .not.toBeInTheDocument()
    expect(screen.getByText('2 jobs open right now.')).toBeInTheDocument()
  })

  it('will not search until there is something to search on', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    expect(screen.getByRole('button', { name: 'Search for jobs' })).toBeDisabled()
  })

  it('shows the jobs on the track the student chose, and only those', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { work: 'Software development' })

    expect(screen.getByText('1 of 2 jobs match')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Junior React Developer' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'Graduate Data Analyst' }))
      .not.toBeInTheDocument()
  })

  it('matches on the years an ad states, not the word in its title', async () => {
    /*
     * The rule the whole redesign rests on. This ad calls itself junior and
     * then asks for five years. A student at junior level should not be
     * shown it, whatever it calls itself.
     */
    mockJobs([{
      ...SAMPLE_JOBS[0],
      title: 'Junior Developer (really is not)',
      level_source: 'title',
      experience_years: 5,
    }])

    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { level: 'junior' })

    expect(screen.getByText('0 of 1 jobs match')).toBeInTheDocument()
    expect(screen.getByText(/Nothing open matches that today/)).toBeInTheDocument()
  })

  it('says what each match rests on', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { work: 'Software development' })

    expect(screen.getByText('Asks for 2 years')).toBeInTheDocument()
  })

  it('warns when a job is only titled for the level and says nothing else', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { work: 'Data & BI' })

    expect(screen.getByText(/the ad gives no other detail/i)).toBeInTheDocument()
  })

  it('orders by skill overlap and says how much each job matched', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /entry level/ }))
    await user.click(screen.getByRole('checkbox', { name: /^junior/ }))
    await user.click(screen.getByRole('checkbox', { name: /React/ }))
    await user.click(screen.getByRole('button', { name: 'Search for jobs' }))

    const cards = screen.getAllByRole('heading', { level: 2 })
    expect(cards[0]).toHaveTextContent('Junior React Developer')
    expect(screen.getByText(/Matches 1 of your 1 skills/)).toBeInTheDocument()
    expect(screen.getByText(/Matches 0 of your 1 skills/)).toBeInTheDocument()
  })

  it('never hides a job for a skill the student lacks', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /entry level/ }))
    await user.click(screen.getByRole('checkbox', { name: /^junior/ }))
    await user.click(screen.getByRole('checkbox', { name: /Python/ }))
    await user.click(screen.getByRole('button', { name: 'Search for jobs' }))

    expect(screen.getByText('2 of 2 jobs match')).toBeInTheDocument()
  })

  it('clears stale results when the selection changes', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { work: 'Software development' })
    expect(screen.getByText('1 of 2 jobs match')).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /Data & BI/ }))

    expect(screen.queryByText(/jobs match/)).not.toBeInTheDocument()
    expect(screen.getByText('Tell us what you are looking for')).toBeInTheDocument()
  })

  it('narrows the results with the keyword box, once there are results', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    expect(screen.queryByLabelText('Search jobs')).not.toBeInTheDocument()

    await user.click(screen.getByRole('checkbox', { name: /entry level/ }))
    await user.click(screen.getByRole('checkbox', { name: /^junior/ }))
    await user.click(screen.getByRole('button', { name: 'Search for jobs' }))
    expect(screen.getByText('2 of 2 jobs match')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Search jobs'), 'Acme')

    await waitFor(() => expect(screen.getByText('1 of 2 jobs match')).toBeInTheDocument())
  })

  it('re-orders on request without losing the match reasons', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await user.click(screen.getByRole('checkbox', { name: /entry level/ }))
    await user.click(screen.getByRole('checkbox', { name: /^junior/ }))
    await user.click(screen.getByRole('button', { name: 'Search for jobs' }))

    await user.selectOptions(screen.getByLabelText('Sort jobs'), 'oldest')

    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings[0]).toHaveTextContent('Junior React Developer')
    expect(screen.getByText('Asks for 2 years')).toBeInTheDocument()
  })

  it('draws exactly as many cards as the count claims, even when two jobs share an apply link', async () => {
    /*
     * Emma's report: the board said "4 of 377 jobs" with thirty-two cards
     * under it. Twenty-one rows shared an apply link, React mis-reconciled
     * the repeated keys, and stale cards were left in the DOM.
     */
    mockJobs([
      SAMPLE_JOBS[0],
      { ...SAMPLE_JOBS[0], title: 'Junior React Developer (Cape Town)' },
      { ...SAMPLE_JOBS[0], title: 'Junior React Developer (Durban)' },
    ])

    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    await searchFor(user, { work: 'Software development' })
    expect(screen.getByText('3 of 3 jobs match')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(3)

    await user.type(screen.getByLabelText('Search jobs'), 'Durban')

    await waitFor(() => expect(screen.getByText('1 of 3 jobs match')).toBeInTheDocument())
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1)
  })

  it('shows the advert on demand, so nobody clicks Apply to find out what the job wants', async () => {
    mockJobs([{
      ...SAMPLE_JOBS[0],
      description_snippet:
        'We are looking for a junior developer.\n\nYou will need React and a willingness to learn.',
    }])

    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())
    await searchFor(user, { work: 'Software development' })

    expect(screen.queryByText(/willingness to learn/)).not.toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: 'View description' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(screen.getByText(/willingness to learn/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide description' }))
      .toHaveAttribute('aria-expanded', 'true')

    await user.click(screen.getByRole('button', { name: 'Hide description' }))
    expect(screen.queryByText(/willingness to learn/)).not.toBeInTheDocument()
  })

  it('offers no description button when the job has no description', async () => {
    const user = userEvent.setup()
    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())
    await searchFor(user, { work: 'Software development' })

    expect(screen.queryByRole('button', { name: 'View description' })).not.toBeInTheDocument()
  })

  it('offers no soft skills in the picker', async () => {
    mockJobs([{ ...SAMPLE_JOBS[0], must_have_skills: 'React, Communication, Documentation' }])

    render(<App />)
    await waitFor(() => expect(screen.getByText(/jobs open right now/)).toBeInTheDocument())

    const form = screen.getByRole('form', { name: /Find jobs/i })
    expect(within(form).getByRole('checkbox', { name: /React/ })).toBeInTheDocument()
    expect(within(form).queryByRole('checkbox', { name: /Communication/ })).not.toBeInTheDocument()
    expect(within(form).queryByRole('checkbox', { name: /Documentation/ })).not.toBeInTheDocument()
  })
})
