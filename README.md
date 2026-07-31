# South African Tech Job Aggregator

Automated daily pipeline that scrapes software and tech jobs from South African job boards, enriches them with AI-extracted metadata (skills, level, role category), and publishes them to a public Google Sheet for CodeSpace graduates.

**Live sheet:** [View current jobs](https://docs.google.com/spreadsheets/d/1TPn_2Q-01Bx9rAzOp_nYt5sltHQWObjtKnxe9T73SOM)
**Feature backlog:** see `Job_Scraper_Feature_Backlog_31072026.md` (CodeSpace internal) for the current roadmap.

## Status at a glance

| Piece | State |
|---|---|
| OfferZen scraper (public API) | ✅ Active in daily run |
| Indeed scraper (JobSpy) | ✅ Active in daily run |
| AI enrichment (Claude Haiku) | ✅ **On by default since 31 Jul 2026** — billed to a dedicated, spend-capped Anthropic workspace |
| PNet scraper (JobSpy) | ⏸️ Built, but skipped in the daily workflow (TLS/HTTP2 errors in GitHub Actions) |
| LinkedIn scraper | ⏸️ Built, but skipped in the daily workflow (aggressive rate limiting / ban risk) |

## How it works

Every day at 06:00 UTC (08:00 SAST), GitHub Actions runs the pipeline defined in `.github/workflows/daily-scrape.yml`:

```
OfferZen API    →
Indeed (JobSpy) →  Scrape  →  AI enrichment  →  Dedup by URL  →  Google Sheet
                              (Claude Haiku)                      (append-only)
```

1. **Scrape** — OfferZen's public API is paginated in full and filtered to SA locations; Indeed is searched via JobSpy across six developer-focused terms with a 30-day window. Raw results are cached as JSON under `data/cache/`.
2. **Enrich** — jobs are sent to Claude (Haiku) in batches of 5. For each job it extracts: normalized role category, required skills, nice-to-have skills, years of experience (when stated), level (intern/junior/mid/senior/lead/principal), and a one-sentence summary. Failures are non-fatal: jobs continue un-enriched rather than blocking the run.
3. **Publish** — new jobs (by URL) are appended to the sheet with formatting; existing rows are never overwritten.

### Google Sheet columns (16)

Date Added to Sheet · Date Job Posted · Job Title · Company · Role Category · Location · Work Policy · Required Skills · Nice-to-Have Skills · Years Exp · Level · Type · Salary · Summary · Source · Apply Link

## Repository layout

```
job_scraper/
├── .github/workflows/daily-scrape.yml   # Daily pipeline (GitHub Actions)
├── run.sh                               # Convenience runner for local use
├── src/
│   ├── main.py                          # CLI entry point (python -m src.main)
│   ├── core/orchestrator.py             # Pipeline: scrape → enrich → publish
│   ├── scrapers/
│   │   ├── offerzen.py                  # OfferZen public API
│   │   ├── indeed.py                    # Indeed via JobSpy
│   │   ├── linkedin.py                  # LinkedIn via JobSpy (skipped in CI)
│   │   └── pnet.py                      # PNet (skipped in CI)
│   ├── enrichment/enhancer.py           # Claude AI enrichment
│   ├── writers/sheets.py                # Google Sheets writer (append-only, dedup)
│   └── utils/                           # logging, retry, dates, text, io, http
├── tests/
│   ├── unit/                            # utils tests
│   └── integration/                     # per-scraper tests
└── docs/                                # setup guide, architecture, quick start
```

## Running it

### Full pipeline (as CI runs it)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_SHEETS_CREDS='{"type":"service_account",...}'
export PYTHONPATH=.

python -m src.main --spreadsheet-id "<SHEET_ID>" --skip-linkedin --skip-pnet
```

Useful flags: `--skip-offerzen`, `--skip-indeed`, `--skip-linkedin`, `--skip-pnet`, `--skip-enrichment`, `--indeed-results N`, `--sheet-name NAME`.

### Individual pieces

```bash
python -m src.scrapers.offerzen -o data/cache/offerzen_jobs.json
python -m src.scrapers.indeed --results 50 --days 14
python -m src.enrichment.enhancer -i data/cache/offerzen_jobs.json
python -m src.writers.sheets -i data/cache/*_enriched.json -s "<SHEET_ID>"
```

### Tests

```bash
pip install -r requirements.txt
pytest tests/
```

## Setup (new deployment)

1. **Google Cloud:** create a project, enable the Sheets API, create a service account, download its JSON key, and share the target sheet with the service-account email (Editor).
2. **Anthropic:** create an API key. Recommended: put the key in its own Console workspace with a monthly spend limit and email alerts, so enrichment can never overrun the budget (this is how the production key is set up).
3. **GitHub secrets** (repo Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY` — the workspace-scoped Claude key
   - `GOOGLE_SHEETS_CREDS` — the full service-account JSON
   - `SPREADSHEET_ID` — from the sheet URL

## Cost

- **GitHub Actions:** within the free tier (~8 min/day).
- **Claude enrichment:** Haiku at ~$0.08 per 100 jobs → roughly **$2–5/month** at current volume, hard-capped by the workspace spend limit.
- **Google Sheets API:** free.

## Monitoring & troubleshooting

Check runs under the repo's **Actions** tab. In the log, the healthy sequence is `[PHASE 1] SCRAPING` → `[PHASE 2] AI ENRICHMENT` (with `Enriching jobs N–M...` lines) → `✓ SHEETS UPDATE COMPLETE`.

- **`ENRICHMENT SKIPPED`** in a scheduled run — the workflow's enrichment condition has regressed; check `daily-scrape.yml`.
- **"No jobs scraped from any source"** — a board changed its markup or JobSpy needs updating (`pip install --upgrade python-jobspy`).
- **"Could not open spreadsheet"** — service account lost Editor access, or `GOOGLE_SHEETS_CREDS`/`SPREADSHEET_ID` is wrong.
- **`✗ API error` during enrichment** — bad/expired Anthropic key or the workspace spend cap was hit; jobs still publish, just un-enriched.
- **Sudden drop in daily job counts** — usually a scraper silently failing; check its section of the log.

## Known gaps (tracked in the feature backlog)

- Years Exp is only filled when the ad states a number — a description-parsing pass is planned.
- No relevance filter yet: broad Indeed matching lets non-tech roles (construction, mining, warehouse) into the sheet.
- Search terms are developer-centric; QA, data, IT support, BA and internship roles are planned additions.
- Dedup is exact-URL only, so reposted jobs can appear twice.

## Data privacy and ethics

All data is from publicly available job postings; no personal information is collected. OfferZen is accessed via its public API; Indeed via standard scraping through JobSpy. LinkedIn scraping stays disabled to avoid TOS violations.

## License

For educational and job-search purposes for CodeSpace graduates. Not for commercial redistribution.

---

**Maintained by CodeSpace for graduates seeking tech opportunities in South Africa.**
