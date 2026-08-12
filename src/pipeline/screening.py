"""
screening.py — keep or drop, with a reason for every drop (F1)
===============================================================

The problem
-----------
Indeed matches the words "engineer" and "developer" very loosely, which is how
mining engineers, quantity surveyors and warehouse assistants ended up in the
sheet. Nothing threw the wrong jobs out.

What this does
--------------
Runs one keep-or-drop decision over every job before it reaches the sheet.
Nothing is deleted: a dropped job keeps its full record and goes to the
Exclude tab with the reason written next to it, so the drops can be reviewed
and later used to train a better filter.

The decision, in order
----------------------
1. The title carries a word that means "not our kind of job" -> drop.
2. The AI's role label matches the accept-list -> keep.
3. The role label is missing or unrecognised, but the title itself reads as a
   tech role -> keep.
4. Otherwise -> drop, recording what the role label said.

Why step 3 exists
-----------------
Enrichment can be skipped or can fail (no API key, a bad batch, a spending
cap). Without the title fallback, one bad AI day would silently divert an
entire run into the Exclude tab. The title check keeps the sheet fed when the
AI is unavailable.

Why the blocklist is phrased as role words
------------------------------------------
The blocklist names roles, not industries. Application support at a mining
house is still a tech job, so "mining engineer" is blocked while "mining"
alone is not. Word boundaries matter for the same reason: the rule that drops
sales representatives must not drop a Salesforce developer.

Usage
-----
    from src.pipeline import screening

    kept, excluded, counts = screening.screen_jobs(all_jobs)
    screening.log_screening(counts, excluded)
"""

import re
from typing import Any, Dict, List, Sequence, Tuple

from src.utils import log


# ─── Constants ──────────────────────────────────────────────────────────────

STAGE_NON_TECH = "F1 non-tech"
"""Label written to the Exclude tab's Stage column by this screen."""

SAMPLE_SIZE = 10
"""How many dropped titles to print in the run log, so precision is checkable."""


# ─── Accept-list ────────────────────────────────────────────────────────────
# Tech role labels we keep. Each entry is (rule_name, pattern); the rule name
# is recorded on the job so the run log can show which rule kept it.
#
# Note that a bare "engineer" is deliberately NOT accepted -- that is the exact
# looseness that let mining and civil engineers through. A tech qualifier must
# sit in front of it.

_ACCEPTED_ROLE_RULES: Tuple[Tuple[str, str], ...] = (
    ("developer", r"developer|programmer|software development|software dev"),
    ("tech_engineer",
     r"(?:software|backend|back[\s\-]?end|frontend|front[\s\-]?end|"
     r"full[\s\-]?stack|web|mobile|application|apps?|data|devops|dev ops|"
     r"cloud|platform|infrastructure|site reliability|qa|quality|test|"
     r"automation|security|network|systems?|solutions?|integration|"
     r"machine learning|ai|firmware|embedded)[\s\-/]*engineer"),
    ("tech_analyst",
     r"(?:business|systems?|solutions?|data|test|qa|quality|security|soc|"
     r"information security|cyber|bi|business intelligence)[\s\-/]*analyst"),
    ("support",
     r"it support|technical support|service desk|help ?desk|desktop support|"
     r"application support|end user support|incident management|"
     r"customer success|support (?:technician|analyst|engineer|specialist|"
     r"consultant|agent)"),
    ("qa_testing",
     r"qa\b|quality assurance|software tester|tester|test analyst|"
     r"test automation|sdet"),
    ("cloud_devops",
     r"devops|dev ops|sre\b|site reliability|kubernetes|platform engineer|"
     r"cloud (?:engineer|architect|administrator|specialist|support)"),
    ("data", r"data (?:scientist|engineer|analyst)|machine learning|ml engineer"),
    ("tech_admin",
     r"(?:systems?|network|database|linux|windows|server|cloud)[\s\-]*"
     r"(?:administrator|admin)|dba\b|sysadmin"),
    ("tech_architect",
     r"(?:software|solutions?|technical|cloud|data|systems?|enterprise|"
     r"application|security)[\s\-]*architect"),
    ("low_code",
     r"power (?:platform|apps|automate|bi)|dynamics 365|d365|sharepoint|"
     r"low[\s\-]?code"),
    ("security",
     r"cyber ?security|information security|infosec|soc analyst|"
     r"penetration test\w*|ethical hack\w*|"
     r"security (?:analyst|engineer|specialist|consultant|administrator)"),
    ("mobile",
     r"(?:mobile|android|ios|flutter|react native)[\s\-]*"
     r"(?:developer|engineer|programmer)"),
    ("it_generic",
     r"it (?:technician|specialist|consultant|intern|graduate|professional)|"
     r"information technology"),
)

