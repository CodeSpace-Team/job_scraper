"""
Unit tests for the F1 non-tech screen.

Covers the three things F1 has to get right:
    1. The jobs named in the brief as wrong (mining engineers, quantity
       surveyors, warehouse assistants) are dropped.
    2. Real tech jobs across all seven graduate tracks survive.
    3. Nothing disappears silently -- every dropped job carries a reason,
       and kept + dropped always equals the input.
"""

import pytest

from src.pipeline.screening import (
    STAGE_NON_TECH,
    log_screening,
    match_accepted_role,
    match_blocked_title,
    screen_jobs,
    screen_non_tech,
)


def make_job(title="", primary_role="", **extra):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "primary_role": primary_role, "job_url": f"u/{title}"}
    job.update(extra)
    return job


# ─── The jobs the brief says must go ────────────────────────────────────────

@pytest.mark.parametrize("title,role", [
    ("Mining Engineer", "Mining Engineer"),
    ("Quantity Surveyor", "Quantity Surveyor"),
    ("Warehouse Assistant", "Warehouse Operative"),
    ("Building Surveyor", "Surveyor"),
    ("Civil Engineer", "Civil Engineer"),
    ("Mechanical Engineer", ""),
    ("Sales Representative", "Sales"),
    ("Receptionist", ""),
    ("Diesel Mechanic", ""),
    ("Safety Officer", "SHEQ Officer"),
])
def test_non_tech_jobs_are_dropped(title, role):
    keep, reason, _rule = screen_non_tech(make_job(title, role))
    assert keep is False
    assert reason, "a dropped job must always carry a reason"


# ─── The jobs that must survive, one per graduate track ─────────────────────

@pytest.mark.parametrize("title,role", [
    # Software development
    ("Junior Software Developer", "Backend Engineer"),
    ("Full Stack Developer", "Full Stack Developer"),
    ("C# .NET Developer", "Backend Engineer"),
    ("PHP Developer", "Web Developer"),
    ("Graduate Software Engineer", "Software Engineer"),
    # Technical Support
    ("IT Support Technician", "IT Support Specialist"),
    ("Service Desk Analyst", "Technical Support"),
    ("Application Support Engineer", "Support Engineer"),
    # DevOps / Cloud
    ("DevOps Engineer", "DevOps Engineer"),
    ("Cloud Engineer", "Cloud Engineer"),
    # QA / Testing
    ("Software Tester", "QA Engineer"),
    ("Test Analyst", "Test Analyst"),
    # Business Analysis & Low-code
    ("Business Analyst", "Business Analyst"),
    ("Power Platform Developer", "Business Analyst"),
    ("Dynamics 365 Consultant", "Dynamics 365"),
    # Mobile
    ("Flutter Developer", "Mobile Developer"),
    ("Android Developer", "Mobile Engineer"),
    # Security
    ("SOC Analyst", "Security Analyst"),
    ("Cyber Security Analyst", "Security Analyst"),
])
def test_tech_jobs_are_kept(title, role):
    keep, reason, _rule = screen_non_tech(make_job(title, role))
    assert keep is True, f"{title!r} should have been kept, got: {reason}"


# ─── Boundary cases the blocklist must not overreach on ─────────────────────

def test_salesforce_developer_survives_the_sales_rule():
    """The rule that drops sales reps must not drop a Salesforce developer."""
    assert match_blocked_title("Salesforce Developer") == ""
    keep, _reason, _rule = screen_non_tech(
        make_job("Salesforce Developer", "Developer")
    )
    assert keep is True


def test_tech_job_at_a_mining_company_survives():
    """The blocklist names roles, not industries."""
    keep, _reason, _rule = screen_non_tech(
        make_job("Application Support Analyst - Mining Sector", "Support Analyst")
    )
    assert keep is True


def test_bare_engineer_is_not_enough_to_be_accepted():
    """A bare 'engineer' is the looseness that let mining engineers in."""
    assert match_accepted_role("Engineer") == ""
    assert match_accepted_role("Software Engineer") == "tech_engineer"


# ─── The enrichment-failure fallback ────────────────────────────────────────

def test_title_is_used_when_the_role_label_is_missing():
    """Enrichment can be skipped or fail; the title must still carry the job."""
    keep, _reason, rule = screen_non_tech(make_job("Junior Python Developer", ""))
    assert keep is True
    assert rule.startswith("title:")


def test_title_is_used_when_the_role_label_is_unrecognised():
    keep, _reason, rule = screen_non_tech(
        make_job("Backend Developer", "Operations Specialist")
    )
    assert keep is True
    assert rule.startswith("title:")


def test_job_with_no_title_and_no_role_is_dropped():
    keep, reason, _rule = screen_non_tech(make_job("", ""))
    assert keep is False
    assert "no role label" in reason


# ─── Nothing disappears silently ────────────────────────────────────────────

def test_kept_plus_dropped_equals_input():
    jobs = [
        make_job("Software Developer", "Developer"),
        make_job("Mining Engineer", "Mining Engineer"),
        make_job("IT Support Technician", "IT Support"),
        make_job("Warehouse Assistant", ""),
    ]
    kept, excluded, counts = screen_jobs(jobs)

    assert len(kept) + len(excluded) == len(jobs)
    assert counts["input"] == 4
    assert counts["kept"] == 2
    assert counts["dropped_total"] == 2
    assert counts["kept"] + counts["dropped_total"] == counts["input"]


def test_every_excluded_job_carries_a_stage_and_a_reason():
    _kept, excluded, _counts = screen_jobs([
        make_job("Quantity Surveyor", "Surveyor"),
        make_job("Truck Driver", ""),
    ])

    assert len(excluded) == 2
    for job in excluded:
        assert job["excluded_stage"] == STAGE_NON_TECH
        assert job["excluded_reason"]
        assert job["excluded_rule"]


def test_counts_are_split_by_rule():
    _kept, _excluded, counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),   # blocklist
        make_job("Operations Manager", "Operations"),     # not accepted
    ])
    assert counts["dropped_title_blocklist"] == 1
    assert counts["dropped_role_not_accepted"] == 1


def test_screening_an_empty_list_is_safe():
    kept, excluded, counts = screen_jobs([])
    assert kept == []
    assert excluded == []
    assert counts["input"] == 0
    assert counts["dropped_total"] == 0


def test_log_screening_runs_without_error(capsys):
    """The run log must show the drops -- that is half of F1's done-when."""
    _kept, excluded, counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),
        make_job("Software Developer", "Developer"),
    ])
    log_screening(counts, excluded)

    output = capsys.readouterr().out
    assert "screened 2 jobs" in output
    assert "dropped 1" in output
    assert "Mining Engineer" in output