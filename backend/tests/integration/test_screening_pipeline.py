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

from src.pipeline.experience import apply_experience
from src.pipeline.levels import apply_levels
from src.pipeline.roles import apply_roles
from src.pipeline.screening import (
    MAX_YEARS_FOR_COHORT,
    PUBLISHED_LEVELS,
    PUBLISHED_ROLE_TYPES,
    STAGE_ABOVE_COHORT,
    STAGE_NON_TECH,
    STAGE_OFF_TRACK,
    TIER_APPLY,
    TIER_STRETCH,
    screen_jobs,
)

APPLY, STRETCH, OUT = TIER_APPLY, TIER_STRETCH, ""
"""Short names, so the fixture below reads as a table rather than a wall."""

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
    return apply_roles(tech + non_tech)


NON_TECH_TITLES = frozenset({
    "Mining Engineer", "Quantity Surveyor", "Warehouse Assistant",
    "Civil Engineer", "Sales Representative", "Boilermaker",
})
"""The six in ``mixed_day`` that F1 exists to remove."""


# ─── The done-when check ────────────────────────────────────────────────────

def test_non_tech_stays_under_five_percent(mixed_day):
    """
    F1's done-when: less than 5 percent of new rows is a non-tech job.

    Measured here on a known batch, so a regression in the rules fails the
    build rather than quietly re-polluting the sheet.
    """
    _kept, excluded, _counts = screen_jobs(mixed_day)

    # Measured on what F1 itself let through, not on the final list. The two
    # screens after it drop plenty of perfectly good tech jobs for reasons of
    # scope and level, and counting those would flatter F1's own number.
    thrown_out_by_f1 = {
        job["job_url"] for job in excluded
        if job["excluded_stage"] == STAGE_NON_TECH
    }
    past_f1 = [job for job in mixed_day if job["job_url"] not in thrown_out_by_f1]
    leaked = [job for job in past_f1 if job["title"] in NON_TECH_TITLES]
    ratio = len(leaked) / len(past_f1) if past_f1 else 0

    assert ratio < 0.05, f"non-tech got past F1: {[j['title'] for j in leaked]}"


def test_no_tech_job_is_lost(mixed_day):
    """
    A false drop costs a graduate a job, so it matters more than a leak.

    "Lost" means thrown out as not-a-tech-job. A QA engineer dropped by the
    scope screen is not lost -- it is on the Exclude tab under a reason that
    names a decision somebody made, and one constant reverses it.
    """
    _kept, excluded, _counts = screen_jobs(mixed_day)

    wrongly_dropped = [
        job["title"] for job in excluded
        if job["excluded_stage"] == STAGE_NON_TECH
        and job["title"] not in NON_TECH_TITLES
    ]

    assert wrongly_dropped == [], f"tech jobs were wrongly dropped: {wrongly_dropped}"


def test_screening_runs_before_anything_reaches_the_sheet(mixed_day):
    """The kept list is what the Jobs tab gets; it must be clean."""
    kept, excluded, counts = screen_jobs(mixed_day)

    assert counts["input"] == 26
    assert counts["dropped_title_blocklist"] + counts["dropped_role_not_accepted"] == 6
    assert counts["kept"] + counts["dropped_total"] == counts["input"]
    assert len(excluded) == counts["dropped_total"]

    for job in kept:
        assert job["role_type"] in PUBLISHED_ROLE_TYPES
        # These fixtures never went through F2, so they carry no level at
        # all -- which is exactly the case the stretch tier exists for.
        assert job.get("job_level", "unknown") in PUBLISHED_LEVELS
        assert job["tier"] in (TIER_APPLY, TIER_STRETCH)


# ─── The Exclude tab ────────────────────────────────────────────────────────

@pytest.fixture
def fake_sheet():
    """A stand-in gspread worksheet that records what was appended to it."""
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = []
    worksheet.col_count = len(sheets.EXCLUDE_HEADERS)
    worksheet.row_values.return_value = list(sheets.EXCLUDE_HEADERS)

    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = worksheet

    client = MagicMock()
    client.open_by_key.return_value = spreadsheet

    return client, worksheet


