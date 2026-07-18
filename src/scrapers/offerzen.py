#!/usr/bin/env python3
"""
offerzen.py — OfferZen SA Job Scraper
======================================

Scrapes all South African tech jobs from OfferZen's public API.

Features:
---------
- Pagination through all job listings (safety cap: 50 pages)
- Automatic retries with exponential backoff on API failures
- SA location filtering using SA_KEYWORDS
- Structured data extraction with fallbacks for missing fields
- Safe URL generation with multiple fallbacks

API Endpoint:
-------------
    https://oz-public.vercel.app/api/jobs/{page}?sort_direction=desc

Usage (Standalone):
-------------------
    python -m src.scrapers.offerzen
    python -m src.scrapers.offerzen -o custom_output.json
    python -m src.scrapers.offerzen --csv

Usage (Imported):
-----------------
    from src.scrapers import offerzen
    jobs = offerzen.scrape_offerzen()

Dependencies:
-------------
    - requests: HTTP client
    - src.utils: logging, date parsing, text cleaning, retry, safe_get

Environment:
------------
    None required.
"""

import argparse
import sys
import time
from typing import List, Dict, Any, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

from src.utils import (
    log,
    parse_date,
    clean_text,
    save_jobs,
    SA_KEYWORDS,
    retry,
    safe_get
)

# ─── Constants ──────────────────────────────────────────────────────────────

OFFERZEN_API = "https://oz-public.vercel.app/api/jobs"
"""Base URL for OfferZen's public job API."""

OFFERZEN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.offerzen.com/jobs",
}
"""HTTP headers mimicking a real browser."""

MAX_PAGES = 50
"""Safety cap to prevent infinite pagination loops."""


# ─── Helper Functions ──────────────────────────────────────────────────────

@retry(
    exceptions=(requests.RequestException, ConnectionError, TimeoutError),
    tries=3,
    delay=1.5,
    backoff=2.0
)
def _fetch_page(page: int) -> Dict[str, Any]:
    """
    Fetch a single page of jobs from OfferZen API with retries.

    Args:
        page (int): Page number to fetch.

    Returns:
        dict: JSON response from the API.

    Raises:
        Exception: If the request fails after all retries.

    Note:
        Decorated with @retry for automatic retry on network failures.
    """
    url = f"{OFFERZEN_API}/{page}?sort_direction=desc"
    resp = safe_get(url, headers=OFFERZEN_HEADERS, timeout=30)

    if resp is None:
        raise Exception(f"OfferZen page {page} request failed")

    # Check for valid JSON
    try:
        return resp.json()
    except ValueError as e:
        raise Exception(f"OfferZen page {page} invalid JSON: {e}")


def _build_job_url(company_id: Optional[str], job_id: Optional[str]) -> str:
    """
    Build a safe job URL with fallbacks.

    Args:
        company_id (str, optional): Company ID from OfferZen.
        job_id (str, optional): Job ID from OfferZen.

    Returns:
        str: A valid URL, or empty string if no ID is available.
    """
    if company_id and company_id != "None":
        return f"https://www.offerzen.com/companies/{company_id}"
    if job_id and job_id != "None":
        return f"https://www.offerzen.com/jobs/{job_id}"
    return ""


# ─── Main Scraper ──────────────────────────────────────────────────────────

