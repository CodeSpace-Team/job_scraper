"""
Unit tests for the QA review sheets (src/pipeline/qa.py).

What these cover
----------------
The tool builds the sheets a person fills in by hand, so most of it is
formatting and there is not much to get wrong. Two things are worth pinning
down properly:

1. **Working out which jobs were kept.** The run now saves that list
   (board_jobs.json), but older runs did not, and for those it is the
   leveled file minus the excluded file, matched by web address. If that
   subtraction is wrong then F1's non-tech rate is measured over the wrong
   population entirely -- including, at worst, the very jobs F1 dropped.

2. **The three modes stay separate.** They ask three different questions of
   the reviewer, and the wrong heading on a sheet wastes somebody's hour of
   reading real job ads.
"""
import pytest

from src.pipeline.qa import (
    MODE_TECH,
    TECH_TARGET_RATE,
    build_report,
    build_tech_report,
    needs_a_look,
    job_identity,
    kept_jobs,
    sample_jobs,
    target_for,
)


# ─── Working out which jobs reached the sheet ───────────────────────────────

def test_kept_is_everything_not_dropped():
    leveled = [
        {"job_url": "a", "title": "Junior Developer"},
        {"job_url": "b", "title": "Quantity Surveyor"},
        {"job_url": "c", "title": "IT Support Technician"},
    ]
    excluded = [{"job_url": "b", "title": "Quantity Surveyor"}]

    kept = kept_jobs(leveled, excluded)

    assert [job["job_url"] for job in kept] == ["a", "c"]


def test_kept_keeps_the_original_order():
    """
    The sample is random, but the list it is drawn from should not be.

    A set-based implementation would be the obvious way to write this and
    would silently reorder, which makes a --seed sample unrepeatable
    between runs on the same data.
    """
    leveled = [{"job_url": str(i), "title": f"Job {i}"} for i in range(10)]
    excluded = [{"job_url": "3"}, {"job_url": "7"}]

    kept = kept_jobs(leveled, excluded)

    assert [job["job_url"] for job in kept] == ["0", "1", "2", "4", "5", "6", "8", "9"]


def test_nothing_dropped_means_everything_kept():
    leveled = [{"job_url": "a"}, {"job_url": "b"}]
    assert len(kept_jobs(leveled, [])) == 2


def test_everything_dropped_means_nothing_kept():
    leveled = [{"job_url": "a"}, {"job_url": "b"}]
    excluded = [{"job_url": "a"}, {"job_url": "b"}]
    assert kept_jobs(leveled, excluded) == []


def test_a_job_with_no_web_address_still_matches_on_title_and_company():
    """
    Some feeds hand over a job with no link. Falling back to title and
    company is weaker than a web address, but the alternative is treating
    every such job as kept -- which would count dropped non-tech jobs as
    part of F1's own pass rate, flattering exactly the number being measured.
    """
    leveled = [{"title": "Mining Engineer", "company": "Acme"}]
    excluded = [{"title": "Mining Engineer", "company": "Acme"}]

    assert kept_jobs(leveled, excluded) == []


def test_the_web_address_wins_over_title_when_both_are_present():
    """Two different jobs at one company must not collapse into each other."""
    leveled = [
        {"job_url": "a", "title": "Developer", "company": "Acme"},
        {"job_url": "b", "title": "Developer", "company": "Acme"},
    ]
    excluded = [{"job_url": "a", "title": "Developer", "company": "Acme"}]

    kept = kept_jobs(leveled, excluded)

    assert [job["job_url"] for job in kept] == ["b"]


def test_job_identity_is_stable_for_the_same_job():
    job = {"job_url": " https://example.com/1 ", "title": "Dev"}
    assert job_identity(job) == job_identity(dict(job))
    assert job_identity(job) == "https://example.com/1"


# ─── The non-tech sheet (F1) ────────────────────────────────────────────────

SAMPLE = [
    {
        "title": "Junior React Developer",
        "company": "Acme",
        "job_url": "https://example.com/1",
        "primary_role": "Software Engineer",
        "role_type": "Software development",
        "role_source": "title",
    },
    {
        "title": "Warehouse Coordinator",
        "company": "Widgets",
        "job_url": "https://example.com/2",
        "primary_role": "Warehouse Coordinator",
        "role_type": "Technical Support",
        "role_source": "search_term",
    },
]


def test_the_tech_sheet_asks_the_non_tech_question():
    report = build_tech_report(SAMPLE, total_jobs=171, source_file="x")

    assert "Non-tech check (F1)" in report
    assert "is this actually a tech job?" in report
    assert "Correct?" not in report


def test_the_tech_sheet_shows_both_labels():
    """
    The AI's label is what F1 screened on; role_type is what the board
    shows. When a job turns out to be non-tech, which one was fooled is the
    thing that tells you where to fix it.
    """
    report = build_tech_report(SAMPLE, total_jobs=171, source_file="x")

    assert "Software Engineer" in report
    assert "Software development (title)" in report
    assert "Technical Support (search_term)" in report


def test_the_tech_sheet_states_the_target_as_a_count():
    report = build_tech_report([dict(SAMPLE[0]) for _ in range(20)],
                               total_jobs=171, source_file="x")

    assert "at most **1 of 20**" in report
    assert "Non-tech: ___ of 20   (target: at most 1)" in report


