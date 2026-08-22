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

from src.pipeline.roles import BUSINESS_ANALYSIS, DATA, MOBILE, QA, SOFTWARE, SUPPORT
from src.pipeline.screening import (
    MAX_YEARS_FOR_COHORT,
    PUBLISHED_LEVELS,
    PUBLISHED_ROLE_TYPES,
    TIER_APPLY,
    TIER_STRETCH,
    STAGE_ABOVE_COHORT,
    STAGE_NON_TECH,
    STAGE_OFF_TRACK,
    log_screening,
    match_accepted_role,
    match_blocked_title,
    screen_above_cohort,
    screen_jobs,
    screen_non_tech,
    screen_off_track,
)


def make_job(title="", primary_role="", **extra):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "primary_role": primary_role, "job_url": f"u/{title}"}
    job.update(extra)
    return job


def leveled(title="Software Developer", level="", years=None, **extra):
    """
    Build a software job that has already been through F2, F3 and F7.

    The role type is set here because the scope screen sits between F1 and
    F4: without it every fixture would fail the wrong screen and these tests
    would stop saying anything about levels.
    """
    extra.setdefault("role_type", SOFTWARE)
    extra.setdefault("role_source", "title")
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
        leveled("Junior Software Developer", level="junior"),
        make_job("Mining Engineer", "Mining Engineer"),
        make_job("IT Support Technician", "IT Support",
                 role_type=SUPPORT, job_level="junior"),
        make_job("Warehouse Assistant", ""),
    ]
    kept, excluded, counts = screen_jobs(jobs)

    assert len(kept) + len(excluded) == len(jobs)
    assert counts["input"] == 4
    assert counts["kept"] == 1
    assert counts["dropped_total"] == 3
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
        leveled("Junior Software Developer", level="junior"),
    ])
    log_screening(counts, excluded)

    output = capsys.readouterr().out
    assert "screened 2 jobs" in output
    assert "dropped 1" in output
    assert "Mining Engineer" in output


# ─── Scope: the tracks this course leads to ─────────────────────────────────

@pytest.mark.parametrize("role", [SOFTWARE, MOBILE, QA, BUSINESS_ANALYSIS, DATA])
def test_the_published_tracks_are_on_track(role):
    keep, _reason, _review = screen_off_track(leveled(level="junior", role_type=role))
    assert keep is True


@pytest.mark.parametrize("role", [SUPPORT, "DevOps/Cloud", "Security"])
def test_the_other_tech_tracks_are_off_track(role):
    """
    Real tech jobs, and still not where this course leads -- a service desk
    leads to infrastructure, not development. They stay on the Exclude tab so
    widening the scope later is a name in a set, not a rebuild.
    """
    keep, reason, _review = screen_off_track(leveled(level="junior", role_type=role))
    assert keep is False
    assert role in reason


def test_a_job_with_no_role_type_is_dropped_and_flagged():
    """
    Unclassified is not the same as off-track: nobody decided this job was
    the wrong kind of work, F7 just could not tell. It still does not ship,
    but the review flag means the QA pass can measure what that costs.
    """
    keep, reason, review = screen_off_track(leveled(level="junior", role_type=""))
    assert keep is False
    assert review is True
    assert "no role type" in reason


def test_the_published_tracks_are_stated_in_one_place():
    """Core plus adjacent. Support, security and DevOps are deliberately out."""
    assert PUBLISHED_ROLE_TYPES == {SOFTWARE, MOBILE, QA, BUSINESS_ANALYSIS, DATA}
    assert SUPPORT not in PUBLISHED_ROLE_TYPES


# ─── F4: apply, stretch, or out of reach ────────────────────────────────────

@pytest.mark.parametrize("level,years,expected", [
    # Clearly in reach.
    ("entry level", None, TIER_APPLY),
    ("entry level", 0,    TIER_APPLY),
    ("junior",      None, TIER_APPLY),
    ("junior",      2,    TIER_APPLY),
    # Reaching slightly past a graduate.
    ("junior",      3,    TIER_STRETCH),
    ("mid",         3,    TIER_STRETCH),
    ("mid",         None, TIER_STRETCH),
    ("unknown",     None, TIER_STRETCH),
    ("",            None, TIER_STRETCH),
    # Out of reach.
    ("junior",      4,    ""),
    ("mid",         5,    ""),
    ("senior",      None, ""),
    ("lead",        None, ""),
    ("principal",   None, ""),
])
def test_the_tier_a_job_lands_in(level, years, expected):
    tier, _reason, _review = screen_above_cohort(leveled(level=level, years=years))
    assert tier == expected


def test_three_years_is_a_stretch_not_a_rejection():
    """
    The decision this tier exists for. A developer two years in reads
    "3 years required", checks the requirements listed underneath, meets
    them, and applies -- employers write the years line as a filter and then
    hire on the requirements. Twenty-eight software jobs on the live board
    asked for exactly three years.
    """
    tier, reason, _review = screen_above_cohort(leveled(level="mid", years=3))
    assert tier == TIER_STRETCH
    assert "3 years" in reason


@pytest.mark.parametrize("level", ["unknown", ""])
def test_a_job_with_no_level_is_a_stretch_and_is_flagged(level):
    """
    The reversal that gave the board 31 software jobs back. An ad that says
    nothing about level -- *Full Stack Developer*, *Software Engineer –
    GoLang* -- was being thrown out for lack of proof, never for evidence
    against. It now ships, labelled a stretch, and flagged so the QA pass can
    see what we put in front of people without being sure.
    """
    tier, reason, review = screen_above_cohort(leveled(level=level))
    assert tier == TIER_STRETCH
    assert review is True
    assert "could not be established" in reason


