"""
dedupe.py — catch the same job posted twice (F9)
=================================================

The problem
-----------
The same job often turns up twice. Indeed re-posts an ad after a few weeks
under a new web address. Or a recruitment agency lists a role at the same
time as the employer's own HR team, under two different company names.
Matching on the web address alone catches neither.

What this does
--------------
Plain matching on top of the address check. Same title, same company, same
city -- tidied up for spacing, capitals, and the decoration job boards staple
onto titles: reference numbers, trailing locations, "(Remote)", "URGENT".

And then, for the agency case, same title and same city with the same advert
text. The company name is the thing that differs there, so it is left out and
the words of the advert stand in for it. Agencies copy the employer's text
across word for word often enough that this catches the common case; one
that has been rewritten will not be caught, and that is the honest limit of
plain matching.

Plain matching only, as the brief asks. No fuzzy scoring and no similarity
thresholds: those go wrong quietly, and a graduate who never sees a real job
because two adverts scored 0.87 has no way of knowing it happened.

Where it runs
-------------
Twice, for two different kinds of duplicate.

1. **Inside a run**, straight after scraping. The same advert listed for
   three cities collapses to one before the AI ever sees it, which also
   stops us paying to enrich the same job three times.
2. **Against the sheet**, when deciding what is new. This is the one that
   catches a re-post: an advert from three weeks ago reappearing today with
   a fresh address would otherwise sail past the address check and land as a
   second row.

When two records collide the fuller one is kept -- the longer description
wins, and the newer posting date breaks a tie.

Usage
-----
    from src.pipeline import dedupe

    jobs, counts = dedupe.deduplicate(jobs)
    dedupe.log_dedupe(counts)
"""

import re
from typing import Any, Dict, List, Sequence, Tuple

from src.utils import log

# ─── Noise that job boards add to titles ────────────────────────────────────

_NOISE_PATTERNS: Tuple["re.Pattern[str]", ...] = (
    # "(Remote)", "(Contract)", "(Hybrid - 3 days)"
    re.compile(r"\((?:remote|hybrid|on[\s\-]?site|contract|temp|perm)[^)]*\)", re.I),
    # "Ref: ABC123", "Job ID 4471", "REQ-99"
    re.compile(r"\b(?:ref|reference|job id|req)\.?\s*[:#\-]?\s*[A-Za-z0-9\-/]+", re.I),
    # "URGENT", "Apply now", "HOT JOB"
    re.compile(r"\b(?:urgent|hot job|new|apply now|hiring)\b", re.I),
    # A trailing city or province: "Developer - Cape Town"
    re.compile(r"[\-–—|,]\s*(?:cape town|johannesburg|durban|pretoria|centurion|"
               r"sandton|midrand|port elizabeth|gqeberha|bloemfontein|"
               r"east london|stellenbosch|gauteng|western cape|kwazulu[\s\-]?natal|"
               r"south africa|remote|hybrid)\s*$", re.I),
)

_COMPANY_SUFFIXES = re.compile(
    # "pty" is listed on its own as well as with "ltd", because South African
    # companies are usually written "Acme (Pty) Ltd" -- the bracket sits
    # between the two words, so a combined pattern misses and leaves "pty"
    # stuck to the name.
    r"\b(?:pty\.?\s*ltd\.?|pty\.?|proprietary limited|ltd\.?|limited|inc\.?|"
    r"incorporated|group|holdings|sa|south africa|recruitment|recruiters)\b",
    re.I,
)
"""Legal and agency suffixes, so "Acme" matches "Acme (Pty) Ltd"."""


MIN_DESCRIPTION_FOR_MATCHING = 200
"""
How much description text is needed before it can identify a job.

Two ads sharing a short blurb prove nothing -- "Apply now" is not evidence.
Two ads sharing several paragraphs word for word are the same advert.
"""


# ─── Normalisation ──────────────────────────────────────────────────────────

def normalise(value: Any) -> str:
    """
    Tidy a value for comparison: lowercase, no punctuation, single spaces.

    Args:
        value: Any value. None is treated as empty.

    Returns:
        A comparison-safe string.

    Examples:
        >>> normalise("  Cape   TOWN, ")
        'cape town'
    """
    if not value:
        return ""

    text = str(value).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_title(title: Any) -> str:
    """
    Tidy a job title, stripping the decoration boards add to it.

    Args:
        title: Job title.

    Returns:
        A comparison-safe title.

    Examples:
        >>> normalise_title("Junior Developer (Remote) - Cape Town")
        'junior developer'
    """
    if not title:
        return ""

    text = str(title)
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub(" ", text)

    return normalise(text)


def normalise_company(company: Any) -> str:
    """
    Tidy a company name, stripping legal and agency suffixes.

    Args:
        company: Company name.

    Returns:
        A comparison-safe company name.

    Examples:
        >>> normalise_company("Acme Solutions (Pty) Ltd")
        'acme solutions'
    """
    if not company:
        return ""

    text = _COMPANY_SUFFIXES.sub(" ", str(company))
    return normalise(text)


def normalise_city(job: Dict[str, Any]) -> str:
    """
    Work out a comparable city for a job.

    Falls back to the first part of the location string when the scraper did
    not separate the city out.

    Args:
        job: Job dictionary.

    Returns:
        A comparison-safe city.
    """
    city = job.get("city")
    if not city:
        location = str(job.get("location", "") or "")
        city = location.split(",")[0] if location else ""

    return normalise(city)


def description_fingerprint(job: Dict[str, Any]) -> str:
    """
    Reduce a job's description to something comparable.

    Args:
        job: Job dictionary.

    Returns:
        The tidied description, or '' when there is too little of it to
        identify anything.
    """
    text = normalise(job.get("description_snippet"))
    return text if len(text) >= MIN_DESCRIPTION_FOR_MATCHING else ""


