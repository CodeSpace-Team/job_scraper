"""
Unit tests for working out a job's level (F2).

The things that matter most:
    1. Clear titles are read correctly.
    2. The rules refuse to guess -- an ad that says nothing gets 'unknown'.
    3. The traps are avoided. "Reports to senior management" must not make a
       job senior, and "International" must not be read as "intern".
    4. Every job records why it got the level it got, because F4 removes
       jobs from a graduate's view based on it.
"""

import pytest

from src.pipeline.levels import (
    ENTRY,
    JUNIOR,
    LEAD,
    LEVELS,
    MID,
    PRINCIPAL,
    SENIOR,
    UNKNOWN,
    apply_levels,
    derive_level,
    level_counts,
    level_from_description,
    level_from_title,
    level_from_years,
    log_levels,
    normalise_level,
)


def make_job(title="", description="", years=None, ai_level=None):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "description_snippet": description}
    if years is not None:
        job["experience_years"] = years
    if ai_level is not None:
        job["job_level"] = ai_level
    return job


# ─── Titles ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("Senior .NET Developer", SENIOR),
    ("Snr Software Engineer", SENIOR),
    ("Sr. Developer", SENIOR),
    ("Junior Developer", JUNIOR),
    ("Jnr PHP Developer", JUNIOR),
    ("Graduate Software Engineer", ENTRY),
    ("Software Development Intern", ENTRY),
    ("IT Learnership 2026", ENTRY),
    ("Trainee Technician", ENTRY),
    ("Entry-Level Developer", ENTRY),
    ("Intermediate Developer", MID),
    ("Mid-Level Engineer", MID),
    ("Team Leader - Service Desk", LEAD),
    ("Tech Lead", LEAD),
    ("Principal Engineer", PRINCIPAL),
    ("Solutions Architect", SENIOR),
])
def test_titles_are_read_correctly(title, expected):
    level, evidence = level_from_title(title)
    assert level == expected
    assert evidence


def test_a_title_spanning_a_range_takes_the_lower_rung():
    """'Junior to Mid' is open to a junior, so it is a junior job."""
    level, _evidence = level_from_title("Junior to Mid Developer")
    assert level == JUNIOR


def test_senior_or_lead_still_lands_above_the_cohort():
    """Taking the lower rung must not rescue a job that is clearly senior."""
    level, _evidence = level_from_title("Senior / Lead Developer")
    assert level == SENIOR


# ─── The word-boundary traps ────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Internal Sales Consultant",
    "International Support Analyst",
    "Internet Systems Engineer",
])
def test_intern_does_not_match_inside_other_words(title):
    """'Internal' and 'International' are not internships."""
    level, _evidence = level_from_title(title)
    assert level != ENTRY


def test_leadership_is_not_a_lead_role():
    level, _evidence = level_from_title("Developer with leadership qualities")
    assert level != LEAD


# ─── Years ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("years,expected", [
    (0, ENTRY),
    (1, JUNIOR),
    (2, JUNIOR),
    (3, MID),
    (4, MID),
    (5, SENIOR),
    (7, SENIOR),
    (8, LEAD),
    (12, LEAD),
    (None, ""),
])
def test_years_map_to_the_bands_in_the_brief(years, expected):
    assert level_from_years(years) == expected


def test_years_are_used_when_the_title_says_nothing():
    job = make_job("Software Developer", years=3)
    result = derive_level(job)
    assert result["level"] == MID
    assert result["source"] == "years"


def test_the_title_beats_the_years():
    """A title saying 'Junior' outranks an ad asking for 5 years."""
    job = make_job("Junior Developer", years=5)
    result = derive_level(job)
    assert result["level"] == JUNIOR
    assert result["source"] == "title"


# ─── The description, and the trap it has to avoid ──────────────────────────

def test_a_self_describing_phrase_is_read():
    job = make_job("Developer", "We are hiring a senior developer for our team")
    result = derive_level(job)
    assert result["level"] == SENIOR
    assert result["source"] == "description"


def test_a_graduate_programme_is_entry_level():
    job = make_job("2026 Opportunities", "Join our graduate programme this year")
    result = derive_level(job)
    assert result["level"] == ENTRY


