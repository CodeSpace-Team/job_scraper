# Architecture Documentation — South African Tech Job Aggregator

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Details](#component-details)
4. [Data Models](#data-models)
5. [Data Flow](#data-flow)
6. [Error Handling & Resilience](#error-handling--resilience)
7. [Performance Considerations](#performance-considerations)
8. [Security & Secrets Management](#security--secrets-management)
9. [Deployment Architecture](#deployment-architecture)
10. [Future Improvements](#future-improvements)

---

## System Overview

The **South African Tech Job Aggregator** is an automated daily scraping pipeline that collects software development job listings from multiple South African job boards, enriches them with AI-extracted metadata, and publishes them to a public Google Sheet for CodeSpace graduates.

### Core Objectives

| Objective | Description |
| :--- | :--- |
| **Daily Automation** | Runs every day at 8 AM SAST without manual intervention |
| **Multi-Source Aggregation** | Collects jobs from OfferZen, Indeed, and PNet |
| **AI Enrichment** | Extracts skills, seniority levels, and summaries using Claude |
| **Public Accessibility** | Publishes to a Google Sheet with filtering and sorting |
| **Historical Tracking** | Append-only updates preserve historical job data |

### Key Metrics

| Metric | Value |
| :--- | :--- |
| **Daily Job Volume** | 500–700 jobs |
| **Runtime** | 8–12 minutes (with PNet details) |
| **Cost** | ~$2.40/month (Anthropic API) |
| **Availability** | 99% (with fallbacks) |

---

## Architecture Diagram
┌─────────────────────────────────────────────────────────────────────────────────┐
│ GITHUB ACTIONS (Daily Trigger) │
│ 6:00 AM UTC / 8 AM SAST │
└─────────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR (src/core/orchestrator.py) │
│ "Conductor" – coordinates all pipeline phases │
└─────────────────────────────────────────────────────────────────────────────────┘
│
┌───────────────────────────┼───────────────────────────┐
│ │ │
▼ ▼ ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ OFFERZEN │ │ INDEED │ │ PNET │
│ API Scraper │ │ JobSpy Scraper │ │ HTML Scraper │
│ (REST API) │ │ (za.indeed.com)│ │ (pnet.co.za) │
└─────────────────┘ └─────────────────┘ └─────────────────┘
│ │ │
└────────────────────────┼────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ JSON CACHE (data/cache/*.json) │
│ Raw scraped data saved for debugging & fallback │
└─────────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ AI ENRICHMENT (src/enrichment/enhancer.py) │
│ Claude Haiku extracts: skills, level, summary │
└─────────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ SHEETS WRITER (src/writers/sheets.py) │
│ Deduplicates, formats, and appends to Google Sheet │
└─────────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ GOOGLE SHEETS (Public) │
│ https://docs.google.com/spreadsheets/d/1TPn_2Q-... │
└─────────────────────────────────────────────────────────────────────────────────┘

text

---

## Component Details

### 1. Orchestrator (`src/core/orchestrator.py`)

**Role:** Pipeline conductor – runs all phases in sequence.

**Responsibilities:**
- Parses CLI arguments and environment variables
- Executes each scraper with error isolation
- Coordinates enrichment and sheet writing
- Handles graceful degradation on failures

**Key Methods:**
```python
def main() -> None:
    # Parse arguments
    # Phase 1: Scrape all sources
    # Phase 2: AI enrichment (if enabled)
    # Phase 3: Write to Google Sheets
    # Summary and logging
Configuration Flags:

--skip-linkedin – LinkedIn disabled by default

--skip-enrichment – Skip AI to save cost

--scraper-only – Only run scrapers (no sheets)

--indeed-results – Control Indeed volume

--linkedin-results – Control LinkedIn volume

2. Scrapers (src/scrapers/)
2.1 OfferZen (offerzen.py)
Type: REST API scraper
Source: https://oz-public.vercel.app/api/jobs
Method: HTTP GET with pagination

Key Features:

Paginates through all job listings (safety cap: 50 pages)

Filters jobs to South Africa using SA_KEYWORDS

Retries with exponential backoff (3 attempts)

Safe URL generation with fallbacks

Data Extraction:

jobListings array from JSON response

company_profile for company details

must_have_skill_experiences for required skills

locations for city/country extraction

Performance: ~30s for 100–150 jobs

2.2 Indeed (indeed.py)
Type: JobSpy library wrapper
Source: za.indeed.com
Method: python-jobspy library handles HTML parsing

Key Features:

6 search terms (software developer, junior developer, etc.)

100 results per term (configurable)

30-day lookback window

Smart company name extraction (URL slug + description regex)

Salary range extraction

Anti-Blocking:

JobSpy handles headers and delays

3s delay between search terms

@retry decorator for API calls

Performance: ~2–3 minutes for 250–300 jobs

2.3 PNet (pnet.py)
Type: HTML parsing (BeautifulSoup)
Source: pnet.co.za
Method: HTTP GET with TLS fingerprinting

Key Features:

Multiple CSS selectors for resilience

TLS fingerprinting via tls_client (Chrome 120)

Optional detail fetching (full description, logo, industry)

Session reset and exponential backoff

Anti-Blocking:

TLS fingerprinting (tls_client)

Session reset on errors

3 retries with 10s/20s delays

2.5s delay between requests

Performance: 2–3 min (listing) + 6–8 min (details) for 150 jobs

2.4 LinkedIn (linkedin.py)
Status: DISABLED by default
Type: JobSpy library wrapper
Source: linkedin.com/jobs

Why Disabled:

Aggressive rate limiting (429 errors)

Account suspension risk

5 search terms × 300 results = 1500 requests

Configuration:

linkedin_fetch_description=True (full descriptions)

5s delay between terms

Per-term deduplication

Recommendation: Keep disabled in production. Use --skip-linkedin.

3. AI Enrichment (src/enrichment/enhancer.py)
Role: Extracts structured metadata from job descriptions.

Model: Claude Haiku 4.5 (cheapest, ~$0.25/1M tokens)

Extracted Fields:

Field	Description
primary_role	Normalized role (e.g., "Backend Engineer")
must_have_skills	3–8 key technical skills
nice_to_have_skills	2–5 bonus/preferred skills
experience_years	Required years (integer)
job_level	intern	junior	mid	senior	lead	principal
blurb	1–2 sentence summary
Batch Processing:

5 jobs per API call (configurable)

1.5s delay between batches (rate limiting)

Retries with exponential backoff (3 attempts)

Cost: ~$0.08 per 100 jobs (~$2.40/month)

4. Sheet Writer (src/writers/sheets.py)
Role: Writes enriched jobs to Google Sheets.

Features:

Append-only (never overwrites existing data)

Deduplication by URL

Migration from old 15-column format

Professional formatting:

Teal header with white bold text

Frozen header row

Auto-resized columns

Wrapped text in skills/summary columns

Sorted by Date Added (newest first)

Columns (16):

#	Column	#	Column
A	Date Added to Sheet	I	Nice-to-Have Skills
B	Date Job Posted	J	Years Exp
C	Job Title	K	Level
D	Company	L	Type
E	Role Category	M	Salary
F	Location	N	Summary
G	Work Policy	O	Source
H	Required Skills	P	Apply Link
Authentication:

Service account credentials from GOOGLE_SHEETS_CREDS

OAuth2 scopes: Sheets and Drive

5. Shared Utilities (src/utils/)
Module	Purpose
constants.py	SA_KEYWORDS – South African location keywords
logging.py	log() – Timestamped console logging
dates.py	parse_date(), parse_date_for_sort() – Date parsing
text.py	clean_text() – Text normalization
io.py	load_jobs(), save_jobs() – JSON file I/O
retry.py	@retry decorator – Exponential backoff retries
http.py	safe_get() – Safe HTTP requests
Data Models
Job Dictionary (Standardized Schema)
python
{
    "source": "offerzen" | "indeed" | "linkedin" | "pnet",
    "title": "Senior Software Engineer",
    "company": "ABC Corp",
    "company_logo": "https://...",
    "company_url": "https://...",
    "company_description": "About the company...",
    "company_industry": "Fintech",
    "company_size": "100-200 employees",
    "company_rating": 4.5,
    "location": "Cape Town, Western Cape, South Africa",
    "city": "Cape Town",
    "country": "South Africa",
    "is_remote": True,
    "workplace_policy": "remote",
    "primary_role": "Backend Engineer",
    "other_roles": "",
    "must_have_skills": "Python, Django, PostgreSQL, REST APIs",
    "nice_to_have_skills": "Docker, AWS, Redis",
    "company_tech_stack": "Python, Django, PostgreSQL",
    "experience_years": 3,
    "job_level": "mid",
    "employment_type": "fulltime",
    "date_posted": "2026-07-18",
    "time_posted": "",
    "job_url": "https://...",
    "job_url_direct": "",
    "description_snippet": "...",
    "salary_min": 50000,
    "salary_max": 80000,
    "salary_currency": "ZAR",
    "salary_period": "monthly",
    "visa_sponsorship": False,
    "requires_work_auth": True,
    "blurb": "Backend engineer role building scalable APIs...",
}
Data Flow
Phase 1: Scraping
text
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  OfferZen   │     │   Indeed    │     │    PNet     │
│  API Call   │     │  JobSpy     │     │   HTML      │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ offerzen_   │     │ indeed_     │     │ pnet_       │
│ jobs.json   │     │ jobs.json   │     │ jobs.json   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
                   ┌─────────────────┐
                   │  all_jobs (list) │
                   └─────────────────┘
Phase 2: Enrichment
text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  all_jobs       │────▶│  Claude API     │────▶│  enriched_jobs  │
│  (raw)          │     │  (batch=5)      │     │  (with metadata)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
Phase 3: Writing
text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  enriched_jobs  │────▶│  Deduplicate    │────▶│  Append to      │
│                 │     │  by URL         │     │  Google Sheet   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                   ┌─────────────┐
                                                   │  Public     │
                                                   │  Google     │
                                                   │  Sheet      │
                                                   └─────────────┘
Error Handling & Resilience
Retry Strategy
Component	Retries	Delay	Backoff
OfferZen API	3	1.5s	2.0x
Indeed JobSpy	3	2.0s	2.0x
PNet HTML	3	5.0s	2.0x
Claude API	3	2.0s	2.0x
PNet Session Reset	3	10s, 20s	linear
Graceful Degradation
Failure	Action
One scraper fails	Continue with other scrapers
Enrichment fails	Continue with un-enriched jobs
Sheets write fails	Save fallback JSON to data/cache/
PNet detail fetch fails	Return original job (no details)
Caching & Fallback
All scrapers save JSON to data/cache/

If sheets write fails, combined_jobs_fallback.json is saved

No automatic cache fallback yet (future improvement)

Performance Considerations
Runtime Breakdown
Phase	Time	Jobs
OfferZen	~30s	100–150
Indeed	~2–3 min	250–300
PNet (listing)	~2–3 min	150
PNet (details)	~6–8 min	150
Enrichment	~1–2 min	500–700
Sheets	~30s	50–100 (new)
Total	~8–12 min	500–700
Optimizations
Area	Current	Potential
PNet details	Sequential	Parallel (future)
Scrapers	Sequential	Parallel (future)
Batch size	5 jobs/call	10 (higher, but lower accuracy)
PNet pages	100 max	Reduce to 50
PNet details	Always on	Off by default (use --fetch-details)
Security & Secrets Management
Environment Variables
Variable	Purpose	Required
ANTHROPIC_API_KEY	Claude API key	For enrichment
GOOGLE_SHEETS_CREDS	Service account JSON	For sheets
SPREADSHEET_ID	Google Sheet ID	For sheets
GitHub Secrets
All secrets are stored in GitHub Actions secrets:

text
Settings → Secrets and variables → Actions
Never commit secrets to the repository.

Service Account Permissions
The Google Sheets service account requires:

Access: Editor on the target sheet

API: Google Sheets API enabled

Scopes: Sheets and Drive

Deployment Architecture
GitHub Actions Workflow
yaml
name: Daily Job Scraper
on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM UTC = 8 AM SAST
  workflow_dispatch:     # Manual trigger

jobs:
  scrape-and-publish:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - Checkout code
      - Setup Python 3.11
      - Install dependencies
      - Run pipeline with --skip-linkedin
      - Archive JSON artifacts
      - Notify on failure
Python Version
Python 3.11 (aligned with GitHub Actions ubuntu-latest)

Dependencies
Library	Purpose
requests	HTTP client
beautifulsoup4	HTML parsing
tls-client	TLS fingerprinting
python-jobspy	Indeed/LinkedIn scraping
pandas	DataFrame handling
gspread	Google Sheets API
oauth2client	Service account auth
anthropic	Claude API
File Structure
text
job-scraper/
├── .github/workflows/
│   └── daily-scrape.yml          # GitHub Actions workflow
├── src/
│   ├── core/
│   │   └── orchestrator.py       # Pipeline conductor
│   ├── scrapers/
│   │   ├── offerzen.py           # OfferZen API
│   │   ├── indeed.py             # Indeed (JobSpy)
│   │   ├── linkedin.py           # LinkedIn (disabled)
│   │   └── pnet.py               # PNet HTML
│   ├── enrichment/
│   │   └── enhancer.py           # Claude AI enrichment
│   ├── writers/
│   │   └── sheets.py             # Google Sheets writer
│   ├── utils/
│   │   ├── constants.py          # SA_KEYWORDS
│   │   ├── logging.py            # log()
│   │   ├── dates.py              # Date parsing
│   │   ├── text.py               # Text cleaning
│   │   ├── io.py                 # JSON I/O
│   │   ├── retry.py              # @retry decorator
│   │   └── http.py               # safe_get()
│   └── main.py                   # Entry point
├── data/cache/                   # Scraped JSON files
├── docs/                         # Documentation
├── tests/                        # Unit tests (future)
├── pyproject.toml                # Project config
└── requirements.txt              # Dependencies
Future Improvements
Short-Term (Next Sprint)
Add --fetch-pnet-details flag for opt-in detail fetching

Add Slack/Discord notifications on pipeline success/failure

Add --fast flag that skips PNet details and reduces search terms

Medium-Term (Next Month)
Implement caching (fallback to yesterday's data on failure)

Parallelize scrapers using ThreadPoolExecutor

Add SQLite database for historical tracking

Create public dashboard with Streamlit

Long-Term (Next Quarter)
Dockerize the pipeline for portability

Migrate to a more robust scheduler (Kubernetes, AWS Lambda)

Add more job sources (e.g., Adzuna, Jooble)

Implement email digest for students

Build a full job board web application

Appendix
Architecture Decision Records (ADRs)
ADR-001: Use Claude Haiku for Enrichment
Context: Need to extract structured metadata from job descriptions.
Decision: Use Claude Haiku 4.5 over GPT-3.5.
Rationale: Lower cost ($0.25/1M tokens vs $0.50), faster response times, and better structured output.

ADR-002: Disable LinkedIn by Default
Context: LinkedIn aggressively rate-limits and blocks scrapers.
Decision: Disable LinkedIn in production, keep code for potential future use.
Rationale: Risk of account suspension outweighs benefit of extra jobs.

ADR-003: Use Append-Only for Google Sheets
Context: Need to preserve historical data.
Decision: Always append new jobs, never overwrite existing data.
Rationale: Enables trend analysis and prevents data loss.

Last Updated: July 2026
Maintainer: CodeSpace Job Aggregator Team