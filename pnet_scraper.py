#!/usr/bin/env python3
"""
PNet Job Scraper
=================
Scrapes tech job listings from pnet.co.za.
PNet pages are server-rendered HTML — no browser needed.

URL pattern: https://www.pnet.co.za/jobs/{search-term}?pg={page}
Individual jobs: https://www.pnet.co.za/jobs--{slug}--{id}-inline.html

Can be used standalone or imported into gajit_scraper.py.

Setup:
    pip install requests beautifulsoup4

Usage (standalone):
    python pnet_scraper.py                          # Default search terms
    python pnet_scraper.py --search "data engineer"  # Single search
    python pnet_scraper.py --pages 5 --csv           # Limit pages, CSV output
"""

import argparse
import json
import re
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing: pip install beautifulsoup4")
    sys.exit(1)

# Use tls_client (mimics real browser TLS fingerprint) to bypass PNet's blocking.
# Falls back to requests if tls_client isn't available.
_session = None
def get_session():
    global _session
    if _session is not None:
        return _session
    try:
        import tls_client
        _session = tls_client.Session(
            client_identifier="chrome_120",
            random_tls_extension_order=True,
        )
        log("  Using tls_client (chrome_120 fingerprint)")
    except ImportError:
        import requests as _req
        _session = _req.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        log("  tls_client not found, falling back to requests (may get blocked)")
    return _session


def reset_session():
    """Discard the current TLS session so the next get_session() call creates a fresh one."""
    global _session
    _session = None


