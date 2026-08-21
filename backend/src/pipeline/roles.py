"""
roles.py — the seven role types, and the searches that find them (F7)
======================================================================

The scraper used to search Indeed for six phrases, all variations of
"software developer". Our graduates are positioned for a much wider set of
tracks, and the scraper never looked for them.

This module holds two things:

1. **The fixed role list.** Every job gets exactly one role type from
   ``ROLE_TYPES`` — never free text, because free text cannot be filtered.
   The board's role filter shows exactly this list.
2. **The search terms**, grouped by track, each tagged with the role type it
   belongs to and how often it should run. Internship, learnership and
   graduate-programme phrasings are in there too: those ads often say neither
   "developer" nor "support" in the title, so nothing else would find them.

Search cadence
--------------
Running every term daily makes the run slow and makes Indeed unhappy. Core
terms (software development and technical support, our two biggest tracks)
run every day; the rest alternate between even and odd days of the year, so
the whole set is covered every two days.
"""

import re
from datetime import date
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from src.utils import log

# ─── The fixed role list ────────────────────────────────────────────────────

SOFTWARE = "Software development"
SUPPORT = "Technical Support"
DEVOPS = "DevOps/Cloud"
QA = "QA/Testing"
BUSINESS_ANALYSIS = "Business Analysis & Low-code (Power Platform)"
MOBILE = "Mobile"
SECURITY = "Security"

ROLE_TYPES: Tuple[str, ...] = (
    SOFTWARE,
    SUPPORT,
    DEVOPS,
    QA,
    BUSINESS_ANALYSIS,
    MOBILE,
    SECURITY,
)
"""The only role types allowed on the sheet and the board (F7, appendix)."""


# ─── Search terms ───────────────────────────────────────────────────────────

class SearchTerm(NamedTuple):
    """One Indeed search phrase, and what to do with what it finds."""

    phrase: str
    role_type: Optional[str]
    """Role type to fall back on when the ad's own words are inconclusive.
    None means 'work it out from the ad' — used for generic IT internships."""
    cadence: str
    """'daily', 'even' or 'odd' — see ``terms_for_today``."""


SEARCH_TERMS: Tuple[SearchTerm, ...] = (
    # ── Software development (core, daily) ──
    SearchTerm("software developer", SOFTWARE, "daily"),
    SearchTerm("junior developer", SOFTWARE, "daily"),
    SearchTerm("software engineer", SOFTWARE, "daily"),
    SearchTerm("full stack developer", SOFTWARE, "daily"),
    SearchTerm("javascript developer", SOFTWARE, "daily"),
    SearchTerm("frontend developer", SOFTWARE, "daily"),
    SearchTerm("backend developer", SOFTWARE, "even"),
    SearchTerm("c# developer", SOFTWARE, "even"),
    SearchTerm(".net developer", SOFTWARE, "odd"),
    SearchTerm("php developer", SOFTWARE, "odd"),
    SearchTerm("python developer", SOFTWARE, "even"),
    SearchTerm("java developer", SOFTWARE, "odd"),
    SearchTerm("react developer", SOFTWARE, "even"),
    SearchTerm("ai developer", SOFTWARE, "odd"),

    # ── Technical Support (core, daily) ──
    SearchTerm("it support", SUPPORT, "daily"),
    SearchTerm("service desk", SUPPORT, "daily"),
    SearchTerm("technical support", SUPPORT, "daily"),
    SearchTerm("desktop support", SUPPORT, "even"),
    SearchTerm("help desk", SUPPORT, "odd"),
    SearchTerm("it technician", SUPPORT, "even"),
    SearchTerm("customer success", SUPPORT, "odd"),

    # ── DevOps / Cloud ──
    SearchTerm("devops engineer", DEVOPS, "even"),
    SearchTerm("cloud engineer", DEVOPS, "even"),
    SearchTerm("azure engineer", DEVOPS, "odd"),
    SearchTerm("aws engineer", DEVOPS, "odd"),

    # ── QA / Testing ──
    SearchTerm("qa engineer", QA, "even"),
    SearchTerm("software tester", QA, "even"),
    SearchTerm("test analyst", QA, "odd"),
    SearchTerm("automation tester", QA, "odd"),

    # ── Business Analysis & Low-code ──
    SearchTerm("business analyst", BUSINESS_ANALYSIS, "even"),
    SearchTerm("systems analyst", BUSINESS_ANALYSIS, "odd"),
    SearchTerm("power platform developer", BUSINESS_ANALYSIS, "even"),
    SearchTerm("dynamics 365", BUSINESS_ANALYSIS, "odd"),
    SearchTerm("sharepoint developer", BUSINESS_ANALYSIS, "odd"),
    SearchTerm("power bi developer", BUSINESS_ANALYSIS, "even"),

    # ── Mobile ──
    SearchTerm("flutter developer", MOBILE, "even"),
    SearchTerm("mobile developer", MOBILE, "even"),
    SearchTerm("android developer", MOBILE, "odd"),
    SearchTerm("ios developer", MOBILE, "odd"),

    # ── Security ──
    SearchTerm("security analyst", SECURITY, "even"),
    SearchTerm("soc analyst", SECURITY, "odd"),
    SearchTerm("cyber security", SECURITY, "even"),
    SearchTerm("information security", SECURITY, "odd"),

    # ── Early-career phrasings (F7) ──
    # These ads rarely say "developer" or "support" in the title, so without
    # their own searches they would never be found at all.
    SearchTerm("software developer internship", SOFTWARE, "daily"),
    SearchTerm("developer learnership", SOFTWARE, "even"),
    SearchTerm("it internship", None, "daily"),
    SearchTerm("it learnership", None, "daily"),
    SearchTerm("graduate programme information technology", None, "daily"),
    SearchTerm("it graduate programme", None, "even"),
    SearchTerm("graduate software engineer", SOFTWARE, "odd"),
    SearchTerm("trainee it", None, "odd"),
)


