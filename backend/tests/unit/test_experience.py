"""
Unit tests for reading years of experience out of a job ad (F3).

Two things have to hold:
    1. The common ways an ad states experience are all understood.
    2. Numbers that are not about experience are ignored. A wrong number is
       worse than a blank, because F4 drops jobs on this figure.
"""

import pytest

from src.pipeline.experience import (
    MAX_PLAUSIBLE_YEARS,
    apply_experience,
    coerce_existing,
    extract_years,
    fill_rate,
    find_year_mentions,
    log_experience,
)


# ─── The phrasings that must be understood ──────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    # Plain statements
    ("1 year experience", 1),
    ("Experience: 4 years", 4),
    ("Candidates with 10 years experience preferred", 10),
    # "At least" and friends
    ("We need at least 3 years experience in Java", 3),
    ("minimum 2 years relevant experience", 2),
    ("Minimum of 5 years experience required", 5),
    ("A minimum of 6 years of commercial experience", 6),
    # Plus
    ("3+ years of hands-on experience with React", 3),
    ("5+ years experience", 5),
    # Written out
    ("At least two years working in a service desk", 2),
    ("minimum of three years experience", 3),
    # Bracketed
    ("Minimum of five (5) years experience", 5),
])
def test_common_phrasings_are_read(text, expected):
    years, _mentions = extract_years(text)
    assert years == expected


# ─── Ranges record the lower number ─────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("2-4 years' experience required", 2),
    ("The successful candidate will have 2 to 4 years experience", 2),
    ("0-2 years experience", 0),
    ("3 - 5 years of experience", 3),
    ("We are looking for 1-3 years experience", 1),
])
def test_a_range_records_the_lower_number(text, expected):
    """A person with the lower number can apply, so that is what we store."""
    years, _mentions = extract_years(text)
    assert years == expected


def test_several_mentions_record_the_lowest():
    """
    An ad asking for 5 years of one thing and 3 of another is open to
    someone with 3. Recording the highest would drop jobs a graduate
    could get.
    """
    years, mentions = extract_years(
        "5+ years in .NET and 3+ years experience in Azure"
    )
    assert years == 3
    assert len(mentions) == 2


# ─── Numbers that are not about experience ──────────────────────────────────

@pytest.mark.parametrize("text", [
    "Join us on a 3 year contract",
    "A 3 year degree in Computer Science",
    "You will need a 4 year qualification",
    "We have grown a lot over the last 5 years",
    "Founded 25 years ago",
    "Our company has been running for the past 12 years",
    "This is a 2 year fixed-term position",
    "No experience required, graduate role",
    "A great place to spend the next 3 years",
])
def test_numbers_that_are_not_about_experience_are_ignored(text):
    """A wrong number is worse than a blank -- F4 drops jobs on this."""
    years, _mentions = extract_years(text)
    assert years is None


def test_an_empty_ad_gives_nothing():
    assert extract_years("") == (None, [])
    assert extract_years(None) == (None, [])
    assert find_year_mentions("") == []


def test_absurd_numbers_are_ignored():
    """Nobody asks for 45 years of experience; that is a typo or a date."""
    years, _mentions = extract_years("45 years of experience required")
    assert years is None


def test_the_upper_bound_is_inclusive():
    years, _mentions = extract_years(
        f"{MAX_PLAUSIBLE_YEARS} years of experience required"
    )
    assert years == MAX_PLAUSIBLE_YEARS


# ─── Evidence is kept for review ────────────────────────────────────────────

def test_the_phrase_is_kept_as_evidence():
    """Somebody checking the sheet needs to see where the number came from."""
    _years, mentions = extract_years("Applicants need at least 3 years experience.")
    assert len(mentions) == 1
    assert "3 years" in mentions[0]["quote"]
    assert mentions[0]["years"] == 3


# ─── Tidying up whatever was already in the field ───────────────────────────

@pytest.mark.parametrize("value,expected", [
    (3, 3),
    ("3", 3),
    ("3+ years", 3),
    ("3-5", 3),
    (3.0, 3),
    ("", None),
    (None, None),
    ("not specified", None),
    (-1, None),
    (99, None),
    (True, None),
])
def test_existing_values_become_a_number_or_nothing(value, expected):
    """The column must be numeric or empty so it can be sorted."""
    assert coerce_existing(value) == expected


# ─── The pipeline step ──────────────────────────────────────────────────────

