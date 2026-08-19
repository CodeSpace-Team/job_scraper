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
    MAX_YEARS_FOR_COHORT,
    STAGE_ABOVE_COHORT,
    STAGE_NON_TECH,
    log_screening,
    match_accepted_role,
    match_blocked_title,
    screen_above_cohort,
    screen_jobs,
    screen_non_tech,
)


def make_job(title="", primary_role="", **extra):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "primary_role": primary_role, "job_url": f"u/{title}"}
    job.update(extra)
    return job


def leveled(title="Software Developer", level="", years=None, **extra):
    """Build a tech job that has already been through F2 and F3."""
    job = make_job(title, "Developer", job_level=level, **extra)
    job.setdefault("level_source", "title")
    job.setdefault("level_evidence", level or "")
    if years is not None:
        job["experience_years"] = years
        job.setdefault("years_source", "text")
        job.setdefault("years_evidence", f"{years} years")
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

# ─── F4: the first three years ──────────────────────────────────────────────

@pytest.mark.parametrize("level", ["senior", "lead", "principal"])
def test_levels_above_the_cohort_are_dropped(level):
    keep, reason, _review = screen_above_cohort(leveled(level=level))
    assert keep is False
    assert level in reason


@pytest.mark.parametrize("level", ["entry level", "junior", "mid", "unknown", ""])
def test_levels_within_the_cohort_are_kept(level):
    keep, _reason, _review = screen_above_cohort(leveled(level=level))
    assert keep is True


@pytest.mark.parametrize("years,expected_keep", [
    (0, True),
    (1, True),
    (2, True),
    (3, True),
    (4, False),
    (5, False),
    (12, False),
])
def test_the_boundary_sits_at_four_years(years, expected_keep):
    """
    Three years in is still our cohort; four is not. The brief draws the
    line at 4+, so 3 and 4 are the two cases worth pinning down.
    """
    keep, _reason, _review = screen_above_cohort(leveled(years=years))
    assert keep is expected_keep


def test_the_boundary_matches_the_named_constant():
    """If the constant moves, the rule moves with it."""
    keep, _r, _v = screen_above_cohort(leveled(years=MAX_YEARS_FOR_COHORT - 1))
    assert keep is True
    keep, _r, _v = screen_above_cohort(leveled(years=MAX_YEARS_FOR_COHORT))
    assert keep is False


def test_a_job_with_no_level_and_no_years_is_kept():
    """
    The most important rule in F4. About a quarter of scraped jobs say
    nothing about seniority, and those ads are usually open to anyone.
    Dropping them would throw away exactly what this tool exists to find.
    """
    keep, _reason, _review = screen_above_cohort(make_job("Software Developer", "Developer"))
    assert keep is True


def test_the_reason_names_the_evidence():
    """A drop has to be traceable back to words in the ad."""
    _keep, reason, _review = screen_above_cohort(
        leveled(title="Senior Developer", level="senior",
                level_source="title", level_evidence="Senior")
    )
    assert "senior" in reason
    assert "title" in reason
    assert "Senior" in reason


# ─── Flagging the softer drops ──────────────────────────────────────────────

def test_a_level_from_the_title_is_not_flagged():
    _k, _r, review = screen_above_cohort(leveled(level="senior", level_source="title"))
    assert review is False


def test_a_level_from_the_description_is_flagged():
    """The narrow phrase rule is the softest path to a senior label."""
    _k, _r, review = screen_above_cohort(
        leveled(level="senior", level_source="description")
    )
    assert review is True


def test_years_read_from_the_ad_are_not_flagged():
    _k, _r, review = screen_above_cohort(leveled(years=6, years_source="text"))
    assert review is False


def test_years_from_a_feed_are_flagged():
    """A feed's number cannot be traced back to any wording in the ad."""
    _k, _r, review = screen_above_cohort(leveled(years=6, years_source="feed"))
    assert review is True


# ─── Both screens together ──────────────────────────────────────────────────

def test_f1_runs_before_f4():
    """
    A Senior Quantity Surveyor belongs in the Exclude tab as a surveyor,
    not as a senior -- the non-tech reason is the useful one.
    """
    _kept, excluded, _counts = screen_jobs([
        make_job("Senior Quantity Surveyor", "Surveyor", job_level="senior"),
    ])
    assert excluded[0]["excluded_stage"] == STAGE_NON_TECH


def test_each_screen_files_under_its_own_stage():
    _kept, excluded, _counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),
        leveled(title="Senior Developer", level="senior"),
    ])
    stages = [job["excluded_stage"] for job in excluded]
    assert stages == [STAGE_NON_TECH, STAGE_ABOVE_COHORT]


def test_counts_are_split_across_both_screens():
    _kept, _excluded, counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),      # F1 blocklist
        make_job("Operations Manager", "Operations"),        # F1 not accepted
        leveled(title="Senior Developer", level="senior"),   # F4 level
        leveled(years=7),                                    # F4 years
        leveled(level="junior"),                             # kept
    ])
    assert counts["dropped_title_blocklist"] == 1
    assert counts["dropped_role_not_accepted"] == 1
    assert counts["dropped_above_cohort"] == 2
    assert counts["kept"] == 1
    assert counts["dropped_total"] == 4
    assert counts["kept"] + counts["dropped_total"] == counts["input"]


def test_review_flags_are_counted():
    _kept, _excluded, counts = screen_jobs([
        leveled(level="senior", level_source="description"),   # flagged
        leveled(title="Senior Developer", level="senior"),     # not flagged
    ])
    assert counts["needs_review"] == 1


def test_every_kept_job_carries_a_needs_review_field():
    """The Sheets writer reads this field on every row it writes."""
    kept, excluded, _counts = screen_jobs([
        leveled(level="junior"),
        leveled(title="Senior Developer", level="senior"),
    ])
    for job in kept + excluded:
        assert "needs_review" in job