_ACCEPTED_COMPILED: Tuple[Tuple[str, "re.Pattern[str]"], ...] = tuple(
    (name, re.compile(rf"\b(?:{pattern})", re.IGNORECASE))
    for name, pattern in _ACCEPTED_ROLE_RULES
)


# ─── Blocklist ──────────────────────────────────────────────────────────────
# Title words that mean "drop this". Phrased as role words rather than
# industry words, and matched on word boundaries, so that:
#   - "Mining Engineer" drops, but "Application Support (Mining)" survives
#   - "Sales Representative" drops, but "Salesforce Developer" survives

_TITLE_BLOCKLIST: Tuple[str, ...] = (
    # Engineering disciplines that are not software
    r"mining engineer", r"civil engineer", r"structural engineer",
    r"mechanical engineer", r"electrical engineer", r"chemical engineer",
    r"industrial engineer", r"mechatronic\w* engineer", r"process engineer",
    r"production engineer", r"maintenance engineer", r"site engineer",
    r"metallurg\w+", r"geolog\w+", r"agronom\w+",
    # Built environment
    r"quantity surveyor", r"land surveyor", r"building surveyor", r"surveyor",
    r"draughts\w+", r"estimator", r"foreman", r"site agent",
    r"construction manager", r"architectural technologist",
    # Trades and plant
    r"boilermaker", r"millwright", r"welder", r"fitter and turner",
    r"diesel mechanic", r"panel beater", r"plumber", r"electrician",
    r"artisan", r"rigger", r"machine operator",
    # Warehouse, transport, retail
    r"warehouse", r"storeman", r"store man", r"picker packer", r"forklift",
    r"truck driver", r"delivery driver", r"courier", r"merchandiser",
    r"cashier", r"retail assistant", r"shop assistant", r"promoter",
    # Health, care, education, hospitality
    r"nurse", r"pharmacist", r"caregiver", r"paramedic",
    r"teacher", r"chef", r"waiter", r"waitress", r"barista",
    # Office functions that are not tech
    r"sales", r"telesales", r"business development", r"debt collector",
    r"call cent\w+ agent", r"contact cent\w+ agent",
    r"accountant", r"bookkeep\w+", r"payroll", r"credit controller",
    r"human resources", r"recruitment consultant", r"talent acquisition",
    r"marketing", r"copywriter", r"social media",
    r"receptionist", r"personal assistant", r"admin clerk", r"data captur\w+",
    # Facilities
    r"cleaner", r"security guard", r"security officer", r"safety officer",
    r"sheq", r"occupational health",
)

_BLOCKLIST_COMPILED = re.compile(
    r"\b(?:" + "|".join(_TITLE_BLOCKLIST) + r")\b", re.IGNORECASE
)


# ─── Helper Functions ───────────────────────────────────────────────────────

def match_accepted_role(text: str) -> str:
    """
    Check a role label or job title against the accept-list.

    Args:
        text: A role label (e.g. "Backend Engineer") or a job title.

    Returns:
        The name of the rule that matched (e.g. "tech_engineer"), or an
        empty string if nothing matched.

    Examples:
        >>> match_accepted_role("Backend Engineer")
        'tech_engineer'
        >>> match_accepted_role("Mining Engineer")
        ''
    """
    if not text:
        return ""

    for name, pattern in _ACCEPTED_COMPILED:
        if pattern.search(text):
            return name

    return ""


