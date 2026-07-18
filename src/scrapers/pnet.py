"""
pnet.py — PNet SA Job Scraper (HTML Parsing)
=============================================

Scrapes software development jobs from PNet South Africa (pnet.co.za)
using BeautifulSoup HTML parsing.

⚠️  DISCLAIMER: PNet actively blocks scrapers.
    This scraper uses TLS fingerprinting (tls_client) to bypass blocking.
    Falls back to requests if tls_client is not available.

Architecture:
-------------
1. Search Results Scraping:
   - Visits: https://www.pnet.co.za/jobs/{search-term}?pg={page}
   - Extracts job cards from HTML (BeautifulSoup)
   - Handles pagination and duplicate detection

2. Individual Job Detail Scraping (Optional):
   - Visits each job's detail page
   - Extracts: full description, company info, industry, logo, etc.
   - Uses 30s cooldown + 2.5s delay per job (slow but thorough)

3. Anti-Blocking:
   - TLS fingerprinting with chrome_120 (tls_client)
   - Session reset on errors
   - Exponential backoff retries (10s, then 20s)
   - Random delays between requests

Features:
---------
- 30-day lookback window (configurable)
- 100 pages max per search term (configurable)
- 3000-character description snippets
- Smart company name extraction (URL slug + page title)
- Company logo and industry extraction
- Remote/hybrid detection
- Automatic deduplication by URL
- Sorted newest-first
- Multiple CSS selectors for resilience against HTML changes
- Safe regex extraction with fallbacks

Performance:
------------
- ~6 search terms × 25 jobs/page = ~150 jobs per run
- Detail fetching: ~6+ minutes for 150 jobs (2.5s each + 30s cooldown)
- Total runtime: ~8-12 minutes (with details)

Dependencies:
-------------
- beautifulsoup4: HTML parsing
- tls-client: TLS fingerprinting (optional, falls back to requests)
- requests: HTTP client (fallback)

Environment:
------------
    None required (no API keys needed)

Recommendation:
---------------
    PNet is the most brittle scraper due to HTML reliance.
    Monitor regularly for failures and use --no-details for faster runs.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from src.utils import (
    log,
    clean_text,
    parse_date,
    parse_date_for_sort,
    retry,
    safe_get
)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    sys.exit(1)


# ─── Constants ──────────────────────────────────────────────────────────────

BASE_URL = "https://www.pnet.co.za/jobs"
"""Base URL for PNet search results."""

REQUEST_DELAY = 2.5
"""Seconds between requests — be respectful."""

MAX_PAGES = 100
"""Safety cap to prevent infinite pagination loops."""

# Default search terms (URL-slug format)
DEFAULT_SEARCH_TERMS: Tuple[str, ...] = (
    "software-developer",
    "software-engineer",
    "javascript-developer",
    "full-stack-developer",
    "frontend-developer",
    "mobile-developer",
)

# South African cities for location extraction
SA_CITIES: Tuple[str, ...] = (
    "johannesburg", "cape town", "pretoria", "durban", "sandton",
    "centurion", "midrand", "stellenbosch", "bryanston", "rosebank",
    "port elizabeth", "gqeberha", "randburg", "century city",
    "bellville", "wynberg", "brackenfell", "northern suburbs",
    "southern suburbs", "somerset west", "parktown", "gauteng",
    "western cape", "kwazulu-natal"
)

# HTML selectors to find job cards (multiple fallbacks)
JOB_LINK_SELECTORS: Tuple[str, ...] = (
    "a[href*='jobs--'][href*='-inline.html']",
    "article[class*='job'] a[href*='/jobs--']",
    "div[class*='listing'] a[href*='/jobs--']",
)
"""CSS selectors for job links, in order of preference."""


# ─── Session Management ──────────────────────────────────────────────────

_session = None


def get_session():
    """
    Get or create a TLS session with anti-blocking fingerprint.

    Uses tls_client for Chrome 120 fingerprint, falls back to requests.
    """
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


def reset_session() -> None:
    """
    Discard the current TLS session to force a fresh one on next request.
    Used during retries to bypass temporary blocks.
    """
    global _session
    _session = None


@retry(
    exceptions=(Exception,),
    tries=3,
    delay=5.0,
    backoff=2.0
)
def _fetch_page_with_retry(url: str) -> Optional[str]:
    """
    Fetch a page with retries using the TLS session.

    Args:
        url: URL to fetch.

    Returns:
        HTML content as string, or None if request fails.

    Note:
        Decorated with @retry for automatic retry on failure.
    """
    session = get_session()
    try:
        resp = session.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-ZA,en;q=0.9",
            },
            timeout_seconds=45,  # type: ignore
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
            log(f"  PNet request error: {e}")
            raise  # re-raise for retry
    except Exception as e:
        log(f"  PNet request error: {e}")
        raise  # re-raise for retry


def fetch_page(url: str) -> Optional[str]:
    """
    Fetch a page using the TLS session with retries.

    Args:
        url: URL to fetch.

    Returns:
        HTML content as string, or None if request fails.

    Note:
        Wrapper around _fetch_page_with_retry that catches the final failure
        and returns None gracefully.
    """
    try:
        return _fetch_page_with_retry(url)
    except Exception as e:
        log(f"  PNet page fetch failed after retries: {e}")
        return None


# ─── Helper Functions ──────────────────────────────────────────────────────

def clean_title(title: str) -> str:
    """
    Clean up a PNet job title by removing extra whitespace and artifacts.

    Args:
        title: Raw job title from PNet

    Returns:
        Cleaned title string
    """
    return re.sub(r'\s+', ' ', title).strip()


def extract_city(location: str) -> str:
    """
    Extract the primary city from a PNet location string.

    Args:
        location: Location string (e.g., "Johannesburg, Gauteng")

    Returns:
        City name or empty string if not found
    """
    if not location:
        return ""

    # Check against known SA cities
    for city in SA_CITIES:
        if city.title() in location or city.lower() in location.lower():
            return city.title()

    # Fallback: first part of location string
    parts = location.split(",")
    return parts[0].strip() if parts else location


def parse_relative_date(time_posted: str) -> str:
    """
    Convert a relative date string (e.g., "2 days ago") to YYYY-MM-DD.

    Args:
        time_posted: Relative date string from PNet

    Returns:
        Date in YYYY-MM-DD format or empty string
    """
    if not time_posted:
        return ""

    now = datetime.now()
    time_lower = time_posted.lower()

    # Safe regex extraction
    def safe_extract(pattern: str, text: str) -> Optional[str]:
        try:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        except (AttributeError, IndexError):
            pass
        return None

    try:
        if "hour" in time_lower or "minute" in time_lower:
            return now.strftime("%Y-%m-%d")

        if "day" in time_lower:
            days_str = safe_extract(r"(\d+)", time_lower)
            if days_str:
                days = int(days_str)
                return (now - timedelta(days=days)).strftime("%Y-%m-%d")

        if "week" in time_lower:
            weeks_str = safe_extract(r"(\d+)", time_lower)
            if weeks_str:
                weeks = int(weeks_str)
                return (now - timedelta(weeks=weeks)).strftime("%Y-%m-%d")

        if "month" in time_lower:
            months_str = safe_extract(r"(\d+)", time_lower)
            if months_str:
                months = int(months_str)
                return (now - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    except (ValueError, AttributeError):
        pass

    return ""


# ─── Parse Listing Page ────────────────────────────────────────────────────

def parse_listing_page(html: str, search_term: str) -> List[Dict[str, Any]]:
    """
    Extract job cards from a PNet search results page.

    Args:
        html: HTML content of the search results page
        search_term: The search term used (for primary_role field)

    Returns:
        List of job dictionaries with basic fields
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # ── Find job links using multiple selectors ──
    job_links = []
    for selector in JOB_LINK_SELECTORS:
        job_links = soup.select(selector)
        if job_links:
            break

    # Fallback: regex on all <a> tags
    if not job_links:
        job_links = soup.find_all("a", href=re.compile(r"/jobs--.*--\d+-inline\.html"))

    seen_urls: Set[str] = set()

    for link in job_links:
        # Convert href to string to avoid AttributeValueList issues
        href = str(link.get("href", ""))
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)

        full_url = f"https://www.pnet.co.za{href}" if href.startswith("/") else href

        # ── Walk up to find the card container ──
        card = link
        for _ in range(5):
            parent = card.parent
            if parent and parent.name in ("article", "div", "li", "section"):
                card = parent
            else:
                break

        card_text = card.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]

        # ── Title ──
        title_el = card.find(["h2", "h3", "h4"])
        title = title_el.get_text(strip=True) if title_el else ""
        if not title and lines:
            title = lines[0]

        # ── Company ──
        company = ""
        company_el = card.find("img", alt=True)
        if company_el:
            company = str(company_el.get("alt", "")).strip()

        if not company:
            for line in lines[1:]:
                if len(line) < 60 and not any(kw in line.lower() for kw in ["more", "ago", "new", "easy apply"]):
                    company = line
                    break

        # ── Location ──
        location = ""
        for line in lines:
            if any(city.lower() in line.lower() for city in SA_CITIES):
                location = line
                break

        # ── Description Snippet ──
        description = ""
        for line in lines:
            if len(line) > 80:
                description = line[:500]
                break

        # ── Time Posted ──
        time_posted = ""
        for line in lines:
            if any(kw in line.lower() for kw in ["ago", "hour", "day", "week", "month"]):
                time_posted = line.strip()
                break

        # ── Workplace Policy ──
        workplace = ""
        full_text = card_text.lower()
        if "fully remote" in full_text or "work from home" in full_text:
            workplace = "remote"
        elif "partially remote" in full_text or "hybrid" in full_text:
            workplace = "hybrid"

        # ── Employment Type ──
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

        # ── Date Posted ──
        date_posted = parse_relative_date(time_posted)

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


