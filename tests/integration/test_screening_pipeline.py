"""
Integration tests for F1: the screen wired to the Exclude tab writer.

The unit tests prove the decision is right for one job at a time. These prove
the decision survives the trip to the sheet: that a realistic mixed batch
comes out under the 5 percent non-tech target, and that everything dropped
actually lands on the Exclude tab with its reason intact.

The Google Sheets client is mocked -- these tests never touch the network.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.screening import screen_jobs

# The sheets module exits at import time if gspread is missing.
gspread = pytest.importorskip("gspread")

from src.writers import sheets  # noqa: E402


# ─── Fixtures ───────────────────────────────────────────────────────────────

def build_job(title, role="", url=None, description=""):
    """Build a job dictionary shaped like the Indeed scraper's output."""
    return {
        "source": "indeed",
        "title": title,
        "company": "Test Co",
        "primary_role": role,
        "location": "Cape Town, South Africa",
        "job_url": url or f"https://za.indeed.com/viewjob?jk={abs(hash(title))}",
        "description_snippet": description,
    }


@pytest.fixture
def mixed_day():
    """
    A realistic day's scrape: 20 tech jobs and 6 of the wrong kind.

    The wrong ones are the exact categories the brief calls out as the
    problem -- loose "engineer" and "developer" matches from Indeed.
    """
    tech = [
        build_job("Junior Software Developer", "Backend Engineer"),
        build_job("Full Stack Developer", "Full Stack Developer"),
        build_job("Frontend Developer (React)", "Frontend Engineer"),
        build_job("C# Developer", "Backend Engineer"),
        build_job("PHP Developer", "Web Developer"),
        build_job("Python Developer", "Software Engineer"),
        build_job("Graduate Software Engineer", "Software Engineer"),
        build_job("IT Support Technician", "IT Support Specialist"),
        build_job("Service Desk Analyst", "Technical Support"),
        build_job("Desktop Support Engineer", "Support Engineer"),
        build_job("Application Support Analyst", "Support Analyst"),
        build_job("DevOps Engineer", "DevOps Engineer"),
        build_job("Cloud Engineer (Azure)", "Cloud Engineer"),
        build_job("QA Engineer", "QA Engineer"),
        build_job("Test Analyst", "Test Analyst"),
        build_job("Business Analyst", "Business Analyst"),
        build_job("Power BI Developer", "Business Intelligence Analyst"),
        build_job("Flutter Developer", "Mobile Developer"),
        build_job("Android Developer", "Mobile Engineer"),
        build_job("SOC Analyst", "Security Analyst"),
    ]
    non_tech = [
        build_job("Mining Engineer", "Mining Engineer"),
        build_job("Quantity Surveyor", "Quantity Surveyor"),
        build_job("Warehouse Assistant", "Warehouse Operative"),
        build_job("Civil Engineer", "Civil Engineer"),
        build_job("Sales Representative", "Sales Consultant"),
        build_job("Boilermaker", ""),
    ]
    return tech + non_tech


# ─── The done-when check ────────────────────────────────────────────────────

def test_non_tech_stays_under_five_percent(mixed_day):
    """
    F1's done-when: less than 5 percent of new rows is a non-tech job.

    Measured here on a known batch, so a regression in the rules fails the
    build rather than quietly re-polluting the sheet.
    """
    kept, _excluded, _counts = screen_jobs(mixed_day)

    known_non_tech = {
        "Mining Engineer", "Quantity Surveyor", "Warehouse Assistant",
        "Civil Engineer", "Sales Representative", "Boilermaker",
    }
    leaked = [job for job in kept if job["title"] in known_non_tech]
    ratio = len(leaked) / len(kept) if kept else 0

    assert ratio < 0.05, f"non-tech leaked into the sheet: {[j['title'] for j in leaked]}"


def test_no_tech_job_is_lost(mixed_day):
    """A false drop costs a graduate a job, so it matters more than a leak."""
    kept, excluded, _counts = screen_jobs(mixed_day)

    non_tech_titles = {
        "Mining Engineer", "Quantity Surveyor", "Warehouse Assistant",
        "Civil Engineer", "Sales Representative", "Boilermaker",
    }
    wrongly_dropped = [
        job["title"] for job in excluded
        if job["title"] not in non_tech_titles
    ]

    assert wrongly_dropped == [], f"tech jobs were wrongly dropped: {wrongly_dropped}"
    assert len(kept) == 20


def test_screening_runs_before_anything_reaches_the_sheet(mixed_day):
    """The kept list is what the Jobs tab gets; it must be clean."""
    kept, excluded, counts = screen_jobs(mixed_day)

    assert counts["input"] == 26
    assert counts["kept"] == 20
    assert counts["dropped_total"] == 6
    assert len(excluded) == 6


# ─── The Exclude tab ────────────────────────────────────────────────────────

@pytest.fixture
def fake_sheet():
    """A stand-in gspread worksheet that records what was appended to it."""
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = []

    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet

    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    return client, worksheet


def test_excluded_jobs_reach_the_exclude_tab_with_reasons(mixed_day, fake_sheet):
    client, worksheet = fake_sheet
    _kept, excluded, _counts = screen_jobs(mixed_day)

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        written = sheets.write_exclude_tab(excluded, "sheet-id-123")

    assert written == 6

    rows = worksheet.append_rows.call_args[0][0]
    assert len(rows) == 6

    for row in rows:
        assert len(row) == len(sheets.EXCLUDE_HEADERS)
        assert row[1] == "F1 non-tech"   # Stage
        assert row[2]                     # Reason is never blank
        assert row[3]                     # Job Title is carried over

    titles = [row[3] for row in rows]
    assert "Mining Engineer" in titles
    assert "Quantity Surveyor" in titles


def test_exclude_tab_does_not_double_up_on_a_rerun(mixed_day, fake_sheet):
    """Append-only, deduplicated by Apply Link, exactly like the Jobs tab."""
    client, worksheet = fake_sheet
    _kept, excluded, _counts = screen_jobs(mixed_day)

    # Pretend every excluded job is already on the tab.
    worksheet.get_all_records.return_value = [
        {"Apply Link": job["job_url"]} for job in excluded
    ]

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        written = sheets.write_exclude_tab(excluded, "sheet-id-123")

    assert written == 0
    worksheet.append_rows.assert_not_called()


def test_nothing_is_written_when_nothing_was_excluded(fake_sheet):
    client, worksheet = fake_sheet

    with patch.object(sheets, "authenticate_sheets", return_value=client):
        written = sheets.write_exclude_tab([], "sheet-id-123")

    assert written == 0
    worksheet.append_rows.assert_not_called()