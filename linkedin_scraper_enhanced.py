#!/usr/bin/env python3
"""
linkedin_scraper.py — Standalone LinkedIn SA job scraper (via JobSpy)
======================================================================
Improvements over gajit_scraper.py:
  - 300 results per term (was 50)
  - 30-day window (hours_old=720, was 168)
  - Expanded search terms (10 terms)
  - linkedin_fetch_description=True for full descriptions
  - Per-term dedup to avoid re-processing duplicates

Note: LinkedIn aggressively rate-limits. If you see many failures,
reduce --results-per-term and increase term count instead.

Usage:
    python linkedin_scraper.py
    python linkedin_scraper.py --results 300 --days 30
    python linkedin_scraper.py -o linkedin_jobs.json --csv
"""

import argparse
import re
import sys
import time

from scraper_utils import log, parse_date, clean_text, save_jobs, parse_date_for_sort


def _company_from_linkedin_url(url: str) -> str:
    """
    Extract a human-readable company name from a LinkedIn company URL.
    e.g. https://www.linkedin.com/company/mindrift-ai  ->  Mindrift Ai
         https://www.linkedin.com/company/executive-placements  ->  Executive Placements
    """
    if not url:
        return ""
    m = re.search(r'linkedin\.com/company/([^/?#]+)', url)
    if not m:
        return ""
    slug = m.group(1).strip().rstrip('/')
    # Strip trailing numeric ID if present (e.g. "some-company-12345")
    slug = re.sub(r'-\d+$', '', slug)
    # Convert hyphens to spaces and title-case
    name = slug.replace('-', ' ').replace('_', ' ').strip()
    return name.title() if name else ""


DEFAULT_SEARCH_TERMS = [
    "software developer",
    "software engineer",
    "data engineer",
    "devops engineer",
    "full stack developer",
    "python developer",
    "java developer",
    "react developer",

]


def scrape_linkedin(search_terms: list = None, results_per_term: int = 300,
                    hours_old: int = 720) -> list:
    """Scrape LinkedIn SA via JobSpy."""
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
        search_terms = DEFAULT_SEARCH_TERMS

    all_jobs = []
    seen_urls: set = set()

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
                linkedin_fetch_description=True,
            )
        except Exception as e:
            log(f"  LinkedIn error for '{term}': {e}")
            time.sleep(10)
            continue

        if jobs_df is None or len(jobs_df) == 0:
            log(f"  LinkedIn: 0 results for '{term}'")
            continue

        term_new = 0
        for _, row in jobs_df.iterrows():
            def get(col, default=""):
                try:
                    val = row.get(col)
                except Exception:
                    val = None
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    return default
                if str(val) in ("nan", "None", "NaT"):
                    return default
                return val

            url = str(get("job_url", ""))
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            date_str, time_str = parse_date(get("date_posted", ""))

            # Salary
            salary_min = None
            salary_max = None
            salary_currency = ""
            salary_period = ""
            comp = get("compensation", None)
            if comp and hasattr(comp, "min_amount"):
                salary_min = comp.min_amount if comp.min_amount else None
                salary_max = comp.max_amount if comp.max_amount else None
                salary_currency = str(comp.currency) if comp.currency else ""
                salary_period = str(comp.interval) if hasattr(comp, "interval") and comp.interval else ""
            else:
                sal_min = get("min_amount", None)
                sal_max = get("max_amount", None)
                salary_min = float(sal_min) if sal_min and str(sal_min) != "nan" else None
                salary_max = float(sal_max) if sal_max and str(sal_max) != "nan" else None
                salary_currency = clean_text(get("currency", ""))
                salary_period = clean_text(get("interval", ""))

            # Location
            loc = get("location", None)
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

            # Description — 3000 char snippet
            desc_full = str(get("description", ""))
            desc_snippet = clean_text(desc_full, max_len=3000)

            # Employment type
            emp_type = get("job_type", "")
            if isinstance(emp_type, list):
                emp_type = ", ".join(str(t) for t in emp_type)
            else:
                emp_type = str(emp_type) if emp_type else ""

            # Skills
            skills_raw = get("skills", [])
            if isinstance(skills_raw, list):
                skills_str = ", ".join(str(s) for s in skills_raw if s)
            else:
                skills_str = str(skills_raw) if skills_raw else ""

            # Company — normalise LinkedIn placeholder strings, then fall back to URL slug
            _UNLISTED = {"company unlisted", "unlisted", "confidential", "undisclosed", "n/a"}
            company = clean_text(get("company_name", ""))
            if company.lower().strip() in _UNLISTED:
                company = ""
            company_url = str(get("company_url", ""))
            if not company and company_url:
                company = _company_from_linkedin_url(company_url)

            all_jobs.append({
                "source": "linkedin",
                "title": clean_text(get("title", "")),
                "company": company,
                "company_logo": str(get("company_logo", "")),
                "company_url": company_url,
                "company_description": clean_text(get("company_description", ""), 300),
                "company_industry": clean_text(get("company_industry", "")),
                "company_size": clean_text(get("company_num_employees", "")),
                "company_rating": get("company_rating", None),
                "location": loc_str,
                "city": city_val,
                "country": country_val,
                "is_remote": bool(get("is_remote", False)),
                "workplace_policy": "remote" if get("is_remote", False) else clean_text(get("work_from_home_type", "")),
                "primary_role": clean_text(get("job_function", "")),
                "other_roles": "",
                "must_have_skills": skills_str,
                "nice_to_have_skills": "",
                "company_tech_stack": "",
                "experience_years": clean_text(get("experience_range", "")),
                "job_level": clean_text(get("job_level", "")),
                "employment_type": emp_type,
                "date_posted": date_str,
                "time_posted": time_str,
                "job_url": url,
                "job_url_direct": str(get("job_url_direct", "")),
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
        time.sleep(5)

    # Sort newest first
    all_jobs.sort(
        key=lambda j: parse_date_for_sort(j.get("date_posted", ""), j.get("time_posted", "")),
        reverse=True,
    )

    log(f"LinkedIn: {len(all_jobs)} unique jobs")
    return all_jobs


def main():
    parser = argparse.ArgumentParser(description="LinkedIn SA Job Scraper")
    parser.add_argument("-o", "--output", default="linkedin_jobs.json",
                        help="Output JSON file (default: linkedin_jobs.json)")
    parser.add_argument("--results", "-r", type=int, default=300,
                        help="Results per search term (default: 300)")
    parser.add_argument("--days", "-d", type=int, default=30,
                        help="Max age of listings in days (default: 30)")
    parser.add_argument("--search", default=None,
                        help="Single custom search term (overrides defaults)")
    parser.add_argument("--csv", action="store_true",
                        help="Also write a CSV file")
    args = parser.parse_args()

    terms = [args.search] if args.search else None
    hours = args.days * 24

    jobs = scrape_linkedin(search_terms=terms, results_per_term=args.results, hours_old=hours)

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="linkedin")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()
