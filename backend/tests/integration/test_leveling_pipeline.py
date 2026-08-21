"""
Integration tests for F2 and F3 working together on realistic job ads.

The unit tests check one rule at a time. These use full job ads, in the
shape the Indeed scraper produces, and check the things the brief actually
asks for:

    - the years column is filled in on roughly 4 in 10 ads
    - the level is right on at least 18 of 20
    - the two steps agree with each other
    - the QA review sheet can be built from the result
"""

import json
from pathlib import Path

import pytest
from src.utils.text import clean_text

from src.pipeline.experience import apply_experience, fill_rate
from src.pipeline.levels import (
    ENTRY,
    JUNIOR,
    LEVELS,
    MID,
    SENIOR,
    UNKNOWN,
    apply_levels,
)
from src.pipeline.qa import build_report, sample_jobs, target_for


# ─── A realistic day's worth of ads ─────────────────────────────────────────

def ad(title, description, company="Test Co"):
    """Build a job in the shape the scrapers produce."""
    return {
        "source": "indeed",
        "title": title,
        "company": company,
        "location": "Cape Town, South Africa",
        "job_url": f"https://za.indeed.com/viewjob?jk={abs(hash(title))}",
        "description_snippet": description,
    }


@pytest.fixture
def twenty_ads():
    """
    Twenty job ads written the way real ones are, each paired with the level
    a person would give it. This is the sample the brief's 18-of-20 target
    is measured against.
    """
    return [
        (ad("Junior Software Developer",
            "We are looking for a junior developer to join our team. "
            "0-2 years experience. You will work on our web platform."), JUNIOR),

        (ad("Senior Backend Engineer",
            "Minimum of 6 years experience building distributed systems."), SENIOR),

        (ad("Graduate Software Engineer",
            "Our graduate programme takes on 10 new engineers each year. "
            "No prior experience needed."), ENTRY),

        (ad("Software Developer",
            "The successful candidate will have at least 3 years experience "
            "with C# and SQL Server."), MID),

        (ad("IT Support Technician",
            "Provide first line support to staff. You will report to senior "
            "management. Matric plus A+ certification."), UNKNOWN),

        (ad("Intermediate PHP Developer",
            "Join our team building e-commerce sites with Laravel."), MID),

        (ad("Software Development Internship",
            "A 12 month internship for recent graduates."), ENTRY),

        (ad("Full Stack Developer",
            "2-4 years of experience with React and Node.js required."), JUNIOR),

        (ad("Senior QA Analyst",
            "You will lead our testing effort. 7+ years experience in test "
            "automation."), SENIOR),

        (ad("Service Desk Agent",
            "Log and resolve tickets. Full training provided."), UNKNOWN),

        (ad("Junior Data Analyst",
            "A junior analyst role working with our reporting team."), JUNIOR),

        (ad("DevOps Engineer",
            "Minimum 4 years experience with Kubernetes and Terraform."), MID),

        (ad("IT Learnership 2026",
            "A 12 month learnership for unemployed youth. No experience "
            "required."), ENTRY),

        (ad("Snr .NET Developer",
            "Design and build enterprise applications."), SENIOR),

        (ad("Business Analyst",
            "Gather requirements and write specifications. At least 2 years "
            "experience in a similar role."), JUNIOR),

        (ad("Mobile Developer",
            "Build Flutter apps for our clients. Great team, modern stack."), UNKNOWN),

        (ad("Trainee Technician",
            "Learn on the job with our experienced team."), ENTRY),

        (ad("Mid-Level Frontend Developer",
            "Work on our design system. Strong CSS skills needed."), MID),

        (ad("Cloud Engineer",
            "You will have 5+ years experience with AWS."), SENIOR),

        (ad("Software Tester",
            "Manual and automated testing. We work in 2 week sprints and "
            "have been running for the last 8 years."), UNKNOWN),
    ]


@pytest.fixture
def processed(twenty_ads):
    """Run the two steps in the order the pipeline runs them."""
    jobs = [job for job, _expected in twenty_ads]
    jobs = apply_experience(jobs)
    jobs = apply_levels(jobs)
    return jobs


# ─── F2's done-when ─────────────────────────────────────────────────────────