def fetch_page(url: str) -> str | None:
    """Fetch a page using the TLS session. Retries up to 3 times with session reset on error."""
    max_retries = 3
    for attempt in range(max_retries):
        session = get_session()
        try:
            resp = session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-ZA,en;q=0.9",
                },
                timeout_seconds=45,
            )
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                log(f"  PNet HTTP {resp.status_code} for {url[:80]}")
                return None
            return resp.text
        except TypeError:
            # requests session uses 'timeout' not 'timeout_seconds'
            try:
                resp = session.get(url, timeout=45)
                if resp.status_code != 200:
                    return None
                return resp.text
            except Exception as e:
                log(f"  PNet request error (attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            log(f"  PNet request error (attempt {attempt + 1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            wait = (attempt + 1) * 10  # 10s, then 20s
            log(f"  Resetting session, retrying in {wait}s...")
            reset_session()
            time.sleep(wait)

    return None


# ─── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://www.pnet.co.za/jobs"
REQUEST_DELAY = 2.5  # seconds between requests — be respectful

# Default search terms for tech roles
DEFAULT_SEARCHES = [
    "software-developer",
    "software-engineer",
    "javascript-developer",
    "full-stack-developer",
    "frontend-developer",
    "mobile-developer",
]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


# ─── Parse a single listing page ────────────────────────────────────────────
def parse_listing_page(html: str, search_term: str) -> list[dict]:
    """Extract job cards from a PNet search results page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # PNet job cards are typically <article> or <a> elements with job links
    # From the HTML we can see the pattern: links like /jobs--Title-Location-Company--ID-inline.html
    job_links = soup.find_all("a", href=re.compile(r"/jobs--.*--\d+-inline\.html"))

    seen_urls = set()
    for link in job_links:
        href = link.get("href", "")
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)

        full_url = f"https://www.pnet.co.za{href}" if href.startswith("/") else href

        # Walk up to find the card container
        card = link
        for _ in range(5):
            parent = card.parent
            if parent and parent.name in ("article", "div", "li", "section"):
                card = parent
            else:
                break

        card_text = card.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]

        # Extract title from the link or h2/h3 inside the card
        title_el = card.find(["h2", "h3"])
        title = title_el.get_text(strip=True) if title_el else ""
        if not title and lines:
            title = lines[0]

        # Extract company — usually in a separate element after title
        company = ""
        company_el = card.find("img", alt=True)
        if company_el:
            company = company_el.get("alt", "").strip()

        # Look for company name in text (typically second distinct line)
        if not company:
            for line in lines[1:]:
                # Skip lines that look like descriptions or metadata
                if len(line) < 60 and not any(kw in line.lower() for kw in ["more", "ago", "new", "easy apply"]):
                    company = line
                    break

        # Extract location
        location = ""
        for line in lines:
            # PNet locations often contain SA city names
            sa_cities = ["johannesburg", "cape town", "pretoria", "durban", "sandton",
                        "centurion", "midrand", "stellenbosch", "bryanston", "rosebank",
                        "port elizabeth", "gqeberha", "randburg", "century city",
                        "bellville", "wynberg", "brackenfell", "northern suburbs",
                        "southern suburbs", "somerset west", "parktown", "gauteng",
                        "western cape", "kwazulu-natal"]
            if any(city in line.lower() for city in sa_cities):
                location = line
                break

        # Extract description snippet
        description = ""
        for line in lines:
            if len(line) > 80:  # Long lines are likely description text
                description = line[:500]
                break

        # Extract time posted
        time_posted = ""
        for line in lines:
            if any(kw in line.lower() for kw in ["ago", "hour", "day", "week", "month"]):
                time_posted = line.strip()
                break

        # Detect remote/hybrid
        workplace = ""
        full_text = card_text.lower()
        if "fully remote" in full_text or "work from home" in full_text:
            workplace = "remote"
        elif "partially remote" in full_text or "hybrid" in full_text:
            workplace = "hybrid"

        # Detect employment type
        employment = ""
        if "full time" in full_text or "full-time" in full_text:
            employment = "fulltime"
        elif "part time" in full_text or "part-time" in full_text:
            employment = "parttime"
        elif "contract" in full_text:
            employment = "contract"
        elif "fixed term" in full_text:
            employment = "contract"
        elif "permanent" in full_text:
            employment = "permanent"

        # Convert relative time to date
        date_posted = ""
        now = datetime.now()
        time_lower = time_posted.lower()
        if "hour" in time_lower or "minute" in time_lower:
            date_posted = now.strftime("%Y-%m-%d")
        elif "day" in time_lower:
            try:
                days = int(re.search(r"(\d+)", time_lower).group(1))
                from datetime import timedelta
                date_posted = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            except:
                date_posted = now.strftime("%Y-%m-%d")
        elif "week" in time_lower:
            try:
                weeks = int(re.search(r"(\d+)", time_lower).group(1))
                from datetime import timedelta
                date_posted = (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d")
            except:
                pass
        elif "month" in time_lower:
            try:
                months = int(re.search(r"(\d+)", time_lower).group(1))
                from datetime import timedelta
                date_posted = (now - timedelta(days=months*30)).strftime("%Y-%m-%d")
            except:
                pass

        if title:
            jobs.append({
                "source": "pnet",
                "title": clean_title(title),
                "company": company,
                "company_logo": "",
                "company_url": "",
                "company_description": "",
                "company_industry": "",
                "company_size": "",
                "company_rating": None,
                "location": location,
                "city": extract_city(location),
                "country": "South Africa",
                "is_remote": workplace == "remote",
                "workplace_policy": workplace,
                "primary_role": search_term.replace("-", " ").title(),
                "other_roles": "",
                "must_have_skills": "",
                "nice_to_have_skills": "",
                "company_tech_stack": "",
                "experience_years": "",
                "job_level": "",
                "employment_type": employment,
                "date_posted": date_posted,
                "time_posted": "",
                "job_url": full_url,
                "job_url_direct": "",
                "description_snippet": clean_text(description, 500),
                "salary_min": None,
                "salary_max": None,
                "salary_currency": "",
                "salary_period": "",
                "visa_sponsorship": None,
                "requires_work_auth": None,
            })

    return jobs


def clean_title(title: str) -> str:
    """Clean up job title."""
    # Remove common PNet artifacts
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def clean_text(text: str, max_len: int = 500) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    # Remove markdown bold markers from PNet
    text = text.replace("**", "")
    if len(text) > max_len:
        text = text[:max_len].rsplit(' ', 1)[0] + "..."
    return text


def extract_city(location: str) -> str:
    """Pull the primary city from a PNet location string."""
    if not location:
        return ""
    cities = ["Johannesburg", "Cape Town", "Pretoria", "Durban", "Sandton",
              "Centurion", "Midrand", "Stellenbosch", "Bryanston", "Rosebank",
              "Port Elizabeth", "Gqeberha", "Randburg", "Bellville",
              "Century City", "Parktown", "Somerset West", "Wynberg",
              "Brackenfell", "George"]
    for city in cities:
        if city.lower() in location.lower():
            return city
    # Fall back to first part
    parts = location.split(",")
    return parts[0].strip() if parts else location


# ─── Fetch and parse individual job detail page ─────────────────────────────
def fetch_job_details(job: dict) -> dict:
    """
    Visit an individual PNet job page and extract rich details:
    company, description, industry, company size, benefits, location, logo.
    """
    url = job.get("job_url", "")
    if not url:
        return job

    html = fetch_page(url)
    if not html:
        return job

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    # ── Company name ──
    # PNet puts company in links to /cmp/en/CompanyName-ID/work.html
    company_link = soup.find("a", href=re.compile(r"/cmp/en/"))
    if company_link:
        company_text = company_link.get_text(strip=True)
        if company_text and len(company_text) < 100:
            job["company"] = company_text
        # Company URL
        href = company_link.get("href", "")
        if href:
            job["company_url"] = f"https://www.pnet.co.za{href}" if href.startswith("/") else href

    # Fallback 1: page title often reads "Job Title - Job with CompanyName in City"
    if not job.get("company"):
        title_tag = soup.find("title")
        if title_tag:
            m = re.search(r"\bwith\s+(.+?)\s+in\b", title_tag.get_text(strip=True), re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) < 80:
                    job["company"] = candidate

    # Fallback 2: extract from company URL slug (/cmp/en/CompanyName-ID/work.html)
    if not job.get("company") and job.get("company_url"):
        m = re.search(r'/cmp/en/(.+?)(?:/|\?|$)', job["company_url"])
        if m:
            slug = re.sub(r'-\d+$', '', m.group(1)).replace('-', ' ').strip()
            if slug:
                job["company"] = slug

    # ── Company logo ──
    logo_img = soup.find("img", alt=re.compile(r"logo", re.I))
    if logo_img:
        src = logo_img.get("data-src") or logo_img.get("src", "")
        if src and "gif;base64" not in src:
            job["company_logo"] = src if src.startswith("http") else f"https://www.pnet.co.za{src}"

    # ── Location ──
    # Title tag often has "Job with Company in Location"
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        match = re.search(r" in (.+?)$", title_text)
        if match:
            job["location"] = match.group(1).strip()
            job["city"] = extract_city(job["location"])

    # ── Full job description ──
    # The main description is typically the largest text block on the page
    # Look for the content between the job title and the company info section
    desc_parts = []
    for line in text.split("\n"):
        line = line.strip()
        # Skip navigation, headers, and footer content
        if not line or len(line) < 15:
            continue
        if any(skip in line.lower() for skip in [
            "sign in", "find jobs", "easy apply", "these jobs were popular",
            "open map", "company benefits", "show more benefits",
            "our location", "in short", "pnet is south africa",
            "company profile", "slide number"
        ]):
            continue
        # Description lines tend to be longer
        if len(line) > 30:
            desc_parts.append(line)

    if desc_parts:
        # The job description is usually the longest continuous block
        full_desc = " ".join(desc_parts)
        # Keep up to 3000 chars — enrich_jobs.py needs more text for accurate skill extraction
        job["description_snippet"] = clean_text(full_desc, 3000)

    # ── Industry ──
    industry_match = re.search(r"\*\*Industry\*\*\s*(.+?)(?:\n|$)", text)
    if not industry_match:
        # Try plain text pattern from the "In Short" section
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if "Industry" in line and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) < 60:
                    job["company_industry"] = next_line
                    break
            if line.strip().startswith("Industry") and len(line.strip()) > 10:
                job["company_industry"] = line.replace("Industry", "").strip()
                break

    # ── Company size ──
    for line in text.split("\n"):
        if re.search(r"\d+-\d+\s*(employees|Employees)", line):
            match = re.search(r"(\d[\d,]+-\d[\d,]+)", line)
            if match:
                job["company_size"] = match.group(1) + " employees"
                break

    # ── Company description (About us) ──
    about_idx = text.lower().find("about us")
    if about_idx > -1:
        about_text = text[about_idx + 8:about_idx + 800].strip()
        # Clean up - take until we hit navigation/footer content
        about_lines = []
        for line in about_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in ["popular with", "these jobs", "pnet is south"]):
                break
            about_lines.append(line)
        if about_lines:
            job["company_description"] = clean_text(" ".join(about_lines), 300)

    # ── Employment type from detail page ──
    text_lower = text.lower()
    if "permanent" in text_lower and not job["employment_type"]:
        job["employment_type"] = "permanent"
    elif "fixed term" in text_lower and not job["employment_type"]:
        job["employment_type"] = "contract"
    elif "contract" in text_lower and not job["employment_type"]:
        job["employment_type"] = "contract"

    # ── Remote/hybrid from detail page ──
    if not job["workplace_policy"]:
        if "fully remote" in text_lower or "work from home" in text_lower:
            job["workplace_policy"] = "remote"
            job["is_remote"] = True
        elif "hybrid" in text_lower or "partially remote" in text_lower:
            job["workplace_policy"] = "hybrid"

    # ── Auto-enrich: skills, tech stack, experience, level, blurb ──
    # Uses full page text for best extraction quality.
    try:
        import sys as _sys
        from pathlib import Path as _Path
        _sys.path.insert(0, str(_Path(__file__).parent))
        from enrich_jobs import enrich_job as _enrich  # type: ignore
        job = _enrich(job, full_text=text)
    except ImportError:
        pass  # enrich_jobs.py not present — run it as a separate step

    return job


# ─── Scrape all pages for a search term ─────────────────────────────────────
def scrape_pnet_search(search_term: str, max_pages: int = 100, cutoff_days: int = 30) -> list[dict]:
    """Scrape all pages for a given search term on PNet.

    Args:
        search_term: URL-slug search term (e.g. "software-developer")
        max_pages: Safety ceiling — stop after this many pages regardless (default: 100)
        cutoff_days: Only collect jobs posted within this many days; 0 = no cutoff (default: 30)
    """
    from datetime import timedelta
    all_jobs = []
    page = 1
    seen_in_search: set[str] = set()
    cutoff_date = (datetime.now() - timedelta(days=cutoff_days)).strftime("%Y-%m-%d") if cutoff_days else None

    while page <= max_pages:
        url = f"{BASE_URL}/{search_term}"
        if page > 1:
            url += f"?pg={page}"

        html = fetch_page(url)
        if html is None:
            log(f"  PNet: no response for page {page}, stopping.")
            break

        jobs = parse_listing_page(html, search_term)
        if not jobs:
            break

        # ── Loop detection: PNet recycles listings once results are exhausted ──
        new_jobs = [j for j in jobs if j.get("job_url") not in seen_in_search]
        for j in jobs:
            if j.get("job_url"):
                seen_in_search.add(j["job_url"])
        if not new_jobs:
            log(f"  PNet '{search_term}' page {page}: all duplicates, stopping.")
            break
        jobs = new_jobs
        # ──────────────────────────────────────────────────────────────────────

        if cutoff_date:
            # Include jobs with no date (assume recent); exclude only confirmed-old jobs
            recent = [j for j in jobs if not j.get("date_posted") or j.get("date_posted") >= cutoff_date]
            all_jobs.extend(recent)
            log(f"  PNet '{search_term}' page {page}: {len(recent)}/{len(jobs)} new within {cutoff_days}d")
            if len(recent) < len(jobs):
                # At least some confirmed-old jobs appeared — hit the date boundary
                break
        else:
            all_jobs.extend(jobs)
            log(f"  PNet '{search_term}' page {page}: {len(jobs)} new jobs")

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_jobs


# ─── Main PNet scraper ──────────────────────────────────────────────────────
def scrape_pnet(search_terms: list[str] = None, max_pages: int = 100,
                fetch_details: bool = True, cutoff_days: int = 30) -> list[dict]:
    """
    Scrape PNet across multiple search terms, deduplicate, then optionally
    fetch full details from each individual job page.

    Args:
        search_terms: List of URL-slug search terms (e.g. ["software-developer"])
        max_pages: Safety ceiling — max pages per search term (default: 100)
        fetch_details: If True, visit each job page for rich data (slower but much better)
        cutoff_days: Only collect jobs posted within this many days; 0 = no cutoff (default: 30)
    """
    if search_terms is None:
        search_terms = DEFAULT_SEARCHES

    log("PNet: Starting...")
    all_jobs = []

    for term in search_terms:
        jobs = scrape_pnet_search(term, max_pages=max_pages, cutoff_days=cutoff_days)
        all_jobs.extend(jobs)
        if jobs:
            time.sleep(1)

    # Deduplicate by URL
    seen = set()
    unique = []
    for job in all_jobs:
        url = job.get("job_url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(job)

    log(f"  PNet: {len(unique)} unique jobs (from {len(all_jobs)} raw)")

    # Fetch individual job details
    if fetch_details and unique:
        log(f"  PNet: Fetching details for {len(unique)} jobs (30s cooldown)...")
        time.sleep(30)
        for i, job in enumerate(unique):
            unique[i] = fetch_job_details(job)
            if (i + 1) % 10 == 0:
                log(f"    ... {i + 1}/{len(unique)} details fetched")
            time.sleep(REQUEST_DELAY)
        log(f"  PNet: All details fetched.")

    return unique


# ─── Standalone entry point ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="PNet SA Tech Job Scraper")
    parser.add_argument("--output", "-o", default="pnet_jobs.json")
    parser.add_argument("--search", default=None, help="Single search term (use hyphens: software-developer)")
    parser.add_argument("--pages", "-p", type=int, default=100, help="Safety ceiling: max pages per search term (default: 100)")
    parser.add_argument("--days", "-d", type=int, default=30, help="Only collect jobs posted within this many days (default: 30, use 0 for all)")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--no-details", action="store_true",
                        help="Skip fetching individual job pages (faster but less data)")
    args = parser.parse_args()

    terms = [args.search] if args.search else DEFAULT_SEARCHES
    jobs = scrape_pnet(search_terms=terms, max_pages=args.pages,
                       fetch_details=not args.no_details, cutoff_days=args.days)

    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pnet.co.za",
        "total_jobs": len(jobs),
        "jobs": jobs,
    }

    outpath = Path(args.output)
    outpath.write_text(json.dumps(output, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    log(f"\nSaved {len(jobs)} jobs -> {outpath}")

    if args.csv:
        import csv as csv_mod
        csv_path = outpath.with_suffix(".csv")
        if jobs:
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv_mod.DictWriter(f, fieldnames=jobs[0].keys(), extrasaction="ignore")
                writer.writeheader()
                for job in jobs:
                    writer.writerow(job)
            log(f"Saved CSV -> {csv_path}")

    # Summary
    if jobs:
        companies = set(j["company"] for j in jobs if j["company"])
        log(f"\n  Total: {len(jobs)} | Companies: {len(companies)}")
        log(f"\n  Sample:")
        for j in jobs[:5]:
            log(f"    {j['title'][:50]}")
            log(f"      {j['company'][:30]} | {j['city']} | {j['date_posted']}")


if __name__ == "__main__":
    main()