"""
screening.py — keep or drop, with a reason for every drop (F1, F4)
===================================================================

Three screens run here, back to back, and none of them deletes anything. A
dropped job keeps its full record and goes to the Exclude tab with the reason
written next to it, so the drops can be reviewed and later used to train a
better filter.

F1 — only tech jobs
-------------------
Indeed matches the words "engineer" and "developer" very loosely, which is how
mining engineers, quantity surveyors and warehouse assistants ended up in the
sheet. Nothing threw the wrong jobs out.

Scope — the tracks this course leads to
---------------------------------------
CodeSpace teaches people to build software. Core is software development and
mobile; adjacent, and also published, are data & BI, QA and low-code, because
a graduate who can write SQL and Python plausibly takes one of those first.
Out are technical support, security and DevOps -- all genuinely technical,
none of them where this course leads. A service desk leads to infrastructure,
not development.

Note what this is *not*: it is not a judgement that those tracks are worthless,
and the pipeline still scrapes, enriches and classifies them. They are filed in
the Exclude tab under this stage, so widening the scope later is a name added
to ``PUBLISHED_ROLE_TYPES`` and a re-run, not a rebuild.

F4 — apply, stretch, or out of reach
------------------------------------
Three outcomes, not two, because for a large middle group the honest answer is
"worth a shot":

    apply    entry level or junior, asking two years or fewer
    stretch  mid asking three years or fewer, or no level established at all
    neither  four or more years, or senior/lead/principal in any form

The stretch tier is the whole point of the redesign. Under a two-way rule the
board dropped 31 software jobs whose ads simply never mentioned a level --
*Full Stack Developer*, *Software Engineer – GoLang* -- thrown out for lack of
proof rather than for evidence against. It also dropped 28 asking for exactly
three years, when a developer two years in reads that line, checks the
requirements underneath, meets them, and applies anyway.

The gate that does not move is seniority. Senior, lead and principal never
reach the board, and neither does an ad asking four or more years.

F1 runs first, then scope, then F4. When a job fails several screens the
earliest reason is the one recorded: a Senior Quantity Surveyor belongs in the
Exclude tab as a surveyor, not as a senior.

The F1 decision, in order
-------------------------
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

Reviewing the drops
-------------------
F4 removes jobs on the strength of the F2 label, so a wrong label silently
costs a graduate a job. Most drops rest on the title or on a number the ad
states outright, but two paths are softer -- a level read from a phrase in the
body text, and a years figure that came from a feed rather than the ad. Those
are flagged ``needs_review`` so the weekly QA pass can check them:

    python -m src.pipeline.qa -i data/cache/excluded_jobs.json

Usage
-----
    from src.pipeline import screening

    kept, excluded, counts = screening.screen_jobs(all_jobs)
    screening.log_screening(counts, excluded)
"""

import re
from typing import Any, Dict, List, Sequence, Tuple

from src.pipeline.levels import ENTRY, JUNIOR, MID, UNKNOWN
from src.pipeline.roles import BUSINESS_ANALYSIS, DATA, MOBILE, QA, SOFTWARE
from src.utils import log


# ─── Constants ──────────────────────────────────────────────────────────────

STAGE_NON_TECH = "F1 non-tech"
"""Label written to the Exclude tab's Stage column by the F1 screen."""

STAGE_OFF_TRACK = "scope off track"
"""Label written to the Exclude tab's Stage column by the scope screen."""

STAGE_ABOVE_COHORT = "F4 above cohort"
"""Label written to the Exclude tab's Stage column by the F4 screen."""

MAX_YEARS_FOR_COHORT = 4
"""An ad asking for this many years or more is above our graduates (F4)."""

MAX_YEARS_FOR_APPLY = 2
"""Above this, an ad is a stretch rather than a straightforward apply."""

TIER_APPLY = "apply"
"""Clearly in reach: the ad's own words put it at a graduate's level."""