def test_at_least_eighteen_of_twenty_are_leveled_correctly(twenty_ads, processed):
    """
    F2's target: 18 of 20 correct. Checked here on a fixed set so that a
    change which quietly breaks the rules fails the build.
    """
    wrong = []
    for job, expected in zip(processed, [exp for _job, exp in twenty_ads]):
        if job["job_level"] != expected:
            wrong.append(
                f"{job['title']!r}: got {job['job_level']}, expected {expected} "
                f"(from {job['level_source']}: {job['level_evidence']!r})"
            )

    correct = len(processed) - len(wrong)
    assert correct >= 18, (
        f"only {correct}/20 correct\n" + "\n".join(wrong)
    )


def test_no_level_is_ever_invented(processed):
    """Anything the rules cannot work out must say unknown, not guess."""
    for job in processed:
        assert job["job_level"] in list(LEVELS) + [UNKNOWN]


def test_ads_that_say_nothing_come_out_unknown(processed):
    """
    Three of the twenty ads genuinely give no clue. Marking them unknown is
    the right answer, and it keeps them in the sheet -- F4 keeps unknowns
    because they are often open to anyone.
    """
    unknowns = [job["title"] for job in processed if job["job_level"] == UNKNOWN]
    assert "Service Desk Agent" in unknowns
    assert "Mobile Developer" in unknowns


def test_the_senior_management_trap_is_avoided(processed):
    """
    The IT Support ad mentions senior management. It must not come out
    senior, or F4 would drop a perfectly good support job.
    """
    support = next(j for j in processed if j["title"] == "IT Support Technician")
    assert support["job_level"] != SENIOR


# ─── F3's done-when ─────────────────────────────────────────────────────────

def test_the_years_column_is_always_a_number_or_empty(processed):
    """F3's done-when: never text, so the column sorts and filters."""
    for job in processed:
        value = job["experience_years"]
        assert value is None or isinstance(value, int), (
            f"{job['title']!r} has {value!r}"
        )


def test_roughly_four_in_ten_ads_have_the_years_filled_in(processed):
    """
    The brief asks for about 4 in 10. Many ads simply do not say, so this
    checks we are in the right range rather than chasing 100 percent.
    """
    filled, total, percentage = fill_rate(processed)
    assert total == 20
    assert 30 <= percentage <= 70, f"filled {filled}/{total} = {percentage:.0f}%"


def test_a_range_in_a_real_ad_records_the_lower_number(processed):
    """'2-4 years of experience' means someone with 2 years can apply."""
    job = next(j for j in processed if j["title"] == "Full Stack Developer")
    assert job["experience_years"] == 2


def test_a_company_age_is_not_read_as_experience(processed):
    """'running for the last 8 years' is about the company, not the person."""
    job = next(j for j in processed if j["title"] == "Software Tester")
    assert job["experience_years"] is None


# ─── The two steps agreeing ─────────────────────────────────────────────────

def test_levels_taken_from_years_match_the_years(processed):
    """Where the level came from the years, the two must not contradict."""
    for job in processed:
        if job["level_source"] != "years":
            continue

        years = job["experience_years"]
        level = job["job_level"]
        assert isinstance(years, int)

        if years <= 0:
            assert level == ENTRY
        elif years <= 2:
            assert level == JUNIOR
        elif years <= 4:
            assert level == MID
        else:
            assert level in {SENIOR, "lead"}


def test_experience_must_run_before_levels():
    """
    Levels read the years field, so the order matters. Running levels first
    loses the years signal entirely.
    """
    jobs = [ad("Software Developer", "at least 3 years experience required")]

    wrong_order = apply_levels([dict(jobs[0])])
    assert wrong_order[0]["job_level"] == UNKNOWN

    right_order = apply_levels(apply_experience([dict(jobs[0])]))
    assert right_order[0]["job_level"] == MID


# ─── The weekly QA sheet ────────────────────────────────────────────────────

def test_a_review_sheet_can_be_built_from_a_run(processed):
    """F2's check needs a human to read 20 jobs; this is what they read."""
    chosen = sample_jobs(processed, size=20, seed=1)
    report = build_report(chosen, total_jobs=len(processed), source_file="test.json")

    assert "# Level check" in report
    assert "at least **18 of 20**" in report
    assert "Correct?" in report

    for job in chosen:
        assert job["title"][:20] in report