def terms_for_today(today: Optional[date] = None, spread: bool = True) -> List[SearchTerm]:
    """
    Pick the search terms to run on a given day.

    Args:
        today: Date to schedule for (defaults to today).
        spread: When False, every term runs regardless of cadence.

    Returns:
        The search terms to run.
    """
    if not spread:
        return list(SEARCH_TERMS)

    current = today or date.today()
    wanted = "even" if current.timetuple().tm_yday % 2 == 0 else "odd"
    return [t for t in SEARCH_TERMS if t.cadence in ("daily", wanted)]


def role_for_term(phrase: str) -> Optional[str]:
    """Look up the fallback role type for a search phrase."""
    for term in SEARCH_TERMS:
        if term.phrase == phrase:
            return term.role_type
    return None


# ─── Classification ─────────────────────────────────────────────────────────
# Checked most specific first, so "Software Test Engineer" lands in QA/Testing
# rather than Software development, and "Support Engineer" lands in Technical
# Support. Software development is the catch-all for generic build-things
# wording, so it comes last.

_ROLE_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (SECURITY, re.compile(
        r"\b(cyber\s?security|information security|infosec|security analyst|"
        r"security engineer|security specialist|soc analyst|soc\b|penetration "
        r"test|pen test|vulnerability|threat|siem|security operations)\b", re.I)),

    (QA, re.compile(
        r"\b(qa\b|q\.a\.|quality assurance|software tester|test analyst|"
        r"test engineer|automation tester|test automation|testing analyst|"
        r"quality engineer|sdet)\b", re.I)),

    (MOBILE, re.compile(
        r"\b(flutter|react native|android developer|ios developer|"
        r"mobile developer|mobile engineer|mobile application developer|"
        r"app developer)\b", re.I)),

    (DEVOPS, re.compile(
        r"\b(devops|dev ops|site reliability|sre\b|cloud engineer|"
        r"cloud architect|cloud administrator|platform engineer|"
        r"infrastructure engineer|kubernetes|azure engineer|aws engineer|"
        r"cloud support)\b", re.I)),

    (BUSINESS_ANALYSIS, re.compile(
        r"\b(business analyst|systems analyst|solutions analyst|"
        r"business systems analyst|power platform|power apps|power automate|"
        r"power bi|dynamics 365|d365|sharepoint|business intelligence|"
        r"low.?code|process analyst)\b", re.I)),

    (SUPPORT, re.compile(
        r"\b(it support|service desk|help ?desk|desktop support|"
        r"technical support|support technician|support analyst|"
        r"support engineer|support consultant|incident management|"
        r"customer success|end user support|field technician|it technician|"
        r"application support|first line|second line|1st line|2nd line)\b", re.I)),

    (SOFTWARE, re.compile(
        r"\b(software developer|software engineer|developer|programmer|"
        r"full[\s\-]?stack|front[\s\-]?end|back[\s\-]?end|web developer|"
        r"software development|\.net|c#|java|python|php|javascript|"
        r"typescript|react|angular|vue|node|application developer|"
        r"integration developer|systems developer)\b", re.I)),
)