def scrape_offerzen() -> List[Dict[str, Any]]:
    """
    Scrape all jobs from OfferZen's public API with full data extraction.

    Returns:
        List[Dict[str, Any]]: List of job dictionaries, filtered to South Africa.

    Process:
        1. Paginate through all pages (safety cap: MAX_PAGES).
        2. Extract job data from each listing.
        3. Filter to South African jobs using SA_KEYWORDS.
        4. Return the filtered list.

    Raises:
        No exceptions raised; failures are logged and handled gracefully.

    Note:
        - API rate-limiting: sleeps 1.5s between pages.
        - If a page fails after retries, pagination stops.
    """
    log("OfferZen: Starting...")
    all_jobs: List[Dict[str, Any]] = []
    page = 1

    while page <= MAX_PAGES:
        try:
            data = _fetch_page(page)
        except Exception as e:
            log(f"  OfferZen page {page} error after retries: {e}")
            break

        listings = data.get("jobListings", [])
        if not listings:
            # No more jobs
            break

        # ── Process each listing ──
        for raw in listings:
            company = raw.get("company_profile", {})
            locations = raw.get("locations", [])

            # ── Location strings ──
            loc_strs: List[str] = []
            city = ""
            country = ""

            for loc in locations:
                display = loc.get("display_address", "")
                if display:
                    loc_strs.append(display)
                elif loc.get("city") and loc.get("country"):
                    loc_strs.append(f"{loc['city']}, {loc['country']}")

                if not city:
                    city = loc.get("city", "") or ""
                if not country:
                    country = loc.get("country", "") or ""

            # ── Skills ──
            must_have = [
                s.get("skill", "")
                for s in raw.get("must_have_skill_experiences", [])
                if s.get("skill")
            ]

            nice_to_have = raw.get("nice_to_have_skills", [])
            if isinstance(nice_to_have, list) and nice_to_have and isinstance(nice_to_have[0], dict):
                nice_to_have = [
                    s.get("skill", "")
                    for s in nice_to_have
                    if s.get("skill")
                ]
            elif not isinstance(nice_to_have, list):
                nice_to_have = []

            # ── Company tech stack ──
            tech_stack = [
                t.get("title", "")
                for t in company.get("tech_stack", [])
                if t.get("title")
            ]

            # ── Other roles ──
            other_roles = [
                r.get("name", "")
                for r in raw.get("other_roles", [])
                if r.get("name")
            ]

            # ── Parse dates ──
            date_str, time_str = parse_date(raw.get("published_at", ""))

            # ── Safe URL generation ──
            company_id = company.get("id", "")
            job_id = raw.get("id", "")
            job_url = _build_job_url(company_id, job_id)

            # ── Build job object ──
            all_jobs.append({
                "source": "offerzen",
                "title": raw.get("name", ""),
                "company": company.get("name", ""),
                "company_logo": company.get("logo_small_url", ""),
                "company_url": f"https://www.offerzen.com/companies/{company_id}" if company_id else "",
                "company_description": "",
                "company_industry": "",
                "company_size": "",
                "company_rating": None,
                "location": "; ".join(loc_strs),
                "city": city,
                "country": country,
                "is_remote": raw.get("workplace_policy") == "remote",
                "workplace_policy": raw.get("workplace_policy", ""),
                "primary_role": raw.get("primary_role_name", ""),
                "other_roles": ", ".join(other_roles),
                "must_have_skills": ", ".join(must_have),
                "nice_to_have_skills": ", ".join(nice_to_have) if isinstance(nice_to_have, list) else "",
                "company_tech_stack": ", ".join(tech_stack),
                "experience_years": raw.get("years_experience"),
                "job_level": "",
                "employment_type": raw.get("employment_type", ""),
                "date_posted": date_str,
                "time_posted": time_str,
                "job_url": job_url,
                "job_url_direct": "",
                "description_snippet": "",
                "salary_min": None,
                "salary_max": None,
                "salary_currency": raw.get("currency_code", ""),
                "salary_period": raw.get("remuneration_period", ""),
                "visa_sponsorship": raw.get("visa_sponsorship_available"),
                "requires_work_auth": raw.get("requires_work_authorisation"),
            })

        log(f"  OfferZen page {page}: {len(listings)} jobs")
        page += 1
        time.sleep(1.5)  # Polite delay

    # ── Filter to South Africa only ──
    sa_jobs = [
        job for job in all_jobs
        if any(kw in job["location"].lower() for kw in SA_KEYWORDS)
    ]

    log(f"  OfferZen: {len(sa_jobs)} SA jobs (of {len(all_jobs)} total)")
    return sa_jobs


# ─── Standalone Entry Point ────────────────────────────────────────────────

def main() -> None:
    """
    Command-line entry point for standalone OfferZen scraper.
    """
    parser = argparse.ArgumentParser(
        description="OfferZen SA Job Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.scrapers.offerzen
    python -m src.scrapers.offerzen -o data/cache/offerzen_jobs.json
    python -m src.scrapers.offerzen --csv

Output:
    offerzen_jobs.json (or custom filename with -o)
    offerzen_jobs.csv (if --csv flag is used)

Note:
    Uses OfferZen's public API. No API key required.
    Jobs are filtered to South Africa only.
        """
    )
    parser.add_argument(
        "-o", "--output", default="data/cache/offerzen_jobs.json",
        help="Output JSON file (default: data/cache/offerzen_jobs.json)"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Also write a CSV file"
    )
    args = parser.parse_args()

    jobs = scrape_offerzen()

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="offerzen")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()