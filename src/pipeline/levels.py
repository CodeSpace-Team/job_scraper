"""
levels.py — give every job a level, or admit we do not know (F2)
=================================================================

The problem
-----------
Graduates filter by level, so the label has to be trustworthy. The AI fills
it in, but we want it filled in reliably and for the same reasons every time.

The levels
----------
    entry level · junior · mid · senior · lead · principal

plus ``unknown`` for ads that genuinely do not say. The brief is explicit
about that last one: anything the rules cannot work out is marked unknown
rather than guessed at.

How it decides, in order
------------------------
1. **The title.** By far the strongest signal. "Senior .NET Developer" is
   senior; "Graduate Software Engineer" is entry level. Where a title spans
   a range ("Junior to Mid Developer") the lower rung wins, because the ad
   is open to it.
2. **The years asked for** (from F3), using the bands in the brief's
   appendix: 0 is entry level, 1-2 junior, 3-4 mid, 5-7 senior, 8+ lead.
3. **The description**, but only phrases where the level word sits directly
   against a role word — "senior developer", "graduate programme". A loose
   mention of "senior" is ignored, because in most ads it refers to senior
   management or senior stakeholders, not the job being advertised.
4. **The AI's label**, if enrichment supplied one and nothing else fired.
5. **unknown.**

Why every job carries its working
---------------------------------
F4 removes jobs from a graduate's view based on this label. A wrong label
therefore costs somebody a job they could have got. So each job records
which rule decided, the exact words it decided on, and how confident that
makes us — and the QA sampler reads those fields back out for review.

Usage
-----
    from src.pipeline import levels

    jobs = levels.apply_levels(jobs)
    levels.log_levels(jobs)
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.utils import log


# ─── The Levels ─────────────────────────────────────────────────────────────

ENTRY = "entry level"
JUNIOR = "junior"
MID = "mid"
SENIOR = "senior"
LEAD = "lead"
PRINCIPAL = "principal"
UNKNOWN = "unknown"

LEVELS: Tuple[str, ...] = (ENTRY, JUNIOR, MID, SENIOR, LEAD, PRINCIPAL)
"""The six official levels, lowest rung first."""

LEVEL_RANK: Dict[str, int] = {level: i for i, level in enumerate(LEVELS)}
"""Position on the ladder, used to pick the lower of two competing labels."""

_SYNONYMS: Dict[str, str] = {
    "entry": ENTRY, "entry level": ENTRY, "entry-level": ENTRY,
    "intern": ENTRY, "internship": ENTRY, "graduate": ENTRY,
    "trainee": ENTRY, "learnership": ENTRY, "apprentice": ENTRY,
    "junior": JUNIOR, "jnr": JUNIOR, "jr": JUNIOR,
    "mid": MID, "mid level": MID, "mid-level": MID, "intermediate": MID,
    "senior": SENIOR, "snr": SENIOR, "sr": SENIOR,
    "lead": LEAD, "team lead": LEAD, "staff": LEAD,
    "principal": PRINCIPAL,
}
"""Spellings the AI or a feed might use, mapped onto the six levels."""


# ─── Title Rules ────────────────────────────────────────────────────────────
# Every pattern is tried and the lowest rung wins, so "Junior to Mid
# Developer" comes out junior. Word boundaries matter here: \bintern\b must
# not match "Internal" or "International", and \blead\b must not match
# "leadership".

_TITLE_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (ENTRY, re.compile(
        r"\b(graduate|grad|trainee|intern|internship|learner|learnership|"
        r"apprentice|cadet|bursary|entry[\s\-]?level|no experience)\b", re.I)),
    (JUNIOR, re.compile(r"\b(junior|jnr\.?|jr\.?)\b", re.I)),
    (MID, re.compile(r"\b(mid[\s\-]?level|intermediate)\b", re.I)),
    (SENIOR, re.compile(r"\b(senior|snr\.?|sr\.?|architect)\b", re.I)),
    (LEAD, re.compile(r"\b(lead|leader|staff engineer|head of)\b", re.I)),
    (PRINCIPAL, re.compile(r"\b(principal|chief)\b", re.I)),
)


# ─── Description Rules ──────────────────────────────────────────────────────
# Deliberately narrow. The level word must sit against a role word, so
# "reports to senior management" cannot make a job senior.

_ROLE_NOUN = (
    r"(?:developer|engineer|analyst|role|position|consultant|technician|"
    r"administrator|specialist|programmer|tester|designer|support|opportunity)"
)

_DESCRIPTION_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (ENTRY, re.compile(
        r"\b(?:graduate programme|graduate program|learnership|internship|"
        r"no prior experience|no previous experience|"
        r"entry[\s\-]level\s+" + _ROLE_NOUN +
        r"|graduate\s+" + _ROLE_NOUN +
        r"|trainee\s+" + _ROLE_NOUN + r")\b", re.I)),
    (JUNIOR, re.compile(r"\bjunior\s+" + _ROLE_NOUN + r"\b", re.I)),
    (MID, re.compile(
        r"\b(?:mid[\s\-]?level|intermediate)\s+" + _ROLE_NOUN + r"\b", re.I)),
    (SENIOR, re.compile(r"\bsenior\s+" + _ROLE_NOUN + r"\b", re.I)),
    (LEAD, re.compile(r"\b(?:lead|principal)\s+" + _ROLE_NOUN + r"\b", re.I)),
)


# ─── Helper Functions ───────────────────────────────────────────────────────

def normalise_level(value: Any) -> str:
    """
    Map any level spelling onto one of the six official levels.

    Args:
        value: A level label from the AI, a feed, or a sheet.

    Returns:
        One of the six levels, or '' if the value means nothing to us.

    Examples:
        >>> normalise_level("Intern")
        'entry level'
        >>> normalise_level("SNR")
        'senior'
        >>> normalise_level("unknown")
        ''
    """
    if not value:
        return ""

    key = str(value).strip().lower().replace("_", " ")
    if key in LEVEL_RANK:
        return key

    return _SYNONYMS.get(key, "")


def level_from_years(years: Optional[int]) -> str:
    """
    Map a years-of-experience figure onto a level.

    The bands follow the brief's appendix: entry level needs no prior
    experience, junior is 0-2 years, mid is 2-4.

    Args:
        years: Years asked for, or None.

    Returns:
        A level, or '' when there is no number to work from.
    """
    if years is None:
        return ""
    if years <= 0:
        return ENTRY
    if years <= 2:
        return JUNIOR
    if years <= 4:
        return MID
    if years <= 7:
        return SENIOR
    return LEAD


def _lowest(matches: Sequence[str]) -> str:
    """
    Pick the lowest rung among competing labels.

    Args:
        matches: Level labels found in the same piece of text.

    Returns:
        The lowest one, or '' if there were none.
    """
    known = [m for m in matches if m in LEVEL_RANK]
    return min(known, key=lambda level: LEVEL_RANK[level]) if known else ""


def level_from_title(title: str) -> Tuple[str, str]:
    """
    Read the level off the job title.

    Args:
        title: Job title.

    Returns:
        A (level, evidence) tuple. evidence is the word that decided it.
        Both are '' when the title says nothing about level.
    """
    if not title:
        return "", ""

    hits: List[Tuple[str, str]] = []
    for level, pattern in _TITLE_RULES:
        found = pattern.search(title)
        if found:
            hits.append((level, found.group(0)))

    if not hits:
        return "", ""

    winner = _lowest([level for level, _ in hits])
    evidence = next(word for level, word in hits if level == winner)
    return winner, evidence


def level_from_description(description: str) -> Tuple[str, str]:
    """
    Read the level off the description, using narrow phrases only.

    Args:
        description: Job description text.

    Returns:
        A (level, evidence) tuple, both '' when nothing definite is said.
    """
    if not description:
        return "", ""

    hits: List[Tuple[str, str]] = []
    for level, pattern in _DESCRIPTION_RULES:
        found = pattern.search(description)
        if found:
            hits.append((level, found.group(0)))

    if not hits:
        return "", ""

    winner = _lowest([level for level, _ in hits])
    evidence = next(phrase for level, phrase in hits if level == winner)
    return winner, evidence


# ─── The Rule ───────────────────────────────────────────────────────────────

def derive_level(job: Dict[str, Any]) -> Dict[str, str]:
    """
    Work out a job's level and show the working.

    Args:
        job: Job dictionary. Reads 'title', 'description_snippet',
             'experience_years' (set by F3) and the AI's level label.

    Returns:
        A dict with 'level', 'source', 'evidence' and 'confidence'.
    """
    title = job.get("title", "") or ""
    description = job.get("description_snippet", "") or ""

    # 1. The title, the strongest signal.
    level, evidence = level_from_title(title)
    if level:
        return {
            "level": level,
            "source": "title",
            "evidence": evidence,
            "confidence": "high",
        }

    # 2. The years asked for.
    years = job.get("experience_years")
    if isinstance(years, int) and not isinstance(years, bool):
        level = level_from_years(years)
        if level:
            return {
                "level": level,
                "source": "years",
                "evidence": f"{years} years",
                "confidence": "high" if years >= 3 else "medium",
            }

    # 3. The description, narrow phrases only.
    level, evidence = level_from_description(description)
    if level:
        return {
            "level": level,
            "source": "description",
            "evidence": evidence,
            "confidence": "medium",
        }

    # 4. Whatever the AI said, if it said anything usable.
    raw_ai = job.get("ai_job_level", job.get("job_level"))
    ai_level = normalise_level(raw_ai)
    if ai_level:
        return {
            "level": ai_level,
            "source": "ai",
            "evidence": str(raw_ai),
            "confidence": "low",
        }

    # 5. Say so rather than guess.
    return {"level": UNKNOWN, "source": "none", "evidence": "", "confidence": "none"}


# ─── Pipeline Step ──────────────────────────────────────────────────────────

def apply_levels(jobs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Label every job with a level (F2).

    Sets on each job:
        job_level        -- one of the six levels, or 'unknown'
        level_source     -- title | years | description | ai | none
        level_evidence   -- the words the decision rests on
        level_confidence -- high | medium | low | none
        ai_job_level     -- whatever the AI said, kept for comparison

    The AI's original label is preserved before it gets overwritten, both so
    the QA sampler can compare the rules against it, and so that running this
    step twice gives the same answer as running it once.

    Args:
        jobs: Job dictionaries, after ``apply_experience``.

    Returns:
        The same job dictionaries, with a level on each.
    """
    for job in jobs:
        if "ai_job_level" not in job:
            job["ai_job_level"] = job.get("job_level", "") or ""

        result = derive_level(job)
        job["job_level"] = result["level"]
        job["level_source"] = result["source"]
        job["level_evidence"] = result["evidence"]
        job["level_confidence"] = result["confidence"]

    return list(jobs)


