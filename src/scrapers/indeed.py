#!/usr/bin/env python3
"""
indeed_scraper.py — Standalone Indeed SA job scraper (via JobSpy)
==================================================================
Improvements over gajit_scraper.py:
  - 30-day window (hours_old=720, was 168)
  - 100 results per term (was 50)
  - 3000-char description snippets (was 500)
  - Company name fallback from description when missing

Usage:
    python indeed_scraper.py
    python indeed_scraper.py --results 100 --days 30
    python indeed_scraper.py -o indeed_jobs.json --csv
"""

import argparse
import re
import sys
import time

try:
    import requests  # noqa: F401 — ensure requests available
except ImportError:
    print("Missing: pip install requests")
    sys.exit(1)

from src.utils import log, parse_date, clean_text, save_jobs, parse_date_for_sort

DEFAULT_SEARCH_TERMS = [
    "software developer",
    "junior developer",
    "software engineer",
    "full stack developer",
    "javascript developer",
    "frontend developer",
]

_COMPANY_FROM_DESC_RE = re.compile(
    r'^([A-Z][A-Za-z0-9&\s\-\.]{1,49}?)\s+is\s+(?:a|an|the)\b',
    re.MULTILINE,
)

_UNLISTED = {"company unlisted", "unlisted", "confidential", "undisclosed", "n/a"}


def _company_from_indeed_url(url: str) -> str:
    """
    Extract company name from an Indeed company URL.
    e.g. https://za.indeed.com/cmp/Avbob          -> Avbob
         https://za.indeed.com/cmp/Some-Company    -> Some Company
         https://www.indeed.com/cmp/Takealot-Com   -> Takealot Com
    """
    if not url:
        return ""
    m = re.search(r'indeed\.com/cmp/([^/?#]+)', url)
    if not m:
        return ""
    slug = m.group(1).strip().rstrip('/')
    # Strip trailing numeric ID if present
    slug = re.sub(r'-\d+$', '', slug)
    # Convert hyphens/underscores to spaces — preserve original casing (Indeed uses Title Case)
    name = slug.replace('-', ' ').replace('_', ' ').strip()
    return name if name else ""


def _extract_company_from_desc(desc: str) -> str:
    """Attempt to infer company name from opening sentence of job description."""
    if not desc:
        return ""
    m = _COMPANY_FROM_DESC_RE.search(desc[:800])
    if m:
        candidate = m.group(1).strip()
        # Reject generic openers
        if candidate.lower() not in ("we", "our company", "the company", "this role"):
            return candidate
    return ""


def scrape_indeed(search_terms: list = None, results_per_term: int = 100,
                  hours_old: int = 720) -> list:
    """Scrape Indeed SA via JobSpy."""
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

            # Company — normalise placeholders, then try URL slug, then description regex
            company = clean_text(get("company_name", ""))
            if company.lower().strip() in _UNLISTED:
                company = ""
            company_url_val = str(get("company_url", ""))
            if not company and company_url_val:
                company = _company_from_indeed_url(company_url_val)
            if not company:
                company = _extract_company_from_desc(desc_full)

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

            all_jobs.append({
                "source": "indeed",
                "title": clean_text(get("title", "")),
                "company": company,
                "company_logo": str(get("company_logo", "")),
                "company_url": str(get("company_url", "")),
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
                "job_url": str(get("job_url", "")),
                "job_url_direct": str(get("job_url_direct", "")),
                "description_snippet": desc_snippet,
                "salary_min": salary_min,
                "salary_max": salary_max,
                "salary_currency": salary_currency,
                "salary_period": salary_period,
                "visa_sponsorship": None,
                "requires_work_auth": None,
            })

        log(f"  Indeed: {len(all_jobs)} total jobs so far")
        time.sleep(3)

    # Deduplicate by URL
    seen = set()
    unique = []
    for job in all_jobs:
        url = job.get("job_url", "")
        key = url if url else f"{job['title']}|{job['company']}".lower()
        if key not in seen:
            seen.add(key)
            unique.append(job)

    # Sort newest first
    unique.sort(
        key=lambda j: parse_date_for_sort(j.get("date_posted", ""), j.get("time_posted", "")),
        reverse=True,
    )

    log(f"Indeed: {len(unique)} unique jobs (from {len(all_jobs)} raw)")
    return unique


def main():
    parser = argparse.ArgumentParser(description="Indeed SA Job Scraper")
    parser.add_argument("-o", "--output", default="indeed_jobs.json",
                        help="Output JSON file (default: indeed_jobs.json)")
    parser.add_argument("--results", "-r", type=int, default=100,
                        help="Results per search term (default: 100)")
    parser.add_argument("--days", "-d", type=int, default=30,
                        help="Max age of listings in days (default: 30)")
    parser.add_argument("--search", default=None,
                        help="Single custom search term (overrides defaults)")
    parser.add_argument("--csv", action="store_true",
                        help="Also write a CSV file")
    args = parser.parse_args()

    terms = [args.search] if args.search else None
    hours = args.days * 24

    jobs = scrape_indeed(search_terms=terms, results_per_term=args.results, hours_old=hours)

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="indeed")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()
