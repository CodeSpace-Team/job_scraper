"""
skills.py — the one official skills list (F5)
=============================================

Everything that touches skills goes through this module, and this module is the
only thing that reads ``skills.json``. There is no second skills list anywhere:
the keyword matcher, the AI normaliser, the Sheets writer, the published
jobs.json and the board's skill picker all resolve names through here.

What it does
------------
1. ``match_skills(text)`` — free, offline keyword matching over the job title
   and description. Runs before the AI, so most jobs never need an API call.
2. ``canonicalise(names)`` — maps any spelling to the official name, so "JS"
   becomes "JavaScript" and "ReactJS" becomes "React". Applied to the AI's
   output too, so the sheet only ever shows official spellings.
3. ``fill_rate(jobs)`` — the daily score printed in the run log.

Matching rules
--------------
- Aliases written in all capitals with 5 or fewer letters (JS, TS, SQL, AWS,
  REST) match case-sensitively. Without this, "the rest of the team" would
  score a REST APIs hit on nearly every ad.
- Boundaries are non-identifier characters rather than ``\\b``, so "C#",
  ".NET", "CI/CD" and "Node.js" match, while "Java" never matches inside
  "JavaScript".
- Skills flagged ``requires_context`` (short, ambiguous names like Go and
  Swift) only count when a technical context word sits nearby.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.utils import log

# ─── Constants ──────────────────────────────────────────────────────────────

SKILLS_FILE = Path(__file__).resolve().parents[2] / "skills.json"
"""The single skills file, at the repository root."""

MIN_SKILLS_BEFORE_AI = 3
"""Jobs with fewer than this many matched skills get sent to the AI (F5)."""

_CONTEXT_WINDOW = 60
"""Characters either side of an ambiguous match to scan for a context word."""

_CONTEXT_WORDS = (
    "develop", "engineer", "program", "coding", "code", "language",
    "backend", "back-end", "server", "stack", "experience", "knowledge",
    "proficien", "framework", "microservice", "api", "skills", "tech",
)
"""Signals that an ambiguous name (Go, Swift) is being used in a tech sense."""

# Characters that may not sit directly against a match. Includes ``+``, ``#``
# and ``.`` so "C++", "C#" and ".NET" keep their shape.
_BOUNDARY = r"[A-Za-z0-9+#]"


# ─── Loading ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_skills(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load the official skills list, in the order the file defines.

    Order matters: the board's skill picker shows skills in this order, and the
    first 22 entries are the appendix list from the brief.

    Args:
        path: Optional override for the skills file (used by tests).

    Returns:
        List of skill records, each with 'name', 'category' and 'aliases'.
    """
    target = Path(path) if path else SKILLS_FILE
    data = json.loads(target.read_text(encoding="utf-8"))
    return data.get("skills", [])


def official_names(path: Optional[str] = None) -> List[str]:
    """Return every official skill name, in file order."""
    return [skill["name"] for skill in load_skills(path)]


@lru_cache(maxsize=1)
def _alias_index() -> Dict[str, str]:
    """
    Map every lowercased spelling (official name and aliases) to its official
    name, for canonicalisation lookups.
    """
    index: Dict[str, str] = {}
    for skill in load_skills():
        name = skill["name"]
        index[name.lower()] = name
        for alias in skill.get("aliases", []):
            index.setdefault(alias.lower(), name)
    return index


def _is_acronym(term: str) -> bool:
    """True for short all-caps terms (JS, SQL, AWS) that need exact case."""
    letters = [c for c in term if c.isalpha()]
    return bool(letters) and len(letters) <= 5 and all(c.isupper() for c in letters)


@lru_cache(maxsize=1)
def _compiled_patterns() -> List[Tuple[str, "re.Pattern[str]", bool]]:
    """
    Build one regex per skill spelling.

    Returns:
        List of (official_name, compiled_pattern, requires_context) tuples.
    """
    patterns: List[Tuple[str, "re.Pattern[str]", bool]] = []

    for skill in load_skills():
        name = skill["name"]
        needs_context = bool(skill.get("requires_context"))

        # "Go" is too common as an English word to match on its own name;
        # such skills set name_matches false and rely on aliases ("Golang").
        terms = list(skill.get("aliases", []))
        if skill.get("name_matches", True):
            terms.insert(0, name)

        for term in terms:
            # A name like "SQL (MySQL/Postgres)" is a label, not something an
            # ad would ever say verbatim; its aliases carry the matching.
            if "(" in term:
                continue

            body = re.escape(term).replace(r"\ ", r"[\s\-]+")
            expression = f"(?<!{_BOUNDARY}){body}(?!{_BOUNDARY})"
            flags = 0 if _is_acronym(term) else re.IGNORECASE
            patterns.append((name, re.compile(expression, flags), needs_context))

    return patterns


def _has_context(text: str, start: int, end: int) -> bool:
    """Check whether a technical context word sits near an ambiguous match."""
    window = text[max(0, start - _CONTEXT_WINDOW):end + _CONTEXT_WINDOW].lower()
    return any(word in window for word in _CONTEXT_WORDS)


# ─── Matching ───────────────────────────────────────────────────────────────