TIER_STRETCH = "stretch"
"""
Worth a shot: right kind of work, and the ad either reaches slightly past a
graduate or says nothing at all about level.

This tier exists because the alternative was throwing those jobs away. A
developer two years in reads "3+ years required", checks the requirements
listed underneath, meets them, and applies -- employers write the years line
as a filter and then hire on the requirements. And a job that simply does
not state a level is the single most common case in the data; silence is
not evidence that a job is out of reach.
"""

PUBLISHED_ROLE_TYPES = frozenset({SOFTWARE, MOBILE, QA, BUSINESS_ANALYSIS, DATA})
"""
The tracks that reach the sheet and the board.

Core is software and mobile -- what CodeSpace teaches. The other three are
adjacent: jobs a graduate who can build things plausibly takes first, on a
different set of tools. Data & BI is in for exactly that reason, and its
absence from the role taxonomy is why *Junior Data Analyst* used to come out
of F7 with no track at all.

Deliberately out: technical support, security, DevOps/cloud. All genuinely
technical, none of them the work this course leads to -- a service desk
leads to infrastructure, not development. They are still scraped, enriched
and classified, and filed on the Exclude tab under this stage, so widening
the scope is a name in this set and a re-run.
"""

PUBLISHED_LEVELS = frozenset({ENTRY, JUNIOR, MID, UNKNOWN})
"""
The levels that can reach the board at all, in one tier or another.

Not a statement that a mid-level job is a graduate job -- ``tier_for``
decides that, and lands most of them in stretch. This set is the outer
boundary: senior, lead and principal never appear on the board whatever
else an ad says.
"""

_SENIOR_TITLE = re.compile(
    r"\b(senior|snr\.?|sr\.?|lead|principal|head of|chief|"
    r"manager|architect)\b", re.I)
"""
Title words that put a job above a graduate whatever the level field says.

Deliberately redundant with F2, which already reads these off the title and
would normally have set the level to senior or lead. It is here because F2's
rules are allowed to change, and a change there must not be able to quietly
promote a Senior Developer into the stretch tier. A gate the spec names
explicitly gets its own check.
"""

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
    r"gtm", r"go[\s\-]?to[\s\-]?market",
    # Insurance and finance work that reads as analysis but is not tech.
    # The role is named rather than the field, on purpose: an "Actuarial
    # Systems Developer" is a real software job at an insurer and has to
    # survive, so bare "actuarial" is deliberately not blocked.
    r"actuarial (?:analyst|specialist|associate|consultant)",
    # Consumer goods, not software. A bare "product developer" in South
    # Africa is almost always someone developing a physical product --
    # electronics, food, packaging. The tech-qualified forms are real
    # software jobs though, so they are excluded by name, the same way the
    # accept list refuses a bare "engineer" but takes "software engineer".
    r"(?<!software )(?<!digital )(?<!technical )product developer",
    # Facilities
    r"cleaner", r"security guard", r"security officer", r"safety officer",
    r"sheq", r"hse", r"occupational health",
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


# ─── Scope: software development only ───────────────────────────────────────

def screen_off_track(job: Dict[str, Any]) -> Tuple[bool, str, bool]:
    """
    Decide whether a job is on a track CodeSpace actually teaches.

    Reads the role type F7 worked out from the job's own title or body text.
    The search term that found the job is deliberately not consulted -- see
    ``roles.classify_role`` for the measurement that settled that.

    Args:
        job: Job dictionary, already classified by F7.

    Returns:
        A (keep, reason, needs_review) tuple. A job with no role type at all
        is flagged for review: unclassified is not the same as off-track, and
        how often it happens is worth watching.
    """
    role = job.get("role_type") or ""

    if role in PUBLISHED_ROLE_TYPES:
        return True, "", False

    if not role:
        return False, "no role type -- title and description named no role", True

    source = job.get("role_source") or "unknown"
    return False, f"role type is {role}, off track (from {source})", False