def match_blocked_title(title: str) -> str:
    """
    Check a job title against the blocklist of non-tech role words.

    Args:
        title: Job title.

    Returns:
        The blocked word that matched (e.g. "quantity surveyor"), or an
        empty string if the title is clean.

    Examples:
        >>> match_blocked_title("Quantity Surveyor")
        'Quantity Surveyor'
        >>> match_blocked_title("Salesforce Developer")
        ''
    """
    if not title:
        return ""

    found = _BLOCKLIST_COMPILED.search(title)
    return found.group(0) if found else ""


# ─── The Screen ─────────────────────────────────────────────────────────────

def screen_non_tech(job: Dict[str, Any]) -> Tuple[bool, str, str]:
    """
    Decide whether a single job is a tech job at all (F1).

    Args:
        job: Job dictionary. Reads 'title' and 'primary_role'.

    Returns:
        A (keep, reason, rule) tuple:
            keep   -- True to send to the Jobs tab, False for the Exclude tab
            reason -- why it was dropped, in words ('' when kept)
            rule   -- which rule decided, for the run log
    """
    title = job.get("title", "") or ""
    role_label = job.get("primary_role", "") or ""

    # 1. A title word that means "not our kind of job".
    blocked = match_blocked_title(title)
    if blocked:
        return False, f"title matches excluded role word: '{blocked}'", "title_blocklist"

    # 2. The AI's role label is one we accept.
    rule = match_accepted_role(role_label)
    if rule:
        return True, "", f"role_label:{rule}"

    # 3. No usable role label, but the title itself reads as a tech role.
    #    This is what keeps the sheet fed when enrichment is skipped or fails.
    rule = match_accepted_role(title)
    if rule:
        return True, "", f"title:{rule}"

    # 4. Nothing says this is a tech job.
    said = f"role label was '{role_label}'" if role_label else "no role label"
    return False, f"role type not accepted ({said})", "role_not_accepted"


def screen_jobs(
    jobs: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Split a day's jobs into the ones we keep and the ones we exclude (F1).

    Excluded jobs are returned, never discarded, and each one carries:
        excluded_stage  -- which screen dropped it
        excluded_reason -- why, in words
        excluded_rule   -- which rule fired, for the run log

    Args:
        jobs: Job dictionaries, after scraping and enrichment.

    Returns:
        A (kept, excluded, counts) tuple. counts summarises the run and
        always satisfies: kept + dropped == input.
    """
    kept: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    counts: Dict[str, int] = {
        "input": len(jobs),
        "kept": 0,
        "dropped_title_blocklist": 0,
        "dropped_role_not_accepted": 0,
        "dropped_total": 0,
    }

    for job in jobs:
        keep, reason, rule = screen_non_tech(job)

        if keep:
            job["excluded_stage"] = ""
            job["excluded_reason"] = ""
            job["excluded_rule"] = rule
            kept.append(job)
            counts["kept"] += 1
            continue

        job["excluded_stage"] = STAGE_NON_TECH
        job["excluded_reason"] = reason
        job["excluded_rule"] = rule
        excluded.append(job)
        counts[f"dropped_{rule}"] = counts.get(f"dropped_{rule}", 0) + 1
        counts["dropped_total"] += 1

    return kept, excluded, counts


# ─── Run Log ────────────────────────────────────────────────────────────────

def log_screening(
    counts: Dict[str, int],
    excluded: Sequence[Dict[str, Any]],
) -> None:
    """
    Print the screening summary, so nothing disappears silently (F1).

    Prints the totals per rule and a sample of the dropped titles, so the
    quality of the filter can be judged from the log alone without opening
    the sheet.

    Args:
        counts: The counts dictionary returned by ``screen_jobs``.
        excluded: The excluded jobs, used for the sample.
    """
    log(f"  screened {counts['input']} jobs "
        f"-> kept {counts['kept']}, dropped {counts['dropped_total']}")
    log(f"    dropped on title blocklist:  {counts.get('dropped_title_blocklist', 0)}")
    log(f"    dropped on role not accepted: {counts.get('dropped_role_not_accepted', 0)}")

    if not excluded:
        return

    log(f"  sample of dropped jobs (first {min(SAMPLE_SIZE, len(excluded))}):")
    for job in excluded[:SAMPLE_SIZE]:
        title = (job.get("title", "") or "(no title)")[:55]
        log(f"    - {title} | {job.get('excluded_reason', '')}")