# ─── Description rules ──────────────────────────────────────────────────────
# A deliberately narrower set, and the reason is a real failure on the live
# board. The rules above are safe on a title, where every word is about the
# vacancy. Run over a job's body text they are not: an "HPE ATP Compute
# Solutions Certified Engineer" -- infrastructure work -- came out as
# Software development because its description mentioned Python somewhere in
# 1500 characters, and graduates filtering by role type were shown it as a
# software job.
#
# So the description may only be matched on phrases that *name a role*. A
# technology is not a role: a job mentioning Python is no more a software
# development job than a job mentioning Excel is an accountancy one. Bare
# "developer" is out for the same reason -- "you will work alongside our
# developers" describes the team, not the vacancy.
#
# Same discipline F2 already applies to levels, where the level word has to
# sit against a role word before it counts.

_DESCRIPTION_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    (SECURITY, re.compile(
        r"\b(cyber\s?security (?:analyst|engineer|specialist)|"
        r"information security (?:analyst|officer|specialist)|"
        r"soc analyst|penetration tester)\b", re.I)),

    (QA, re.compile(
        r"\b(quality assurance (?:engineer|analyst|specialist)|"
        r"software tester|test analyst|test engineer|automation tester|"
        r"sdet)\b", re.I)),

    (MOBILE, re.compile(
        r"\b(mobile (?:developer|engineer)|android developer|ios developer|"
        r"mobile application developer)\b", re.I)),

    (DEVOPS, re.compile(
        r"\b(devops engineer|site reliability engineer|cloud engineer|"
        r"cloud architect|platform engineer|infrastructure engineer)\b", re.I)),

    (BUSINESS_ANALYSIS, re.compile(
        r"\b(business analyst|systems analyst|solutions analyst|"
        r"business systems analyst|business intelligence developer|"
        r"process analyst)\b", re.I)),

    (SUPPORT, re.compile(
        r"\b(it support (?:technician|analyst|engineer|specialist)|"
        r"service desk (?:analyst|engineer|technician)|"
        r"help ?desk (?:analyst|technician)|desktop support technician|"
        r"technical support (?:engineer|analyst|specialist))\b", re.I)),

    (SOFTWARE, re.compile(
        r"\b(software developer|software engineer|"
        r"full[\s\-]?stack (?:developer|engineer)|"
        r"front[\s\-]?end (?:developer|engineer)|"
        r"back[\s\-]?end (?:developer|engineer)|"
        r"web developer|application developer|systems developer|"
        r"integration developer)\b", re.I)),
)