# ─── F4: apply, stretch, or out of reach ────────────────────────────────────

def _stated_years(job: Dict[str, Any]) -> Any:
    """The years figure, or None. Guards against a bool sneaking in as 0/1."""
    years = job.get("experience_years")
    if isinstance(years, int) and not isinstance(years, bool):
        return years
    return None


def screen_above_cohort(job: Dict[str, Any]) -> Tuple[bool, str, bool]:
    """
    Sort a job into apply, stretch, or out of reach (F4).

    Three outcomes rather than two, because for a large middle group the
    honest answer is "worth a shot" -- see ``TIER_APPLY`` and ``TIER_STRETCH``
    for why that group exists at all.

        apply    entry level or junior, asking two years or fewer
        stretch  mid asking three years or fewer, or no level established
        neither  four or more years, or senior/lead/principal in any form

    Args:
        job: Job dictionary, already leveled by F2 and dated by F3.

    Returns:
        A (tier, reason, needs_review) tuple. tier is '' when the job is out
        of reach, and reason then says why. needs_review marks a decision
        resting on softer evidence, for the weekly QA pass -- on a drop it
        means "we may have thrown away a good job", and on a stretch it means
        "we put this in front of somebody without being sure".
    """
    level = job.get("job_level") or UNKNOWN
    years = _stated_years(job)

    # ── Out of reach: the ad asks for more years than a graduate has ──
    if years is not None and years >= MAX_YEARS_FOR_COHORT:
        source = job.get("years_source") or "unknown"
        evidence = job.get("years_evidence") or f"{years} years"
        # A number the ad states outright is stronger than one a feed handed
        # over, which we cannot trace back to any wording.
        weak = source != "text"
        return "", f"asks for {years}+ years (from {source}: '{evidence}')", weak

    # ── Out of reach: seniority, from the level or from the title ──
    if level not in PUBLISHED_LEVELS:
        source = job.get("level_source") or "unknown"
        evidence = job.get("level_evidence") or "nothing recorded"
        weak = source == "description"
        return "", f"level is {level} (from {source}: '{evidence}')", weak

    senior_word = _SENIOR_TITLE.search(job.get("title") or "")
    if senior_word:
        return "", f"title says '{senior_word.group(0)}'", False

    # ── In reach ──
    if level in (ENTRY, JUNIOR):
        if years is None or years <= MAX_YEARS_FOR_APPLY:
            return TIER_APPLY, "", False
        # Says junior, asks three years. Both are true; the ad is a stretch.
        return TIER_STRETCH, f"{level} but asks {years} years", False

    if level == MID:
        return TIER_STRETCH, f"mid level, asks {years if years is not None else 'no'} years", False

    # Level could not be established. Nothing was wrong with the ad and
    # nothing is wrong with the job -- we simply cannot tell, and the board
    # should say so rather than either hide it or claim it is entry level.
    return TIER_STRETCH, "level could not be established", True


# ─── All three screens ──────────────────────────────────────────────────────

