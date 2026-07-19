"""
Unit tests for date utilities (src/utils/dates.py).

This module tests:
- parse_date(): converts various date strings to (date_str, time_str)
- parse_date_for_sort(): returns sortable ISO format for comparisons
"""
from src.utils.dates import parse_date, parse_date_for_sort


def test_parse_date_iso_full():
    """ISO format with time: '2026-07-19T14:30:00Z' -> ('2026-07-19', '14:30:00')."""
    date_str, time_str = parse_date("2026-07-19T14:30:00Z")
    assert date_str == "2026-07-19"
    assert time_str == "14:30:00"


def test_parse_date_iso_date_only():
    """ISO date only: '2026-07-19' -> ('2026-07-19', '')."""
    date_str, time_str = parse_date("2026-07-19")
    assert date_str == "2026-07-19"
    assert time_str == ""


def test_parse_date_common_format():
    """Common datetime: '2026-07-19 10:20:30' -> ('2026-07-19', '10:20:30')."""
    date_str, time_str = parse_date("2026-07-19 10:20:30")
    assert date_str == "2026-07-19"
    assert time_str == "10:20:30"


def test_parse_date_empty():
    """Empty input returns ('', '')."""
    date_str, time_str = parse_date("")
    assert date_str == ""
    assert time_str == ""


def test_parse_date_none():
    """None input returns ('', '')."""
    date_str, time_str = parse_date(None)
    assert date_str == ""
    assert time_str == ""


def test_parse_date_invalid():
    """Invalid format returns ('', '')."""
    date_str, time_str = parse_date("not a date")
    assert date_str == ""
    assert time_str == ""


def test_parse_date_for_sort_with_time():
    """Date and time -> 'YYYY-MM-DDTHH:MM:SS'."""
    result = parse_date_for_sort("2026-07-19", "14:30:00")
    assert result == "2026-07-19T14:30:00"


def test_parse_date_for_sort_without_time():
    """Date only -> 'YYYY-MM-DDT00:00:00'."""
    result = parse_date_for_sort("2026-07-19")
    assert result == "2026-07-19T00:00:00"


def test_parse_date_for_sort_empty():
    """Empty date -> '0000-00-00T00:00:00'."""
    result = parse_date_for_sort("")
    assert result == "0000-00-00T00:00:00"


def test_parse_date_for_sort_default_time():
    """Time can be empty string, defaults to '00:00:00'."""
    result = parse_date_for_sort("2026-07-19", "")
    assert result == "2026-07-19T00:00:00"