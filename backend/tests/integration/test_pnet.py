"""
Integration tests for PNet scraper (src/scrapers/pnet.py).

These tests verify that the PNet scraper correctly:
- Fetches and parses listing pages with multiple CSS selectors.
- Extracts job cards with title, company, location, date, etc.
- Fetches and parses individual job detail pages.
- Extracts rich details: company, logo, description, industry, etc.
- Handles pagination and duplicate detection.
- Deduplicates jobs across search terms.
- Handles errors gracefully (empty HTML, malformed pages).

All tests use requests_mock to simulate HTTP responses,
so no real network calls are made during testing.
The tests force the scraper to use `requests` instead of `tls_client`
by mocking the `get_session` function to return a standard `requests.Session`.
"""

import pytest
import requests_mock
import time
from unittest.mock import patch, MagicMock
from src.scrapers.pnet import scrape_pnet, fetch_job_details, parse_listing_page


# ─── Mock HTML Responses ──────────────────────────────────────────────────

# HTML for a listing page with a few job cards
LISTING_HTML = """
<html>
<body>
<div class="listing">
    <a href="/jobs--Software-Engineer-CapeTown--123-inline.html">Software Engineer</a>
    <div class="job-details">
        <img alt="Acme Corp" src="logo.png"/>
        <div class="location">Cape Town, South Africa</div>
        <div class="description">We are looking for a software engineer...</div>
        <div class="posted">2 days ago</div>
        <div>Full time, Permanent</div>
        <div class="tags">fully remote</div>
    </div>
</div>
<div class="listing">
    <a href="/jobs--Data-Scientist-Johannesburg--456-inline.html">Data Scientist</a>
    <div class="job-details">
        <img alt="DataCorp" src="logo2.png"/>
        <div class="location">Johannesburg, Gauteng</div>
        <div class="description">Data science role with Python...</div>
        <div class="posted">1 week ago</div>
        <div>Contract</div>
        <div class="tags">hybrid</div>
    </div>
</div>
</body>
</html>
"""

# HTML for a job detail page
DETAIL_HTML = """
<html>
<head>
    <title>Software Engineer - Job with Acme Corp in Cape Town</title>
</head>
<body>
    <a href="/cmp/en/Acme-Corp-123/work.html">Acme Corp</a>
    <img alt="company logo" data-src="https://example.com/logo.png"/>
    <div class="description">
        <p>Job description paragraph 1</p>
        <p>Job description paragraph 2 with skills like Python, Django.</p>
    </div>
    <div>
        <span>Industry</span>
        <span>Technology</span>
    </div>
    <div>
        <span>Company size</span>
        <span>100-200 employees</span>
    </div>
    <div>About us</div>
    <p>Company description text about Acme Corp.</p>
</body>
</html>
"""

# HTML for a listing page with no jobs
EMPTY_LISTING_HTML = """
<html>
<body>
    <div>No results found</div>
</body>
</html>
"""

# HTML for a detail page with no company info (and a long description)
DETAIL_HTML_NO_COMPANY = """
<html>
<head>
    <title>Software Engineer - Job in Cape Town</title>
</head>
<body>
    <p>This is the job description paragraph with enough text to be extracted by the scraper.</p>
    <p>Second paragraph with more details.</p>
</body>
</html>
"""


# ─── Helper Functions ──────────────────────────────────────────────────────

def _mock_listing_page(mock_obj, search_term, page=1, html=LISTING_HTML):
    """Mock the listing page for a given search term and page."""
    url = f"https://www.pnet.co.za/jobs/{search_term}"
    if page > 1:
        url += f"?pg={page}"
    mock_obj.get(url, text=html)


def _mock_detail_page(mock_obj, job_id, html=DETAIL_HTML):
    """Mock a job detail page for a specific job ID."""
    url = f"https://www.pnet.co.za/jobs--Software-Engineer-CapeTown--{job_id}-inline.html"
    mock_obj.get(url, text=html)


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_requests():
    """Provide a requests_mock mocker and force PNet to use requests."""
    with requests_mock.Mocker() as m:
        # Patch get_session to return a standard requests.Session
        with patch('src.scrapers.pnet.get_session') as mock_get_session:
            import requests
            mock_get_session.return_value = requests.Session()
            yield m


# ─── Test Cases ─────────────────────────────────────────────────────────────

