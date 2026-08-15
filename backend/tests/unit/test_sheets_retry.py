"""
Unit tests for Google Sheets connection handling (src/writers/sheets.py).

The problem this covers
------------------------
On the run this was added for, opening the spreadsheet failed once with
"Connection reset by peer" and the whole pipeline stopped there -- nothing
wrong with the request, nothing wrong with the data, just a dropped
connection. Everything the run had already done (240 jobs scraped, screened,
leveled) went nowhere because of one network blip.

Two things had to be fixed, and this file covers both:

1. The connection itself is retried, so a single dropped connection does
   not end the run at all.
2. If it fails anyway, it fails as a plain exception rather than by calling
   sys.exit() directly. The two are not the same to a caller: "except
   Exception" does not catch a SystemExit, so the orchestrator's own
   error handling -- saving a rescue copy, still writing the Exclude tab --
   was being skipped entirely on the exact runs where it mattered most.
"""
import time
from unittest.mock import MagicMock

import pytest

from src.writers.sheets import _open_spreadsheet, write_exclude_tab, write_to_sheet


def test_a_dropped_connection_is_retried(monkeypatch):
    """A ConnectionResetError on the first attempt should not end the run."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = [
        ConnectionResetError(104, "Connection reset by peer"),
        "the spreadsheet",
    ]

    result = _open_spreadsheet(client, "sheet-id")

    assert result == "the spreadsheet"
    assert client.open_by_key.call_count == 2


def test_it_gives_up_after_three_dropped_connections(monkeypatch):
    """A run of bad luck still ends, rather than retrying forever."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = ConnectionResetError(104, "reset")

    with pytest.raises(ConnectionResetError):
        _open_spreadsheet(client, "sheet-id")

    assert client.open_by_key.call_count == 3


def test_a_bad_spreadsheet_id_is_not_retried(monkeypatch):
    """
    A wrong ID or a sharing problem fails once and stays failed.

    Trying again cannot fix either, so retrying would only make a real
    problem take three times as long to report.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = ValueError("spreadsheet not found")

    with pytest.raises(ValueError):
        _open_spreadsheet(client, "wrong-id")

    assert client.open_by_key.call_count == 1


# ─── A failure has to be catchable, not a direct process exit ──────────────

def test_write_to_sheet_raises_instead_of_exiting_on_missing_creds(monkeypatch):
    """
    Missing credentials used to call sys.exit(1) directly. That is invisible
    to a plain "except Exception" in the orchestrator, so the run would end
    right there -- no rescue copy saved, no attempt at the Exclude tab.
    """
    monkeypatch.delenv("GOOGLE_SHEETS_CREDS", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_SHEETS_CREDS"):
        write_to_sheet([{"title": "Junior Developer"}], "sheet-id")


def test_write_to_sheet_raises_instead_of_exiting_when_the_sheet_wont_open(monkeypatch):
    """The same failure this file is named for, all the way through write_to_sheet."""
    monkeypatch.setenv("GOOGLE_SHEETS_CREDS", "{}")
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "src.writers.sheets.authenticate_sheets", lambda _creds: MagicMock()
    )
    monkeypatch.setattr(
        "src.writers.sheets._open_spreadsheet",
        MagicMock(side_effect=ConnectionResetError(104, "Connection reset by peer")),
    )

    with pytest.raises(RuntimeError, match="Could not open spreadsheet"):
        write_to_sheet([{"title": "Junior Developer"}], "sheet-id")


def test_write_exclude_tab_raises_instead_of_exiting_on_missing_creds(monkeypatch):
    """The Exclude tab write has the same missing-creds check, and the same fix."""
    monkeypatch.delenv("GOOGLE_SHEETS_CREDS", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_SHEETS_CREDS"):
        write_exclude_tab([{"title": "Mining Engineer"}], "sheet-id")