# ─── F4's done-when ─────────────────────────────────────────────────────────

def test_nothing_above_the_cohort_survives():
    """
    F4's done-when: no senior, lead or principal rows reach the sheet, and
    no rows asking for 4+ years.
    """
    jobs = [
        leveled(title="Senior Developer", level="senior"),
        leveled(title="Team Lead", level="lead"),
        leveled(title="Principal Engineer", level="principal"),
        leveled(years=4),
        leveled(years=9),
        leveled(level="junior"),
        leveled(level="unknown"),
        leveled(level="mid", years=3),
        make_job("Software Developer", "Developer"),
    ]
    kept, _excluded, _counts = screen_jobs(jobs)

    assert len(kept) == 4
    for job in kept:
        assert job.get("job_level") not in {"senior", "lead", "principal"}
        years = job.get("experience_years")
        assert years is None or years < MAX_YEARS_FOR_COHORT


def test_log_reports_both_screens(capsys):
    _kept, excluded, counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),
        leveled(title="Senior Developer", level="senior"),
        leveled(level="senior", level_source="description"),
    ])
    log_screening(counts, excluded)

    output = capsys.readouterr().out
    assert "F1 dropped on title blocklist" in output
    assert "F4 dropped as above the cohort" in output
    assert "flagged for QA review" in output
    assert "[REVIEW]" in output


# ─── Real leaks found by F1's own non-tech measurement ──────────────────────
# The first real measurement of F1's "fewer than 5 in every 100" target found
# 5 non-tech jobs in a sample of 60 -- 8%, against a target of 3. Every one
# of them reached the sheet because the AI labelled it with a bare
# occupational noun that F1's accept list takes at face value: three separate
# jobs arrived as "Data Analyst", one as "Quality Assurance Manager", one as
# "Product Developer". The titles are the honest signal, so the fix is in the
# title blocklist, which runs before the label is ever consulted.

def test_an_hse_advisor_is_not_a_data_analyst():
    """
    Confirmed non-tech. Health, safety and environment work at BP, which
    the AI labelled "Data Analyst" -- and F1 accepts a bare data analyst.
    "sheq" and "occupational health" were already blocked; the "hse"
    spelling was the gap.
    """
    keep, reason, rule = screen_non_tech(
        {"title": "HSE Data Insights Advisor", "primary_role": "Data Analyst"}
    )
    assert keep is False
    assert rule == "title_blocklist"


def test_an_actuarial_analyst_is_not_a_data_analyst():
    """Confirmed non-tech. Insurance actuarial work, labelled "Data Analyst"."""
    keep, _reason, rule = screen_non_tech(
        {"title": "Junior Actuarial Analyst", "primary_role": "Data Analyst"}
    )
    assert keep is False
    assert rule == "title_blocklist"


def test_an_actuarial_systems_developer_survives():
    """
    The other half of that rule, and the reason "actuarial" alone is not
    blocked. Insurers do employ real software developers on actuarial
    systems, and blocking the field rather than the role would drop them --
    the same mistake as blocking "mining" instead of "mining engineer".
    """
    keep, _reason, _rule = screen_non_tech(
        {"title": "Actuarial Systems Developer", "primary_role": "Software Engineer"}
    )
    assert keep is True


def test_a_go_to_market_analyst_is_not_a_data_analyst():
    """Confirmed non-tech. Sales and marketing operations, labelled "Data Analyst"."""
    for title in ("GTM Operations Analyst", "Go-To-Market Analyst"):
        keep, _reason, rule = screen_non_tech(
            {"title": title, "primary_role": "Data Analyst"}
        )
        assert keep is False, title
        assert rule == "title_blocklist", title


def test_a_real_data_analyst_still_gets_through():
    """
    None of this may cost a genuine data job. These two were confirmed
    tech in the same sample.
    """
    for title in ("Data Analyst (Power BI / SQL)", "Graduate Data Analyst (AI and Analytics)"):
        keep, _reason, _rule = screen_non_tech(
            {"title": title, "primary_role": "Data Analyst"}
        )
        assert keep is True, title


def test_the_two_jobs_wrongly_suspected_still_get_through():
    """
    Both of these were read as non-tech from their titles and turned out to
    be real tech jobs on reading the advert. Pinned so that a later widening
    of the blocklist cannot quietly start dropping them.
    """
    keep, _reason, _rule = screen_non_tech(
        {"title": "Business Process Specialist", "primary_role": "Business Analyst"}
    )
    assert keep is True

    keep, _reason, _rule = screen_non_tech(
        {"title": "Technical Developer - Fresh Foods", "primary_role": "Product Developer"}
    )
    assert keep is True


def test_a_bare_product_developer_is_consumer_goods():
    """
    Confirmed non-tech: a consumer-electronics distributor's product
    developer, which the AI labelled "Product Developer" -- a label F1's
    accept list takes at face value because it contains "developer".
    """
    keep, _reason, rule = screen_non_tech(
        {"title": "Junior Product Developer", "primary_role": "Product Developer"}
    )
    assert keep is False
    assert rule == "title_blocklist"


def test_a_tech_qualified_product_developer_survives():
    """
    The other half of that rule. "Software Product Developer" is a real
    software job, and blocking the bare role without excusing the qualified
    forms would drop it -- the same shape as the accept list refusing a
    bare "engineer" while taking "software engineer".
    """
    for title in ("Software Product Developer", "Digital Product Developer",
                  "Technical Product Developer"):
        keep, _reason, _rule = screen_non_tech(
            {"title": title, "primary_role": "Software Engineer"}
        )
        assert keep is True, title
