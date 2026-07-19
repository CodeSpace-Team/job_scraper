"""
Unit tests for text utilities (src/utils/text.py).

This module tests:
- clean_text(): removes extra whitespace, collapses spaces, and truncates.
"""
from src.utils.text import clean_text


def test_clean_text_basic():
    """Remove leading/trailing spaces and collapse internal spaces."""
    result = clean_text("  Hello   world  ")
    assert result == "Hello world"


def test_clean_text_newlines():
    """Replace newlines with spaces."""
    result = clean_text("Hello\nworld\n\n")
    assert result == "Hello world"


def test_clean_text_max_len():
    """Truncate to max length."""
    result = clean_text("This is a long text", max_len=10)
    assert result == "This is a"


def test_clean_text_exact_max_len():
    """Truncate exactly at max length."""
    result = clean_text("1234567890", max_len=10)
    assert result == "1234567890"


def test_clean_text_none():
    """None input returns empty string."""
    result = clean_text(None)
    assert result == ""


def test_clean_text_empty():
    """Empty string returns empty string."""
    result = clean_text("")
    assert result == ""


def test_clean_text_only_spaces():
    """String of spaces returns empty string."""
    result = clean_text("   ")
    assert result == ""


def test_clean_text_special_chars():
    """Preserve non-space characters."""
    result = clean_text("Hello!@#$%^&*()_+")
    assert result == "Hello!@#$%^&*()_+"