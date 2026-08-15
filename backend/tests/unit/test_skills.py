"""
Unit tests for the official skills list and matcher (F5).

The things that matter most:
    1. The matcher does not false-positive on ordinary English. "The rest
       of the team" must not score a REST hit, and "go the extra mile"
       must not score a Go hit.
    2. Every spelling of a skill resolves to one official name, so the
       sheet never shows "JS" next to "JavaScript" as if they were two
       different things.
    3. 'skills_source' tells the truth about where the value in
       'must_have_skills' actually came from, even after enrichment has
       silently overwritten it. This is the one bug this file exists to
       pin down: checking the field's own prior value cannot tell the
       difference, and it doesn't.
"""

import pytest

from src.pipeline.skills import (
    MIN_SKILLS_BEFORE_AI,
    apply_keyword_skills,
    canonicalise,
    canonicalise_string,
    fill_rate,
    log_fill_rate,
    match_skills,
    normalise_ai_skills,
    official_names,
    split_skills,
)


def make_job(title="", description="", must_have_skills=None):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "description_snippet": description}
    if must_have_skills is not None:
        job["must_have_skills"] = must_have_skills
    return job


# ─── Matching, and the traps it has to avoid ────────────────────────────────

def test_a_realistic_ad_matches_its_real_skills():
    result = match_skills("Junior JS Developer", "React and Node experience, REST APIs, Postgres")
    assert result == ["JavaScript", "React", "REST APIs", "SQL (MySQL/Postgres)", "Node.js"]


@pytest.mark.parametrize("title,description", [
    ("Backend Engineer", "We are hiring across the rest of the team this quarter"),
    ("Support Technician", "You'll go the extra mile for customers"),
    ("Sales Consultant", "We use go-getters who close deals fast"),
])
def test_ordinary_english_does_not_false_positive(title, description):
    """
    'REST' and short acronyms are case-sensitive matches for exactly this
    reason -- "the rest of the team" is not REST APIs. 'Go' additionally
    never matches on its own name at all (see test below); "go-getters"
    and "go the extra mile" would otherwise light it up on every second ad.
    """
    assert match_skills(title, description) == []


def test_short_acronyms_are_case_sensitive():
    assert "JavaScript" in match_skills("", "Strong JS skills required")
    assert "JavaScript" not in match_skills("", "js is sometimes used informally")


@pytest.mark.parametrize("text,expected", [
    ("C# / .NET Developer", "C#/.NET"),
    ("Experience with CI/CD pipelines", "CI/CD"),
    ("Built with Node.js", "Node.js"),
])
def test_punctuation_in_skill_names_is_preserved(text, expected):
    assert expected in match_skills("", text)


def test_java_does_not_match_inside_javascript():
    result = match_skills("", "Strong JavaScript skills required")
    assert "Java" not in result
    assert "JavaScript" in result


def test_go_never_matches_on_its_own_bare_name():
    """
    'Go' is flagged name_matches=False in skills.json -- the word is too
    common as ordinary English to trust even with a context word nearby.
    Only its aliases ('Golang', 'Go Lang') are compiled as patterns.
    """
    result = match_skills("Backend Engineer", "We build our API in Go for the backend")
    assert "Go" not in result


def test_go_matches_through_its_golang_alias():
    result = match_skills("Golang Developer", "")
    assert "Go" in result


@pytest.mark.parametrize("description,expected_swift", [
    ("Taylor Swift is playing this weekend", False),
    ("You will build apps in Swift with UIKit experience", True),
])
def test_ambiguous_names_only_count_with_technical_context(description, expected_swift):
    """'Swift' is requires_context=True -- a bare mention proves nothing."""
    result = match_skills("Musician" if not expected_swift else "iOS Developer", description)
    assert ("Swift" in result) == expected_swift


def test_matches_are_returned_in_skills_file_order_not_match_order():
    """The board's skill picker relies on this order, not the order hits occur in."""
    result = match_skills("", "Node.js and React and JavaScript all mentioned here")
    names = official_names()
    assert result == sorted(result, key=lambda n: names.index(n))


def test_no_text_is_safe():
    assert match_skills() == []
    assert match_skills("", "") == []
    assert match_skills(None, None) == []


# ─── Canonicalisation ────────────────────────────────────────────────────────

def test_any_spelling_resolves_to_the_official_name():
    assert canonicalise(["JS", "reactjs", "Node"]) == ["JavaScript", "React", "Node.js"]


def test_unrecognised_names_are_dropped_not_kept_as_is():
    """This is what stops made-up or misspelled skills ever reaching the sheet."""
    assert canonicalise(["Underwater Basket Weaving"]) == []


def test_light_punctuation_noise_is_tolerated():
    assert canonicalise(["Node.js."]) == ["Node.js"]


def test_canonicalise_drops_duplicates():
    assert canonicalise(["JS", "JavaScript", "js"]) == ["JavaScript"]


def test_canonicalise_is_safe_on_empty_input():
    assert canonicalise([]) == []
    assert canonicalise(["", None, "  "]) == []


def test_canonicalise_string_round_trips_a_comma_separated_field():
    assert canonicalise_string("JS, reactjs, Underwater Basket Weaving") == "JavaScript, React"


def test_canonicalise_string_on_an_empty_field():
    assert canonicalise_string("") == ""
    assert canonicalise_string(None) == ""


@pytest.mark.parametrize("value,expected", [
    ("Python, Django", ["Python", " Django"]),
    (["Python", "Django"], ["Python", "Django"]),
    ("", []),
    (None, []),
])
def test_split_skills_handles_both_shapes(value, expected):
    assert split_skills(value) == expected


