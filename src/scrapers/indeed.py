#!/usr/bin/env python3
"""
indeed.py — Indeed SA Job Scraper (via JobSpy)
===============================================

Scrapes software development jobs from Indeed South Africa (za.indeed.com)
using the python-jobspy library.

Features:
---------
- 30-day lookback window (configurable)
- 100 results per search term (configurable)
- 3000-character description snippets (good for AI enrichment)
- Smart company name extraction (URL slug + description regex fallback)
- Salary range extraction (if available)
- Remote/hybrid detection
- Automatic deduplication by URL
- Sorted newest-first

Why JobSpy?
-----------
JobSpy handles Indeed's anti-bot measures (headers, delays, etc.)
so we don't have to. It's actively maintained and reliable.

Data Sources:
-------------
- Indeed: za.indeed.com
- Search Terms: software developer, junior developer, etc.
- Location: South Africa (country_indeed="South Africa")

Performance:
------------
- ~6 search terms × 100 results = ~600 raw jobs
- Dedup reduces to ~200-400 unique jobs
- ~3s delay between terms to avoid rate limiting

Usage (Standalone):
-------------------
    python -m src.scrapers.indeed
    python -m src.scrapers.indeed --results 50 --days 14
    python -m src.scrapers.indeed --search "python developer" --csv

Usage (Imported):
-----------------
    from src.scrapers import indeed
    jobs = indeed.scrape_indeed(results_per_term=100, hours_old=720)

Dependencies:
-------------
    - python-jobspy: Core scraping engine
    - pandas: For DataFrame handling
    - requests: HTTP client (JobSpy dependency)

Environment:
------------
    None required (no API keys needed)
"""

import argparse
import re
import sys
import time
from typing import List, Dict, Any, Optional, Tuple, Set

try:
    import requests  # noqa: F401 — ensure requests available
except ImportError:
    print("Missing: pip install requests")
    sys.exit(1)

from src.utils import log, parse_date, clean_text, save_jobs, parse_date_for_sort

# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_SEARCH_TERMS: Tuple[str, ...] = (
    "software developer",
    "junior developer",
    "software engineer",
    "full stack developer",
    "javascript developer",
    "frontend developer",
)

_UNLISTED_COMPANIES: Tuple[str, ...] = (
    "company unlisted",
    "unlisted",
    "confidential",
    "undisclosed",
    "n/a",
)

_COMPANY_FROM_DESC_RE = re.compile(
    r'^([A-Z][A-Za-z0-9&\s\-\.]{1,49}?)\s+is\s+(?:a|an|the)\b',
    re.MULTILINE,
)


# ─── Helper Functions ──────────────────────────────────────────────────────

def _company_from_indeed_url(url: str) -> str:
    """
    Extract a human-readable company name from an Indeed company URL.

    Args:
        url: Indeed company URL (e.g., https://za.indeed.com/cmp/Avbob)

    Returns:
        Extracted company name (e.g., "Avbob") or empty string if not found

    Examples:
        >>> _company_from_indeed_url("https://za.indeed.com/cmp/Avbob")
        "Avbob"
        >>> _company_from_indeed_url("https://za.indeed.com/cmp/Some-Company-123")
        "Some Company"
    """
    if not url:
        return ""

    match = re.search(r'indeed\.com/cmp/([^/?#]+)', url)
    if not match:
        return ""

    slug = match.group(1).strip().rstrip('/')
    # Strip trailing numeric ID if present (e.g., "company-12345")
    slug = re.sub(r'-\d+$', '', slug)
    # Convert hyphens/underscores to spaces
    name = slug.replace('-', ' ').replace('_', ' ').strip()
    return name if name else ""


def _extract_company_from_desc(desc: str) -> str:
    """
    Attempt to infer company name from the opening sentence of job description.

    Looks for patterns like:
        "Avbob is a leading financial services company..."
        "Takealot Group is looking for..."

    Args:
        desc: Full job description text

    Returns:
        Extracted company name or empty string if not found
    """
    if not desc:
        return ""

    # Only scan first 800 characters to avoid false positives
    match = _COMPANY_FROM_DESC_RE.search(desc[:800])
    if not match:
        return ""

    candidate = match.group(1).strip()
    # Reject generic openers
    generic_openers = {"we", "our company", "the company", "this role"}
    if candidate.lower() not in generic_openers:
        return candidate

    return ""