def test_the_review_sheet_shows_drop_reasons_when_reviewing_drops(processed):
    """Pointed at dropped jobs, it asks a different question."""
    dropped = [dict(job, excluded_reason="level is senior") for job in processed[:3]]
    report = build_report(dropped, total_jobs=3, source_file="excluded.json")

    assert "Wrongly dropped?" in report
    assert "level is senior" in report


def test_the_pass_mark_scales_with_the_sample_size():
    """18 of 20 is the brief's target; other sizes keep the same proportion."""
    assert target_for(20) == 18
    assert target_for(10) == 9
    assert target_for(50) == 45


def test_a_sample_is_repeatable_with_a_seed(processed):
    first = sample_jobs(processed, size=5, seed=42)
    second = sample_jobs(processed, size=5, seed=42)
    assert [j["title"] for j in first] == [j["title"] for j in second]


def test_asking_for_more_than_there_are_is_safe(processed):
    assert len(sample_jobs(processed, size=500)) == len(processed)
    assert sample_jobs([], size=20) == []


# ─── The saved file the QA sheet reads ──────────────────────────────────────

def test_the_cache_file_carries_the_audit_fields(processed, tmp_path):
    """
    The reasoning lives in the cache file rather than the sheet, so it has
    to survive being written out and read back.
    """
    path = Path(tmp_path) / "leveled.json"
    path.write_text(json.dumps({"jobs": processed}), encoding="utf-8")

    reloaded = json.loads(path.read_text(encoding="utf-8"))["jobs"]

    for job in reloaded:
        assert "level_source" in job
        assert "level_evidence" in job
        assert "level_confidence" in job
        assert "years_source" in job
        assert "years_evidence" in job

# ─── The scraper's own text, escaped and all ────────────────────────────────
# python-jobspy hands Indeed descriptions back as Markdown, which escapes
# ordinary hyphens and plus signs. clean_text() undoes that before the text
# ever reaches F3 -- these check the two stages together, on wording taken
# directly from a live run.

def test_a_real_escaped_range_is_read_correctly():
    """
    "Technical Developer - Fresh Foods" on the run of 14 August was dropped
    for asking for 4+ years. The ad actually said 2-4, and 2 is within the
    cohort -- the escaped hyphen from Markdown conversion was read as if the
    upper number were the one that mattered, which is the opposite of what
    F3 is documented to do.
    """
    description = clean_text(
        "...best practices. * 2\\-4 years' relevant experience in food..."
    )
    job = ad("Technical Developer", description, company="Fresh Foods")

    processed = apply_experience([job])

    assert processed[0]["experience_years"] == 2


def test_a_real_escaped_plus_is_still_read():
    """
    "Quality Assurance Engineer" asked for "3-4 years" elsewhere in the same
    ad, in the same escaped form -- checked here as a plus sign instead,
    since an escaped "\\+" was not being read as a number at all.
    """
    description = clean_text(
        "**Engineer** with 5\\+ years of experience to strengthen our team."
    )
    job = ad("QA Engineer", description)

    processed = apply_experience([job])

    assert processed[0]["experience_years"] == 5

# ─── The job that started this ──────────────────────────────────────────────

def test_developer_level_2_is_not_an_entry_level_job():
    """
    Emma filtered the board for software development at entry level and the
    first thing she got back was a "Developer Level 2". Nothing in that ad
    said entry level. What it said was:

        "brings together over 300 years of combined gaming experience"

    F3 read "00 years" out of "300 years", the experience word was right
    there to confirm it, and 0 years is entry level. The whole chain ran
    correctly on a number that was never in the ad.

    Pinned end to end -- F3 then F2 -- because either half alone would let
    it back in.
    """
    job = ad(
        "Developer Level 2",
        "Games Global brings together over 300 years of combined gaming "
        "experience. You will build and maintain our platform services.",
        company="Games Global",
    )

    processed = apply_levels(apply_experience([job]))[0]

    assert processed["experience_years"] is None
    assert processed["job_level"] == UNKNOWN


def test_a_hundred_years_of_rich_history_is_not_a_level():
    """The same sentence pattern, from a different employer on the same run."""
    job = ad(
        "AI Platform Engineer (Cloud)",
        "With over 100 years of rich history and strongly held values, we "
        "are looking for someone to join our cloud team.",
        company="Absa",
    )

    processed = apply_levels(apply_experience([job]))[0]

    assert processed["experience_years"] is None
    assert processed["job_level"] == UNKNOWN
