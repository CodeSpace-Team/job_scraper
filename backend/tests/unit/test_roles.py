"""
Unit tests for the seven role tracks and their search terms (F7).

The things that matter most:
    1. A title in one track is not mistaken for a neighbouring one --
       "Cloud Support Engineer" is DevOps/Cloud, not Technical Support.
    2. The rules refuse to guess. A title that says nothing gets '', the
       same way an unclear level gets 'unknown' in F2.
    3. 'primary_role' is never touched. That is the AI's own field, and
       F1's screening still reads it -- this module is only meant to sit
       alongside it for now, not replace it.
    4. The search-term cadence actually spreads terms across two days,
       rather than quietly running everything every day.
"""

import pytest
from datetime import date

from src.pipeline.roles import (
    BUSINESS_ANALYSIS,
    DEVOPS,
    MOBILE,
    QA,
    ROLE_TYPES,
    SECURITY,
    SOFTWARE,
    SUPPORT,
    apply_roles,
    classify_role,
    fill_rate,
    log_roles,
    role_counts,
    role_for_term,
    terms_for_today,
)


def make_job(title="", description="", search_term="", primary_role=None):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "description_snippet": description}
    if search_term:
        job["search_term"] = search_term
    if primary_role is not None:
        job["primary_role"] = primary_role
    return job


# ─── The fixed role list ─────────────────────────────────────────────────────

def test_there_are_exactly_seven_tracks():
    """The brief's appendix fixes this at seven -- never free text."""
    assert len(ROLE_TYPES) == 7
    assert len(set(ROLE_TYPES)) == 7


# ─── Titles are read correctly, including the traps ─────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("Junior Developer", SOFTWARE),
    ("Full Stack Developer", SOFTWARE),
    ("C# Developer", SOFTWARE),
    ("IT Support Technician", SUPPORT),
    ("Service Desk Agent", SUPPORT),
    ("DevOps Engineer", DEVOPS),
    ("AWS Cloud Engineer", DEVOPS),
    ("QA Engineer", QA),
    ("Software Tester", QA),
    ("Business Analyst", BUSINESS_ANALYSIS),
    ("Power BI Developer", BUSINESS_ANALYSIS),
    ("Flutter Developer", MOBILE),
    ("Android Developer", MOBILE),
    ("Security Analyst", SECURITY),
    ("SOC Analyst", SECURITY),
])
def test_titles_are_read_correctly(title, expected):
    role, source = classify_role(title)
    assert role == expected
    assert source == "title"


@pytest.mark.parametrize("title,expected", [
    # A test-flavoured software title is QA work, not development.
    ("Software Test Engineer", QA),
    # A support role that happens to say "cloud" is DevOps/Cloud, not
    # Technical Support -- the two share the word "support" and only one
    # rule can win.
    ("Cloud Support Engineer", DEVOPS),
    # A support engineer with no "cloud" in the title stays Technical
    # Support -- the DevOps rule only claims the specific phrase.
    ("Support Engineer", SUPPORT),
])
def test_the_more_specific_track_wins_when_titles_overlap(title, expected):
    role, _source = classify_role(title)
    assert role == expected


def test_an_unrecognisable_title_is_left_undecided():
    """
    'Systems Engineer' says nothing about which of the seven tracks it is.
    The rules refuse to guess, the same way F2 leaves an unclear level as
    'unknown' rather than picking one.
    """
    role, source = classify_role("Systems Engineer")
    assert role == ""
    assert source == ""


def test_a_non_tech_title_is_left_undecided():
    role, source = classify_role("Sales Consultant", "Sell things to people.")
    assert role == ""
    assert source == ""


# ─── The description is only consulted when the title says nothing ──────────

def test_the_description_is_used_when_it_names_a_role():
    role, source = classify_role(
        "2026 Opportunities",
        "Join our graduate programme as a software developer building tools.",
    )
    assert role == SOFTWARE
    assert source == "description"


def test_a_technology_in_the_description_is_not_a_role():
    """
    The failure this rule was rewritten for. An HPE compute-solutions
    engineer -- infrastructure work -- was labelled Software development on
    the live board because its description mentioned Python. Graduates
    filtering by role type were shown it as a software job.

    A technology is not a role. Mentioning Python no more makes a job
    software development than mentioning Excel makes it accountancy.
    """
    role, source = classify_role(
        "HPE ATP - Compute Solutions Certified Engineer",
        "Designing and implementing compute, virtualization and cloud "
        "infrastructure solutions using HPE, VMware and Python scripting.",
    )
    assert role == ""
    assert source == ""


def test_a_bare_developer_mention_in_the_description_is_not_a_role():
    """"You will work alongside our developers" describes the team, not the job."""
    role, source = classify_role(
        "2026 Opportunities",
        "You will work alongside our developers and report to the manager.",
    )
    assert role == ""
    assert source == ""


def test_the_title_beats_the_description():
    """A clear title wins even if the description talks about something else."""
    role, source = classify_role(
        "Junior Developer",
        "You will occasionally support the service desk during releases.",
    )
    assert role == SOFTWARE
    assert source == "title"


# ─── The search term is no longer used at all ───────────────────────────────
# This tier used to exist, on the reasoning that a hit from searching "it
# internship" is still an IT job even when the title only says "2026
# Programme". Real data killed it: of 284 jobs where this classifier
# disagreed with F1's screening, 227 -- four fifths -- had been given their
# track by the search term alone. Indeed matches loosely, so a "technical
# support" search returns waiters, and this tier stamped them Technical
# Support without reading the job.

