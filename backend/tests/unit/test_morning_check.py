"""
Unit tests for the morning check (scripts/morning_check.py).

The script is mostly printing, and printing is hard to get meaningfully
wrong. One thing in it is not: **which jobs it thinks reached the board.**
Every number under "WHAT REACHED THE BOARD LOOKS LIKE" is computed from that
set, so if it picks the wrong one the whole page lies quietly and reads fine.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.morning_check import kept_jobs  # noqa: E402


def job(url, **extra):
    return {"job_url": url, "title": f"Job {url}", **extra}


# ─── Which set the report is built from ─────────────────────────────────────

def test_the_board_file_is_used_when_the_run_wrote_one():
    """
    board_jobs.json is saved straight after screening and carries each job's
    tier. combined_jobs_leveled.json is saved *before* screening, so it has
    neither -- subtracting one file from the other can recover which jobs
    survived, but never what tier they landed in.
    """
    leveled = [job("a"), job("b"), job("c")]
    excluded = [job("c")]
    board = [job("a", tier="apply"), job("b", tier="stretch")]

    result = kept_jobs(leveled, excluded, board)

    assert result is not None
    assert result == board
    assert all("tier" in j for j in result)


def test_it_falls_back_to_subtraction_for_a_run_without_one():
    """A run from before that file existed still has to be readable."""
    leveled = [job("a"), job("b"), job("c")]
    excluded = [job("c")]

    result = kept_jobs(leveled, excluded, None)

    assert result is not None
    assert [j["job_url"] for j in result] == ["a", "b"]


def test_an_empty_board_file_falls_back_rather_than_claiming_nothing_survived():
    """
    An empty list and a missing file mean different things everywhere else in
    this script, but not here: neither is evidence that the board is empty,
    and reporting "0 jobs reached the board" on a healthy run would send
    somebody looking for a fault that is not there.
    """
    leveled = [job("a"), job("b")]

    result = kept_jobs(leveled, [], [])

    assert result is not None
    assert [j["job_url"] for j in result] == ["a", "b"]


def test_a_missing_leveled_file_is_not_an_empty_board():
    assert kept_jobs(None, [], None) is None


def test_nothing_dropped_means_everything_survived():
    leveled = [job("a"), job("b")]

    result = kept_jobs(leveled, [], None)

    assert result is not None
    assert len(result) == 2