def classify_role(
    title: str,
    description: str = "",
    hint: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Give a job at most one role type from the fixed list.

    The title decides where it can. Failing that the description is checked,
    but only against phrases that name a role (see _DESCRIPTION_RULES). If
    neither says what the job is, the answer is nothing.

    **The search term the job was found by is deliberately not used.** It was,
    once, on the reasoning that a hit from "it internship" is still an IT job
    even when the title only says "2026 Programme". Measured against real
    data that reasoning did not survive: of 284 jobs where this classifier
    disagreed with F1's own screening, 227 -- four fifths -- had been given
    their track by the search term alone. Indeed matches loosely, so a
    "technical support" search returns waiters and warehouse coordinators,
    and this tier was stamping them Technical Support without ever reading
    the job. That is the exact looseness F1 exists to undo.

    The `hint` argument is still accepted so existing callers do not break,
    and is ignored.

    Args:
        title: Job title.
        description: Job description text.
        hint: Ignored. Kept for call compatibility.

    Returns:
        (role_type, source) — role_type is '' when nothing matched, and
        source is one of 'title', 'description' or ''.
    """
    for role, pattern in _ROLE_RULES:
        if title and pattern.search(title):
            return role, "title"

    for role, pattern in _DESCRIPTION_RULES:
        if description and pattern.search(description[:1500]):
            return role, "description"

    return "", ""


# ─── Pipeline step ──────────────────────────────────────────────────────────

def apply_roles(jobs: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Give every job exactly one role type from the fixed list (F7).

    Sets on each job:
        role_type    — one of ROLE_TYPES, or '' when undecidable
        role_source  — title | description | ''

    A job whose title and description both say nothing gets no track at all,
    and shows under no role-type filter on the board. That is the intended
    outcome: a blank is honest, a wrong track is not, and the board's filter
    is the one place a wrong label directly costs a graduate a job they were
    looking for.

    Deliberately does not touch 'primary_role'. That field is the AI's own
    label, and F1's screening still reads it to decide keep or drop. Role
    classification is meant to sit alongside it for a while so the two can
    be compared on real jobs -- the same way F2 kept the AI's level label
    as 'ai_job_level' before anyone decided whether to trust the rules over
    it. Overwriting 'primary_role' here would change what F1 sees without
    that comparison ever having happened.

    Args:
        jobs: Job dictionaries, after AI enrichment.

    Returns:
        The same job dictionaries, with a role type.
    """
    for job in jobs:
        # No hint is passed any more. The search term that found a job says
        # nothing about what the job is -- see classify_role for the numbers
        # that settled that.
        role, source = classify_role(
            job.get("title", ""),
            job.get("description_snippet", ""),
        )
        job["role_type"] = role
        job["role_source"] = source

    return list(jobs)


def role_counts(jobs: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    """Count jobs per role type, for the run log."""
    counts: Dict[str, int] = {}
    for job in jobs:
        role = job.get("role_type") or "(none)"
        counts[role] = counts.get(role, 0) + 1
    return counts


def fill_rate(jobs: Sequence[Dict[str, Any]]) -> Tuple[int, int, float]:
    """
    Work out how many jobs got a role type at all.

    Args:
        jobs: Job dictionaries, after ``apply_roles``.

    Returns:
        A (classified, total, percentage) tuple.
    """
    total = len(jobs)
    classified = sum(1 for job in jobs if job.get("role_type"))
    return classified, total, (classified / total * 100) if total else 0.0


def log_roles(jobs: Sequence[Dict[str, Any]]) -> None:
    """
    Print the role breakdown for the run log (F7).

    Includes the AI's own role label alongside the rules' role type, so the
    two can be watched together on real jobs before anyone decides whether
    the rules are solid enough to replace what F1 currently reads.

    Args:
        jobs: Job dictionaries, after ``apply_roles``.
    """
    classified, total, percentage = fill_rate(jobs)
    log(f"  role type assigned: {classified} of {total} = {percentage:.0f}%")

    counts = role_counts(jobs)
    for role in ROLE_TYPES:
        if counts.get(role):
            log(f"    {role}: {counts[role]}")
    if counts.get("(none)"):
        log(f"    (none): {counts['(none)']}")

    by_source: Dict[str, int] = {}
    for job in jobs:
        source = job.get("role_source") or "none"
        by_source[source] = by_source.get(source, 0) + 1
    breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(by_source.items()))
    log(f"  role source — {breakdown}")

    disagreements = sum(
        1 for job in jobs
        if job.get("role_type") and not job.get("primary_role")
    )
    if disagreements:
        log(f"  {disagreements} jobs got a role type but the AI gave no "
            f"role label at all -- worth a look before trusting either on its own")