def _safe_get_row_value(row: Any, col: str, default: str = "") -> Any:
    """
    Safely extract a value from a pandas DataFrame row.

    Handles:
        - NaN values
        - NaT values
        - None values
        - Missing columns

    Args:
        row: Pandas Series (DataFrame row)
        col: Column name to extract
        default: Default value if column is missing or null

    Returns:
        Extracted value or default
    """
    try:
        val = row.get(col)
    except Exception:
        return default

    if val is None:
        return default

    # Handle pandas nulls
    try:
        import pandas as pd
        if isinstance(val, float) and pd.isna(val):
            return default
        if str(val) in ("nan", "None", "NaT"):
            return default
    except ImportError:
        pass

    return val


# ─── Main Scraper ──────────────────────────────────────────────────────────

def scrape_indeed(
    search_terms: Optional[List[str]] = None,
    results_per_term: int = 100,
    hours_old: int = 720
) -> List[Dict[str, Any]]:
    """
    Scrape tech jobs from Indeed South Africa.

    Args:
        search_terms: List of search terms (defaults to DEFAULT_SEARCH_TERMS)
        results_per_term: Max results per search term (default: 100)
        hours_old: Only include jobs posted within this many hours (default: 720 = 30 days)

    Returns:
        List of job dictionaries with standardized fields

    Raises:
        No exceptions raised directly; errors are logged and handled gracefully

    Note:
        Uses JobSpy library which handles Indeed's anti-bot measures.
        Delays 3 seconds between search terms to avoid rate limiting.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        log("JobSpy not installed. Run: pip install python-jobspy")
        return []

    try:
        import pandas as pd
    except ImportError:
        log("pandas not installed. Run: pip install pandas")
        return []

    if search_terms is None:
        search_terms = list(DEFAULT_SEARCH_TERMS)

    all_jobs: List[Dict[str, Any]] = []

    for term in search_terms:
        log(f"  Indeed: searching '{term}' ({results_per_term} results, {hours_old}h window)...")

        try:
            jobs_df = scrape_jobs(
                site_name=["indeed"],
                search_term=term,
                location="South Africa",
                results_wanted=results_per_term,
                hours_old=hours_old,
                country_indeed="South Africa",
                description_format="markdown",
            )
        except Exception as e:
            log(f"  Indeed error for '{term}': {e}")
            time.sleep(5)
            continue

        if jobs_df is None or len(jobs_df) == 0:
            log(f"  Indeed: 0 results for '{term}'")
            continue

        for _, row in jobs_df.iterrows():
            # Extract fields with safe access
            date_str, time_str = parse_date(_safe_get_row_value(row, "date_posted", ""))

            # ── Salary ──
            salary_min = None
            salary_max = None
            salary_currency = ""
            salary_period = ""

            comp = _safe_get_row_value(row, "compensation", None)
            if comp and hasattr(comp, "min_amount"):
                salary_min = comp.min_amount if comp.min_amount else None
                salary_max = comp.max_amount if comp.max_amount else None
                salary_currency = str(comp.currency) if comp.currency else ""
                salary_period = str(comp.interval) if hasattr(comp, "interval") and comp.interval else ""
            else:
                sal_min = _safe_get_row_value(row, "min_amount", None)
                sal_max = _safe_get_row_value(row, "max_amount", None)
                salary_min = float(sal_min) if sal_min and str(sal_min) != "nan" else None
                salary_max = float(sal_max) if sal_max and str(sal_max) != "nan" else None
                salary_currency = clean_text(_safe_get_row_value(row, "currency", ""))
                salary_period = clean_text(_safe_get_row_value(row, "interval", ""))

            # ── Location ──
            loc = _safe_get_row_value(row, "location", None)
            city_val = ""
            country_val = "South Africa"
            loc_str = ""

            if loc and hasattr(loc, "city"):
                city_val = str(loc.city) if loc.city else ""
                country_val = str(loc.country) if loc.country else "South Africa"
                state_val = str(loc.state) if hasattr(loc, "state") and loc.state else ""
                loc_str = ", ".join(p for p in [city_val, state_val, country_val] if p)
            elif loc:
                loc_str = str(loc)
                parts = loc_str.split(",")
                city_val = parts[0].strip() if parts else ""

            # ── Description ──
            desc_full = str(_safe_get_row_value(row, "description", ""))
            desc_snippet = clean_text(desc_full, max_len=3000)

            # ── Company ──
            company = clean_text(_safe_get_row_value(row, "company_name", ""))
            if company.lower().strip() in _UNLISTED_COMPANIES:
                company = ""

            company_url_val = str(_safe_get_row_value(row, "company_url", ""))
            if not company and company_url_val:
                company = _company_from_indeed_url(company_url_val)

            if not company:
                company = _extract_company_from_desc(desc_full)

            # ── Employment Type ──
            emp_type = _safe_get_row_value(row, "job_type", "")
            if isinstance(emp_type, list):
                emp_type = ", ".join(str(t) for t in emp_type)
            else:
                emp_type = str(emp_type) if emp_type else ""

            # ── Skills ──
            skills_raw = _safe_get_row_value(row, "skills", [])
            if isinstance(skills_raw, list):
                skills_str = ", ".join(str(s) for s in skills_raw if s)
            else:
                skills_str = str(skills_raw) if skills_raw else ""

            # ── Build Job Object ──
            all_jobs.append({
                "source": "indeed",
                "title": clean_text(_safe_get_row_value(row, "title", "")),
                "company": company,
                "company_logo": str(_safe_get_row_value(row, "company_logo", "")),
                "company_url": str(_safe_get_row_value(row, "company_url", "")),
                "company_description": clean_text(_safe_get_row_value(row, "company_description", ""), 300),
                "company_industry": clean_text(_safe_get_row_value(row, "company_industry", "")),
                "company_size": clean_text(_safe_get_row_value(row, "company_num_employees", "")),
                "company_rating": _safe_get_row_value(row, "company_rating", None),
                "location": loc_str,
                "city": city_val,
                "country": country_val,
                "is_remote": bool(_safe_get_row_value(row, "is_remote", False)),
                "workplace_policy": "remote" if _safe_get_row_value(row, "is_remote", False) else clean_text(
                    _safe_get_row_value(row, "work_from_home_type", "")
                ),
                "primary_role": clean_text(_safe_get_row_value(row, "job_function", "")),
                "other_roles": "",
                "must_have_skills": skills_str,
                "nice_to_have_skills": "",
                "company_tech_stack": "",
                "experience_years": clean_text(_safe_get_row_value(row, "experience_range", "")),
                "job_level": clean_text(_safe_get_row_value(row, "job_level", "")),
                "employment_type": emp_type,
                "date_posted": date_str,
                "time_posted": time_str,
                "job_url": str(_safe_get_row_value(row, "job_url", "")),
                "job_url_direct": str(_safe_get_row_value(row, "job_url_direct", "")),
                "description_snippet": desc_snippet,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_currency": salary_currency,
                "salary_period": salary_period,
                "visa_sponsorship": None,
                "requires_work_auth": None,
            })

        log(f"  Indeed: {len(all_jobs)} total jobs so far")
        time.sleep(3)  # Polite delay between terms

    # ── Deduplicate by URL ──
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []

    for job in all_jobs:
        url = job.get("job_url", "")
        key = url if url else f"{job['title']}|{job['company']}".lower()
        if key not in seen:
            seen.add(key)
            unique.append(job)

    # ── Sort newest first ──
    unique.sort(
        key=lambda j: parse_date_for_sort(
            j.get("date_posted", ""),
            j.get("time_posted", "")
        ),
        reverse=True,
    )

    log(f"Indeed: {len(unique)} unique jobs (from {len(all_jobs)} raw)")
    return unique


def main() -> None:
    """
    Command-line entry point for standalone Indeed scraper.
    """
    parser = argparse.ArgumentParser(
        description="Indeed SA Job Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.scrapers.indeed
    python -m src.scrapers.indeed --results 50 --days 14
    python -m src.scrapers.indeed --search "python developer" --csv

Output:
    indeed_jobs.json (or custom filename with -o)
    indeed_jobs.csv (if --csv flag is used)

Note:
    Uses JobSpy library which handles Indeed's anti-bot measures.
        """
    )
    parser.add_argument(
        "-o", "--output", default="data/cache/indeed_jobs.json",
        help="Output JSON file (default: data/cache/indeed_jobs.json)"
    )
    parser.add_argument(
        "--results", "-r", type=int, default=100,
        help="Results per search term (default: 100)"
    )
    parser.add_argument(
        "--days", "-d", type=int, default=30,
        help="Max age of listings in days (default: 30)"
    )
    parser.add_argument(
        "--search", default=None,
        help="Single custom search term (overrides defaults)"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Also write a CSV file"
    )
    args = parser.parse_args()

    terms = [args.search] if args.search else None
    hours = args.days * 24

    jobs = scrape_indeed(
        search_terms=terms,
        results_per_term=args.results,
        hours_old=hours
    )

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="indeed")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()