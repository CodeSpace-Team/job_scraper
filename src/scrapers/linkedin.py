"""
linkedin.py — LinkedIn SA Job Scraper (via JobSpy)
===================================================

Scrapes software development jobs from LinkedIn South Africa
using the python-jobspy library.

⚠️  DISCLAIMER: LinkedIn aggressively rate-limits and may block scrapers.
    This scraper is DISABLED BY DEFAULT in the main pipeline.
    Use with extreme caution and only after warming up a dedicated account.

Features:
---------
- 30-day lookback window (configurable)
- 300 results per search term (configurable)
- Full description fetching (linkedin_fetch_description=True)
- Per-term deduplication to avoid re-processing duplicates
- Smart company name extraction from URL slug
- Remote/hybrid detection
- Sorted newest-first

Why JobSpy?
-----------
JobSpy handles LinkedIn's anti-bot measures to some extent,
but LinkedIn is notoriously aggressive. Expect rate-limiting errors.

Performance & Risk:
-------------------
- ~5 search terms × 300 results = ~1500 raw jobs
- Dedup reduces to ~200-400 unique jobs
- 5s delay between terms (aggressive, but necessary)
- High risk of CAPTCHAs and account blocks

Usage (Standalone):
-------------------
    python -m src.scrapers.linkedin
    python -m src.scrapers.linkedin --results 50 --days 14
    python -m src.scrapers.linkedin --search "python developer" --csv

Usage (Imported):
-----------------
    from src.scrapers import linkedin
    jobs = linkedin.scrape_linkedin(results_per_term=100, hours_old=720)

Dependencies:
-------------
    - python-jobspy: Core scraping engine
    - pandas: For DataFrame handling

Environment:
------------
    None required (no API keys needed)

Recommendation:
---------------
    Keep LinkedIn disabled in production (use --skip-linkedin flag)
    and rely on OfferZen + Indeed + PNet for ~700+ jobs.
"""

import argparse
import re
import sys
import time
from typing import List, Dict, Any, Optional, Tuple, Set

from src.utils import log, parse_date, clean_text, save_jobs, parse_date_for_sort


# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_SEARCH_TERMS: Tuple[str, ...] = (
    "software developer",
    "software engineer",
    "full stack developer",
    "javascript developer",
    "react developer",
)

_UNLISTED_COMPANIES: Tuple[str, ...] = (
    "company unlisted",
    "unlisted",
    "confidential",
    "undisclosed",
    "n/a",
)


# ─── Helper Functions ──────────────────────────────────────────────────────

def _company_from_linkedin_url(url: str) -> str:
    """
    Extract a human-readable company name from a LinkedIn company URL.

    Args:
        url: LinkedIn company URL (e.g., https://www.linkedin.com/company/mindrift-ai)

    Returns:
        Extracted company name (e.g., "Mindrift Ai") or empty string if not found

    Examples:
        >>> _company_from_linkedin_url("https://www.linkedin.com/company/mindrift-ai")
        "Mindrift Ai"
        >>> _company_from_linkedin_url("https://www.linkedin.com/company/executive-placements-123")
        "Executive Placements"
    """
    if not url:
        return ""

    match = re.search(r'linkedin\.com/company/([^/?#]+)', url)
    if not match:
        return ""

    slug = match.group(1).strip().rstrip('/')
    # Strip trailing numeric ID if present (e.g., "some-company-12345")
    slug = re.sub(r'-\d+$', '', slug)
    # Convert hyphens to spaces and title-case
    name = slug.replace('-', ' ').replace('_', ' ').strip()
    return name.title() if name else ""


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

def scrape_linkedin(
    search_terms: Optional[List[str]] = None,
    results_per_term: int = 300,
    hours_old: int = 720
) -> List[Dict[str, Any]]:
    """
    Scrape tech jobs from LinkedIn South Africa.

    Args:
        search_terms: List of search terms (defaults to DEFAULT_SEARCH_TERMS)
        results_per_term: Max results per search term (default: 300)
        hours_old: Only include jobs posted within this many hours (default: 720 = 30 days)

    Returns:
        List of job dictionaries with standardized fields

    Raises:
        No exceptions raised directly; errors are logged and handled gracefully

    Note:
        Uses JobSpy library. LinkedIn aggressively rate-limits.
        Expect errors; use --skip-linkedin in production.
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
    seen_urls: Set[str] = set()

    for term in search_terms:
        log(f"  LinkedIn: searching '{term}' ({results_per_term} results, {hours_old}h window)...")

        try:
            jobs_df = scrape_jobs(
                site_name=["linkedin"],
                search_term=term,
                location="South Africa",
                results_wanted=results_per_term,
                hours_old=hours_old,
                description_format="markdown",
                linkedin_fetch_description=True,  # Fetches full descriptions (more requests = higher risk)
            )
        except Exception as e:
            log(f"  LinkedIn error for '{term}': {e}")
            time.sleep(10)  # Longer delay on error
            continue

        if jobs_df is None or len(jobs_df) == 0:
            log(f"  LinkedIn: 0 results for '{term}'")
            continue

        term_new = 0
        for _, row in jobs_df.iterrows():
            # Extract fields with safe access
            url = str(_safe_get_row_value(row, "job_url", ""))
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

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

            company_url = str(_safe_get_row_value(row, "company_url", ""))
            if not company and company_url:
                company = _company_from_linkedin_url(company_url)

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
                "source": "linkedin",
                "title": clean_text(_safe_get_row_value(row, "title", "")),
                "company": company,
                "company_logo": str(_safe_get_row_value(row, "company_logo", "")),
                "company_url": company_url,
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
                "job_url": url,
                "job_url_direct": str(_safe_get_row_value(row, "job_url_direct", "")),
                "description_snippet": desc_snippet,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_currency": salary_currency,
                "salary_period": salary_period,
                "visa_sponsorship": None,
                "requires_work_auth": None,
            })
            term_new += 1

        log(f"  LinkedIn '{term}': {term_new} new jobs (total: {len(all_jobs)})")
        time.sleep(5)  # Longer delay between terms for LinkedIn

    # ── Sort newest first ──
    all_jobs.sort(
        key=lambda j: parse_date_for_sort(
            j.get("date_posted", ""),
            j.get("time_posted", "")
        ),
        reverse=True,
    )

    log(f"LinkedIn: {len(all_jobs)} unique jobs")
    return all_jobs


def main() -> None:
    """
    Command-line entry point for standalone LinkedIn scraper.
    """
    parser = argparse.ArgumentParser(
        description="LinkedIn SA Job Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.scrapers.linkedin
    python -m src.scrapers.linkedin --results 50 --days 14
    python -m src.scrapers.linkedin --search "python developer" --csv

Output:
    linkedin_jobs.json (or custom filename with -o)
    linkedin_jobs.csv (if --csv flag is used)

⚠️  WARNING: LinkedIn aggressively rate-limits. Use with caution.
    Consider using --skip-linkedin in production.

Note:
    Uses JobSpy library which handles LinkedIn's anti-bot measures
    to some extent, but expect rate-limiting errors.
        """
    )
    parser.add_argument(
        "-o", "--output", default="data/cache/linkedin_jobs.json",
        help="Output JSON file (default: data/cache/linkedin_jobs.json)"
    )
    parser.add_argument(
        "--results", "-r", type=int, default=300,
        help="Results per search term (default: 300)"
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

    jobs = scrape_linkedin(
        search_terms=terms,
        results_per_term=args.results,
        hours_old=hours
    )

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="linkedin")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()