"""
Integration tests for Indeed scraper (src/scrapers/indeed.py).

These tests verify that the Indeed scraper correctly:
- Builds search terms and calls JobSpy.
- Parses JobSpy DataFrame responses into job dictionaries.
- Extracts company names from URL slugs and descriptions.
- Handles salaries, locations, and employment types.
- Deduplicates jobs by URL.
- Handles empty responses and JobSpy errors.

All tests mock the JobSpy library at the module level,
so no real network calls are made during testing.
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime
from src.scrapers.indeed import scrape_indeed


# ─── Test Data ──────────────────────────────────────────────────────────────

def _create_mock_jobspy_df():
    """
    Create a pandas DataFrame mimicking JobSpy's output.

    Returns:
        pd.DataFrame: Mocked job data with realistic columns.
    """
    # Mock location object
    class MockLocation:
        def __init__(self, city, state, country):
            self.city = city
            self.state = state
            self.country = country

    # Mock compensation object
    class MockCompensation:
        def __init__(self, min_amount, max_amount, currency, interval):
            self.min_amount = min_amount
            self.max_amount = max_amount
            self.currency = currency
            self.interval = interval

    data = {
        "title": ["Software Developer", "Junior Developer", "Full Stack Developer"],
        "company_name": ["TechCorp", "Startup Inc", "Enterprise Ltd"],
        "company_url": [
            "https://za.indeed.com/cmp/TechCorp",
            "https://za.indeed.com/cmp/Startup-Inc",
            "https://za.indeed.com/cmp/Enterprise-Ltd-123"
        ],
        "company_logo": ["logo1.png", "logo2.png", "logo3.png"],
        "company_description": ["About TechCorp...", "", "About Enterprise..."],
        "company_industry": ["Tech", "", "Finance"],
        "company_num_employees": ["100-200", "10-50", "1000-5000"],
        "company_rating": [4.5, None, 3.8],
        "location": [
            MockLocation("Cape Town", "Western Cape", "South Africa"),
            MockLocation("Johannesburg", "Gauteng", "South Africa"),
            MockLocation("Durban", "Kwazulu-Natal", "South Africa")
        ],
        "is_remote": [False, True, False],
        "work_from_home_type": ["", "remote", ""],
        "job_function": ["Software Engineer", "Junior Developer", "Full Stack"],
        "experience_range": ["3-5 years", "0-2 years", "5-7 years"],
        "job_level": ["mid", "junior", "senior"],
        "job_type": ["fulltime", "fulltime", "contract"],
        "date_posted": ["2026-07-19T10:00:00Z", "2026-07-18T14:30:00Z", "2026-07-17T08:00:00Z"],
        "job_url": [
            "https://za.indeed.com/viewjob?jk=abc123",
            "https://za.indeed.com/viewjob?jk=def456",
            "https://za.indeed.com/viewjob?jk=ghi789"
        ],
        "job_url_direct": ["", "", ""],
        "description": [
            "We are looking for a software developer with Python, Django, and PostgreSQL experience.",
            "Junior developer role with JavaScript, React, and Node.js.",
            "Full stack developer with Java, Spring Boot, and React. "
        ],
        "skills": [["Python", "Django", "PostgreSQL"], ["JavaScript", "React"], ["Java", "Spring Boot", "React"]],
        "compensation": [
            MockCompensation(50000, 70000, "ZAR", "monthly"),
            MockCompensation(30000, 40000, "ZAR", "monthly"),
            MockCompensation(80000, 100000, "ZAR", "monthly")
        ],
        "min_amount": [None, None, None],
        "max_amount": [None, None, None],
        "currency": ["", "", ""],
        "interval": ["", "", ""],
    }

    return pd.DataFrame(data)


def _create_empty_jobspy_df():
    """Return an empty DataFrame for testing no results."""
    return pd.DataFrame()


# ─── Test Cases ─────────────────────────────────────────────────────────────

# FIX: Patch 'jobspy.scrape_jobs' instead of 'src.scrapers.indeed.scrape_jobs'
@patch('jobspy.scrape_jobs')
def test_scrape_indeed_success(mock_scrape_jobs):
    """
    Test successful scraping with multiple job results.

    Given:
    - JobSpy returns a DataFrame with 3 jobs.
    - All jobs are parsed correctly.

    Expected:
    - 3 jobs returned.
    - All fields correctly extracted and formatted.
    - Company names extracted from URL slugs.
    - Locations parsed correctly.
    - Salary ranges formatted.
    """
    # Set up mock to return our test DataFrame
    mock_scrape_jobs.return_value = _create_mock_jobspy_df()

    jobs = scrape_indeed(search_terms=["software developer"], results_per_term=10)

    assert len(jobs) == 3

    # Verify first job
    job = jobs[0]
    assert job["source"] == "indeed"
    assert job["title"] == "Software Developer"
    assert job["company"] == "TechCorp"  # Extracted from URL
    assert job["city"] == "Cape Town"
    assert job["country"] == "South Africa"
    assert job["is_remote"] is False
    assert job["workplace_policy"] == ""
    assert job["must_have_skills"] == "Python, Django, PostgreSQL"
    assert job["experience_years"] == "3-5 years"
    assert job["job_level"] == "mid"
    assert job["employment_type"] == "fulltime"
    assert job["date_posted"] == "2026-07-19"
    assert job["time_posted"] == "10:00:00"
    assert job["salary_min"] == 50000
    assert job["salary_max"] == 70000
    assert job["salary_currency"] == "ZAR"
    assert job["salary_period"] == "monthly"

    # Verify second job (remote)
    job2 = jobs[1]
    assert job2["company"] == "Startup Inc"
    assert job2["is_remote"] is True
    assert job2["workplace_policy"] == "remote"
    assert job2["salary_min"] == 30000
    assert job2["salary_max"] == 40000


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_empty(mock_scrape_jobs):
    """
    Test scraper handles empty JobSpy response.

    Given:
    - JobSpy returns an empty DataFrame.

    Expected:
    - Empty list is returned.
    """
    mock_scrape_jobs.return_value = _create_empty_jobspy_df()

    jobs = scrape_indeed(search_terms=["software developer"])
    assert jobs == []


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_company_from_description(mock_scrape_jobs):
    """
    Test company name extraction from description when URL is missing.

    Given:
    - A job with no company name and no company_url.
    - Description starts with "Avbob is a leading..."

    Expected:
    - Company name is extracted from the description.
    """
    # Create a DataFrame with a job missing company name and URL
    data = {
        "title": ["Software Engineer"],
        "company_name": [""],
        "company_url": [""],
        "company_logo": [""],
        "company_description": [""],
        "company_industry": [""],
        "company_num_employees": [""],
        "company_rating": [None],
        "location": [None],
        "is_remote": [False],
        "work_from_home_type": [""],
        "job_function": [""],
        "experience_range": [""],
        "job_level": [""],
        "job_type": [""],
        "date_posted": ["2026-07-19T10:00:00Z"],
        "job_url": ["https://za.indeed.com/viewjob?jk=abc"],
        "job_url_direct": [""],
        "description": ["Avbob is a leading financial services company looking for a software engineer..."],
        "skills": [[]],
        "compensation": [None],
        "min_amount": [None],
        "max_amount": [None],
        "currency": [""],
        "interval": [""],
    }
    df = pd.DataFrame(data)
    mock_scrape_jobs.return_value = df

    jobs = scrape_indeed(search_terms=["software developer"], results_per_term=10)

    assert len(jobs) == 1
    assert jobs[0]["company"] == "Avbob"


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_company_unlisted(mock_scrape_jobs):
    """
    Test that 'company unlisted' is handled correctly.

    Given:
    - A job with company_name = 'company unlisted'.
    - No company_url or description fallback.

    Expected:
    - Company field is empty (not 'company unlisted').
    """
    data = {
        "title": ["Software Engineer"],
        "company_name": ["company unlisted"],
        "company_url": [""],
        "company_logo": [""],
        "company_description": [""],
        "company_industry": [""],
        "company_num_employees": [""],
        "company_rating": [None],
        "location": [None],
        "is_remote": [False],
        "work_from_home_type": [""],
        "job_function": [""],
        "experience_range": [""],
        "job_level": [""],
        "job_type": [""],
        "date_posted": ["2026-07-19T10:00:00Z"],
        "job_url": ["https://za.indeed.com/viewjob?jk=abc"],
        "job_url_direct": [""],
        "description": ["Software engineer role..."],
        "skills": [[]],
        "compensation": [None],
        "min_amount": [None],
        "max_amount": [None],
        "currency": [""],
        "interval": [""],
    }
    df = pd.DataFrame(data)
    mock_scrape_jobs.return_value = df

    jobs = scrape_indeed(search_terms=["software developer"], results_per_term=10)

    assert len(jobs) == 1
    assert jobs[0]["company"] == ""


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_deduplication(mock_scrape_jobs):
    """
    Test that duplicate jobs (same URL) are removed.

    Given:
    - JobSpy returns 3 jobs, but 2 have the same URL.

    Expected:
    - Only 2 unique jobs are returned.
    """
    data = {
        "title": ["Software Developer", "Senior Developer", "Software Developer"],
        "company_name": ["TechCorp", "TechCorp", "TechCorp"],
        "company_url": ["", "", ""],
        "company_logo": ["", "", ""],
        "company_description": ["", "", ""],
        "company_industry": ["", "", ""],
        "company_num_employees": ["", "", ""],
        "company_rating": [None, None, None],
        "location": [None, None, None],
        "is_remote": [False, False, False],
        "work_from_home_type": ["", "", ""],
        "job_function": ["", "", ""],
        "experience_range": ["", "", ""],
        "job_level": ["", "", ""],
        "job_type": ["", "", ""],
        "date_posted": ["2026-07-19T10:00:00Z", "2026-07-18T10:00:00Z", "2026-07-19T10:00:00Z"],
        "job_url": [
            "https://za.indeed.com/viewjob?jk=abc123",
            "https://za.indeed.com/viewjob?jk=def456",
            "https://za.indeed.com/viewjob?jk=abc123"  # Duplicate URL
        ],
        "job_url_direct": ["", "", ""],
        "description": ["", "", ""],
        "skills": [[], [], []],
        "compensation": [None, None, None],
        "min_amount": [None, None, None],
        "max_amount": [None, None, None],
        "currency": ["", "", ""],
        "interval": ["", "", ""],
    }
    df = pd.DataFrame(data)
    mock_scrape_jobs.return_value = df

    jobs = scrape_indeed(search_terms=["software developer"], results_per_term=10)

    assert len(jobs) == 2


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_jobspy_error(mock_scrape_jobs):
    """
    Test scraper handles JobSpy exceptions gracefully.

    Given:
    - JobSpy raises an exception.

    Expected:
    - Scraper returns empty list (or whatever jobs were collected).
    - No exception is propagated.
    """
    # Simulate an exception from scrape_jobs
    mock_scrape_jobs.side_effect = Exception("JobSpy connection error")

    jobs = scrape_indeed(search_terms=["software developer"])

    # With our retry logic, it should return empty list after retries exhausted
    # But it may return empty list directly
    assert jobs == []


@patch('jobspy.scrape_jobs')
def test_scrape_indeed_sorting(mock_scrape_jobs):
    """
    Test that jobs are sorted newest first.

    Given:
    - Jobs with different dates.

    Expected:
    - Newest date comes first.
    """
    df = _create_mock_jobspy_df()
    mock_scrape_jobs.return_value = df

    jobs = scrape_indeed(search_terms=["software developer"], results_per_term=10)

    # Check sorting: first job should be the newest (2026-07-19)
    assert jobs[0]["date_posted"] == "2026-07-19"
    assert jobs[0]["time_posted"] == "10:00:00"

    # Last job should be the oldest (2026-07-17)
    assert jobs[-1]["date_posted"] == "2026-07-17"
    assert jobs[-1]["time_posted"] == "08:00:00"