# ─── Parse Job Detail Page ─────────────────────────────────────────────────

def fetch_job_details(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Visit an individual PNet job page and extract rich details.

    Extracts:
        - Full company name (from multiple fallbacks)
        - Company logo
        - Full job description (up to 3000 chars)
        - Industry
        - Company size
        - About Us section
        - Enhanced location
        - Enhanced employment type

    Args:
        job: Basic job dictionary from listing page

    Returns:
        Enriched job dictionary (or original on failure)
    """
    url = job.get("job_url", "")
    if not url:
        return job

    try:
        html = fetch_page(url)
        if not html:
            return job

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)

        # ── Company Name ──
        # Method 1: Company link (/cmp/en/CompanyName-ID/work.html)
        company_link = soup.find("a", href=re.compile(r"/cmp/en/"))
        if company_link:
            company_text = company_link.get_text(strip=True)
            if company_text and len(company_text) < 100:
                job["company"] = company_text

            href = str(company_link.get("href", ""))
            if href:
                job["company_url"] = f"https://www.pnet.co.za{href}" if href.startswith("/") else href

        # Method 2: Page title ("Job Title - Job with CompanyName in City")
        if not job.get("company"):
            title_tag = soup.find("title")
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                match = re.search(r"\bwith\s+(.+?)\s+in\b", title_text, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()
                    if candidate and len(candidate) < 80:
                        job["company"] = candidate

        # Method 3: URL slug (/cmp/en/CompanyName-ID/work.html)
        if not job.get("company") and job.get("company_url"):
            match = re.search(r'/cmp/en/(.+?)(?:/|\?|$)', str(job["company_url"]))
            if match:
                slug = re.sub(r'-\d+$', '', match.group(1)).replace('-', ' ').strip()
                if slug:
                    job["company"] = slug

        # ── Company Logo ──
        logo_img = soup.find("img", alt=re.compile(r"logo", re.I))
        if logo_img:
            src = str(logo_img.get("data-src") or logo_img.get("src", ""))
            if src and "gif;base64" not in src:
                job["company_logo"] = src if src.startswith("http") else f"https://www.pnet.co.za{src}"

        # ── Location from Title ──
        title_tag = soup.find("title")
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            match = re.search(r" in (.+?)$", title_text)
            if match:
                job["location"] = match.group(1).strip()
                job["city"] = extract_city(job["location"])

        # ── Full Description ──
        desc_parts = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or len(line) < 15:
                continue

            # Skip navigation/footer content
            skip_keywords = (
                "sign in", "find jobs", "easy apply", "these jobs were popular",
                "open map", "company benefits", "show more benefits",
                "our location", "in short", "pnet is south africa",
                "company profile", "slide number"
            )
            if any(kw in line.lower() for kw in skip_keywords):
                continue

            if len(line) > 30:
                desc_parts.append(line)

        if desc_parts:
            full_desc = " ".join(desc_parts)
            job["description_snippet"] = clean_text(full_desc, 3000)

        # ── Industry ──
        industry_match = re.search(r"\*\*Industry\*\*\s*(.+?)(?:\n|$)", text)
        if not industry_match:
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

        # ── Company Size ──
        for line in text.split("\n"):
            if re.search(r"\d+-\d+\s*(employees|Employees)", line):
                match = re.search(r"(\d[\d,]+-\d[\d,]+)", line)
                if match:
                    job["company_size"] = match.group(1) + " employees"
                    break

        # ── Company Description (About Us) ──
        about_idx = text.lower().find("about us")
        if about_idx > -1:
            about_text = text[about_idx + 8:about_idx + 800].strip()
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

        # ── Employment Type (Enhanced) ──
        text_lower = text.lower()
        if "permanent" in text_lower and not job["employment_type"]:
            job["employment_type"] = "permanent"
        elif "fixed term" in text_lower and not job["employment_type"]:
            job["employment_type"] = "contract"
        elif "contract" in text_lower and not job["employment_type"]:
            job["employment_type"] = "contract"

        # ── Workplace Policy (Enhanced) ──
        if not job["workplace_policy"]:
            if "fully remote" in text_lower or "work from home" in text_lower:
                job["workplace_policy"] = "remote"
                job["is_remote"] = True
            elif "hybrid" in text_lower or "partially remote" in text_lower:
                job["workplace_policy"] = "hybrid"

    except Exception as e:
        log(f"  Detail fetch error for {url[:60]}: {e}")
        # Return original job unchanged

    return job


# ─── Scrape Search Term ────────────────────────────────────────────────────

def scrape_pnet_search(
    search_term: str,
    max_pages: int = MAX_PAGES,
    cutoff_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Scrape all pages for a given search term on PNet.

    Args:
        search_term: URL-slug search term (e.g., "software-developer")
        max_pages: Safety ceiling – stop after this many pages
        cutoff_days: Only collect jobs posted within this many days (0 = no cutoff)

    Returns:
        List of job dictionaries from this search term
    """
    all_jobs = []
    page = 1
    seen_in_search: Set[str] = set()
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

        # Loop detection: PNet recycles listings once results are exhausted
        new_jobs = [j for j in jobs if j.get("job_url") not in seen_in_search]
        for j in jobs:
            if j.get("job_url"):
                seen_in_search.add(j["job_url"])

        if not new_jobs:
            log(f"  PNet '{search_term}' page {page}: all duplicates, stopping.")
            break

        jobs = new_jobs

        # Filter by cutoff date
        if cutoff_date:
            recent = [
                j for j in jobs
                if not j.get("date_posted") or (j.get("date_posted") and j["date_posted"] >= cutoff_date)
            ]
            all_jobs.extend(recent)
            log(f"  PNet '{search_term}' page {page}: {len(recent)}/{len(jobs)} new within {cutoff_days}d")

            if len(recent) < len(jobs):
                # Hit the date boundary
                break
        else:
            all_jobs.extend(jobs)
            log(f"  PNet '{search_term}' page {page}: {len(jobs)} new jobs")

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_jobs


# ─── Main Scraper ──────────────────────────────────────────────────────────

def scrape_pnet(
    search_terms: Optional[List[str]] = None,
    max_pages: int = MAX_PAGES,
    fetch_details: bool = True,
    cutoff_days: int = 30
) -> List[Dict[str, Any]]:
    """
    Scrape PNet across multiple search terms with optional detail fetching.

    Args:
        search_terms: List of URL-slug search terms (defaults to DEFAULT_SEARCH_TERMS)
        max_pages: Safety ceiling – max pages per search term (default: 100)
        fetch_details: If True, visit each job page for rich data (slower but better)
        cutoff_days: Only collect jobs posted within this many days (default: 30)

    Returns:
        List of unique job dictionaries

    Note:
        Detail fetching adds significant runtime:
        - ~6+ minutes for 150 jobs
        - Use --no-details for faster runs
    """
    if search_terms is None:
        search_terms = list(DEFAULT_SEARCH_TERMS)

    log("PNet: Starting...")
    all_jobs = []

    for term in search_terms:
        jobs = scrape_pnet_search(term, max_pages=max_pages, cutoff_days=cutoff_days)
        all_jobs.extend(jobs)
        if jobs:
            time.sleep(1)

    # Deduplicate by URL
    seen: Set[str] = set()
    unique: List[Dict[str, Any]] = []

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


# ─── Standalone Entry Point ───────────────────────────────────────────────

def main() -> None:
    """
    Command-line entry point for standalone PNet scraper.
    """
    parser = argparse.ArgumentParser(
        description="PNet SA Tech Job Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.scrapers.pnet
    python -m src.scrapers.pnet --search "data-engineer" --pages 5
    python -m src.scrapers.pnet --no-details --csv

Output:
    data/cache/pnet_jobs.json (or custom filename with -o)
    data/cache/pnet_jobs.csv (if --csv flag is used)

⚠️  WARNING: PNet actively blocks scrapers.
    This scraper uses tls_client for TLS fingerprinting.
    If it fails, try installing tls_client: pip install tls-client

Note:
    Detail fetching (--no-details to skip) takes ~6+ minutes for 150 jobs.
    Use --no-details for faster runs.
        """
    )
    parser.add_argument(
        "-o", "--output", default="data/cache/pnet_jobs.json",
        help="Output JSON file (default: data/cache/pnet_jobs.json)"
    )
    parser.add_argument(
        "--search", default=None,
        help="Single search term (use hyphens: software-developer)"
    )
    parser.add_argument(
        "--pages", "-p", type=int, default=MAX_PAGES,
        help=f"Safety ceiling: max pages per search term (default: {MAX_PAGES})"
    )
    parser.add_argument(
        "--days", "-d", type=int, default=30,
        help="Only collect jobs posted within this many days (default: 30, use 0 for all)"
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Also write a CSV file"
    )
    parser.add_argument(
        "--no-details", action="store_true",
        help="Skip fetching individual job pages (faster but less data)"
    )
    args = parser.parse_args()

    terms = [args.search] if args.search else None
    jobs = scrape_pnet(
        search_terms=terms,
        max_pages=args.pages,
        fetch_details=not args.no_details,
        cutoff_days=args.days
    )

    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source": "pnet.co.za",
        "total_jobs": len(jobs),
        "jobs": jobs,
    }

    outpath = Path(args.output)
    outpath.write_text(
        json.dumps(output, indent=2, default=str, ensure_ascii=False),
        encoding='utf-8'
    )
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