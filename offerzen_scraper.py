#!/usr/bin/env python3
"""
offerzen_scraper.py — Standalone OfferZen scraper
==================================================
Scrapes all SA tech jobs from OfferZen's public API.

Usage:
    python offerzen_scraper.py
    python offerzen_scraper.py -o offerzen_jobs.json
    python offerzen_scraper.py --csv
"""

import argparse
import sys
import time

try:
    import requests
except ImportError:
    print("Missing: pip install requests")
    sys.exit(1)

from scraper_utils import log, parse_date, clean_text, save_jobs, SA_KEYWORDS


OFFERZEN_API = "https://oz-public.vercel.app/api/jobs"
OFFERZEN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.offerzen.com/jobs",
}


def scrape_offerzen() -> list:
    """Scrape all jobs from OfferZen's public API with full data extraction."""
    log("OfferZen: Starting...")
    all_jobs = []
    page = 1

    while True:
        try:
            resp = requests.get(
                f"{OFFERZEN_API}/{page}?sort_direction=desc",
                headers=OFFERZEN_HEADERS, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"  OfferZen page {page} error: {e}")
            break

        listings = data.get("jobListings", [])
        if not listings:
            break

        for raw in listings:
            company = raw.get("company_profile", {})
            locations = raw.get("locations", [])

            # Build location strings
            loc_strs = []
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

            # Skills
            must_have = [s.get("skill", "") for s in raw.get("must_have_skill_experiences", []) if s.get("skill")]
            nice_to_have = raw.get("nice_to_have_skills", [])
            if isinstance(nice_to_have, list) and nice_to_have and isinstance(nice_to_have[0], dict):
                nice_to_have = [s.get("skill", "") for s in nice_to_have if s.get("skill")]
            elif not isinstance(nice_to_have, list):
                nice_to_have = []

            # Company tech stack
            tech_stack = [t.get("title", "") for t in company.get("tech_stack", []) if t.get("title")]

            # Other roles
            other_roles = [r.get("name", "") for r in raw.get("other_roles", []) if r.get("name")]

            # Parse dates
            date_str, time_str = parse_date(raw.get("published_at", ""))

            all_jobs.append({
                "source": "offerzen",
                "title": raw.get("name", ""),
                "company": company.get("name", ""),
                "company_logo": company.get("logo_small_url", ""),
                "company_url": f"https://www.offerzen.com/companies/{company.get('id', '')}",
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
                "job_url": f"https://www.offerzen.com/companies/{company.get('id', '')}",
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
        time.sleep(1.5)

    # Filter to SA only
    sa_jobs = [j for j in all_jobs if any(kw in j["location"].lower() for kw in SA_KEYWORDS)]
    log(f"  OfferZen: {len(sa_jobs)} SA jobs (of {len(all_jobs)} total)")
    return sa_jobs


def main():
    parser = argparse.ArgumentParser(description="OfferZen SA Job Scraper")
    parser.add_argument("-o", "--output", default="offerzen_jobs.json",
                        help="Output JSON file (default: offerzen_jobs.json)")
    parser.add_argument("--csv", action="store_true",
                        help="Also write a CSV file")
    args = parser.parse_args()

    jobs = scrape_offerzen()

    if not jobs:
        log("No jobs found.")
        sys.exit(1)

    save_jobs(jobs, args.output, write_csv=args.csv, source_name="offerzen")
    log(f"Done. {len(jobs)} jobs saved to {args.output}")


if __name__ == "__main__":
    main()