# ─── Run Log ────────────────────────────────────────────────────────────────

def level_counts(jobs: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """
    Count jobs per level.

    Args:
        jobs: Job dictionaries.

    Returns:
        A dict of level name to count.
    """
    counts: Dict[str, int] = {}
    for job in jobs:
        level = job.get("job_level") or UNKNOWN
        counts[level] = counts.get(level, 0) + 1
    return counts


def log_levels(jobs: Sequence[Dict[str, Any]]) -> None:
    """
    Print the level breakdown for the run log (F2).

    Shows how many jobs landed on each level and which rule decided, so a
    rule that stops working is visible without opening the sheet.

    Args:
        jobs: Job dictionaries, after ``apply_levels``.
    """
    counts = level_counts(jobs)
    total = len(jobs)
    known = total - counts.get(UNKNOWN, 0)
    percentage = (known / total * 100) if total else 0.0

    log(f"  levels worked out: {known} of {total} = {percentage:.0f}%")

    ordered = list(LEVELS) + [UNKNOWN]
    breakdown = ", ".join(
        f"{level}: {counts[level]}" for level in ordered if counts.get(level)
    )
    log(f"  levels — {breakdown}")

    by_source: Dict[str, int] = {}
    for job in jobs:
        source = job.get("level_source") or "none"
        by_source[source] = by_source.get(source, 0) + 1

    sources = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
    log(f"  levels by source — {sources}")