def match_skills(*texts: Optional[str]) -> List[str]:
    """
    Find official skills in free text, without calling the AI.

    Args:
        *texts: Any number of text fragments (title, description, ...).
            None is accepted and skipped, since callers often pass
            job.get(...) straight through.

    Returns:

    Examples:
        >>> match_skills("Junior JS Developer", "React and Node experience")
        ['JavaScript', 'React', 'Node.js']
    """
    haystack = " \n ".join(t for t in texts if t)
    if not haystack:
        return []

    found: Dict[str, None] = {}

    for name, pattern, needs_context in _compiled_patterns():
        if name in found:
            continue
        for hit in pattern.finditer(haystack):
            if needs_context and not _has_context(haystack, hit.start(), hit.end()):
                continue
            found[name] = None
            break

    # Preserve skills-file order rather than match order.
    order = {name: i for i, name in enumerate(official_names())}
    return sorted(found, key=lambda n: order.get(n, 999))


def canonicalise(names: Iterable[Optional[str]]) -> List[str]:
    """
    Convert any spelling to its official name and drop anything unrecognised.

    This is what stops "JS" ever reaching the sheet. It is applied to the AI's
    output as well as to keyword matches, so both sides speak one vocabulary.

    Args:
        names: Skill names in any spelling. A None or empty entry is
            skipped rather than rejected, since split_skills() and a raw
            job.get(...) can both hand one over.

    Returns:

    Examples:
        >>> canonicalise(["JS", "reactjs", "Node", "Underwater Basket Weaving"])
        ['JavaScript', 'React', 'Node.js']
    """
    index = _alias_index()
    order = {name: i for i, name in enumerate(official_names())}
    resolved: Dict[str, None] = {}

    for raw in names:
        if not raw:
            continue
        key = str(raw).strip().strip(".,;•").lower()
        official = index.get(key)
        if official is None:
            # Tolerate light punctuation noise, e.g. "Node.js." or "React.js"
            official = index.get(key.replace(" ", ""))
        if official:
            resolved[official] = None

    return sorted(resolved, key=lambda n: order.get(n, 999))


def canonicalise_string(value: Optional[str]) -> str:
    """
    Canonicalise a comma-separated skills string in place.

    Args:
        value: Comma-separated skills in any spelling. None is accepted and
            treated as empty, since it usually arrives as job.get(...) on a
            field that was never set.

    Returns:
        Comma-separated official names (empty string if nothing resolved).
    """
    if not value:
        return ""
    return ", ".join(canonicalise(part for part in str(value).split(",")))


def split_skills(value: Any) -> List[str]:
    """Normalise a skills field that may be a list or a comma-separated string."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [part for part in str(value).split(",")]


# ─── Pipeline step ──────────────────────────────────────────────────────────

def apply_keyword_skills(jobs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fill in ``must_have_skills`` by keyword matching, before the AI runs.

    Any skills the scraper already supplied are canonicalised and merged with
    the keyword hits. Jobs left with fewer than ``MIN_SKILLS_BEFORE_AI`` skills
    are marked ``needs_ai_skills`` so only they cost money.

    Args:
        jobs: Job dictionaries.

    Returns:
        The same job dictionaries, with skills filled in.
    """
    for job in jobs:
        existing = canonicalise(split_skills(job.get("must_have_skills")))
        matched = match_skills(
            job.get("title", ""),
            job.get("description_snippet", ""),
        )

        merged = canonicalise(existing + matched)
        job["must_have_skills"] = ", ".join(merged)
        job["skills_source"] = "keyword" if merged else ""
        job["needs_ai_skills"] = len(merged) < MIN_SKILLS_BEFORE_AI

    return list(jobs)


def normalise_ai_skills(job: Dict[str, Any]) -> None:
    """
    Tidy the skills the AI returned to official spellings (F5).

    Called after enrichment so that "JS" from Claude is corrected exactly like
    "JS" from a job ad. Also corrects 'skills_source', which enrichment can
    make wrong without this function's help: when enrichment succeeds it
    overwrites 'must_have_skills' outright with its own list, but a job the
    keyword matcher had already labelled 'keyword' keeps that label unless
    something updates it -- checking the field's own prior value cannot tell
    the difference. 'blurb' is only ever set by enrichment, so its presence
    is what actually tells the two cases apart.

    Args:
        job: A job dictionary, after the enrichment step has run (or tried
            to and failed).
    """
    for field in ("must_have_skills", "nice_to_have_skills"):
        tidied = canonicalise(split_skills(job.get(field)))
        job[field] = ", ".join(tidied)

    if not job.get("must_have_skills"):
        job["skills_source"] = ""
    elif job.get("blurb"):
        # Enrichment ran and succeeded on this job, so whatever is in
        # 'must_have_skills' now is the AI's, not the keyword matcher's --
        # even if this job started out labelled 'keyword'.
        job["skills_source"] = "ai"
    # else: no blurb means enrichment never touched this job (skipped,
    # failed, or the batch errored) and whatever was already there --
    # 'keyword' or '' -- survived untouched. Leave it as it is.


def fill_rate(jobs: Sequence[Dict[str, Any]]) -> Tuple[int, int, float]:
    """
    Work out the daily skills score for the run log.

    Args:
        jobs: Job dictionaries.

    Returns:
        (filled, total, percentage) — e.g. (143, 162, 88.3).
    """
    total = len(jobs)
    filled = sum(1 for job in jobs if job.get("must_have_skills"))
    percentage = (filled / total * 100) if total else 0.0
    return filled, total, percentage


def log_fill_rate(jobs: Sequence[Dict[str, Any]]) -> None:
    """Print the daily skills score, so nobody has to open the sheet (F5)."""
    filled, total, percentage = fill_rate(jobs)
    log(f"  skills filled in: {filled} of {total} = {percentage:.0f}%")

    by_source: Dict[str, int] = {}
    for job in jobs:
        source = job.get("skills_source") or "none"
        by_source[source] = by_source.get(source, 0) + 1
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
    log(f"  skills by source — {breakdown}")