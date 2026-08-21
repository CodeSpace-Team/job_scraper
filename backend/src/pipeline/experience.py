"""
experience.py — read the years of experience out of the ad (F3)
================================================================

The problem
-----------
The "Years Exp" column was nearly always empty, because it only got filled
when a job feed handed over a clean number. Most ads state it in a sentence
instead: "at least 3 years' experience", "2-4 years in a similar role",
"minimum five (5) years".

What this does
--------------
A plain text search over the job description for the common phrasings. The
result is always a number or nothing at all -- never text -- so the column
can be sorted and filtered, and so F4 can compare against it safely.

Decisions worth knowing
-----------------------
- **A range records the lower number.** "2-4 years" is stored as 2, because
  a person with 2 years can apply.
- **Several mentions record the lowest.** An ad asking for "5+ years in .NET,
  3+ years in Azure" is stored as 3, for the same reason. This also stops F4
  dropping a job a graduate could actually get.
- **The wording has to be about experience.** A bare "3 years" is ignored
  unless the sentence around it is about experience. Without this check,
  "3 year contract", "3-year degree" and "in the last 5 years" would all turn
  into experience requirements, and the column would be worse than empty.

Usage
-----
    from src.pipeline import experience

    jobs = experience.apply_experience(jobs)
    experience.log_experience(jobs)
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils import log


# ─── Constants ──────────────────────────────────────────────────────────────

MAX_PLAUSIBLE_YEARS = 20
"""Anything above this is noise (a founding date, a company's age)."""

_WORD_NUMBERS: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15,
}
"""Written-out numbers, because plenty of ads spell them out."""

_NUMBER = (
    r"(?:(?<!\d)\d{1,2}(?!\d)|"
    r"(?<![A-Za-z])(?:" + "|".join(_WORD_NUMBERS) + r")(?![A-Za-z]))"
)
"""
One-or-two digits, or a written-out number.

The digit guards are load-bearing rather than tidiness. Without them,
``\\d{1,2}`` happily matches the *tail* of a longer number: "over 300 years
of combined gaming experience" handed back "00" -> 0 years, and "with over
100 years of rich history" did the same. Both are real sentences off the
live board, and both came out as 0 years -> entry level, which is how a
"Developer Level 2" ended up in a graduate's entry-level results.
"""

_EXPERIENCE_WORDS = (
    r"(?:experience|exp\.?|working|hands[\s\-]?on|industry|commercial|"
    r"background|track record|in\s+a\s+similar|as\s+a)"
)
"""Wording that means the number is a requirement, not a passing mention."""

_NEGATIVE_BEFORE = re.compile(
    r"(?:last|past|next|previous|over the|within the|since|for the past)\s*$",
    re.IGNORECASE,
)
"""Wording before the number that means it is about a period, not a person."""

_NEGATIVE_AFTER = re.compile(
    r"^\s*(?:contract|degree|diploma|qualification|warranty|guarantee|old|"
    r"fixed[\s\-]term|ago|nqf)",
    re.IGNORECASE,
)
"""Wording after the number that means it describes something else."""

_COMPANY_HISTORY = re.compile(
    r"^\W*(?:of\s+)?(?:rich\s+|proud\s+|long\s+)?"
    r"(?:history|heritage|legacy|excellence|standing|combined|collective|"
    r"in\s+(?:business|operation|the\s+industry|the\s+market))",
    re.IGNORECASE,
)
"""
Wording after the number that means it is the *company's* age, not what the
job asks of a person.

Ads open on this constantly -- "with over 100 years of rich history", "brings
together over 300 years of combined gaming experience". The word
"experience" is right there, so the context check above says yes; it is just
somebody else's experience. Left alone these land as a low number and
therefore a low level, which puts a job a graduate cannot do in front of one.
"""


# ─── Patterns ───────────────────────────────────────────────────────────────
# Each pattern captures the number to record as "low". Ranges also capture a
# "high" group, which is deliberately thrown away.