def test_the_search_term_is_ignored_even_when_it_names_a_real_track():
    """
    The tier that caused the damage. Kept as a test rather than deleted,
    because the reasoning behind it was plausible and somebody will be
    tempted to add it back.
    """
    role, source = classify_role("2026 Programme", "", hint="Technical Support")
    assert role == ""
    assert source == ""


def test_a_hint_outside_the_fixed_list_is_ignored():
    role, source = classify_role("2026 Programme", "", hint="Made Up Track")
    assert role == ""
    assert source == ""


def test_a_missing_hint_is_safe():
    role, source = classify_role("2026 Programme", "", hint=None)
    assert role == ""
    assert source == ""


# ─── Search cadence ──────────────────────────────────────────────────────────

def test_daily_terms_run_every_day():
    even_day = date(2026, 8, 4)
    odd_day = date(2026, 8, 5)

    even_phrases = {t.phrase for t in terms_for_today(even_day)}
    odd_phrases = {t.phrase for t in terms_for_today(odd_day)}

    assert "software developer" in even_phrases
    assert "software developer" in odd_phrases
    assert "it support" in even_phrases
    assert "it support" in odd_phrases


def test_even_and_odd_terms_alternate():
    even_day = date(2026, 8, 4)
    odd_day = date(2026, 8, 5)

    even_phrases = {t.phrase for t in terms_for_today(even_day)}
    odd_phrases = {t.phrase for t in terms_for_today(odd_day)}

    assert "backend developer" in even_phrases
    assert "backend developer" not in odd_phrases
    assert "php developer" in odd_phrases
    assert "php developer" not in even_phrases


def test_spread_false_runs_every_term_regardless_of_day():
    every_term = terms_for_today(date(2026, 8, 4), spread=False)
    daily_only = terms_for_today(date(2026, 8, 4), spread=True)
    assert len(every_term) > len(daily_only)


def test_role_for_term_looks_up_the_track():
    assert role_for_term("it support") == SUPPORT
    assert role_for_term("cloud engineer") == DEVOPS


def test_role_for_term_is_none_for_generic_early_career_phrasings():
    """
    'it internship' has no fixed track -- classify_role has to work it out
    from the ad itself, the same as any other job.
    """
    assert role_for_term("it internship") is None


def test_role_for_term_is_none_for_an_unknown_phrase():
    assert role_for_term("nonsense phrase") is None


# ─── The pipeline step, and the boundary it must not cross ──────────────────

def test_apply_roles_sets_role_type_and_source():
    jobs = [make_job("Junior Developer"), make_job("IT Support Technician")]
    apply_roles(jobs)

    assert jobs[0]["role_type"] == SOFTWARE
    assert jobs[0]["role_source"] == "title"
    assert jobs[1]["role_type"] == SUPPORT


def test_apply_roles_never_touches_primary_role():
    """
    The one thing this feature must not do. F1's screening still reads
    'primary_role' -- the AI's own field -- to decide keep or drop. Role
    classification is meant to sit alongside it for now, not replace it,
    until there has been a chance to compare the two on real jobs.
    """
    job = make_job("Junior Developer", primary_role="Software Developer")
    apply_roles([job])

    assert job["primary_role"] == "Software Developer"
    assert job["role_type"] == SOFTWARE


def test_apply_roles_adds_primary_role_to_nothing():
    """A job the AI never labelled stays that way -- apply_roles only adds
    its own two fields, it does not invent a primary_role that was never
    there."""
    job = make_job("Junior Developer")
    apply_roles([job])

    assert "primary_role" not in job


def test_apply_roles_uses_the_jobs_own_search_term():
    job = make_job("2026 Programme", search_term="it internship")
    apply_roles([job])

    # "it internship" has no fixed track (role_for_term is None for it),
    # so an uninformative title and description still end up undecided.
    assert job["role_type"] == ""


def test_apply_roles_is_safe_on_an_empty_list():
    assert apply_roles([]) == []


# ─── The run log ──────────────────────────────────────────────────────────

def test_role_counts_add_up():
    jobs = [
        make_job("Junior Developer"),
        make_job("Junior Developer"),
        make_job("IT Support Technician"),
        make_job("Systems Engineer"),
    ]
    apply_roles(jobs)

    counts = role_counts(jobs)
    assert counts[SOFTWARE] == 2
    assert counts[SUPPORT] == 1
    assert counts["(none)"] == 1
    assert sum(counts.values()) == len(jobs)


def test_fill_rate_counts_only_classified_jobs():
    jobs = [make_job("Junior Developer"), make_job("Systems Engineer")]
    apply_roles(jobs)

    classified, total, percentage = fill_rate(jobs)
    assert classified == 1
    assert total == 2
    assert percentage == 50.0


def test_fill_rate_on_an_empty_list_is_safe():
    assert fill_rate([]) == (0, 0, 0.0)


def test_log_roles_prints_the_breakdown(capsys):
    jobs = [make_job("Junior Developer"), make_job("Systems Engineer")]
    apply_roles(jobs)
    log_roles(jobs)

    output = capsys.readouterr().out
    assert "1 of 2 = 50%" in output
    assert SOFTWARE in output


def test_log_roles_flags_jobs_the_ai_gave_no_label_at_all(capsys):
    """
    Not a strict comparison against the AI's label -- 'primary_role' is
    free text and 'role_type' is a fixed list, so the two rarely match
    word for word. This just flags the cheap, unambiguous case: the rules
    found a track and the AI found nothing at all.
    """
    jobs = [make_job("Junior Developer", primary_role="")]
    apply_roles(jobs)
    log_roles(jobs)

    output = capsys.readouterr().out
    assert "gave no role label at all" in output
