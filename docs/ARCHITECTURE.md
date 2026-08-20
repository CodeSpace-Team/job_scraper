# Architecture — South African Tech Job Aggregator

## Table of Contents
1. [System Overview](#system-overview)
2. [Pipeline Diagram](#pipeline-diagram)
3. [The Phases](#the-phases)
4. [Component Details](#component-details)
5. [Data Model](#data-model)
6. [Error Handling & Resilience](#error-handling--resilience)
7. [Quality Assurance](#quality-assurance)
8. [Performance & Cost](#performance--cost)
9. [Security & Secrets](#security--secrets)
10. [Deployment](#deployment)
11. [Known Limits](#known-limits)
12. [Architecture Decision Records](#architecture-decision-records)

---

## System Overview

An automated daily pipeline that scrapes tech jobs from South African job boards, screens them down to roles a graduate in their first three years could realistically get, enriches them with AI-extracted metadata, and publishes to two places: a Google Sheet for the CodeSpace team, and a public job board for graduates.

The screening is the part that matters most. Roughly 670 jobs are scraped each morning and about 170 reach the board — the other 500 are dropped as non-tech or above the cohort, and every one of them is recorded with its reason rather than deleted.

### Core objectives

| Objective | How it is met |
| :--- | :--- |
| **Daily automation** | GitHub Actions, 06:00 UTC / 08:00 SAST, no manual step |
| **Coverage of all seven role tracks** | ~40 Indeed search terms split across two days (F7) |
| **Only relevant jobs** | Two screens: non-tech (F1), then above-cohort (F4) |
| **Decisions that can be explained** | Rules read the ad's own words; the AI never decides a level |
| **Nothing lost** | Drops go to an Exclude tab with reasons; nothing is deleted |
| **Public accessibility** | A static job board, plus the Sheet |

### Key metrics (19 August 2026 run)

| Metric | Value |
| :--- | :--- |
| Scraped, after deduplication | ~670 |
| Reaching the board | ~170 |
| Runtime | ~18 minutes, mostly AI enrichment |
| AI cost | ~$0.50–$1.00/day (estimated, spend-capped) |
| Tests | 489 backend, 62 frontend |

---

## Pipeline Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  GITHUB ACTIONS — daily at 06:00 UTC / 08:00 SAST                    │
│  .github/workflows/daily-scrape.yml                                  │
└──────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR — src/core/orchestrator.py                             │
│  Runs every phase in order, isolating failures                       │
└──────────────────────────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│   OFFERZEN    │        │    INDEED     │        │  PNET / LI    │
│  public API   │        │    JobSpy     │        │ skipped in CI │
└───────────────┘        └───────────────┘        └───────────────┘
        └────────────────────────┼────────────────────────┘
                                 ▼

      [PHASE 1]    scrape                              ~680 jobs
      [PHASE 1.5]  dedupe (F9)        three checks     ~660 unique
      [PHASE 1.7]  skills (F5)        free, no AI
      [PHASE 2]    enrich             Claude Haiku
      [PHASE 2.4]  label (F2/F3/F7)   level, years, role track
      [PHASE 2.5]  screen (F1/F4)     keep or drop     ~170 kept

                                 │
             ┌───────────────────┼───────────────────┐
             ▼                   ▼                   ▼
      [PHASE 3]            [PHASE 3.5]         [PHASE 3.7]
      Jobs sheet           Exclude tab         jobs.json
      append-only          with reasons        merge + prune
             │                   │                   │
             ▼                   ▼                   ▼
      ┌─────────────────────────────┐        ┌──────────────┐
      │      GOOGLE SHEET           │        │   NETLIFY    │
      │  Jobs tab + Exclude tab     │        │  job board   │
      └─────────────────────────────┘        └──────────────┘
```

**The three write steps are independent.** A failure in Phase 3 does not prevent 3.5 or 3.7 from running. See [Error Handling](#error-handling--resilience).

---

## The Phases

| Phase | Feature | What it does |
| :--- | :--- | :--- |
| **1** | — | Scrape Indeed (32 terms/day) and OfferZen |
| **1.5** | F9 | Remove duplicates — three checks, before the AI so nothing is enriched twice |
| **1.7** | F5 | Match skills from the job text for free, offline |
| **2** | — | AI enrichment: summary, role label, skills the keyword match missed |
| **2.4** | F2, F3, F7, F5 | Derive level and years from the ad; assign a role track; normalise skill names |
| **2.5** | F1, F4 | Drop non-tech jobs, then anything above the first three years |
| **3** | — | Append new jobs to the Jobs tab |
| **3.5** | F1, F4 | Append drops to the Exclude tab with their reasons |
| **3.7** | F6 | Merge today's jobs into the board's `jobs.json`, prune past 45 days, commit |

Ordering is deliberate in three places:

- **Deduplication runs before enrichment**, so a job advertised in three cities is sent to the AI once rather than three times.
- **Keyword skill matching runs before enrichment**, so the AI has less to work out.
- **F1 runs before F4.** When a job fails both, "not a tech job" is the more useful reason to record. A Senior Quantity Surveyor belongs in the Exclude tab as a surveyor, not as a senior.

---

## Component Details

### Orchestrator — `src/core/orchestrator.py`

Runs the phases above, isolating failures so one broken step does not lose the run's work. Prints a per-phase summary that the morning check reads back.

Flags: `--skip-offerzen`, `--skip-indeed`, `--skip-linkedin`, `--skip-pnet`, `--skip-enrichment`, `--indeed-results N`, `--sheet-name NAME`, `--spreadsheet-id ID`.

### Scrapers — `src/scrapers/`

| Scraper | Type | Status |
| :--- | :--- | :--- |
| `indeed.py` | JobSpy wrapper | Active. 32 search terms/day, 30-day window, records which term found each job |
| `offerzen.py` | Public REST API | Active but intermittent — returned zero on at least one recent run. Non-fatal |
| `pnet.py` | BeautifulSoup + TLS fingerprinting | Built, skipped in CI (TLS/HTTP2 errors on GitHub runners) |
| `linkedin.py` | JobSpy wrapper | Built, skipped in CI (rate limiting, account suspension risk) |

Indeed records `search_term` on every job. That matters downstream: F7's classifier uses it as a last-resort hint, and knowing a track came from the search rather than from the job itself is what exposed the classifier's weakness (see ADR-007).

### Pipeline — `src/pipeline/`

| Module | Feature | Role |
| :--- | :--- | :--- |
| `dedupe.py` | F9 | Three checks: exact link; title+company+city for re-posts; title+city+advert text for agency-vs-employer |
| `skills.py` | F5 | Keyword matcher against `skills.json`, plus a canonicaliser applied to the AI's output too |
| `experience.py` | F3 | Years of experience, only where the sentence is genuinely about experience |
| `levels.py` | F2 | Level from title, then years, then a narrowly-scoped description check, else `unknown` |
| `roles.py` | F7 | Seven role tracks, the search-term schedule, and the classifier |
| `screening.py` | F1, F4 | Keep-or-drop, and the reason |
| `publish.py` | F6 | Merges the board's running `jobs.json`, prunes past 45 days |
| `qa.py` | F1, F2, F4 | Builds the three human review sheets |

### Enrichment — `src/enrichment/enhancer.py`

Claude Haiku, batched. Extracts `primary_role`, skills, `experience_years`, `ai_job_level` and `blurb`. Failures are non-fatal — jobs continue un-enriched.

**The AI's level output is recorded but never used.** It is stored as `ai_job_level` so the weekly check can compare it against the rules, and nothing reads it. See ADR-004.

### Writers — `src/writers/sheets.py`

Append-only, deduplicated by link *and* by F9's title/company/city key, so a re-post under a new URL does not land as a second row. Writes both the 16-column Jobs tab and the 11-column Exclude tab, and repairs the Exclude header when it finds an older column count.

### Frontend — `frontend/`

Vite + React + Tailwind, reading a static `jobs.json`. No backend, no API. `lib/filters.js` holds the search and filter rules and extracts filter options from the real data; `lib/sort.js` holds the ordering. 62 tests.

### Utilities — `src/utils/`

| Module | Purpose |
| :--- | :--- |
| `constants.py` | `SA_KEYWORDS` — South African location keywords |
| `logging.py` | `log()` — timestamped console output |
| `dates.py` | Date parsing and sort keys |
| `text.py` | Text normalisation |
| `io.py` | `load_jobs()`, `save_jobs()` |
| `retry.py` | `@retry` with exponential backoff and an optional `should_retry` predicate |
| `http.py` | `safe_get()` |

---

## Data Model

A job accumulates fields as it moves through the phases. Which phase set a field matters when debugging — a missing field usually means a phase did not run, not that the data was bad.

### From the scrapers

```python
{
    "source": "offerzen" | "indeed" | "linkedin" | "pnet",
    "search_term": "junior software developer",   # Indeed only — F7 uses it
    "title": "Junior Backend Developer",
    "company": "ABC Corp",
    "location": "Cape Town, Western Cape, South Africa",
    "city": "Cape Town",
    "country": "South Africa",
    "is_remote": True,
    "workplace_policy": "remote",
    "employment_type": "fulltime",
    "date_posted": "2026-08-18",
    "job_url": "https://...",
    "description_snippet": "...",
    "salary_min": None,        # never populated in practice — see ADR-006
    "salary_max": None,
    "salary_currency": "ZAR",
}
```

### Added by the pipeline

| Field | Phase | Meaning |
| :--- | :--- | :--- |
| `duplicate_count` | 1.5 (F9) | How many copies collapsed into this one |
| `must_have_skills` | 1.7 / 2.4 (F5) | Canonical skill names, comma-separated |
| `skills_source` | 1.7 / 2.4 (F5) | `keyword`, `ai` or empty |
| `needs_ai_skills` | 1.7 (F5) | Keyword match found fewer than three skills |
| `primary_role` | 2 | The AI's role label — **what F1 screens on** |
| `blurb` | 2 | One-sentence summary shown on the board |
| `ai_job_level` | 2 | The AI's level guess. Recorded, never used |
| `experience_years` | 2.4 (F3) | Integer or absent — never text |
| `years_source`, `years_evidence` | 2.4 (F3) | Where the number came from, and the exact words |
| `job_level` | 2.4 (F2) | `entry`/`junior`/`mid`/`senior`/`lead`/`principal`/`unknown` |
| `level_source`, `level_evidence` | 2.4 (F2) | Which rule decided, and on what words |
| `role_type` | 2.4 (F7) | One of the seven tracks, or empty |
| `role_source` | 2.4 (F7) | `title`, `description`, `search_term` or empty |
| `excluded_stage` | 2.5 (F1/F4) | `F1 non-tech` or `F4 above cohort` |
| `excluded_reason` | 2.5 | Why, in words |
| `excluded_rule` | 2.5 | `title_blocklist` or `role_not_accepted` |
| `needs_review` | 2.5 (F4) | The drop rests on softer evidence |
| `date_added` | 3.7 (F6) | When the board first saw this job |

**`level_source` and `level_evidence` exist because F4 deletes jobs based on the level.** A wrong label costs somebody a job they will never know existed, so every level decision has to be traceable back to words in the ad afterwards.

---

## Error Handling & Resilience

### Retry strategy

| Component | Attempts | Initial delay | Backoff | Notes |
| :--- | ---: | ---: | ---: | :--- |
| OfferZen API | 3 | 1.5s | 2.0× | |
| Indeed (JobSpy) | 3 | 2.0s | 2.0× | |
| PNet HTML | 3 | 5.0s | 2.0× | Plus session reset |
| Claude API | 3 | 2.0s | 2.0× | |
| **Sheets open** | **4** | **3.0s** | **2.0×** | Only for retryable statuses — see below |

The Sheets connection is the only one with a predicate. gspread reports everything as `APIError`: a 503 outage and a 403 "this sheet was never shared" arrive as the same exception class. Statuses `429, 500, 502, 503, 504` are Google's problem and are retried across roughly 21 seconds; `400, 403, 404` are ours and fail on the first attempt, because retrying a configuration error only makes it slower to report.

### Graceful degradation

| Failure | What happens |
| :--- | :--- |
| One scraper fails | The others continue; the run proceeds |
| Enrichment fails on a batch | Those jobs continue un-enriched; F1 falls back to reading the title |
| **Jobs sheet write fails** | A rescue copy is saved to `combined_jobs_fallback.json`, **Phases 3.5 and 3.7 still run**, and the run exits non-zero at the end |
| Exclude tab write fails | Logged; the board still publishes |
| Board publish fails | Logged; the Sheet is unaffected |

That third row was a real incident, twice. The first time, a Sheets failure called `sys.exit()` directly, which skipped the rescue copy and both remaining write steps — a whole run's work lost to one dropped connection. The writer now raises a plain exception instead, so the orchestrator can catch it and decide. `except Exception` does not catch a `SystemExit`, which is precisely why the original code failed silently in the one situation it most needed to handle.

### Recovering a failed Sheets write

```bash
cd backend
python -m src.writers.sheets -i data/cache/combined_jobs_fallback.json -s "<SHEET_ID>"
```

Safe to run: the writer is append-only and deduplicated, so this cannot double up rows.

---

## Quality Assurance

Two things the pipeline cannot check about itself: whether the levels are right, and whether anything is reaching the board that should not be. Both need a person reading real adverts.

| Check | Command | Target |
| :--- | :--- | :--- |
| Level accuracy (F2) | `python -m src.pipeline.qa` | 18 of 20 |
| Wrong drops (F4) | `python -m src.pipeline.qa -i data/cache/excluded_jobs.json` | No real job wrongly dropped |
| Non-tech rate (F1) | `python -m src.pipeline.qa --check tech --size 60` | Fewer than 5 in 100 |

The non-tech check samples 60 rather than 20 deliberately. A 5% target measured over 20 jobs can only produce 0%, 5% or 10% — one wrong job is exactly the pass mark, so a single unlucky draw would decide it.

`scripts/morning_check.py` reads a run's saved files and prints one page: the stage counts, whether they agree with each other, and whether each feature left its fingerprint on the data. A missing fingerprint means the runner was on older code, which no amount of reading the counts would reveal.

`scripts/decision_check.py` counts the evidence behind design decisions that were parked pending real data.

**Neither check may use the AI to grade the AI.** F1 screens on the AI's label; asking the AI whether F1 was right is asking it to mark its own homework.

---

## Performance & Cost

| Phase | Approximate share of an ~18 minute run |
| :--- | :--- |
| Scraping (32 Indeed terms) | ~4–5 min |
| AI enrichment | ~12 min — the bulk |
| Everything else | ~1 min |

### Cost

Roughly **$0.50–$1.00/day**, or **$15–30/month**, against a hard workspace spend cap. This is arithmetic from the model's pricing and jobs per run, not a figure read off an invoice.

Four things keep it there:

1. **Deduplication before enrichment** — a job listed in three cities is enriched once.
2. **Free keyword skill matching first** — less for the AI to work out.
3. **Claude Haiku** — the cheapest model that does the job well.
4. **Search terms split across two days** — ~40 terms, 32 per morning, avoiding paying twice for jobs F9 would discard anyway.

**Known headroom, deliberately unused:** just over half of jobs get enough skills from the free keyword match alone and could skip enrichment entirely. They are not skipped, because those same jobs rely on enrichment for their `blurb` and for the `primary_role` that F1 screens on. See ADR-007 — the two are one decision, in an order.

---

## Security & Secrets

| Variable | Purpose |
| :--- | :--- |
| `ANTHROPIC_API_KEY` | Claude API key, scoped to its own spend-capped workspace |
| `GOOGLE_SHEETS_CREDS` | Service account JSON |
| `SPREADSHEET_ID` | From the sheet URL |

Stored in GitHub Actions secrets (Settings → Secrets and variables → Actions). Never committed.

The service account needs Editor on the target sheet, the Sheets API enabled, and Sheets + Drive scopes.

The Anthropic key sits in its own Console workspace with a monthly spend limit and email alerts, so enrichment cannot overrun the budget even if a scraper returns ten times the usual volume.

---

## Deployment

### GitHub Actions

```yaml
name: Daily Job Scraper
on:
  schedule:
    - cron: '0 6 * * *'   # 06:00 UTC = 08:00 SAST
  workflow_dispatch:
    inputs:
      skip_linkedin:   { type: boolean, default: true }
      skip_enrichment: { type: boolean, default: false }

jobs:
  scrape-and-publish:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    permissions:
      contents: write     # to commit jobs.json
    defaults:
      run:
        working-directory: backend
```

The runner uses **Python 3.11**; local development is typically **3.12**. Avoid 3.12-only syntax — the tests pass locally and fail in CI otherwise.

The workflow commits `frontend/public/jobs.json` after every run, independent of whether the Sheets write succeeded.

### The board

Currently a manual deploy: `git pull` → `npm run build` in `frontend/` → drag `dist/` onto Netlify. Connecting Netlify directly to the repository needs organisation access to `CodeSpace-Team/job_scraper`, which is pending. Once granted, `netlify.toml` takes over and the manual step disappears.

### Repository layout

```
job_scraper/
├── .github/workflows/daily-scrape.yml
├── netlify.toml
├── backend/
│   ├── skills.json                  # F5's canonical list
│   ├── src/
│   │   ├── core/orchestrator.py
│   │   ├── pipeline/                # screening, levels, experience,
│   │   │                            #   roles, skills, dedupe, publish, qa
│   │   ├── scrapers/
│   │   ├── enrichment/enhancer.py
│   │   ├── writers/sheets.py
│   │   └── utils/
│   ├── scripts/                     # morning_check, decision_check
│   ├── tests/unit/  tests/integration/
│   └── data/cache/  data/qa/
├── frontend/
│   ├── public/jobs.json             # what the board renders
│   └── src/lib/  src/components/  src/hooks/
└── docs/
```

### Dependencies

| Library | Purpose |
| :--- | :--- |
| `python-jobspy` | Indeed and LinkedIn scraping |
| `requests`, `beautifulsoup4`, `tls-client` | OfferZen and PNet |
| `anthropic` | Claude API |
| `gspread`, `oauth2client` | Google Sheets |
| `pandas` | DataFrame handling inside JobSpy |

---

## Known Limits

Stated rather than tracked as work:

- **An advert an agency has rewritten in its own words is not caught as a duplicate.** Different title, company and text leaves nothing to match on without guessing, and fuzzy matching fails quietly in the direction that costs a graduate a job they never saw.
- **Years of experience is filled for roughly 35–43% of jobs.** Many ads simply do not state it.
- **About half the jobs reaching the board carry no level.** Expected — those ads say nothing about seniority, and they are kept deliberately, since silence usually means open to anyone.
- **The board's role-type filter mislabels some jobs.** Where neither title nor description names a track, the label falls back to the search term. Affects grouping, not which jobs appear. Being fixed.
- **The Jobs sheet holds several thousand rows from before F1 and F4 existed**, none screened. The board keeps its own list precisely so that history is not republished.

---

## Architecture Decision Records

### ADR-001: Claude Haiku for enrichment
**Context:** Structured metadata needs extracting from free-text job descriptions.
**Decision:** Claude Haiku.
**Rationale:** Lowest cost per token of the suitable models, fast, and reliable at structured output. Cost matters here — the daily budget is $1.

### ADR-002: LinkedIn disabled by default
**Context:** LinkedIn rate-limits and blocks scrapers aggressively.
**Decision:** Built but skipped in CI.
**Rationale:** Account suspension risk outweighs the extra listings. PNet is skipped for a different reason — TLS/HTTP2 failures specific to GitHub runners.

### ADR-003: Append-only writes to the Sheet
**Context:** Historical data has value and overwrites are unrecoverable.
**Decision:** Never overwrite an existing row.
**Rationale:** Enables trend analysis, prevents data loss, and makes a re-run safe.

### ADR-004: Rules decide the level, not the AI
**Context:** F4 deletes jobs based on their level.
**Decision:** Level comes from rules reading the ad. Where the rules cannot tell, the level is `unknown`. The AI's guess is stored as `ai_job_level` and never read.
**Rationale:** On the first live run the AI decided 81 of 255 levels, and 17 came out senior or above — including a plain "Test Analyst" called a *lead*. F4 was about to delete them. A guess is not a good enough reason to take a job away from someone, and an honest "don't know" is safe because F4 keeps unknowns.

### ADR-005: The board keeps its own `jobs.json`, not a copy of the Sheet
**Context:** The Sheet holds several thousand rows scraped before F1 and F4 existed.
**Decision:** `publish.py` maintains a separate running list, built only from screened jobs, pruned at 45 days.
**Rationale:** Publishing from the Sheet would put all the unscreened history back in front of graduates. Reading the Sheet back is also lossy — its rows are flattened — and would mean re-solving the legacy problem on every run instead of once.

### ADR-006: Salary is displayed, never filtered on
**Context:** A salary filter is an obvious thing for a job board to offer.
**Decision:** Not built.
**Rationale:** Checked the real data first. Zero of the 653 jobs on the first live run carried a salary figure — OfferZen and PNet never populate it, and Indeed only sometimes does. A filter that returns nothing is worse than no filter. Settled, not deferred.

### ADR-007: F1 screens on the AI's label, not on `role_type`
**Context:** F7 built a rules-based role classifier and deliberately did not wire it into F1 without evidence.
**Decision:** Measured on 19 August, and declined. `role_type` stays a label, not a gate.
**Rationale:** Over 671 jobs the two disagreed on 284. Four fifths of those disagreements came from the classifier's search-term fallback, which never looks at the job — it labels whatever Indeed returned for a given search as belonging to that track, so a waiter and a warehouse coordinator both acquired tech tracks. Swapping would have put ~284 non-tech jobs in front of graduates. The title tier disagreed only 3 times out of 284, so the rules are not the problem; the fallbacks are.

**Consequence:** this also blocks the enrichment cost saving. Skipping enrichment would remove the `primary_role` F1 depends on, and moving F1 off it is not available. The two are one decision, in an order.

### ADR-008: A Sheets failure must be catchable, not a process exit
**Context:** The writer originally called `sys.exit(1)` when the spreadsheet would not open.
**Decision:** Raise `RuntimeError` instead; the orchestrator catches it, saves a rescue copy, and continues to the Exclude tab and the board.
**Rationale:** `except Exception` does not catch `SystemExit`, so the orchestrator's error handling was skipped on exactly the runs where it mattered. A transient network blip cost a full run's work before this changed.

### ADR-009: The blocklist names roles, not industries
**Context:** Non-tech jobs leak through because occupational nouns mean different things in different industries — a *developer* writes software in tech and recipes in food.
**Decision:** Block the role, not the field. `actuarial analyst`, not `actuarial`. `product developer`, but excusing `software product developer`.
**Rationale:** Blocking a field drops real software jobs at non-software employers — an Actuarial Systems Developer at an insurer is genuinely a developer. This is the same rule the accept list already follows in refusing a bare "engineer" while taking "software engineer". The failure mode of over-blocking is invisible: a graduate never learns about the job they did not see, so both halves of every such rule are pinned by tests.

---

**Last updated:** 19 August 2026
**Maintainer:** CodeSpace Job Aggregator Team