def test_parse_listing_page_success():
    """
    Test that the listing page parser extracts job cards correctly.

    Given:
    - HTML with two job cards (one remote, one hybrid).

    Expected:
    - Two job dictionaries with correct fields.
    """
    jobs = parse_listing_page(LISTING_HTML, search_term="software-engineer")

    assert len(jobs) == 2

    # Verify first job (remote)
    job1 = jobs[0]
    assert job1["title"] == "Software Engineer"
    assert job1["company"] == "Acme Corp"  # from img alt
    assert job1["location"] == "Cape Town, South Africa"
    assert job1["city"] == "Cape Town"
    assert job1["country"] == "South Africa"
    assert job1["is_remote"] is True  # because "fully remote" in tags
    assert job1["workplace_policy"] == "remote"
    assert job1["employment_type"] == "fulltime"  # "Full time, Permanent"
    assert job1["date_posted"] is not None  # date parsed from "2 days ago"
    assert job1["primary_role"] == "Software Engineer"  # from search term title case

    # Verify second job (hybrid)
    job2 = jobs[1]
    assert job2["title"] == "Data Scientist"
    assert job2["company"] == "DataCorp"
    assert job2["location"] == "Johannesburg, Gauteng"
    assert job2["city"] == "Johannesburg"
    assert job2["is_remote"] is False
    assert job2["workplace_policy"] == "hybrid"
    assert job2["employment_type"] == "contract"


def test_parse_listing_page_empty():
    """
    Test that empty HTML returns empty list.
    """
    jobs = parse_listing_page(EMPTY_LISTING_HTML, search_term="software-engineer")
    assert jobs == []


def test_parse_listing_page_no_job_links():
    """
    Test HTML without job links returns empty list.
    """
    html = "<html><body>No jobs here</body></html>"
    jobs = parse_listing_page(html, search_term="software-engineer")
    assert jobs == []


@patch('src.scrapers.pnet.time.sleep')  # speed up tests
def test_scrape_pnet_search_success(mock_sleep, mock_requests):
    """
    Test scraping a search term with multiple pages.

    Given:
    - Listing page 1 has 2 jobs.
    - Listing page 2 has 1 new job (replaces one of the jobs).
    - Listing page 3 is empty (end of results).

    Expected:
    - 3 jobs are returned (2 from page 1 + 1 from page 2).
    - Duplicates are handled.
    """
    # Create a second page with a different job
    listing_page_2 = LISTING_HTML.replace("Software Engineer", "Senior Developer")
    listing_page_2 = listing_page_2.replace("jobs--Software-Engineer-CapeTown--123-inline.html",
                                            "jobs--Senior-Developer-Johannesburg--789-inline.html")

    _mock_listing_page(mock_requests, "software-engineer", page=1)
    _mock_listing_page(mock_requests, "software-engineer", page=2, html=listing_page_2)
    _mock_listing_page(mock_requests, "software-engineer", page=3, html=EMPTY_LISTING_HTML)

    # Mock detail pages for the jobs found (we'll mock a few)
    # We'll mock 3 detail pages for the unique jobs
    _mock_detail_page(mock_requests, 123)  # Software Engineer
    _mock_detail_page(mock_requests, 456)  # Data Scientist
    _mock_detail_page(mock_requests, 789)  # Senior Developer

    # Disable detail fetching to keep it fast
    jobs = scrape_pnet(search_terms=["software-engineer"], fetch_details=False, max_pages=3)

    # Should have 3 jobs (2 from page 1, 1 from page 2)
    assert len(jobs) == 3

    # Check titles: should have "Software Engineer", "Data Scientist", "Senior Developer"
    titles = [j["title"] for j in jobs]
    assert "Software Engineer" in titles
    assert "Data Scientist" in titles
    assert "Senior Developer" in titles


@patch('src.scrapers.pnet.time.sleep')
def test_scrape_pnet_search_empty(mock_sleep, mock_requests):
    """
    Test scraping when no jobs are found.

    Given:
    - First page returns empty HTML.

    Expected:
    - Empty list.
    """
    _mock_listing_page(mock_requests, "software-engineer", page=1, html=EMPTY_LISTING_HTML)

    jobs = scrape_pnet(search_terms=["software-engineer"], fetch_details=False)
    assert jobs == []


@patch('src.scrapers.pnet.time.sleep')
def test_scrape_pnet_deduplication(mock_sleep, mock_requests):
    """
    Test that duplicate URLs are removed across pages.

    Given:
    - Two pages with overlapping jobs.

    Expected:
    - Unique jobs only.
    """
    # Page 1 has job1 and job2
    # Page 2 has job2 (duplicate) and job3
    # Create a modified version of LISTING_HTML with job2 removed and job3 added
    # For simplicity, we'll just use the same HTML for both pages but with different URLs
    # Actually, we'll mock page 1 and page 2 with same URLs (duplicates)
    _mock_listing_page(mock_requests, "software-engineer", page=1, html=LISTING_HTML)
    _mock_listing_page(mock_requests, "software-engineer", page=2, html=LISTING_HTML)  # same jobs
    _mock_listing_page(mock_requests, "software-engineer", page=3, html=EMPTY_LISTING_HTML)

    # Mock detail pages for 2 jobs (since only 2 unique)
    _mock_detail_page(mock_requests, 123)
    _mock_detail_page(mock_requests, 456)

    jobs = scrape_pnet(search_terms=["software-engineer"], fetch_details=False, max_pages=3)

    # Should have 2 unique jobs (since page 2 had duplicates)
    assert len(jobs) == 2


