# South African Software Jobs Aggregator

Automated daily pipeline that scrapes **software jobs from South African job boards**, screens them down to roles a graduate in their first three years could realistically pursue, enriches them with AI-extracted metadata, and publishes them to both a Google Sheet and a public job board.

**Live board:**
[codespace-jobscraperboard](https://codespace-jobscraper.netlify.app/)

**Live sheet:** [View current jobs](https://docs.google.com/spreadsheets/d/1TPn_2Q-01Bx9rAzOp_nYt5sltHQWObjtKnxe9T73SOM)

**Build notes:** `docs/BUILD_NOTES.md` — what each feature does, why it was built that way, and what was deliberately left out.

The feature backlog (`Job_Scraper_Feature_Backlog_31072026.md`, CodeSpace internal) is **complete**: F1–F7 and F9 are all built, tested and verified against live runs. There is no F8 — a numbering skip in the brief.

---

## Status at a glance

| Piece                         | State                                                                                               |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| Indeed scraper (JobSpy)       | ✅ Active — search terms covering the current software role tracks                                   |
| AI enrichment (Claude Haiku)  | ✅ On by default — billed to a dedicated, spend-capped Anthropic workspace                           |
| Screening (F1 + F4)           | ✅ Non-software and above-cohort jobs dropped to an Exclude tab                                      |
| Levels & years (F2/F3)        | ✅ Read from the ad by rules; the AI never decides a level                                           |
| Skills (F5)                   | ✅ One canonical list of 130 skills, matched free before the AI runs                                 |
| Duplicates (F9)               | ✅ Three checks — same link, same job re-posted, agency vs employer                                  |
| Job board (F6)                | ✅ Built and live; deployed by hand pending Netlify org access                                       |
| OfferZen scraper (public API) | ⚠️ Active but intermittent — returned zero on at least one recent run. Non-fatal; the run continues |
| PNet scraper (JobSpy)         | ⏸️ Built, skipped in CI (TLS/HTTP2 errors in GitHub Actions)                                        |
| LinkedIn scraper              | ⏸️ Built, skipped in CI (rate limiting / ban risk)                                                  |

---

## How it works

Every day, GitHub Actions runs the pipeline in `.github/workflows/daily-scrape.yml`.

The pipeline collects software-related jobs, removes duplicates, extracts skills, enriches job data, classifies the role and experience requirements, applies the graduate-level screening rules, and publishes the resulting dataset.

```text
Indeed (JobSpy)  →  scrape         [PHASE 1]
OfferZen API     →
                    dedupe (F9)    [PHASE 1.5]
                    skills (F5)    [PHASE 1.7]
                    enrich         [PHASE 2]    Claude Haiku
                    label          [PHASE 2.4]  levels, years, software role
                    screen         [PHASE 2.5]  F1 + F4
                                        │
                        ┌───────────────┼────────────────┐
                        ▼               ▼                ▼
                  Jobs sheet      Exclude tab       jobs.json
                  [PHASE 3]       [PHASE 3.5]       [PHASE 3.7]
                  accepted jobs   excluded jobs     → Netlify board
```

The three write steps are independent on purpose. If the Jobs sheet write fails, the Exclude tab and the board can still publish, a rescue copy of the day's jobs is saved to `data/cache/combined_jobs_fallback.json`, and the run still reports red so the failure is not hidden.

### Pipeline stages

1. **Scrape** — software jobs are collected from supported South African job sources. Search coverage includes the current software role tracks as well as internship, graduate, learnership and junior-role terminology.
2. **Dedupe (F9)** — duplicate detection occurs before AI enrichment using multiple identifying signals, including application links, job identity, location and advert content.
3. **Skills (F5)** — a free offline keyword match against `skills.json` identifies recognised software skills before AI enrichment.
4. **Enrich** — jobs are sent to Claude Haiku in batches. Enrichment failures are non-fatal; jobs can continue through the pipeline without AI-generated enrichment.
5. **Label (F2/F3/F7)** — level, years of experience and software role track are determined from evidence in the job advert. Where the advert does not establish a level, the level is recorded as `unknown` rather than guessed. **No level is decided by the AI.**
6. **Screen (F1/F4)** — non-software roles are removed first, followed by roles outside the intended first-three-years graduate cohort. Nothing is silently deleted; excluded jobs are retained in the Exclude tab with a reason.
7. **Publish** — accepted jobs are written to the Jobs sheet, excluded jobs to the Exclude tab, and the public board dataset is updated through `frontend/public/jobs.json`.

---

## Software job scope

The platform is specifically focused on **software development and closely related software delivery roles**.

The current role tracks include:

* Software Development
* Mobile Development
* Data & BI
* QA / Testing
* Low-Code

These tracks represent the software-focused scope of the current MVP.

The project is **not intended to be a general technology-job aggregator**.

Roles outside the current software scope, including areas such as:

* Technical Support
* Cybersecurity / Security
* DevOps
* Cloud Infrastructure
* General IT
* Hardware
* Networking

are not currently part of the primary published job scope.

A technology appearing somewhere in a job description does not automatically make the role a software job. Role classification is based on the actual responsibilities and role language in the advert.

---

## Screening model

The primary purpose of screening is to identify software opportunities that are relevant to a graduate or early-career developer.

The screening process considers:

* software role relevance
* role level
* required years of experience
* seniority indicators
* evidence contained in the job advert

The system does not simply classify a job as "tech" and publish it.

### Apply

Generally aligned with the intended graduate cohort based on:

* software role relevance
* entry-level or junior positioning
* approximately two years or less of required experience

### Stretch

Potentially suitable depending on the candidate and the exact requirements.

This includes roles with:

* mid-level positioning
* up to approximately three years of experience
* insufficient evidence to confidently establish the required level

### Neither

Generally outside the intended first-three-years cohort because of:

* seniority
* lead/principal positioning
* substantially higher experience requirements

Each screened job receives a `tier` and `tier_reason` so that the decision remains explainable.

---

## Levels and experience

Level and experience classification is intentionally rule-based.

The system considers evidence such as:

* explicit seniority terminology
* stated years of experience
* relevant wording in the job description

The AI does not determine the final level.

When a job advert does not provide sufficient evidence, the system records the uncertainty rather than inventing a level.

This is important because job advertisements frequently contain ambiguous or incomplete information.

---

## Skills

The project maintains one canonical skills catalogue containing approximately 130 software and technical skills.

Skills are matched against the job description before AI enrichment.

The skills system supports:

* structured job metadata
* search relevance
* result ranking
* match explanations
* consistent skill naming

Skills do not currently act as a hard exclusion filter.

A job can therefore remain visible even if a particular skill is not present in the user's selected criteria.

---

## Google Sheet columns

### Jobs tab

The Jobs tab contains:

* Date Added to Sheet
* Date Job Posted
* Job Title
* Company
* Role Category
* Location
* Work Policy
* Required Skills
* Nice-to-Have Skills
* Years Exp
* Level
* Type
* Salary
* Summary
* Source
* Apply Link

### Exclude tab

The Exclude tab contains:

* Date Excluded
* Stage
* Reason
* Job Title
* Company
* Role Label
* Location
* Source
* Apply Link
* Description
* Needs Review

`Stage` distinguishes between the primary screening stages.

`Needs Review` identifies decisions that relied on softer evidence and may require manual inspection.

---

## Public job board

The public board is a Vite + React + Tailwind application.

It is designed around a search-first workflow rather than a general job-listing feed.

Users can search using criteria including:

* software role
* location
* work type
* skills
* experience level

The board supports:

* best-match sorting
* skill relevance
* match explanations
* job descriptions
* recent job listings
* filtering by software role track

The board does not currently require user authentication.

---

## Job freshness

The public board uses a current freshness policy rather than retaining jobs indefinitely.

Jobs are currently presented within a **seven-day freshness window**, with a minimum five-day floor from the date the job was first discovered.

This keeps the public board focused on opportunities that are still reasonably actionable.

Historical operational data remains available separately in the Google Sheet.

---

## Repository layout

```text
job_scraper/
├── .github/workflows/daily-scrape.yml   # Daily pipeline
├── netlify.toml                         # Netlify build configuration
├── backend/
│   ├── run.sh                           # Local runner
│   ├── skills.json                      # Canonical skills list
│   ├── src/
│   │   ├── main.py                      # Pipeline entry point
│   │   ├── core/
│   │   │   └── orchestrator.py          # Pipeline orchestration
│   │   ├── pipeline/
│   │   │   ├── screening.py             # Software screening
│   │   │   ├── levels.py                # Level rules
│   │   │   ├── experience.py            # Experience extraction
│   │   │   ├── roles.py                 # Software role classification
│   │   │   ├── skills.py                # Skills matching
│   │   │   ├── dedupe.py                # Duplicate detection
│   │   │   ├── publish.py               # Board publication
│   │   │   └── qa.py                    # QA tooling
│   │   ├── scrapers/                    # Source scrapers
│   │   ├── enrichment/
│   │   │   └── enhancer.py              # AI enrichment
│   │   ├── writers/
│   │   │   └── sheets.py                # Google Sheets writer
│   │   └── utils/                       # Shared utilities
│   ├── scripts/
│   │   ├── morning_check.py             # Daily operational check
│   │   └── decision_check.py            # Evidence-based decision checks
│   ├── tests/
│   │   ├── unit/
│   │   └── integration/
│   └── data/                            # Run cache and QA output
│
├── frontend/
│   ├── public/
│   │   └── jobs.json                    # Published board dataset
│   └── src/                             # React application
│
└── docs/
    └── BUILD_NOTES.md                   # Detailed development history
```

---

# Running the pipeline

All backend commands assume that the working directory is `backend/`.

## Full pipeline

The full pipeline can be run locally using the same major stages as the scheduled workflow.

```bash
cd backend

export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_SHEETS_CREDS='{"type":"service_account",...}'
export PYTHONPATH=.

python -m src.main --spreadsheet-id "<SHEET_ID>" --skip-linkedin --skip-pnet
```

Useful options include:

* `--skip-offerzen`
* `--skip-indeed`
* `--skip-linkedin`
* `--skip-pnet`
* `--skip-enrichment`
* `--indeed-results N`
* `--sheet-name NAME`

---

## Individual pipeline components

Individual components can also be executed for development and troubleshooting.

```bash
cd backend

python -m src.scrapers.offerzen -o data/cache/offerzen_jobs.json

python -m src.scrapers.indeed --results 50 --days 14

python -m src.enrichment.enhancer \
  -i data/cache/offerzen_jobs.json

python -m src.writers.sheets \
  -i data/cache/combined_jobs_fallback.json \
  -s "<SHEET_ID>"
```

The fallback dataset can be used to recover a failed Jobs-sheet publication.

The writer is append-only and performs duplicate checks, so re-running the publication step should not create duplicate rows.

---

# Testing

Backend tests:

```bash
cd backend
python -m pytest -q
```

Frontend tests:

```bash
cd frontend
npm test
```

The repository contains unit and integration coverage for the backend pipeline as well as tests for the public job board.

---

# Daily and weekly checks

The pipeline produces its own operational data, but human QA remains important for evaluating the quality of classification and screening decisions.

## Daily check

`morning_check.py` provides a high-level health check of a completed pipeline run.

It evaluates:

* job counts through each stage
* duplicate-processing fingerprints
* enrichment status
* level classification
* screening results
* agreement between generated datasets

The purpose is to identify pipeline regressions that may not be visible from the final job count alone.

For example, a normal-looking number of jobs could still indicate that a pipeline stage failed to execute.

---

## Weekly QA

The project includes additional review tooling for:

* level classification
* excluded jobs
* software/non-software classification

These reviews are used to validate the deterministic screening rules against real job advertisements.

The detailed methodology and historical QA findings are documented in:

[`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md)

---

# Deploying the board

The frontend is currently deployed manually.

```bash
git pull

cd frontend
npm run build
```

The generated `frontend/dist` directory is then deployed to Netlify.

Direct repository deployment requires organisation access to:

`CodeSpace-Team/job_scraper`

Once the required access is available, Netlify can be connected directly to the repository and deployments can become automatic.

---

# Setup

A new deployment requires three main external services.

## Google Sheets

1. Create a Google Cloud project.
2. Enable the Google Sheets API.
3. Create a service account.
4. Download the service-account credentials.
5. Share the target Google Sheet with the service-account email as an Editor.

## Anthropic

Create an Anthropic API key for AI enrichment.

The recommended production setup is a dedicated workspace with:

* monthly spend limit
* usage monitoring
* email alerts

This prevents unexpected enrichment costs.

## GitHub Actions

The following repository secrets are required:

* `ANTHROPIC_API_KEY`
* `GOOGLE_SHEETS_CREDS`
* `SPREADSHEET_ID`

---

# Cost

The MVP is designed to operate at relatively low infrastructure cost.

| Service           | Current cost profile                   |
| ----------------- | -------------------------------------- |
| GitHub Actions    | Within applicable free usage           |
| Google Sheets API | Free                                   |
| Netlify           | Free tier                              |
| Claude enrichment | Approximately $0.50–$1.00/day estimate |

The current estimated AI cost is approximately:

**$15–$30 per month**

This is an estimate based on model pricing and expected job volume rather than an invoice amount.

Cost controls include:

* deduplicating before AI enrichment
* free skill matching before AI
* using a suitable low-cost model
* limiting search volume
* spreading search coverage across runs
* applying an Anthropic workspace spending limit

---

# Monitoring and troubleshooting

The GitHub Actions **Actions** tab should be the first place to inspect when a scheduled run behaves unexpectedly.

The healthy pipeline should progress through:

```text
PHASE 1
PHASE 1.5
PHASE 1.7
PHASE 2
PHASE 2.4
PHASE 2.5
PHASE 3
PHASE 3.5
PHASE 3.7
```

Common operational issues include:

### Google Sheets 503

Usually indicates a temporary Google-side availability issue.

The pipeline retries the operation and retains the fallback dataset.

The Exclude tab and public board can still publish independently.

### Google Sheets 403 / 404

Usually indicates a credentials or permissions problem.

Check:

* service-account access
* `GOOGLE_SHEETS_CREDS`
* `SPREADSHEET_ID`

### Enrichment skipped

If scheduled runs unexpectedly skip enrichment, inspect the enrichment condition in `.github/workflows/daily-scrape.yml`.

### No jobs scraped

Usually indicates a source or scraper problem.

Check the relevant source logs and JobSpy/source availability.

### Anthropic API error

Check:

* API key
* workspace status
* spending limit
* API availability

Jobs can continue through the pipeline without enrichment, but metadata quality will be reduced.

### AI determining a level

This should not occur.

Level classification is intentionally deterministic and should not fall back to AI.

### Sudden reduction in job volume

A significant drop should be treated as a potential scraper or source failure until investigated.

---

# Known limitations

The current MVP has several known limitations.

### Rewritten agency advertisements

An agency can completely rewrite a job advertisement, changing the title, company representation and advert text.

Such listings may evade duplicate detection because there is insufficient reliable evidence to establish that they represent the same original opportunity.

### Experience coverage

Years-of-experience information is incomplete because many software job advertisements do not explicitly state a required number of years.

The system deliberately avoids inventing experience requirements.

### Missing levels

Some jobs do not explicitly identify their seniority.

These jobs are retained with an `unknown` level rather than being automatically excluded.

### Role classification ambiguity

Some job descriptions contain overlapping responsibilities or insufficient role information.

The classifier therefore uses evidence from the title and description rather than relying solely on the technology or search term that discovered the listing.

### Historical Jobs sheet

The Jobs sheet contains historical records from earlier pipeline versions.

Some older rows were created before the current F1/F4 screening model was implemented.

The public board maintains its own current dataset and therefore does not automatically republish the historical sheet contents.

### Source availability

PNet and LinkedIn are currently not active in the scheduled workflow.

This limits the breadth of job-source coverage.

### Manual deployment

Netlify deployment is still manual until repository integration is enabled.

---

# MVP boundaries

Several capabilities were intentionally excluded from the MVP.

There is currently no:

* production database
* backend application API
* user authentication
* user profiles
* saved jobs
* application tracking
* saved searches
* personalised job alerts
* email notification system
* personalised recommendations
* administrative dashboard
* production user analytics

These are **post-MVP capabilities**, not unfinished MVP requirements.

The MVP focuses on establishing a reliable software-job discovery, screening, enrichment and publication pipeline before introducing persistent user-specific functionality.

---

# Post-MVP direction

The next phase should move the project from a software-job aggregation pipeline toward a personalised software-job discovery platform.

The logical progression is:

```text
Current MVP
Software Job Aggregation
        ↓
Production Database
        ↓
Backend API
        ↓
User Accounts
        ↓
User Preferences
        ↓
Saved Jobs
        ↓
Application Tracking
        ↓
Saved Searches
        ↓
Email Alerts
        ↓
Personalised Matching
        ↓
Administration & Analytics
```

## Priority 1 — Production database

Introduce a production database as the central source of truth for application data.

This should eventually contain:

* jobs
* sources
* users
* user preferences
* saved jobs
* applications
* alerts
* audit records

Google Sheets can remain as an operational or administrative interface where useful.

## Priority 2 — Backend API

Introduce an application backend between the database and frontend.

This will allow the platform to move beyond a static `jobs.json` publication model.

## Priority 3 — User accounts

Introduce authentication and persistent user profiles.

Users should eventually be able to define:

* software role interests
* skills
* experience
* location
* work preferences
* job-search preferences

## Priority 4 — Saved jobs

Allow users to save relevant software opportunities and maintain a personal shortlist.

## Priority 5 — Application tracking

Allow users to track their progress through the application process.

Potential statuses include:

* Saved
* Interested
* Applied
* Interview
* Offer
* Closed

## Priority 6 — Saved searches and alerts

Allow users to create persistent searches and receive notifications when matching software jobs are discovered.

## Priority 7 — Personalised matching

Use the existing screening and enrichment foundation to compare individual user preferences and capabilities against newly discovered software jobs.

The matching system should remain explainable rather than becoming an opaque AI score.

## Priority 8 — Administration and analytics

Introduce operational visibility into:

* source health
* job volumes
* duplicate rates
* screening results
* AI usage
* publishing status
* user activity
* notification delivery

## Priority 9 — Source expansion

Additional software-job sources can be introduced where they provide meaningful increases in:

* job coverage
* data quality
* geographic coverage
* role diversity

Source expansion should continue to respect source terms, access restrictions and reliability.

---

# Project principles

Future development should preserve the core principles established during the MVP.

### Software-first scope

The platform should remain focused on software employment opportunities rather than becoming a generic technology-job aggregator.

### Evidence over inference

Classification should be based on information contained in the actual job advertisement wherever possible.

### Deterministic rules for critical decisions

Important screening decisions should remain predictable and explainable.

### AI as enrichment

AI should enhance the dataset rather than replace deterministic logic where deterministic logic is more reliable.

### Auditability

Excluded jobs and important processing decisions should remain traceable.

### Live-data validation

Changes to classification and screening rules should be evaluated against real job data before being adopted.

### Incremental product development

The system should evolve through measurable product stages rather than attempting to build a complete recruitment platform at once.

### User value

Future features should ultimately reduce the time and effort required for a software candidate to discover, evaluate, save and act on relevant opportunities.

---

# Documentation

Detailed implementation history is maintained separately in:

[`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md)

The build notes contain:

* feature development history
* implementation decisions
* QA findings
* production issues
* fixes
* screening experiments
* data observations
* operational notes

The README describes the current product and system state, while the build notes preserve the detailed engineering history.

---

# Final MVP assessment

The MVP establishes the core software-job discovery pipeline:

**Discover → Deduplicate → Enrich → Classify → Screen → Publish**

The system automates the repetitive process of finding software opportunities while maintaining deterministic screening rules and an auditable exclusion process.

The current architecture deliberately prioritises simplicity, low operating cost and rapid development.

The next major architectural transition should therefore be the move from the current operational publishing model toward a **production database and application backend**.

Once that foundation exists, user accounts, saved jobs, application tracking, saved searches, alerts and personalised software-job matching can be introduced without fundamentally redesigning the existing discovery and screening pipeline.

The MVP should therefore be viewed as the **data, classification and screening foundation for a larger personalised software-job platform**.

---

# Maintainer

**CodeSpace**

Maintained for CodeSpace graduates seeking software development and related software opportunities in South Africa.

---

# License / Usage

This project is intended for educational and job-search purposes.

It is not intended for unrestricted commercial redistribution of scraped job data or source content.

Future production use should continue to evaluate the terms, policies and technical restrictions of every external job source integrated into the platform.
