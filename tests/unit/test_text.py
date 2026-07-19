"""
Unit tests for text utilities (src/utils/text.py).

This module tests:
- clean_text(): a function used extensively across the pipeline to:
  * Normalize whitespace (remove extra spaces, tabs, newlines).
  * Collapse multiple spaces into a single space.
  * Optionally truncate text to a maximum length.

Why these tests matter:
- Text normalization is crucial for consistent job data.
- Descriptions, titles, and company names come from various sources with
  inconsistent formatting (extra spaces, newlines, tabs).
- Clean text is essential for:
  - AI enrichment (Claude works better with clean input).
  - Google Sheets presentation (no awkward line breaks or excessive spaces).
  - Deduplication and comparisons.
- Truncation ensures that we don't exceed field limits (e.g., sheet columns).
"""
from src.utils.text import clean_text


def test_clean_text_basic():
    """
    Test clean_text() on a string with leading/trailing spaces and multiple internal spaces.

    Input: '  Hello   world  '
    Expected: 'Hello world'

    Scenario:
    - Typical user input or scraped text with inconsistent spacing.
    - The function should trim leading/trailing spaces and collapse
      multiple spaces within the string to a single space.

    Why this matters:
    - Ensures that descriptions and titles are clean and readable.
    - Prevents ugly formatting in the Google Sheet.
    - Helps with deduplication (e.g., "Hello  world" vs "Hello world").

    Edge cases covered:
    - Leading and trailing spaces are removed.
    - Multiple spaces between words are reduced to one.
    """
    result = clean_text("  Hello   world  ")
    assert result == "Hello world"


def test_clean_text_newlines():
    """
    Test clean_text() on a string with newline characters.

    Input: 'Hello\nworld\n\n'
    Expected: 'Hello world'

    Scenario:
    - Descriptions scraped from HTML often contain newlines (\n).
    - The function replaces all newlines and other whitespace characters with spaces.

    Why this matters:
    - Newlines cause formatting issues in the Google Sheet (multi-line cells).
    - AI enrichment (Claude) expects contiguous text, not scattered by line breaks.
    - Normalises text for easier processing.

    Edge cases covered:
    - Single newline replaced with space.
    - Multiple consecutive newlines collapsed to one space.
    - Trailing newline does not leave an extra space.
    """
    result = clean_text("Hello\nworld\n\n")
    assert result == "Hello world"


def test_clean_text_max_len():
    """
    Test clean_text() with truncation to a maximum length.

    Input: text='This is a long text', max_len=10
    Expected: 'This is a'

    Scenario:
    - Some fields have character limits (e.g., sheet columns, display previews).
    - The function should truncate the text to the specified max length.

    Why this matters:
    - Prevents extremely long descriptions from breaking sheet formatting.
    - Ensures that previews (like the job summary) fit in limited space.
    - Truncation should be clean (cut at character boundary, not word).

    Edge cases covered:
    - Text longer than max_len is truncated exactly to max_len.
    - No extra spaces or ellipsis are added (keeps it simple).
    """
    result = clean_text("This is a long text", max_len=10)
    assert result == "This is a"


def test_clean_text_exact_max_len():
    """
    Test clean_text() when the text length is exactly the max length.

    Input: text='1234567890', max_len=10
    Expected: '1234567890'

    Scenario:
    - The text already fits exactly within the limit.
    - The function should return the text unchanged.

    Why this matters:
    - Ensures that truncation does not occur unnecessarily.
    - Avoids off-by-one errors in length handling.

    Edge cases covered:
    - Length == max_len (should not truncate).
    - No additional characters or spaces added.
    """
    result = clean_text("1234567890", max_len=10)
    assert result == "1234567890"


def test_clean_text_none():
    """
    Test clean_text() with None input.

    Input: None
    Expected: ''

    Scenario:
    - Scraped data may have missing fields (null/None).
    - The function should return an empty string instead of raising an error.

    Why this matters:
    - The pipeline must handle missing data gracefully.
    - Prevents AttributeError (e.g., calling .strip() on None).
    - Empty strings are safer for further processing.

    Edge cases covered:
    - None input is converted to empty string.
    - No exception is raised.
    """
    result = clean_text(None)
    assert result == ""


def test_clean_text_empty():
    """
    Test clean_text() with an empty string.

    Input: ''
    Expected: ''

    Scenario:
    - Explicitly empty fields in the data.
    - The function should return an empty string.

    Why this matters:
    - Ensures the function is idempotent for empty input.
    - Consistent with behaviour for None.

    Edge cases covered:
    - Empty string returns empty string.
    - No additional characters or modifications.
    """
    result = clean_text("")
    assert result == ""


def test_clean_text_only_spaces():
    """
    Test clean_text() with a string containing only spaces.

    Input: '   '
    Expected: ''

    Scenario:
    - Text with only whitespace (e.g., from malformed HTML or user input).
    - The function should return an empty string.

    Why this matters:
    - Prevents empty-looking strings from being stored or displayed.
    - Reduces noise in the data (spaces are not meaningful).
    - Consistent with the idea that whitespace-only input should be treated as empty.

    Edge cases covered:
    - Leading, trailing, and only spaces are removed.
    - Returns an empty string.
    """
    result = clean_text("   ")
    assert result == ""


def test_clean_text_special_chars():
    """
    Test clean_text() with special characters (non-space).

    Input: 'Hello!@#$%^&*()_+'
    Expected: 'Hello!@#$%^&*()_+'

    Scenario:
    - Job titles and descriptions often contain special characters (e.g., C#, C++, Python 3.12).
    - The function should preserve all non-whitespace characters.

    Why this matters:
    - Preserves technical terms like 'C#', 'C++', '&', '@'.
    - Prevents unintended removal of important symbols.
    - Ensures that the text remains accurate for AI and human reading.

    Edge cases covered:
    - All special characters are preserved.
    - No transformation of non-space characters.
    """
    result = clean_text("Hello!@#$%^&*()_+")
    assert result == "Hello!@#$%^&*()_+"