"""
Unit tests for the board's running jobs.json (F6).

The things that matter most:
    1. A job already on the board that matches something scraped again
       today is replaced, not duplicated -- and keeps its original
       'date_added' so re-scraping it does not reset its place in the
       retention window.
    2. A job whose posting has aged past the retention window drops off
       the board on its own, using date_posted when the ad states one and
       date_added when it does not.
    3. Nothing is ever guessed away -- a job with no usable date at all is
       kept rather than pruned on a coin flip.
"""

import json
from datetime import date, timedelta

import pytest

from src.pipeline.publish import (
    RETENTION_DAYS,
    load_existing,
    log_publish,
    merge,
    prune,
    publish,
    save,
)


def make_job(title="Junior Developer", company="Acme", city="Cape Town",
             date_posted=None, date_added=None, **extra):
    """Build a minimal job dictionary for a test case."""
    job = {"title": title, "company": company, "city": city}
    if date_posted is not None:
        job["date_posted"] = date_posted
    if date_added is not None:
        job["date_added"] = date_added
    job.update(extra)
    return job


# ─── load_existing ────────────────────────────────────────────────────────

def test_load_existing_with_no_file_is_an_empty_board(tmp_path):
    assert load_existing(str(tmp_path / "jobs.json")) == []


def test_load_existing_with_corrupt_json_is_an_empty_board(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("not json", encoding="utf-8")
    assert load_existing(str(path)) == []


def test_load_existing_reads_the_jobs_list_out_of_the_wrapper(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"updated_at": "x", "count": 1,
                                 "jobs": [make_job()]}), encoding="utf-8")
    result = load_existing(str(path))
    assert len(result) == 1
    assert result[0]["title"] == "Junior Developer"


# ─── merge ────────────────────────────────────────────────────────────────

