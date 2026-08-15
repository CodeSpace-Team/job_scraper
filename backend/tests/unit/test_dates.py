"""
Unit tests for date utilities (src/utils/dates.py).

This module tests two core functions used throughout the scraper pipeline:
- parse_date(): Converts various date string formats into a normalized
  (date_str, time_str) tuple.
- parse_date_for_sort(): Converts a date (and optional time) into a sortable
  ISO‑like string format used for ordering job listings.

These functions are critical for:
- Sorting jobs chronologically (newest first) in the Google Sheet.
- Normalizing date formats from different scrapers (OfferZen, Indeed, PNet)
  into a consistent format.
- Handling invalid or missing date data gracefully.

The tests ensure that date parsing is robust and handles all expected edge cases.
"""
from src.utils.dates import parse_date, parse_date_for_sort


def test_parse_date_iso_full():
    """
    Test parse_date with a full ISO 8601 timestamp.

    Input: '2026-07-19T14:30:00Z'
    Expected: ('2026-07-19', '14:30:00')

    This format is commonly used in:
    - OfferZen API responses
    - JSON data from various job sources
    - API webhook payloads

    Verifies:
    - Date component is correctly extracted as YYYY-MM-DD.
    - Time component is correctly extracted as HH:MM:SS.
    - The 'Z' timezone indicator is ignored (we only care about the time value).
    """
    date_str, time_str = parse_date("2026-07-19T14:30:00Z")
    assert date_str == "2026-07-19"
    assert time_str == "14:30:00"


def test_parse_date_iso_date_only():
    """
    Test parse_date with ISO date format (no time).

    Input: '2026-07-19'
    Expected: ('2026-07-19', '')

    This format is used when:
    - The source provides only a date, not a time.
    - Excel/CSV imports where time is not required.

    Verifies:
    - Date is correctly extracted.
    - Time field is returned as an empty string when not present.
    """
    date_str, time_str = parse_date("2026-07-19")
    assert date_str == "2026-07-19"
    assert time_str == ""


def test_parse_date_common_format():
    """
    Test parse_date with a common datetime format (space-separated).

    Input: '2026-07-19 10:20:30'
    Expected: ('2026-07-19', '10:20:30')

    This format is commonly used in:
    - Some web scraping libraries.
    - User-facing date displays.
    - Custom API implementations.

    Verifies:
    - Both date and time are correctly extracted.
    - The function can handle formats other than ISO 8601.
    """
    date_str, time_str = parse_date("2026-07-19 10:20:30")
    assert date_str == "2026-07-19"
    assert time_str == "10:20:30"


def test_parse_date_empty():
    """
    Test parse_date with an empty string.

    Input: ''
    Expected: ('', '')

    This is a common scenario when:
    - The source has a missing date field.
    - The source returns null/None which gets serialized to ''.
    - The date is not available for a particular listing.

    Verifies:
    - The function handles empty input gracefully without raising exceptions.
    - Both date and time are returned as empty strings.
    """
    date_str, time_str = parse_date("")
    assert date_str == ""
    assert time_str == ""


def test_parse_date_none():
    """
    Test parse_date with None input.

    Input: None
    Expected: ('', '')

    This scenario occurs when:
    - The scraper receives a null date field from an API.
    - The JSON parser converts null to None.
    - The date is not provided in the source data.

    Verifies:
    - The function handles None input gracefully (no TypeError).
    - Both date and time are returned as empty strings.
    """
    date_str, time_str = parse_date(None)
    assert date_str == ""
    assert time_str == ""


def test_parse_date_invalid():
    """
    Test parse_date with an entirely invalid format.

    Input: 'not a date'
    Expected: ('', '')

    This tests the fallback behaviour when:
    - The source provides unexpected data (e.g., a string that is not a date).
    - The date format is not recognised by any of the parsing strategies.

    Verifies:
    - The function does not crash on invalid input.
    - Returns empty strings as a safe fallback.
    - Logging/error handling would be triggered elsewhere (not in this test).
    """
    date_str, time_str = parse_date("not a date")
    assert date_str == ""
    assert time_str == ""


def test_parse_date_for_sort_with_time():
    """
    Test parse_date_for_sort with both date and time.

    Input: date='2026-07-19', time='14:30:00'
    Expected: '2026-07-19T14:30:00'

    This ISO‑like format is used for:
    - Sorting jobs by date and time in the Google Sheet.
    - Chronological ordering (newest jobs at the top).
    - Internal comparison of job freshness.

    Verifies:
    - The function returns a sortable string with date and time.
    - The format is consistent with ISO 8601 for lexicographic sorting.
    """
    result = parse_date_for_sort("2026-07-19", "14:30:00")
    assert result == "2026-07-19T14:30:00"


def test_parse_date_for_sort_without_time():
    """
    Test parse_date_for_sort with date only (no time provided).

    Input: date='2026-07-19', time=None
    Expected: '2026-07-19T00:00:00'

    This scenario occurs when:
    - The source provides only a date, not a time.
    - The time is missing or unavailable.

    Verifies:
    - The function defaults time to '00:00:00' when not provided.
    - Ensures consistent sorting: all jobs from the same date are treated equally.
    - The date part is preserved correctly.
    """
    result = parse_date_for_sort("2026-07-19")
    assert result == "2026-07-19T00:00:00"


def test_parse_date_for_sort_empty():
    """
    Test parse_date_for_sort with an empty date.

    Input: date='', time=''
    Expected: '0000-00-00T00:00:00'

    This is a fallback scenario where:
    - The date was never parsed or is missing.
    - The date is invalid and returned as empty string from parse_date().
    - The job should be sorted to the bottom (oldest possible date).

    Verifies:
    - The function returns a sentinel value (epoch-like) for empty dates.
    - Jobs with missing dates are placed at the bottom of the sorted list.
    - The sentinel value is lexicographically lower than any real date.
    """
    result = parse_date_for_sort("")
    assert result == "0000-00-00T00:00:00"


def test_parse_date_for_sort_default_time():
    """
    Test parse_date_for_sort with an explicit empty time string.

    Input: date='2026-07-19', time=''
    Expected: '2026-07-19T00:00:00'

    This differs from test_parse_date_for_sort_without_time in that:
    - Here we explicitly pass an empty string for time (instead of None).
    - This scenario occurs when the time string is available but empty.

    Verifies:
    - The function treats an empty time string the same as missing time.
    - Both cases result in the same default time ('00:00:00').
    - Ensures consistent behaviour across different input representations.
    """
    result = parse_date_for_sort("2026-07-19", "")
    assert result == "2026-07-19T00:00:00"