_RANGE = re.compile(
    rf"(?P<low>{_NUMBER})\s*(?:-|–|—|\bto\b|\bor\b)\s*(?P<high>{_NUMBER})\s*"
    rf"(?:\+\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)

_BRACKETED = re.compile(
    rf"(?P<low>{_NUMBER})\s*\(\s*\d{{1,2}}\s*\)\s*(?:\+\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)

_AT_LEAST = re.compile(
    rf"(?:at least|minimum(?:\s+of)?|min\.?|no less than|more than|over|"
    rf"upwards of|in excess of)\s*(?P<low>{_NUMBER})\s*(?:\+\s*)?"
    rf"(?:years?|yrs?)\b",
    re.IGNORECASE,
)

_PLUS = re.compile(
    rf"(?P<low>{_NUMBER})\s*(?:\+|plus)\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)

_PLAIN = re.compile(
    rf"(?P<low>{_NUMBER})\s*(?:\+\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)

_PATTERNS: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("range", _RANGE),
    ("bracketed", _BRACKETED),
    ("at_least", _AT_LEAST),
    ("plus", _PLUS),
    ("plain", _PLAIN),
)
"""Most specific first. The first pattern to claim a span keeps it."""


# ─── Helper Functions ───────────────────────────────────────────────────────

def _to_int(token: str) -> Optional[int]:
    """
    Convert a captured token to a number.

    Args:
        token: Either digits ("3") or a written-out number ("three").

    Returns:
        The number, or None if the token is neither.
    """
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORD_NUMBERS.get(token)


def _has_experience_context(text: str, start: int, end: int) -> bool:
    """
    Check the wording around a match to confirm it is about experience.

    Looks ahead for experience words, and behind for requirement phrasing
    such as "at least" or "must have".

    Args:
        text: The full text being scanned.
        start: Start index of the match.
        end: End index of the match.

    Returns:
        True if the surrounding wording is about experience.
    """
    after = text[end:end + 60]
    if re.search(
        rf"^\W*(?:of\s+|in\s+|as\s+|with\s+)?\W*{_EXPERIENCE_WORDS}",
        after, re.IGNORECASE,
    ):
        return True
    if re.search(rf"\b{_EXPERIENCE_WORDS}\b", after[:45], re.IGNORECASE):
        return True

    before = text[max(0, start - 60):start]
    if re.search(
        r"\b(?:at least|minimum|min\.?|requires?|required|must have|ideally|"
        r"preferably|proven|with|least)\b\W*$",
        before, re.IGNORECASE,
    ):
        return True

    return bool(re.search(rf"\b{_EXPERIENCE_WORDS}\b\W*$", before[-45:], re.IGNORECASE))


def _is_rejected(text: str, start: int, end: int) -> bool:
    """
    Check for wording that means the number is not about experience.

    Args:
        text: The full text being scanned.
        start: Start index of the match.
        end: End index of the match.

    Returns:
        True if the match should be thrown away.
    """
    before = text[max(0, start - 25):start]
    after = text[end:end + 40]
    return bool(
        _NEGATIVE_BEFORE.search(before)
        or _NEGATIVE_AFTER.match(after)
        or _COMPANY_HISTORY.match(after)
    )


# ─── Extraction ─────────────────────────────────────────────────────────────

def find_year_mentions(text: str) -> List[Dict[str, Any]]:
    """
    Find every credible mention of years of experience in a block of text.

    Args:
        text: Job description, or any free text.

    Returns:
        A list of dicts with 'years', 'pattern' and 'quote' keys, in the
        order they appear. Empty when the ad never says.
    """
    if not text:
        return []

    mentions: List[Dict[str, Any]] = []
    claimed: List[Tuple[int, int]] = []

    for label, pattern in _PATTERNS:
        for hit in pattern.finditer(text):
            start, end = hit.span()

            # A more specific pattern already covered this stretch of text.
            if any(start < c_end and end > c_start for c_start, c_end in claimed):
                continue

            years = _to_int(hit.group("low"))
            if years is None or years > MAX_PLAUSIBLE_YEARS:
                continue
            if _is_rejected(text, start, end):
                continue
            if not _has_experience_context(text, start, end):
                continue

            claimed.append((start, end))
            quote = re.sub(r"\s+", " ", text[max(0, start - 20):end + 30]).strip()
            mentions.append({"years": years, "pattern": label, "quote": quote})

    return mentions


def extract_years(*texts: Optional[str]) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """
    Read the years of experience an ad asks for.

    Args:
        *texts: Text fragments to scan (description, title, and so on).
                None and empty strings are allowed and simply skipped, since
                the fields these come from are often missing.

    Returns:
        A (years, mentions) tuple. years is the lowest credible figure, or
        None when the ad never says. mentions is the audit trail.

    Examples:
        >>> extract_years("We need at least 3 years' experience in Java")[0]
        3
        >>> extract_years("2-4 years of experience required")[0]
        2
        >>> extract_years("Join us on a 3 year contract")[0]
    """
    all_mentions: List[Dict[str, Any]] = []
    for text in texts:
        all_mentions.extend(find_year_mentions(text or ""))

    if not all_mentions:
        return None, []

    return min(m["years"] for m in all_mentions), all_mentions


def coerce_existing(value: Any) -> Optional[int]:
    """
    Turn whatever is already in the years field into a number or nothing.

    Feeds and the AI hand over things like "3-5", "3+ years" or "". The
    column has to end up numeric or empty, never text.

    Args:
        value: Whatever was already in the field.

    Returns:
        A number in range, or None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= MAX_PLAUSIBLE_YEARS else None
    if isinstance(value, float):
        return int(value) if 0 <= value <= MAX_PLAUSIBLE_YEARS else None

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"\d{1,2}", text)
    if not match:
        return None

    years = int(match.group())
    return years if 0 <= years <= MAX_PLAUSIBLE_YEARS else None


# ─── Pipeline Step ──────────────────────────────────────────────────────────

def apply_experience(jobs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fill in the years of experience for every job (F3).

    Sets on each job:
        experience_years -- a number, or None. Never text.
        years_source     -- 'text' (read from the ad), 'feed' (already
                            supplied), or '' (not stated anywhere)
        years_evidence   -- the phrase the number came from, for review

    Args:
        jobs: Job dictionaries.

    Returns:
        The same job dictionaries, with the years field sorted out.
    """
    for job in jobs:
        years, mentions = extract_years(
            job.get("description_snippet", ""),
            job.get("title", ""),
        )

        if years is not None:
            job["experience_years"] = years
            job["years_source"] = "text"
            job["years_evidence"] = " | ".join(m["quote"] for m in mentions[:3])
            continue

        from_feed = coerce_existing(job.get("experience_years"))
        job["experience_years"] = from_feed
        job["years_source"] = "feed" if from_feed is not None else ""
        job["years_evidence"] = ""

    return list(jobs)


# ─── Run Log ────────────────────────────────────────────────────────────────

def fill_rate(jobs: Sequence[Dict[str, Any]]) -> Tuple[int, int, float]:
    """
    Work out how much of the years column is filled in.

    Args:
        jobs: Job dictionaries.

    Returns:
        A (filled, total, percentage) tuple.
    """
    total = len(jobs)
    filled = sum(1 for job in jobs if job.get("experience_years") is not None)
    return filled, total, (filled / total * 100) if total else 0.0


def log_experience(jobs: Sequence[Dict[str, Any]]) -> None:
    """
    Print the years-of-experience score for the run log (F3).

    The target is roughly 4 in 10. Many ads simply do not say, so chasing
    100 percent would mean inventing numbers.

    Args:
        jobs: Job dictionaries, after ``apply_experience``.
    """
    filled, total, percentage = fill_rate(jobs)
    log(f"  years of experience filled in: {filled} of {total} = {percentage:.0f}%")

    by_source: Dict[str, int] = {}
    for job in jobs:
        source = job.get("years_source") or "not stated"
        by_source[source] = by_source.get(source, 0) + 1

    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
    log(f"  years by source — {breakdown}")