def test_a_genuinely_new_job_is_appended():
    existing = [make_job(title="Support Agent", date_added="2026-08-01")]
    incoming = [make_job(title="QA Engineer")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    titles = {job["title"] for job in result}
    assert titles == {"Support Agent", "QA Engineer"}


def test_a_new_job_is_stamped_with_todays_date():
    result = merge([], [make_job()], today=date(2026, 8, 15))
    assert result[0]["date_added"] == "2026-08-15"


def test_a_rescraped_job_replaces_its_old_copy_instead_of_duplicating():
    existing = [make_job(date_added="2026-08-01", must_have_skills="Python")]
    incoming = [make_job(must_have_skills="Python, Django")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert len(result) == 1
    assert result[0]["must_have_skills"] == "Python, Django"


def test_a_rescraped_job_keeps_its_original_date_added():
    """
    This is the whole point of matching on re-scrapes at all -- a job that
    gets picked up again every day it is still open must not have its
    retention clock reset every single run.
    """
    existing = [make_job(date_added="2026-08-01")]
    incoming = [make_job()]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert result[0]["date_added"] == "2026-08-01"


def test_a_job_with_no_title_no_company_and_no_link_is_always_kept():
    """Nothing to match on is not evidence that two jobs are the same."""
    existing = [make_job(title="", company="", date_added="2026-08-01")]
    incoming = [make_job(title="", company="")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert len(result) == 2


# ─── merge: the apply link ──────────────────────────────────────────────────

def test_the_same_apply_link_is_the_same_advert():
    existing = [make_job(job_url="https://indeed/jk=1", date_added="2026-08-01")]
    incoming = [make_job(title="Junior Developer (Cape Town)",
                         job_url="https://indeed/jk=1")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert len(result) == 1
    assert result[0]["title"] == "Junior Developer (Cape Town)"
    assert result[0]["date_added"] == "2026-08-01"


def test_an_ad_with_no_company_does_not_pile_up_day_after_day():
    """
    The defect that put one Power Platform advert on six rows of the live
    board and one ABAP advert on five.

    F9's key needs a title *and* a company before it will match, and plenty
    of Indeed ads carry no company at all. Those matched nothing, every day,
    and were appended again on every run. The apply link is what settles it:
    Indeed's jk is the posting's own id.
    """
    board = []
    for day in range(1, 6):
        board = merge(
            board,
            [make_job(company="", job_url="https://indeed/jk=abap")],
            today=date(2026, 8, day),
        )

    assert len(board) == 1
    assert board[0]["date_added"] == "2026-08-01"


def test_two_different_adverts_are_still_two_rows():
    """
    The link check adds a way to match; it must not take one away. Two
    genuinely different jobs at the same employer stay two rows.
    """
    existing = [make_job(title="Junior Developer", job_url="https://indeed/jk=1")]
    incoming = [make_job(title="Junior QA Analyst", job_url="https://indeed/jk=2")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert len(result) == 2


def test_the_title_key_still_matches_when_the_link_has_changed():
    """The same advert reached through two different links (F9's own key)."""
    existing = [make_job(job_url="https://indeed/jk=1", date_added="2026-08-01")]
    incoming = [make_job(job_url="https://pnet/12345")]

    result = merge(existing, incoming, today=date(2026, 8, 15))

    assert len(result) == 1
    assert result[0]["job_url"] == "https://pnet/12345"
    assert result[0]["date_added"] == "2026-08-01"


def test_merge_is_safe_on_an_empty_board():
    assert merge([], [], today=date(2026, 8, 15)) == []


# ─── prune ────────────────────────────────────────────────────────────────

def test_a_fresh_posting_is_kept():
    jobs = [make_job(date_posted="2026-08-10")]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert len(kept) == 1
    assert dropped == 0


def test_a_posting_past_the_window_is_dropped():
    stale = date(2026, 8, 15) - timedelta(days=RETENTION_DAYS + 1)
    jobs = [make_job(date_posted=stale.isoformat())]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert kept == []
    assert dropped == 1


def test_the_retention_boundary_is_exact():
    cutoff_day = date(2026, 8, 15) - timedelta(days=RETENTION_DAYS)
    jobs = [make_job(date_posted=cutoff_day.isoformat())]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert len(kept) == 1
    assert dropped == 0


def test_date_posted_is_preferred_over_date_added():
    """A job re-scraped long after it first appeared should prune off the
    date the ad itself states, not the date this module first saw it."""
    stale = date(2026, 8, 15) - timedelta(days=RETENTION_DAYS + 10)
    jobs = [make_job(date_posted=stale.isoformat(), date_added="2026-08-14")]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert kept == []
    assert dropped == 1


def test_date_added_is_used_when_the_ad_states_no_posting_date():
    """OfferZen and PNet never state a posting date at all -- date_added,
    stamped by merge() the day this module first saw the job, is what
    stops those sources' jobs staying on the board forever."""
    stale = date(2026, 8, 15) - timedelta(days=RETENTION_DAYS + 1)
    jobs = [make_job(date_added=stale.isoformat())]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert kept == []
    assert dropped == 1


def test_a_job_with_no_usable_date_at_all_is_kept_not_guessed_away():
    jobs = [make_job()]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert len(kept) == 1
    assert dropped == 0


def test_a_malformed_date_is_kept_not_dropped():
    jobs = [make_job(date_posted="not-a-date")]
    kept, dropped = prune(jobs, today=date(2026, 8, 15))
    assert len(kept) == 1
    assert dropped == 0


def test_prune_is_safe_on_an_empty_board():
    assert prune([], today=date(2026, 8, 15)) == ([], 0)


# ─── save ─────────────────────────────────────────────────────────────────

def test_save_writes_the_expected_shape(tmp_path):
    path = tmp_path / "jobs.json"
    save([make_job()], str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["count"] == 1
    assert "updated_at" in data
    assert data["jobs"][0]["title"] == "Junior Developer"


def test_save_orders_newest_posting_first(tmp_path):
    path = tmp_path / "jobs.json"
    older = make_job(title="Older", date_posted="2026-08-01")
    newer = make_job(title="Newer", date_posted="2026-08-14")
    save([older, newer], str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    assert [job["title"] for job in data["jobs"]] == ["Newer", "Older"]


def test_save_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "jobs.json"
    save([make_job()], str(path))
    assert path.exists()


# ─── publish: the pipeline step ──────────────────────────────────────────

def test_publish_end_to_end_on_a_fresh_board(tmp_path):
    path = tmp_path / "jobs.json"
    counts = publish([make_job()], str(path), today=date(2026, 8, 15))

    assert counts == {"carried_over": 0, "from_today": 1, "pruned": 0, "published": 1}
    assert json.loads(path.read_text(encoding="utf-8"))["count"] == 1


def test_publish_carries_over_and_prunes_in_the_same_run(tmp_path):
    path = tmp_path / "jobs.json"
    stale = date(2026, 8, 15) - timedelta(days=RETENTION_DAYS + 1)
    save([make_job(title="Stale", date_posted=stale.isoformat())], str(path))

    counts = publish([make_job(title="Fresh")], str(path), today=date(2026, 8, 15))

    assert counts == {"carried_over": 1, "from_today": 1, "pruned": 1, "published": 1}
    titles = [job["title"] for job in json.loads(path.read_text(encoding="utf-8"))["jobs"]]
    assert titles == ["Fresh"]


def test_publish_is_safe_with_nothing_kept_today(tmp_path):
    path = tmp_path / "jobs.json"
    counts = publish([], str(path), today=date(2026, 8, 15))
    assert counts == {"carried_over": 0, "from_today": 0, "pruned": 0, "published": 0}


# ─── the run log ────────────────────────────────────────────────────────

def test_log_publish_prints_the_summary(capsys):
    log_publish({"carried_over": 40, "from_today": 5, "pruned": 2, "published": 43})
    output = capsys.readouterr().out
    assert "43 jobs published" in output
    assert "40 carried over" in output
    assert "5 from today" in output
    assert "2 pruned" in output