# ─── The pipeline step, before enrichment ────────────────────────────────────

def test_apply_keyword_skills_fills_in_the_fields():
    job = make_job("Junior JS Developer", "React and Node experience")
    apply_keyword_skills([job])

    assert job["must_have_skills"] == "JavaScript, React, Node.js"
    assert job["skills_source"] == "keyword"
    assert job["needs_ai_skills"] is False  # 3 skills == MIN_SKILLS_BEFORE_AI


def test_apply_keyword_skills_flags_a_job_with_too_few_skills():
    job = make_job("IT Support Technician", "Service desk role")
    apply_keyword_skills([job])

    assert job["needs_ai_skills"] is True


def test_the_min_skills_boundary_is_exact():
    """MIN_SKILLS_BEFORE_AI is the number of skills that is *just enough*."""
    assert MIN_SKILLS_BEFORE_AI == 3


def test_apply_keyword_skills_merges_with_whatever_the_feed_already_had():
    """A job feed sometimes hands over its own skills field. Keyword matches add
    to it, not replace it."""
    job = make_job("Backend Developer", "Deployed with Docker", must_have_skills="Python")
    apply_keyword_skills([job])

    assert "Python" in job["must_have_skills"]
    assert "Docker" in job["must_have_skills"]


def test_apply_keyword_skills_on_a_job_with_nothing_to_find():
    job = make_job("Mining Engineer", "Drill and blast planning")
    apply_keyword_skills([job])

    assert job["must_have_skills"] == ""
    assert job["skills_source"] == ""
    assert job["needs_ai_skills"] is True


def test_apply_keyword_skills_is_safe_on_an_empty_list():
    assert apply_keyword_skills([]) == []


# ─── The bug: 'skills_source' after enrichment has run ───────────────────────
# enrich_batch() overwrites 'must_have_skills' outright when it succeeds --
# job['must_have_skills'] = enrichment.get(...). A job the keyword matcher
# had already labelled 'keyword' keeps that label unless something checks
# for the overwrite. 'blurb' is only ever set by enrichment, so it is the
# only reliable signal that enrichment actually touched this job.

def test_normalise_ai_skills_relabels_a_job_the_ai_successfully_overwrote():
    job = make_job("Junior JS Developer", "React experience")
    apply_keyword_skills([job])
    assert job["skills_source"] == "keyword"  # before enrichment

    # Simulate what enrich_batch() does on success: it overwrites the
    # field outright and is the only step that ever sets 'blurb'.
    job["must_have_skills"] = "Python, Django, PostgreSQL"
    job["blurb"] = "A backend role."

    normalise_ai_skills(job)

    assert job["must_have_skills"] == "Python, SQL (MySQL/Postgres), Django"
    assert job["skills_source"] == "ai"


def test_normalise_ai_skills_leaves_a_job_the_ai_never_touched_alone():
    """
    Enrichment failing or being skipped for a batch leaves the job
    unchanged -- no 'blurb' gets set in that case. The keyword match must
    survive, labelled correctly as having come from keyword matching.
    """
    job = make_job("React Developer", "Node.js and TypeScript")
    apply_keyword_skills([job])
    before = job["must_have_skills"]

    normalise_ai_skills(job)  # no blurb -- enrichment never ran

    assert job["must_have_skills"] == before
    assert job["skills_source"] == "keyword"


def test_normalise_ai_skills_on_a_job_with_nothing_from_either_source():
    job = make_job("Sales Consultant", "Sell things to people")
    apply_keyword_skills([job])

    normalise_ai_skills(job)

    assert job["must_have_skills"] == ""
    assert job["skills_source"] == ""


def test_normalise_ai_skills_tidies_spellings_the_ai_invented():
    """The AI does not always use official spellings -- this is what fixes that."""
    job = {"must_have_skills": "JS, reactjs", "nice_to_have_skills": "Node", "blurb": "A role."}

    normalise_ai_skills(job)

    assert job["must_have_skills"] == "JavaScript, React"
    assert job["nice_to_have_skills"] == "Node.js"


def test_normalise_ai_skills_when_the_ai_finds_nothing_useful():
    """
    A rare edge case: enrichment succeeded (blurb is set) but the AI's own
    skill list resolves to nothing recognised. The field ends up empty,
    which is correctly reported as no source at all, not as 'ai'.
    """
    job = {"must_have_skills": "Underwater Basket Weaving", "blurb": "A role."}

    normalise_ai_skills(job)

    assert job["must_have_skills"] == ""
    assert job["skills_source"] == ""


# ─── The run log ────────────────────────────────────────────────────────────

def test_fill_rate_counts_jobs_with_something_in_the_field():
    jobs = [
        make_job("A", must_have_skills="Python"),
        make_job("B", must_have_skills=""),
        make_job("C", must_have_skills="React"),
    ]
    filled, total, percentage = fill_rate(jobs)
    assert filled == 2
    assert total == 3
    assert percentage == pytest.approx(66.7, abs=0.1)


def test_fill_rate_on_an_empty_list_is_safe():
    assert fill_rate([]) == (0, 0, 0.0)


def test_log_fill_rate_prints_the_breakdown(capsys):
    jobs = [make_job("Junior JS Developer", "React experience")]
    apply_keyword_skills(jobs)
    log_fill_rate(jobs)

    output = capsys.readouterr().out
    assert "1 of 1 = 100%" in output
    assert "keyword" in output