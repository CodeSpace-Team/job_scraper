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

The second problem this covers
-------------------------------
A later run failed with "APIError: [503]: The service is currently
unavailable" -- a Google-side outage of under a second, in the middle of an
otherwise healthy run. The retry above did not help, because a 503 arrives as
gspread's own APIError rather than as a network error, and only network errors
were being retried. The tests below cover which API failures are now retried
and, just as importantly, which are still reported immediately.
"""
import time
from unittest.mock import MagicMock

import gspread
import pytest

from src.writers.sheets import _open_spreadsheet, write_exclude_tab, write_to_sheet


def api_error(status, message="The service is currently unavailable.", body_is_json=True):
    """
    Build a real gspread APIError, the way gspread itself builds one.

    gspread reads the status out of the JSON error body Google returns. When
    that body is not JSON -- an HTML error page from a load balancer during an
    outage, say -- it stores -1 instead, and only the response carries the real
    status. Both shapes are worth testing, so both can be built here.
    """
    response = MagicMock()
    response.status_code = status
    if body_is_json:
        response.json.return_value = {
            "error": {"code": status, "message": message, "status": "UNAVAILABLE"}
        }
    else:
        response.json.side_effect = ValueError("not JSON")
        response.text = "<html>502 Bad Gateway</html>"
    return gspread.exceptions.APIError(response)


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


def test_it_gives_up_after_four_dropped_connections(monkeypatch):
    """A run of bad luck still ends, rather than retrying forever."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = ConnectionResetError(104, "reset")

    with pytest.raises(ConnectionResetError):
        _open_spreadsheet(client, "sheet-id")

    assert client.open_by_key.call_count == 4


def test_a_bad_spreadsheet_id_is_not_retried(monkeypatch):
    """
    A wrong ID or a sharing problem fails once and stays failed.

    Trying again cannot fix either, so retrying would only make a real
    problem take four times as long to report.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = ValueError("spreadsheet not found")

    with pytest.raises(ValueError):
        _open_spreadsheet(client, "wrong-id")

    assert client.open_by_key.call_count == 1


# ─── Google's own outages are retried; our own mistakes are not ────────────

def test_a_503_from_google_is_retried(monkeypatch):
    """
    The exact failure that took a Sheet write out: a one-off 503.

    Everything else in that run was healthy -- the jobs were scraped,
    screened and leveled, the Exclude tab written moments later went
    through, the board published. Only this one call landed inside the
    outage, and it was not retried at all.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = [api_error(503), "the spreadsheet"]

    assert _open_spreadsheet(client, "sheet-id") == "the spreadsheet"
    assert client.open_by_key.call_count == 2


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_every_google_side_status_is_retried(status, monkeypatch):
    """A 5xx is Google failing to serve us; a 429 is Google asking us to wait."""
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = [api_error(status), "the spreadsheet"]

    assert _open_spreadsheet(client, "sheet-id") == "the spreadsheet"
    assert client.open_by_key.call_count == 2


@pytest.mark.parametrize("status", [400, 403, 404])
def test_a_permissions_or_id_problem_is_not_retried(status, monkeypatch):
    """
    A sheet that was never shared, or an ID that does not exist, fails once.

    This is the half of the change that is easy to get wrong. Catching
    APIError and retrying all of it would mean a genuine setup mistake --
    the sort someone hits on their first run -- takes four attempts and
    twenty seconds to report, with the real reason buried in retry noise.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = api_error(status, "The caller does not have permission")

    with pytest.raises(gspread.exceptions.APIError):
        _open_spreadsheet(client, "sheet-id")

    assert client.open_by_key.call_count == 1


def test_a_503_behind_an_unparseable_error_page_is_still_retried(monkeypatch):
    """
    An outage does not always return tidy JSON.

    When the body is an HTML error page, gspread stores -1 as the code and
    only the response itself knows the real status. Reading the status from
    the response as a second opinion is what keeps this retryable.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = [
        api_error(502, body_is_json=False),
        "the spreadsheet",
    ]

    assert _open_spreadsheet(client, "sheet-id") == "the spreadsheet"
    assert client.open_by_key.call_count == 2


def test_it_gives_up_on_an_outage_that_does_not_clear(monkeypatch):
    """
    A long outage still ends the phase, rather than retrying forever.

    Four attempts, then the run reports the failure -- and the orchestrator
    takes over from there, saving the rescue copy and carrying on to the
    Exclude tab and the board.
    """
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    client = MagicMock()
    client.open_by_key.side_effect = api_error(503)

    with pytest.raises(gspread.exceptions.APIError):
        _open_spreadsheet(client, "sheet-id")

    assert client.open_by_key.call_count == 4


def test_the_delays_between_attempts_grow(monkeypatch):
    """
    Backoff, not four requests in a row.

    Hammering a service that just said it was unavailable is both rude and
    less likely to work than waiting a moment longer each time.
    """
    slept = []
    monkeypatch.setattr(time, "sleep", lambda seconds: slept.append(seconds))

    client = MagicMock()
    client.open_by_key.side_effect = api_error(503)

    with pytest.raises(gspread.exceptions.APIError):
        _open_spreadsheet(client, "sheet-id")

    assert slept == [3.0, 6.0, 12.0]


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