def test_a_small_sample_says_it_is_a_rough_measure():
    """
    A 20-job sample cannot resolve a 5% target -- one wrong job is exactly
    the pass mark. The sheet has to say so, or somebody records "target met"
    off a number that could not have told them either way.
    """
    report = build_tech_report(SAMPLE[:1] * 20, total_jobs=171, source_file="x")
    assert "only roughly" in report


def test_a_big_enough_sample_drops_the_warning():
    report = build_tech_report(SAMPLE[:1] * 60, total_jobs=171, source_file="x")
    assert "only roughly" not in report
    assert "at most **3 of 60**" in report


def test_an_empty_sample_does_not_divide_by_zero():
    report = build_tech_report([], total_jobs=0, source_file="x")
    assert "Non-tech check (F1)" in report


def test_a_job_with_no_labels_at_all_still_renders():
    report = build_tech_report([{"title": "Mystery Job"}], total_jobs=1, source_file="x")
    assert "(none)" in report


# ─── The other two modes are unchanged ──────────────────────────────────────

def test_the_level_sheet_still_asks_about_levels():
    jobs = [{"title": "Dev", "job_level": "junior", "level_source": "title"}]
    report = build_report(jobs, total_jobs=10, source_file="x")

    assert "Level check" in report
    assert "Correct?" in report
    assert "Non-tech" not in report


def test_the_drops_sheet_still_asks_about_wrong_drops():
    jobs = [{"title": "Dev", "excluded_reason": "role type not accepted"}]
    report = build_report(jobs, total_jobs=10, source_file="x")

    assert "Wrongly dropped?" in report


def test_target_for_scales_with_the_sample():
    assert target_for(20) == 18
    assert target_for(40) == 36


def test_sampling_with_a_seed_repeats_exactly():
    jobs = [{"job_url": str(i)} for i in range(50)]
    first = sample_jobs(jobs, size=10, seed=7)
    second = sample_jobs(jobs, size=10, seed=7)
    assert first == second


def test_sampling_asks_for_more_than_there_are():
    jobs = [{"job_url": "a"}]
    assert len(sample_jobs(jobs, size=20)) == 1


def test_the_tech_rate_target_is_the_brief_s_number():
    assert TECH_TARGET_RATE == 0.05
    assert MODE_TECH == "tech"


# ─── Triage: which adverts actually need opening ────────────────────────────

def test_a_clear_tech_title_does_not_need_a_look():
    """A "Full Stack Java Developer" settles itself. No advert needed."""
    job = {"title": "Full Stack Java Developer", "role_source": "title"}
    assert needs_a_look(job) is False


def test_a_title_that_says_nothing_tech_needs_a_look():
    """
    The exact leak this was built for. An HSE advisor reaches the sheet only
    because the AI labelled it "Data Analyst" -- the title itself matches
    nothing in F1's accept list, so a person has to judge it.
    """
    job = {"title": "HSE Data Insights Advisor", "role_source": "description"}
    assert needs_a_look(job) is True


def test_a_tech_title_still_needs_a_look_when_the_track_came_from_the_search():
    """
    Second signal, and it catches what the first one misses. "People Data
    analyst" contains "data analyst", so the title check passes it -- but
    F7's classifier could not read the job either and fell back to whichever
    search found it. Two weak signals together are worth one look.
    """
    job = {"title": "People Data analyst", "role_source": "search_term"}
    assert needs_a_look(job) is True


def test_a_missing_title_needs_a_look():
    assert needs_a_look({}) is True


def test_the_sheet_puts_the_thin_evidence_first():
    jobs = [
        {"title": "Full Stack Developer", "role_source": "title"},
        {"title": "Transport Analyst", "role_source": "search_term"},
        {"title": "QA Engineer", "role_source": "title"},
    ]
    report = build_tech_report(jobs, total_jobs=100, source_file="x")
    body = report[report.index("| # |"):]

    assert body.index("Transport Analyst") < body.index("Full Stack Developer")
    assert "**look**" in body


def test_the_sheet_says_how_many_need_opening():
    jobs = [
        {"title": "Full Stack Developer", "role_source": "title"},
        {"title": "Transport Analyst", "role_source": "search_term"},
    ]
    report = build_tech_report(jobs, total_jobs=100, source_file="x")

    assert "Open the advert for the 1 marked `look`" in report
    assert "The other 1 can be judged from the title" in report


def test_a_sheet_where_everything_is_clear_says_nothing_about_looking():
    jobs = [{"title": "Full Stack Developer", "role_source": "title"}]
    report = build_tech_report(jobs, total_jobs=100, source_file="x")

    assert "Open the advert" not in report


# ─── Which file the review is drawn from ────────────────────────────────────

def test_the_level_review_samples_the_board_by_default():
    """
    It used to sample combined_jobs_leveled.json -- every job the run
    touched. On run 137 that put a Wakeboarding Crew instructor, a Physics
    teacher and a Medical Officer into a twenty-job review: fifteen of the
    twenty were jobs nobody would ever be shown. A review pass is somebody
    reading twenty adverts by hand, and it belongs on the jobs a graduate
    actually sees.
    """
    from src.pipeline.qa import DEFAULT_INPUT, FALLBACK_INPUT

    assert DEFAULT_INPUT.endswith("board_jobs.json")
    assert FALLBACK_INPUT.endswith("combined_jobs_leveled.json")