def test_excluded_jobs_reach_the_exclude_tab_with_reasons(mixed_day, fake_sheet):
    client, worksheet = fake_sheet
    _kept, excluded, _counts = screen_jobs(mixed_day)
    f1_drops = [j for j in excluded if j["excluded_stage"] == STAGE_NON_TECH]

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        written = sheets.write_exclude_tab(f1_drops, "sheet-id-123")

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



# ─── F4 on realistic ads ────────────────────────────────────────────────────

def full_ad(title, description):
    """A job with a description, so F2 and F3 have something to read."""
    job = build_job(title, "")
    job["description_snippet"] = description
    return job


@pytest.fixture
def cohort_day():
    """
    A day's tech jobs spanning the whole seniority range and several tracks,
    written the way real ads are. Each is paired with the tier it should land
    in: "apply", "stretch", or "" for the ones that should not reach the board
    at all.

    The two entries that carry the redesign are the plain *Software Developer*
    asking three years and the *Software Developer (Integration)* that never
    mentions a level. Under the old two-way rule both were thrown out -- one
    for reaching slightly past a graduate, the other for lack of proof.
    """
    return [
        (full_ad("Junior Software Developer",
                 "0-2 years experience with React."), APPLY),
        (full_ad("Graduate Software Engineer",
                 "Our graduate programme, no prior experience needed."), APPLY),
        (full_ad("Junior Test Analyst",
                 "Write and run test cases. 1-2 years experience."), APPLY),
        (full_ad("Software Developer",
                 "At least 3 years experience with C#."), STRETCH),
        (full_ad("Software Developer (Integration)",
                 "Join our team building integrations."), STRETCH),
        (full_ad("Flutter Developer",
                 "Build apps for our clients. Modern stack."), STRETCH),
        (full_ad("Service Desk Agent",
                 "Log and resolve tickets. Full training provided."), OUT),
        (full_ad("Senior Backend Engineer",
                 "Minimum of 6 years building distributed systems."), OUT),
        (full_ad("Snr .NET Developer",
                 "Design and build enterprise applications."), OUT),
        (full_ad("Technical Lead - SOC Cyber Defense",
                 "Lead our security operations centre."), OUT),
        (full_ad("Principal Engineer",
                 "Set technical direction across the group."), OUT),
        (full_ad("DevOps Engineer",
                 "Minimum 4 years experience with Kubernetes."), OUT),
        (full_ad("Cloud Engineer",
                 "You will have 5+ years experience with AWS."), OUT),
    ]


@pytest.fixture
def screened(cohort_day):
    """Run the real pipeline order: F3, then F2, then F7, then the screens."""
    jobs = [job for job, _reachable in cohort_day]
    jobs = apply_experience(jobs)
    jobs = apply_levels(jobs)
    jobs = apply_roles(jobs)
    return screen_jobs(jobs)


def test_every_ad_lands_in_the_tier_it_should(cohort_day, screened):
    """The done-when, on real ads rather than hand-set fields."""
    kept, _excluded, _counts = screened
    tiers = {job["title"]: job["tier"] for job in kept}

    wrong = []
    for job, expected in cohort_day:
        actual = tiers.get(job["title"], OUT)
        if actual != expected:
            wrong.append(
                f"{job['title']}: expected {expected or 'off the board'}, "
                f"got {actual or 'off the board'}"
            )

    assert wrong == [], "\n".join(wrong)


def test_no_senior_lead_or_principal_reaches_the_sheet(screened):
    kept, _excluded, _counts = screened
    for job in kept:
        assert job["job_level"] not in {"senior", "lead", "principal"}


def test_no_job_asking_four_or_more_years_reaches_the_sheet(screened):
    kept, _excluded, _counts = screened
    for job in kept:
        years = job.get("experience_years")
        assert years is None or years < MAX_YEARS_FOR_COHORT