def test_the_years_gate_does_not_move():
    """Four years is out whatever the level says, and matches the constant."""
    tier, _r, _v = screen_above_cohort(
        leveled(level="junior", years=MAX_YEARS_FOR_COHORT - 1))
    assert tier == TIER_STRETCH
    tier, reason, _v = screen_above_cohort(
        leveled(level="junior", years=MAX_YEARS_FOR_COHORT))
    assert tier == ""
    assert "years" in reason


@pytest.mark.parametrize("title", [
    "Senior Software Developer",
    "Snr Developer",
    "Lead Developer",
    "Principal Engineer",
    "Head of Engineering",
    "Development Manager",
    "Solutions Architect",
])
def test_a_senior_title_is_out_whatever_the_level_field_says(title):
    """
    Deliberately redundant with F2, which would normally have set the level
    to senior or lead off the same words. It is here because F2's rules are
    allowed to change, and a change there must not be able to quietly promote
    a Senior Developer into the stretch tier.
    """
    tier, reason, _review = screen_above_cohort(
        leveled(title=title, level="unknown"))
    assert tier == ""
    assert "title says" in reason


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
    _k, _r, review = screen_above_cohort(
        leveled(level="junior", years=6, years_source="text"))
    assert review is False


def test_years_from_a_feed_are_flagged():
    """A feed's number cannot be traced back to any wording in the ad."""
    _k, _r, review = screen_above_cohort(
        leveled(level="junior", years=6, years_source="feed"))
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
        leveled(title="Junior Service Desk Analyst", level="junior",
                role_type=SUPPORT),
        leveled(title="Senior Developer", level="senior"),
    ])
    stages = [job["excluded_stage"] for job in excluded]
    assert stages == [STAGE_NON_TECH, STAGE_OFF_TRACK, STAGE_ABOVE_COHORT]


def test_a_senior_job_off_track_is_filed_as_off_track():
    """
    Order matters in the reason, not just the outcome. Scope runs before F4,
    so a Senior Support Engineer reads as off-track: somebody might widen the
    scope one day, and nobody is going to widen the cohort to seniors.
    """
    _kept, excluded, _counts = screen_jobs([
        leveled(title="Senior Support Engineer", level="senior",
                role_type=SUPPORT),
    ])
    assert excluded[0]["excluded_stage"] == STAGE_OFF_TRACK


def test_counts_are_split_across_all_three_screens():
    _kept, _excluded, counts = screen_jobs([
        make_job("Mining Engineer", "Mining Engineer"),      # F1 blocklist
        make_job("Operations Manager", "Operations"),        # F1 not accepted
        leveled(title="Junior IT Support", level="junior",   # off track
                role_type=SUPPORT),
        leveled(title="Senior Developer", level="senior"),   # F4 level
        leveled(level="junior", years=7),                    # F4 years
        leveled(level="junior"),                             # kept
    ])
    assert counts["dropped_title_blocklist"] == 1
    assert counts["dropped_role_not_accepted"] == 1
    assert counts["dropped_off_track"] == 1
    assert counts["dropped_above_cohort"] == 2
    assert counts["kept"] == 1
    assert counts["dropped_total"] == 5
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

def test_the_whole_screen_on_one_realistic_batch():
    """
    The done-when, in one list. Two reach the board as apply, three as a
    stretch, and the rest do not reach it at all.
    """
    jobs = [
        # Out of reach.
        leveled(title="Senior Developer", level="senior"),
        leveled(title="Team Lead", level="lead"),
        leveled(title="Principal Engineer", level="principal"),
        leveled(level="junior", years=4),
        leveled(level="junior", years=9),
        # Off track.
        leveled(title="Junior IT Support", level="junior", role_type=SUPPORT),
        # A stretch.
        leveled(title="Mid-level Developer", level="mid"),
        leveled(title="Full Stack Developer", level="unknown"),
        leveled(title="Junior Data Analyst", level="junior", years=3,
                role_type=DATA),
        # Straightforwardly in reach.
        leveled(title="Junior Software Developer", level="junior"),
        leveled(title="Graduate Software Engineer", level="entry level"),
    ]
    kept, _excluded, counts = screen_jobs(jobs)

    assert counts["kept_apply"] == 2
    assert counts["kept_stretch"] == 3
    assert len(kept) == 5

    for job in kept:
        assert job["tier"] in (TIER_APPLY, TIER_STRETCH)
        assert job["job_level"] in PUBLISHED_LEVELS
        assert job["role_type"] in PUBLISHED_ROLE_TYPES
        years = job.get("experience_years")
        assert years is None or years < MAX_YEARS_FOR_COHORT


def test_every_kept_job_says_which_tier_it_is_in():
    """The board reads this field on every card it draws."""
    kept, _excluded, _counts = screen_jobs([
        leveled(title="Junior Software Developer", level="junior"),
        leveled(title="Full Stack Developer", level="unknown"),
    ])

    tiers = {job["title"]: job["tier"] for job in kept}
    assert tiers["Junior Software Developer"] == TIER_APPLY
    assert tiers["Full Stack Developer"] == TIER_STRETCH

    stretch = next(j for j in kept if j["tier"] == TIER_STRETCH)
    assert stretch["tier_reason"], "a stretch has to say why it is one"


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