@patch('src.scrapers.pnet.time.sleep')
def test_fetch_job_details_success(mock_sleep, mock_requests):
    """
    Test that fetching a job detail page enriches the job with rich data.

    Given:
    - A job with a URL to a detail page.
    - Detail page returns HTML with company name, logo, description, etc.

    Expected:
    - Job dictionary is updated with new fields.
    """
    job = {
        "job_url": "https://www.pnet.co.za/jobs--Software-Engineer-CapeTown--123-inline.html",
        "title": "Software Engineer",
        "company": "",
        "company_logo": "",
        "location": "",
        "description_snippet": "",
    }

    # Mock the detail page
    _mock_detail_page(mock_requests, 123)

    enriched_job = fetch_job_details(job)

    assert enriched_job["company"] == "Acme Corp"
    assert enriched_job["company_url"].startswith("https://www.pnet.co.za/cmp/en/")
    assert enriched_job["company_logo"] == "https://example.com/logo.png"
    assert "Job description paragraph" in enriched_job["description_snippet"]
    assert enriched_job["company_industry"] == "Technology"
    assert enriched_job["company_size"] == "100-200 employees"
    assert "Acme Corp" in enriched_job["company_description"]


@patch('src.scrapers.pnet.time.sleep')
def test_fetch_job_details_missing_company(mock_sleep, mock_requests):
    """
    Test that job details are handled gracefully when company info is missing.

    Given:
    - Detail page without company name or logo.
    - But it has a long description.

    Expected:
    - Job retains original fields.
    - No exception raised.
    - Description snippet is extracted from the page.
    """
    job = {
        "job_url": "https://www.pnet.co.za/jobs--Software-Engineer-CapeTown--123-inline.html",
        "title": "Software Engineer",
        "company": "Unknown",
        "description_snippet": "old desc",
    }

    # Mock detail page without company info
    _mock_detail_page(mock_requests, 123, html=DETAIL_HTML_NO_COMPANY)

    enriched_job = fetch_job_details(job)

    # Company should remain unchanged (unless overridden)
    assert enriched_job["company"] == "Unknown"  # not overwritten
    assert enriched_job.get("company_logo", "") == ""
    # Description snippet should be updated from the detail page
    assert "This is the job description paragraph" in enriched_job["description_snippet"]


@patch('src.scrapers.pnet.time.sleep')
def test_fetch_job_details_http_error(mock_sleep, mock_requests):
    """
    Test that fetch_job_details returns the original job if HTTP fails.

    Given:
    - The detail page returns a 404.

    Expected:
    - Original job is returned.
    """
    job = {
        "job_url": "https://www.pnet.co.za/jobs--Software-Engineer-CapeTown--123-inline.html",
        "title": "Software Engineer",
        "company": "Acme",
    }

    mock_requests.get(job["job_url"], status_code=404)

    enriched_job = fetch_job_details(job)

    # Should be the same as input
    assert enriched_job == job


@patch('src.scrapers.pnet.time.sleep')
def test_scrape_pnet_full_integration(mock_sleep, mock_requests):
    """
    Full integration test: scrape all search terms, with detail fetching.

    Given:
    - Two search terms: "software-engineer" and "full-stack-developer".
    - Each has a listing page with 2 jobs.
    - Detail pages are mocked.

    Expected:
    - Total of 4 jobs, deduplicated across terms.
    """
    # Mock listing pages for both terms
    for term in ["software-engineer", "full-stack-developer"]:
        _mock_listing_page(mock_requests, term, page=1, html=LISTING_HTML)
        _mock_listing_page(mock_requests, term, page=2, html=EMPTY_LISTING_HTML)

    # Mock detail pages for each job (assuming 2 unique jobs per term)
    # We'll mock detail pages for IDs 123, 456 (from the HTML)
    for i in [123, 456]:
        _mock_detail_page(mock_requests, i)

    jobs = scrape_pnet(search_terms=["software-engineer", "full-stack-developer"], fetch_details=True, max_pages=2)

    # Since both terms use the same listing HTML, we'll have duplicates.
    # The dedup should reduce to 2 unique jobs.
    assert len(jobs) == 2