def test_an_ad_that_says_nothing_about_level_is_a_stretch_and_is_flagged(screened):
    """
    The reversal, on a real ad. "Software Developer (Integration)" is on the
    right track and might well be a graduate job -- nothing in it says either
    way. It used to be dropped for lack of proof. It now ships, labelled a
    stretch rather than claimed as entry level, and flagged for the QA pass.
    """
    kept, _excluded, _counts = screened

    job = next(j for j in kept if j["title"] == "Software Developer (Integration)")
    assert job["tier"] == TIER_STRETCH
    assert job["needs_review"] is True
    assert "could not be established" in job["tier_reason"]


def test_an_ad_asking_three_years_is_a_stretch_not_a_drop(screened):
    """A developer two years in meets the requirements and applies anyway."""
    kept, _excluded, _counts = screened

    job = next(j for j in kept if j["title"] == "Software Developer")
    assert job["tier"] == TIER_STRETCH
    assert job["experience_years"] == 3


def test_an_off_track_job_still_does_not_reach_the_sheet(screened):
    """
    Widening the tiers is not widening the scope. A service desk agent is a
    perfectly good junior job and still not where this course leads.
    """
    kept, excluded, _counts = screened
    assert "Service Desk Agent" not in {job["title"] for job in kept}

    dropped = next(j for j in excluded if j["title"] == "Service Desk Agent")
    assert dropped["excluded_stage"] == STAGE_OFF_TRACK


def test_every_f4_drop_explains_itself(screened):
    _kept, excluded, _counts = screened
    f4_drops = [j for j in excluded if j["excluded_stage"] == STAGE_ABOVE_COHORT]

    assert f4_drops
    for job in f4_drops:
        reason = job["excluded_reason"]
        assert reason
        assert (
            "level is" in reason                     # a level we do not publish
            or "years" in reason                     # too many years asked for
            or "could not be established" in reason  # no level to go on
        ), reason


def test_the_counts_add_up(screened):
    kept, excluded, counts = screened
    assert len(kept) + len(excluded) == counts["input"]
    assert counts["kept"] == len(kept)
    assert counts["dropped_total"] == len(excluded)


# ─── F4 drops reaching the Exclude tab ──────────────────────────────────────

def test_f4_drops_reach_the_exclude_tab_with_the_review_column(screened, fake_sheet):
    client, worksheet = fake_sheet
    _kept, excluded, _counts = screened

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        written = sheets.write_exclude_tab(excluded, "sheet-id-123")

    assert written == len(excluded)

    rows = worksheet.append_rows.call_args[0][0]
    for row in rows:
        assert len(row) == len(sheets.EXCLUDE_HEADERS)
        assert row[-1] in {"", "YES"}          # Needs Review

    stages = {row[1] for row in rows}
    assert STAGE_ABOVE_COHORT in stages


def test_an_old_ten_column_tab_gets_its_header_repaired(fake_sheet):
    """
    The Exclude tab was created before the Needs Review column existed.
    Appending an 11th value to a 10-column grid fails outright, so the tab
    has to be widened and its header rewritten -- once.
    """
    client, worksheet = fake_sheet
    worksheet.col_count = 10
    worksheet.row_values.return_value = sheets.EXCLUDE_HEADERS[:10]

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        sheets.write_exclude_tab([build_job("Senior Dev", "Developer")], "sheet-id-123")

    worksheet.resize.assert_called_once_with(cols=len(sheets.EXCLUDE_HEADERS))
    assert worksheet.update.call_args[0][0] == [sheets.EXCLUDE_HEADERS]


def test_a_current_tab_is_left_alone(fake_sheet):
    """The repair must not fire on every run."""
    client, worksheet = fake_sheet

    with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDS": "{}"}), \
            patch.object(sheets, "authenticate_sheets", return_value=client):
        sheets.write_exclude_tab([build_job("Senior Dev", "Developer")], "sheet-id-123")

    worksheet.resize.assert_not_called()
    worksheet.update.assert_not_called()