@pytest.mark.parametrize("description", [
    "You will report to senior management",
    "Working with senior stakeholders across the business",
    "Our senior leadership team is growing",
    "Reporting into the senior executive",
])
def test_a_loose_mention_of_senior_does_not_make_a_job_senior(description):
    """
    This is the single most common way this rule goes wrong. Nearly every
    corporate ad mentions senior management somewhere.
    """
    level, _evidence = level_from_description(description)
    assert level != SENIOR

    job = make_job("IT Support Technician", description)
    assert derive_level(job)["level"] == UNKNOWN


# ─── Refusing to guess ──────────────────────────────────────────────────────

def test_an_ad_that_says_nothing_is_unknown():
    """The brief is explicit: mark it unknown rather than guess."""
    result = derive_level(make_job("Software Developer", "Come and build things."))
    assert result["level"] == UNKNOWN
    assert result["source"] == "none"
    assert result["confidence"] == "none"


def test_an_empty_job_is_unknown():
    assert derive_level({})["level"] == UNKNOWN


# ─── Falling back to the AI ─────────────────────────────────────────────────

def test_the_ai_label_is_used_as_a_last_resort():
    job = make_job("Developer", ai_level="Intern")
    result = derive_level(job)
    assert result["level"] == ENTRY
    assert result["source"] == "ai"
    assert result["confidence"] == "low"


def test_the_rules_beat_the_ai():
    """The AI is the fallback, not the authority."""
    job = make_job("Junior Developer", ai_level="senior")
    assert derive_level(job)["level"] == JUNIOR


@pytest.mark.parametrize("value,expected", [
    ("Intern", ENTRY),
    ("internship", ENTRY),
    ("SNR", SENIOR),
    ("Mid-Level", MID),
    ("staff", LEAD),
    ("principal", PRINCIPAL),
    ("unknown", ""),
    ("", ""),
    (None, ""),
    ("nonsense", ""),
])
def test_level_spellings_are_tidied_up(value, expected):
    assert normalise_level(value) == expected


# ─── The audit trail ────────────────────────────────────────────────────────

def test_every_job_records_why_it_got_its_level():
    """F4 drops jobs on this label, so each one has to be traceable."""
    jobs = [
        make_job("Senior Developer"),
        make_job("Developer", years=3),
        make_job("Developer", "join our graduate programme"),
        make_job("Developer", ai_level="junior"),
        make_job("Developer"),
    ]
    apply_levels(jobs)

    for job in jobs:
        assert job["job_level"] in list(LEVELS) + [UNKNOWN]
        assert job["level_source"] in {"title", "years", "description", "ai", "none"}
        assert "level_evidence" in job
        assert job["level_confidence"] in {"high", "medium", "low", "none"}

    assert [job["level_source"] for job in jobs] == [
        "title", "years", "description", "ai", "none"
    ]


def test_the_ai_label_is_kept_for_comparison():
    """Keeping it lets the QA check compare the rules against the AI."""
    jobs = [make_job("Senior Developer", ai_level="junior")]
    apply_levels(jobs)

    assert jobs[0]["job_level"] == SENIOR
    assert jobs[0]["ai_job_level"] == "junior"


def test_running_it_twice_gives_the_same_answer():
    """The step overwrites job_level, so it must not read back its own output."""
    jobs = [
        make_job("Developer", ai_level="senior"),
        make_job("Developer"),
        make_job("Senior Developer"),
    ]
    apply_levels(jobs)
    first = [job["job_level"] for job in jobs]

    apply_levels(jobs)
    assert [job["job_level"] for job in jobs] == first


def test_an_empty_list_is_safe():
    assert apply_levels([]) == []
    assert level_counts([]) == {}


# ─── The run log ────────────────────────────────────────────────────────────

def test_level_counts_add_up():
    jobs = [
        make_job("Senior Developer"),
        make_job("Junior Developer"),
        make_job("Junior Developer"),
        make_job("Developer"),
    ]
    apply_levels(jobs)

    counts = level_counts(jobs)
    assert counts[SENIOR] == 1
    assert counts[JUNIOR] == 2
    assert counts[UNKNOWN] == 1
    assert sum(counts.values()) == len(jobs)


def test_log_levels_prints_the_breakdown(capsys):
    jobs = [make_job("Senior Developer"), make_job("Developer")]
    apply_levels(jobs)
    log_levels(jobs)

    output = capsys.readouterr().out
    assert "1 of 2 = 50%" in output
    assert "senior" in output
    assert "unknown" in output