def agency_key(job: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Build the key that catches an agency and an employer posting the same job.

    Company is deliberately left out: that is the field which differs when a
    recruitment agency lists a role alongside the employer's own HR team.
    What identifies the job instead is the advert text, which agencies
    routinely copy across word for word.

    Args:
        job: Job dictionary.

    Returns:
        A (title, city, description) key. The third part is '' when the
        description is too short to identify anything, and such keys are
        never matched on.
    """
    return (
        normalise_title(job.get("title")),
        normalise_city(job),
        description_fingerprint(job),
    )



def duplicate_key(job: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Build the plain match key: tidied title, company and city.

    Args:
        job: Job dictionary.

    Returns:
        The three-part key used to spot a re-post.
    """
    return (
        normalise_title(job.get("title")),
        normalise_company(job.get("company")),
        normalise_city(job),
    )


def key_from_row(row: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Build the same key from a row already in the sheet.

    The sheet stores a full location string rather than a separate city, so
    this rebuilds the shape ``duplicate_key`` expects before hashing it.

    Args:
        row: A row from the Jobs tab, keyed by column heading.

    Returns:
        The three-part key, comparable with ``duplicate_key``.
    """
    return duplicate_key({
        "title": row.get("Job Title", ""),
        "company": row.get("Company", ""),
        "location": row.get("Location", ""),
    })


def is_comparable(key: Tuple[str, str, str]) -> bool:
    """
    Check whether a key is solid enough to match on.

    A job missing its title or its company cannot be compared -- an empty
    key is not evidence that two jobs are the same, and collapsing on one
    would silently lose real listings.

    Args:
        key: A three-part duplicate key.

    Returns:
        True when the key can be trusted.
    """
    return bool(key[0] and key[1])


# ─── Choosing between duplicates ────────────────────────────────────────────

def _richness(job: Dict[str, Any]) -> Tuple[int, str]:
    """Rank a record so the fuller, newer copy of a duplicate pair wins."""
    return (
        len(str(job.get("description_snippet", "") or "")),
        str(job.get("date_posted", "") or ""),
    )


# ─── Pipeline step ──────────────────────────────────────────────────────────

def deduplicate(
    jobs: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Remove repeated and re-posted jobs from a single run (F9).

    Three passes, each catching a kind the one before it cannot:

    1. Exact web address -- the same listing scraped twice.
    2. Title, company and city -- the same advert re-posted under a new
       address.
    3. Title, city and the advert text -- the same job listed by both a
       recruitment agency and the employer, under two different company
       names.

    Args:
        jobs: Job dictionaries, straight from the scrapers.

    Returns:
        A (unique_jobs, counts) tuple. counts reports what each pass removed.
    """
    counts = {
        "input": len(jobs),
        "by_url": 0,
        "by_title_company_city": 0,
        "by_same_advert_text": 0,
    }

    # ── Pass 1: exact web address ──
    seen_urls: Dict[str, None] = {}
    after_urls: List[Dict[str, Any]] = []

    for job in jobs:
        url = str(job.get("job_url", "") or "").strip()
        if url and url in seen_urls:
            counts["by_url"] += 1
            continue
        if url:
            seen_urls[url] = None
        after_urls.append(job)

    # ── Pass 2: plain title + company + city ──
    best_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    unique: List[Dict[str, Any]] = []

    for job in after_urls:
        key = duplicate_key(job)

        if not is_comparable(key):
            job["duplicate_count"] = 0
            unique.append(job)
            continue

        existing = best_by_key.get(key)
        if existing is None:
            job["duplicate_count"] = 0
            best_by_key[key] = job
            unique.append(job)
            continue

        counts["by_title_company_city"] += 1

        if _richness(job) > _richness(existing):
            # Swap the fuller record in, keeping its place in the list.
            job["duplicate_count"] = existing.get("duplicate_count", 0) + 1
            unique[unique.index(existing)] = job
            best_by_key[key] = job
        else:
            existing["duplicate_count"] = existing.get("duplicate_count", 0) + 1

        # ── Pass 3: same advert, different poster ──
    # A recruitment agency and the employer's own HR team both list the role,
    # under two different company names. Company is left out of this key and
    # the advert text stands in for it.
    best_by_advert: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    after_agency: List[Dict[str, Any]] = []

    for job in unique:
        key = agency_key(job)

        # No title, or too little description to be sure. Keep it.
        if not key[0] or not key[2]:
            after_agency.append(job)
            continue

        existing = best_by_advert.get(key)
        if existing is None:
            best_by_advert[key] = job
            after_agency.append(job)
            continue

        counts["by_same_advert_text"] += 1

        if _richness(job) > _richness(existing):
            job["duplicate_count"] = existing.get("duplicate_count", 0) + 1
            after_agency[after_agency.index(existing)] = job
            best_by_advert[key] = job
        else:
            existing["duplicate_count"] = existing.get("duplicate_count", 0) + 1

    unique = after_agency

    counts["output"] = len(unique)
    counts["removed"] = (counts["by_url"]
                         + counts["by_title_company_city"]
                         + counts["by_same_advert_text"])
    return unique, counts


# ─── Run Log ────────────────────────────────────────────────────────────────

def log_dedupe(counts: Dict[str, int]) -> None:
    """
    Print the duplicate summary for the run log (F9).

    Args:
        counts: The counts dictionary returned by ``deduplicate``.
    """
    log(f"  duplicates removed: {counts['removed']} "
        f"({counts['by_url']} same web address, "
        f"{counts['by_title_company_city']} same title/company/city, "
        f"{counts['by_same_advert_text']} same advert via another poster)")
    log(f"  unique jobs: {counts['output']} of {counts['input']}")