def test_the_field_is_always_a_number_or_none():
    """F3's done-when: the column is always a number or empty, never text."""
    jobs = [
        {"title": "Dev", "description_snippet": "at least 3 years experience"},
        {"title": "Dev", "description_snippet": "no mention here"},
        {"title": "Dev", "description_snippet": "", "experience_years": "3+ years"},
        {"title": "Dev", "description_snippet": "", "experience_years": "rubbish"},
    ]
    apply_experience(jobs)

    for job in jobs:
        value = job["experience_years"]
        assert value is None or isinstance(value, int), f"got {value!r}"

    assert jobs[0]["experience_years"] == 3
    assert jobs[1]["experience_years"] is None
    assert jobs[2]["experience_years"] == 3
    assert jobs[3]["experience_years"] is None


def test_where_the_number_came_from_is_recorded():
    jobs = [
        {"title": "Dev", "description_snippet": "at least 3 years experience"},
        {"title": "Dev", "description_snippet": "", "experience_years": 5},
        {"title": "Dev", "description_snippet": "nothing stated"},
    ]
    apply_experience(jobs)

    assert jobs[0]["years_source"] == "text"
    assert jobs[0]["years_evidence"]
    assert jobs[1]["years_source"] == "feed"
    assert jobs[2]["years_source"] == ""
    assert jobs[2]["years_evidence"] == ""


def test_the_ad_beats_whatever_the_feed_said():
    """The ad is the source of truth; the feed is only a fallback."""
    jobs = [{
        "title": "Dev",
        "description_snippet": "at least 2 years experience",
        "experience_years": 9,
    }]
    apply_experience(jobs)

    assert jobs[0]["experience_years"] == 2
    assert jobs[0]["years_source"] == "text"


def test_running_it_twice_changes_nothing():
    jobs = [{"title": "Dev", "description_snippet": "at least 3 years experience"}]
    apply_experience(jobs)
    first = jobs[0]["experience_years"]
    apply_experience(jobs)
    assert jobs[0]["experience_years"] == first


def test_an_empty_list_is_safe():
    assert apply_experience([]) == []
    assert fill_rate([]) == (0, 0, 0.0)


# ─── The run log ────────────────────────────────────────────────────────────

def test_fill_rate_counts_correctly():
    jobs = [
        {"experience_years": 3},
        {"experience_years": 0},
        {"experience_years": None},
        {"experience_years": None},
    ]
    filled, total, percentage = fill_rate(jobs)
    assert (filled, total) == (2, 4)
    assert percentage == 50.0


def test_zero_years_counts_as_filled_in():
    """Zero is a real answer -- it means the ad wants no prior experience."""
    filled, _total, _pct = fill_rate([{"experience_years": 0}])
    assert filled == 1


def test_log_experience_prints_the_score(capsys):
    jobs = [
        {"title": "Dev", "description_snippet": "at least 3 years experience"},
        {"title": "Dev", "description_snippet": "nothing stated"},
    ]
    apply_experience(jobs)
    log_experience(jobs)

    output = capsys.readouterr().out
    assert "1 of 2 = 50%" in output
    assert "text" in output

# ─── The company's age is not the candidate's experience ────────────────────
# Both of these are real sentences off the live board, and both produced
# "0 years" -> entry level. That is how a "Developer Level 2" came to sit in a
# graduate's entry-level results, which is what Emma opened the board and found.

@pytest.mark.parametrize("text", [
    "Games Global brings together over 300 years of combined gaming experience",
    "With over 100 years of rich history and strongly held values",
    "A business with 40 years of heritage in financial services",
    "Celebrating 25 years of excellence in software delivery",
    "We have been in the market for 30 years and counting",
    "A firm with 15 years of combined experience across the team",
])
def test_a_companys_own_age_is_not_a_requirement(text):
    assert extract_years(text)[0] is None


def test_a_long_number_is_not_read_as_its_last_two_digits():
    """
    The mechanism underneath the bug: \\d{1,2} with nothing guarding either
    end happily matched the "00" in "300 years". Every such sentence came out
    as 0 -- the lowest possible answer, from the largest possible number.
    """
    assert extract_years("300 years of experience")[0] is None
    assert extract_years("120 years of experience")[0] is None
    assert extract_years("We ask for 12 years of experience")[0] == 12


def test_a_real_requirement_next_to_a_company_boast_still_counts():
    """The rejection has to be local to the phrase, not to the whole ad."""
    text = (
        "With over 100 years of rich history, we are looking for a developer "
        "with at least 2 years of experience in C#."
    )
    assert extract_years(text)[0] == 2
