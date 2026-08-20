# South African Tech Job Aggregator

Automated daily pipeline that scrapes software and tech jobs from South African job boards, screens them down to roles a graduate in their first three years could actually get, enriches them with AI-extracted metadata, and publishes them to both a Google Sheet and a public job board.

**Live board:** 
[codespace-jobscraperboard](https://codespace-jobscraper.netlify.app/)
**Live sheet:** [View current jobs](https://docs.google.com/spreadsheets/d/1TPn_2Q-01Bx9rAzOp_nYt5sltHQWObjtKnxe9T73SOM)
**Build notes:** `docs/BUILD_NOTES.md` — what each feature does, why it was built that way, and what was deliberately left out.

The feature backlog (`Job_Scraper_Feature_Backlog_31072026.md`, CodeSpace internal) is **complete**: F1–F7 and F9 are all built, tested and verified against live runs. There is no F8 — a numbering skip in the brief.

## Status at a glance

| Piece | State |
|---|---|
| Indeed scraper (JobSpy) | ✅ Active — 32 search terms/day across all seven role tracks |
| AI enrichment (Claude Haiku) | ✅ On by default — billed to a dedicated, spend-capped Anthropic workspace |
| Screening (F1 + F4) | ✅ Non-tech and above-cohort jobs dropped to an Exclude tab |
| Levels & years (F2/F3) | ✅ Read from the ad by rules; the AI never decides a level |
| Skills (F5) | ✅ One canonical list of 130 skills, matched free before the AI runs |
| Duplicates (F9) | ✅ Three checks — same link, same job re-posted, agency vs employer |
| Job board (F6) | ✅ Built and live; deployed by hand pending Netlify org access |
| OfferZen scraper (public API) | ⚠️ Active but intermittent — returned zero on at least one recent run. Non-fatal; the run continues |
| PNet scraper (JobSpy) | ⏸️ Built, skipped in CI (TLS/HTTP2 errors in GitHub Actions) |
| LinkedIn scraper | ⏸️ Built, skipped in CI (rate limiting / ban risk) |

## How it works

Every day at 06:00 UTC (08:00 SAST), GitHub Actions runs the pipeline in `.github/workflows/daily-scrape.yml`. A typical run takes about 18 minutes, most of it AI enrichment.

```
Indeed (JobSpy)  →  scrape         [PHASE 1]    ~680 jobs
OfferZen API     →
                    dedupe (F9)    [PHASE 1.5]  ~660 unique
                    skills (F5)    [PHASE 1.7]  free keyword match, no AI
                    enrich         [PHASE 2]    Claude Haiku
                    label          [PHASE 2.4]  levels, years, role tracks
                    screen         [PHASE 2.5]  F1 + F4  →  ~170 kept
                                        │
                        ┌───────────────┼────────────────┐
                        ▼               ▼                ▼
                  Jobs sheet      Exclude tab       jobs.json
                  [PHASE 3]       [PHASE 3.5]       [PHASE 3.7]
                  append-only     with reasons      → Netlify board
```

The three write steps are independent on purpose. If the Jobs sheet write fails, the Exclude tab and the board still publish, a rescue copy of the day's jobs is saved to `data/cache/combined_jobs_fallback.json`, and the run still reports red so the failure is not hidden.

1. **Scrape** — Indeed via JobSpy across 32 search terms covering all seven role tracks, plus internship/learnership/graduate wording. The full set of ~40 terms is split across even and odd days. OfferZen's public API is paginated and filtered to SA locations.
2. **Dedupe (F9)** — three checks: exact link, then title+company+city for re-posts under a new link, then title+city+advert text for the same role posted by both an agency and the employer. Runs before the AI, so a job listed in three cities is enriched once rather than three times.
3. **Skills (F5)** — a free offline keyword match against `skills.json` before the AI is involved, so the AI has less to work out.
4. **Enrich** — jobs are sent to Claude Haiku in batches. Failures are non-fatal: jobs continue un-enriched rather than blocking the run.
5. **Label (F2/F3/F7)** — level, years of experience and role track are decided by rules reading the ad's own words. Where the ad says nothing, the level is recorded as `unknown` rather than guessed. **No level is ever decided by the AI** — that was tried, and it labelled a plain "Test Analyst" a *lead*.
6. **Screen (F1/F4)** — drops non-tech roles, then anything above the first three years. Nothing is deleted; every drop lands in the Exclude tab with its reason.
7. **Publish** — new jobs are appended to the Jobs sheet, drops to the Exclude tab, and the board's `frontend/public/jobs.json` is merged and committed. Board entries age out after 45 days.

### Google Sheet columns

**Jobs tab (16):** Date Added to Sheet · Date Job Posted · Job Title · Company · Role Category · Location · Work Policy · Required Skills · Nice-to-Have Skills · Years Exp · Level · Type · Salary · Summary · Source · Apply Link

**Exclude tab (11):** Date Excluded · Stage · Reason · Job Title · Company · Role Label · Location · Source · Apply Link · Description · Needs Review

`Stage` distinguishes `F1 non-tech` from `F4 above cohort`. `Needs Review` marks a drop resting on softer evidence, so a review can go straight to the doubtful ones.

## Repository layout

```
job_scraper/
├── .github/workflows/daily-scrape.yml   # Daily pipeline (GitHub Actions)
├── netlify.toml                         # Netlify build config
├── backend/
│   ├── run.sh                           # Convenience runner for local use
│   ├── skills.json                      # The one official skills list (F5)
│   ├── src/
│   │   ├── main.py                      # CLI entry point (python -m src.main)
│   │   ├── core/orchestrator.py         # The phases above, in order
│   │   ├── pipeline/
│   │   │   ├── screening.py             # F1 + F4 keep-or-drop
│   │   │   ├── levels.py                # F2 level rules
│   │   │   ├── experience.py            # F3 years-of-experience extraction
│   │   │   ├── roles.py                 # F7 seven tracks + search terms
│   │   │   ├── skills.py                # F5 matcher and canonicaliser
│   │   │   ├── dedupe.py                # F9 three duplicate checks
│   │   │   ├── publish.py               # F6 board jobs.json merge/prune
│   │   │   └── qa.py                    # The three weekly review sheets
│   │   ├── scrapers/                    # offerzen, indeed, linkedin, pnet
│   │   ├── enrichment/enhancer.py       # Claude AI enrichment
│   │   ├── writers/sheets.py            # Jobs + Exclude tab writer
│   │   └── utils/                       # logging, retry, dates, text, io, http
│   ├── scripts/
│   │   ├── morning_check.py             # Reads a run's files, prints one verdict
│   │   └── decision_check.py            # Evidence for parked design decisions
│   ├── tests/unit/  tests/integration/  # 489 tests
│   └── data/                            # Run cache and QA output
├── frontend/                            # The job board (Vite + React + Tailwind)
│   ├── public/jobs.json                 # What the board renders, committed daily
│   └── src/                             # lib/filters, lib/sort, components, hooks
└── docs/                                # Build notes, setup guide, architecture
```

All backend commands below assume you're in `backend/` — `cd backend` first.

## Running it

### Full pipeline (as CI runs it)

```bash
cd backend
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_SHEETS_CREDS='{"type":"service_account",...}'
export PYTHONPATH=.

python -m src.main --spreadsheet-id "<SHEET_ID>" --skip-linkedin --skip-pnet
```

Useful flags: `--skip-offerzen`, `--skip-indeed`, `--skip-linkedin`, `--skip-pnet`, `--skip-enrichment`, `--indeed-results N`, `--sheet-name NAME`.

### Individual pieces

```bash
cd backend
python -m src.scrapers.offerzen -o data/cache/offerzen_jobs.json
python -m src.scrapers.indeed --results 50 --days 14
python -m src.enrichment.enhancer -i data/cache/offerzen_jobs.json
python -m src.writers.sheets -i data/cache/combined_jobs_fallback.json -s "<SHEET_ID>"
```

That last one is also how to recover a failed Jobs-sheet write: the fallback file holds the day's screened jobs, and the writer is append-only and deduplicated, so re-running it cannot double up rows.

### Tests

```bash
cd backend && python -m pytest -q          # 489 backend tests
cd frontend && npm test                    # 62 board tests
```

## The daily and weekly checks

The pipeline reports its own numbers, but two things need a person: whether the levels are right, and whether anything is reaching the board that should not be.

**Every morning** — download the run's artifact from the Actions tab, unzip it over `backend/data/cache/`, then:

```bash
The commands
# 1. Download the artifact
# Actions -> the run -> "Artifacts" at the bottom -> job-data-<number>
# It lands in Downloads as a .zip

# 2. Unzip it over data/cache
cd ~/job_scraper/backend
rm -rf data/cache/*.json
unzip -o ~/Downloads/job-data-<number e.g 133>.zip -d data/cache/

# 3. Run the script to check the results
export PYTHONPATH=.
python -m scripts.morning_check

# Example: Sample of what it prints on a healthy run:

WHAT HAPPENED TO THE JOBS
  scraped, after duplicates removed  6
  enriched by the AI                 6
  levels and years worked out        6
  dropped by the screens             3
  REACHING THE BOARD                 3

WHY JOBS WERE DROPPED
  F4 above cohort          2
  F1 non-tech              1
  flagged for review       0

And on a broken one:

3 THING(S) TO LOOK AT:

  ✗ F9 duplicates: no job in combined_jobs_leveled.json has 'duplicate_count' — 
     that step did not run
  ✗ F2 levels: no job in combined_jobs_leveled.json has 'level_source' — 
     that step did not run
  ✗ excluded_jobs.json holds 1, but 3 jobs in combined_jobs_leveled.json are marked as dropped 
     — the two files disagree

```

It prints one page: how many jobs survived each stage, whether the numbers agree with each other, and whether anything looks wrong enough to investigate. It also checks that each feature left its fingerprint on the data — if F9 ran, jobs carry a duplicate count; if F2 ran, they carry a level source. A missing fingerprint means the runner was on older code, which no amount of reading the counts would tell you.

**Weekly** — three review sheets, all written to `data/qa/` and filled in by hand:

```bash
python -m src.pipeline.qa                                    # F2: are the levels right? (target 18/20)
python -m src.pipeline.qa -i data/cache/excluded_jobs.json   # F4: was anything wrongly dropped?
python -m src.pipeline.qa --check tech --size 60             # F1: any non-tech jobs slipping through?
```

The third measures F1's target of *fewer than 5 in every 100 rows*. It samples 60 rather than 20 on purpose — a 5% target measured over 20 jobs can only produce 0%, 5% or 10%, so one unlucky draw would decide it. Rows marked `look` are the ones whose advert genuinely needs opening; the rest can be judged from the title.

Keep the filled-in files. They are the record that the check was done.

## Deploying the board

The board is currently deployed by hand each morning:

```bash
git pull
cd frontend && npm run build
# drag frontend/dist/ onto Netlify
```

Connecting Netlify directly to the repository needs organisation access to `CodeSpace-Team/job_scraper`, which is still pending. Once granted, every push deploys automatically and this step disappears.

## Setup (new deployment)

1. **Google Cloud:** create a project, enable the Sheets API, create a service account, download its JSON key, and share the target sheet with the service-account email (Editor).
2. **Anthropic:** create an API key. Recommended: put the key in its own Console workspace with a monthly spend limit and email alerts, so enrichment can never overrun the budget (this is how the production key is set up).
3. **GitHub secrets** (repo Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY` — the workspace-scoped Claude key
   - `GOOGLE_SHEETS_CREDS` — the full service-account JSON
   - `SPREADSHEET_ID` — from the sheet URL

## Cost

- **GitHub Actions:** ~18 min/day, within the free tier.
- **Google Sheets API and Netlify:** free.
- **Claude enrichment:** the significant one. Roughly **$0.50–$1.00/day**, or **$15–30/month**, against a hard workspace spend cap. That is an estimate from the model's pricing and the jobs per run, not a figure read off an invoice — check the Anthropic console for the real number.

Four things keep it there: duplicates are removed *before* the AI sees them, skills are matched free from the job text first, the cheapest suitable model is used, and the ~40 search terms are spread across two days rather than all running every morning.

There is headroom if it ever needs cutting. Just over half of jobs get enough skills from the free keyword match alone and could skip enrichment entirely. That is deliberately not done, because those same jobs rely on enrichment for their summary and for the role label F1 screens on — see *Two decisions closed by counting* in the build notes.

## Monitoring & troubleshooting

Check runs under the repo's **Actions** tab. The healthy sequence is `[PHASE 1]` through `[PHASE 3.7]`, ending with the board's publish summary and a `chore: publish today's jobs.json` commit.

- **`✗ Sheets write error: ... APIError: [503]`** — a Google-side outage, not a credentials problem, despite the generic hints printed alongside it. Retried automatically now. The Exclude tab and board still publish; the day's jobs are in `combined_jobs_fallback.json`.
- **"Could not open spreadsheet"** with a 403 or 404 — that one *is* real: the service account lost Editor access, or `GOOGLE_SHEETS_CREDS`/`SPREADSHEET_ID` is wrong.
- **`ENRICHMENT SKIPPED`** in a scheduled run — the workflow's enrichment condition has regressed; check `daily-scrape.yml`.
- **"No jobs scraped from any source"** — a board changed its markup or JobSpy needs updating (`pip install --upgrade python-jobspy`).
- **`✗ API error` during enrichment** — bad/expired Anthropic key or the workspace spend cap was hit; jobs still publish, just un-enriched.
- **A level decided by "ai" in the `[PHASE 2.4]` breakdown** — should never happen. That fallback was removed on purpose; if one appears it has crept back in.
- **Sudden drop in daily job counts** — usually a scraper silently failing; check its section of the log.

## Known limits

Stated honestly rather than tracked as work:

- **An advert an agency has rewritten in its own words is not caught as a duplicate.** Different title, different company, different text — nothing left to match on without guessing, and fuzzy matching fails quietly in the direction that costs a graduate a job they never saw.
- **Years of experience is filled for roughly 35–43% of jobs.** Plenty of ads simply do not state it, and the only way to reach 100% would be to invent numbers.
- **About half the jobs reaching the board have no level.** Expected: those ads say nothing about seniority, and they are kept deliberately, since silence usually means open to anyone.
- **The board's role-type filter mislabels some jobs.** Where neither the title nor the description names a track, the label falls back to whichever search found the job — so a data engineer can appear under DevOps. It affects grouping, not which jobs appear. Being fixed.
- **The Jobs sheet still holds several thousand rows from before F1 and F4 existed**, none of them screened. The board keeps its own separate list precisely so that history is not republished. Cleaning up the sheet's back-catalogue is out of scope.

## Data privacy and ethics

All data is from publicly available job postings; no personal information is collected. OfferZen is accessed via its public API; Indeed via standard scraping through JobSpy. LinkedIn scraping stays disabled to avoid TOS violations.

## License

For educational and job-search purposes for CodeSpace graduates. Not for commercial redistribution.

---

**Maintained by CodeSpace for graduates seeking tech opportunities in South Africa.**