def screen_jobs(
    jobs: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """
    Split a day's jobs into the ones we keep and the ones we exclude.

    Runs F1, then scope, then F4, and a job that fails one never reaches the
    next -- so each job is filed under the first reason that disqualified it,
    which is the one that actually matters. A Senior QA Engineer is filed as
    off-track rather than as senior, because widening the scope is a decision
    somebody might make and being senior is not.

    Every kept job carries:
        tier        -- 'apply' or 'stretch' (see TIER_APPLY / TIER_STRETCH)
        tier_reason -- why it is a stretch rather than an apply ('' for apply)

    Excluded jobs are returned, never discarded, and each one carries:
        excluded_stage  -- which screen dropped it
        excluded_reason -- why, in words
        excluded_rule   -- which rule fired, for the run log
        needs_review    -- True when the drop rests on softer evidence

    Args:
        jobs: Job dictionaries, after scraping, enrichment, F2 and F3.

    Returns:
        A (kept, excluded, counts) tuple. counts summarises the run and
        always satisfies: kept + dropped == input.
    """
    kept: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    counts: Dict[str, int] = {
        "input": len(jobs),
        "kept": 0,
        "kept_apply": 0,
        "kept_stretch": 0,
        "dropped_title_blocklist": 0,
        "dropped_role_not_accepted": 0,
        "dropped_off_track": 0,
        "dropped_above_cohort": 0,
        "dropped_total": 0,
        "needs_review": 0,
    }

    for job in jobs:
        # ── F1: is this a tech job at all? ──
        keep, reason, kept_by = screen_non_tech(job)
        if not keep:
            _record_drop(job, excluded, counts, STAGE_NON_TECH, reason, kept_by, False)
            continue

        # ── Scope: is it a track we publish? ──
        keep, reason, needs_review = screen_off_track(job)
        if not keep:
            _record_drop(
                job, excluded, counts,
                STAGE_OFF_TRACK, reason, "off_track", needs_review,
            )
            continue

        # ── F4: apply, stretch, or out of reach? ──
        tier, reason, needs_review = screen_above_cohort(job)
        if not tier:
            _record_drop(
                job, excluded, counts,
                STAGE_ABOVE_COHORT, reason, "above_cohort", needs_review,
            )
            continue

        job["tier"] = tier
        job["tier_reason"] = reason
        job["excluded_stage"] = ""
        job["excluded_reason"] = ""
        job["excluded_rule"] = kept_by
        job["needs_review"] = needs_review
        kept.append(job)
        counts["kept"] += 1
        counts["kept_apply" if tier == TIER_APPLY else "kept_stretch"] += 1
        counts["needs_review"] += int(needs_review)

    return kept, excluded, counts


def _record_drop(
    job: Dict[str, Any],
    excluded: List[Dict[str, Any]],
    counts: Dict[str, int],
    stage: str,
    reason: str,
    rule: str,
    needs_review: bool,
) -> None:
    """
    Mark a job as dropped and file it, so no drop is ever silent.

    Args:
        job: The job being dropped.
        excluded: The list collecting dropped jobs.
        counts: The running summary, updated in place.
        stage: Which screen dropped it.
        reason: Why, in words.
        rule: Which rule fired, for the run log.
        needs_review: True when the drop rests on softer evidence.
    """
    job["excluded_stage"] = stage
    job["excluded_reason"] = reason
    job["excluded_rule"] = rule
    job["needs_review"] = needs_review

    excluded.append(job)
    counts[f"dropped_{rule}"] = counts.get(f"dropped_{rule}", 0) + 1
    counts["dropped_total"] += 1
    counts["needs_review"] += int(needs_review)


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
    log(f"    of the kept: {counts.get('kept_apply', 0)} apply, "
        f"{counts.get('kept_stretch', 0)} stretch")
    log(f"    F1 dropped on title blocklist:   "
        f"{counts.get('dropped_title_blocklist', 0)}")
    log(f"    F1 dropped on role not accepted: "
        f"{counts.get('dropped_role_not_accepted', 0)}")
    log(f"    dropped as not software:         "
        f"{counts.get('dropped_off_track', 0)}")
    log(f"    F4 dropped as above the cohort:  "
        f"{counts.get('dropped_above_cohort', 0)}")
    log(f"    flagged for QA review:           {counts.get('needs_review', 0)}")

    if not excluded:
        return

    log(f"  sample of dropped jobs (first {min(SAMPLE_SIZE, len(excluded))}):")
    for job in excluded[:SAMPLE_SIZE]:
        title = (job.get("title", "") or "(no title)")[:45]
        flag = " [REVIEW]" if job.get("needs_review") else ""
        log(f"    - {title} | {job.get('excluded_stage', '')}{flag} | "
            f"{job.get('excluded_reason', '')}")
