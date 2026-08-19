"""
decision_check.py — evidence for the two decisions we parked
=============================================================

The problem
-----------
Two decisions were deliberately left open, both waiting on real data rather
than on an argument:

1. **F1 still screens on the AI's role label, not on F7's `role_type`.**
   F7 built a rules-based classifier and then refused to wire it into F1 on
   the same day it shipped, because the only evidence was made-up titles.
   The plan was to let the two sit side by side on real jobs first.

2. **Nothing skips AI enrichment yet.** F5 built a free keyword matcher and
   recorded `needs_ai_skills` next to every job, but deliberately did not
   act on it -- the saving was a guess until there were real days to count.

Both are now answerable from a run's own artifact. This script counts, and
prints what it counted. It does not decide anything.

What it cannot tell you
-----------------------
Whether a disagreement is F1 being wrong or the classifier being wrong. It
can only find the jobs the two disagree about and put their titles in front
of you. Reading twenty of those is the actual evidence; the counts just say
whether it is worth reading them.

Nothing here talks to Google Sheets or GitHub. It reads files, so it is safe
to run as often as you like and it works offline.

Usage
-----
    # after unzipping the artifact over data/cache/
    python -m scripts.decision_check

    # or point it somewhere else
    python -m scripts.decision_check -d ~/Downloads/job-data-133

    # show more of the disagreeing titles
    python -m scripts.decision_check --sample 30
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_DIR = Path("data/cache")

LEVELED = "combined_jobs_leveled.json"
EXCLUDED = "excluded_jobs.json"

STAGE_NON_TECH = "F1 non-tech"
"""The Stage value F1's own screen writes. Must match screening.py."""

DEFAULT_SAMPLE = 15

LINE = "=" * 68
RULE = "─" * 68


# ─── Reading ────────────────────────────────────────────────────────────────

def load_jobs(path: Path) -> Optional[List[Dict[str, Any]]]:
    """
    Load a run's saved job file.

    Args:
        path: Path to the JSON file.

    Returns:
        The job list, or None when the file is missing or unreadable. None
        and an empty list mean different things here -- a run with nothing
        excluded is not the same as an artifact that was never unzipped.
    """
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if isinstance(raw, dict):
        return raw.get("jobs", [])
    if isinstance(raw, list):
        return raw
    return None


def job_key(job: Dict[str, Any]) -> str:
    """
    A stable identity for matching a job across two files.

    The web address is what the pipeline itself dedupes on, so it is what
    lines up between the leveled file and the excluded file. Jobs without
    one fall back to title + company, which is weaker but better than
    dropping them from the comparison silently.
    """
    url = str(job.get("job_url", "") or "").strip()
    if url:
        return url
    return f"{job.get('title', '')}|{job.get('company', '')}".strip().lower()


# ─── Question 1: F1's label against F7's classifier ─────────────────────────

def compare_f1_against_role_type(
    leveled: List[Dict[str, Any]],
    excluded: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Put F1's keep-or-drop next to what F7's classifier would have said.

    F1 decides on the AI's `primary_role`. F7's `role_type` is decided by
    rules and is currently only recorded, never acted on. Where the two
    agree there is nothing to discuss. Where they disagree, one of them is
    costing somebody something -- a job dropped that a graduate could have
    had, or a non-tech job left on the board.

    Args:
        leveled: Every job in the run, after Phase 2.4 and before screening.
        excluded: The jobs the screens dropped, carrying `excluded_stage`.

    Returns:
        The four buckets, plus the jobs behind the two that disagree.
    """
    # Keep the whole excluded record, not just the key. The rule that fired
    # is written on the excluded copy of a job, never on the leveled one --
    # screening runs after Phase 2.4 saved that file -- so the reason has to
    # be carried across or every sample row prints "unknown".
    f1_dropped: Dict[str, Dict[str, Any]] = {
        job_key(job): job
        for job in excluded
        if job.get("excluded_stage") == STAGE_NON_TECH
    }

    kept_with_track: List[Dict[str, Any]] = []
    kept_no_track: List[Dict[str, Any]] = []
    dropped_with_track: List[Dict[str, Any]] = []
    dropped_no_track: List[Dict[str, Any]] = []

    for job in leveled:
        drop_record = f1_dropped.get(job_key(job))
        has_track = bool(job.get("role_type"))

        if drop_record is not None and has_track:
            # Copy so the sample can print both halves -- the rules' verdict
            # from the leveled job, the drop reason from the excluded one.
            merged = dict(job)
            merged["excluded_rule"] = drop_record.get("excluded_rule", "")
            merged["excluded_reason"] = drop_record.get("excluded_reason", "")
            dropped_with_track.append(merged)
        elif drop_record is not None:
            dropped_no_track.append(job)
        elif has_track:
            kept_with_track.append(job)
        else:
            kept_no_track.append(job)

    return {
        "kept_with_track": kept_with_track,
        "kept_no_track": kept_no_track,
        "dropped_with_track": dropped_with_track,
        "dropped_no_track": dropped_no_track,
        "matched": len(f1_dropped),
    }


def excluded_rule_of(job: Dict[str, Any]) -> str:
    """Which F1 rule dropped this job, as a readable label."""
    rule = job.get("excluded_rule", "") or ""
    if rule == "title_blocklist":
        return "title blocklist"
    if rule == "role_not_accepted":
        return "role not accepted"
    return rule or "unknown"


# ─── Question 2: how much enrichment could be skipped ───────────────────────

def measure_enrichment_headroom(leveled: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Count how many jobs the free keyword matcher already covered.

    F5 marks a job `needs_ai_skills` when its keyword match found fewer than
    three skills. The jobs where that is False are the ones enrichment could
    have been skipped for, as far as *skills* go.

    That last clause is the whole catch, and it is why this returns counts
    rather than a recommendation: enrichment does not only fill skills. It
    writes the blurb the board shows and the `primary_role` F1 currently
    screens on, so skipping it is not free unless those are covered too.

    Args:
        leveled: Every job in the run, after Phase 2.4.

    Returns:
        The counts, and how many of the skippable jobs would lose something
        other than skills by being skipped.
    """
    sources = Counter(job.get("skills_source") or "none" for job in leveled)

    could_skip = [job for job in leveled if job.get("needs_ai_skills") is False]
    marked = sum(1 for job in leveled if "needs_ai_skills" in job)

    # Of the jobs that could skip on skills alone, how many currently rely on
    # enrichment for something else? These are what a naive skip would break.
    skip_loses_blurb = sum(1 for job in could_skip if job.get("blurb"))
    skip_loses_role = sum(1 for job in could_skip if job.get("primary_role"))

    return {
        "sources": sources,
        "could_skip": len(could_skip),
        "marked": marked,
        "skip_loses_blurb": skip_loses_blurb,
        "skip_loses_role": skip_loses_role,
    }


# ─── Printing ───────────────────────────────────────────────────────────────

def pct(part: int, whole: int) -> str:
    """Format a share, without dividing by zero."""
    if whole <= 0:
        return "  n/a"
    return f"{100 * part / whole:4.0f}%"


def print_sample(jobs: List[Dict[str, Any]], limit: int, show_rule: bool) -> None:
    """Print a readable sample of jobs, newest concern first."""
    for job in jobs[:limit]:
        title = str(job.get("title", "") or "(no title)")[:56]
        track = job.get("role_type", "") or "-"
        print(f"    - {title}")
        if show_rule:
            said = job.get("primary_role", "") or "(no AI label)"
            source = job.get("role_source", "") or "?"
            print(f"        F1 dropped it: {excluded_rule_of(job)}, "
                  f"AI said '{said}'")
            print(f"        rules say:     {track}  (from the {source})")
        else:
            said = job.get("primary_role", "") or "(no AI label)"
            print(f"        AI said '{said}', rules could not place it")

    if len(jobs) > limit:
        print(f"    ... and {len(jobs) - limit} more")


def report(
    leveled: List[Dict[str, Any]],
    excluded: List[Dict[str, Any]],
    sample: int,
) -> None:
    """Print both questions' evidence as one page."""
    print(LINE)
    print("DECISION CHECK")
    print(LINE)

    # ── Question 1 ──
    f1 = compare_f1_against_role_type(leveled, excluded)
    kept_track = len(f1["kept_with_track"])
    kept_none = len(f1["kept_no_track"])
    drop_track = len(f1["dropped_with_track"])
    drop_none = len(f1["dropped_no_track"])
    total = kept_track + kept_none + drop_track + drop_none

    print()
    print("QUESTION 1 — should F1 screen on role_type instead of the AI's label?")
    print()
    print("  F1's decision against what F7's rules would have said:")
    print()
    print("                     rules gave a track   rules gave nothing")
    print(f"    F1 kept it       {kept_track:>12}   {kept_none:>18}")
    print(f"    F1 dropped it    {drop_track:>12}   {drop_none:>18}")
    print()
    print(f"  They agree on {kept_track + drop_none} of {total} jobs "
          f"({pct(kept_track + drop_none, total)}).")
    print()

    if drop_track:
        print(f"  DROPPED BY F1, BUT THE RULES CALL IT TECH — {drop_track} jobs")
        print("  These are the possible lost jobs. Read them first.")
        print()
        by_rule = Counter(excluded_rule_of(j) for j in f1["dropped_with_track"])
        for rule, count in by_rule.most_common():
            print(f"    {rule}: {count}")
        print()
        # Which tier of the classifier produced the disagreeing track. This is
        # the number that says whether the classifier is reading the job or
        # just inheriting the search that found it.
        print("  ...and where the rules got that track from:")
        by_source = Counter(
            (j.get("role_source", "") or "(none)") for j in f1["dropped_with_track"]
        )
        for source, count in by_source.most_common():
            print(f"    {source:<14} {count:>5}  ({pct(count, drop_track)})")
        print()
        print_sample(f1["dropped_with_track"], sample, show_rule=True)
        print()

    if kept_none:
        print(f"  KEPT BY F1, BUT THE RULES CANNOT PLACE IT — {kept_none} jobs")
        print("  Swapping F1 over to role_type would drop these. Check whether")
        print("  they are non-tech leaks or real jobs the rules just missed.")
        print()
        print_sample(f1["kept_no_track"], sample, show_rule=False)
        print()

    # ── Question 2 ──
    print(RULE)
    print()
    print("QUESTION 2 — is there room to skip AI enrichment?")
    print()

    f5 = measure_enrichment_headroom(leveled)

    if not f5["marked"]:
        print("  No job carries needs_ai_skills. Either F5 did not run on this")
        print("  artifact, or the runner was on older code. Nothing to measure.")
        print()
    else:
        print("  Where each job's skills ended up coming from:")
        for source, count in f5["sources"].most_common():
            print(f"    {source:<10} {count:>5}  ({pct(count, len(leveled))})")
        print()
        print(f"  Keyword matching alone found enough (3+ skills) for "
              f"{f5['could_skip']} of {len(leveled)} jobs "
              f"({pct(f5['could_skip'], len(leveled))}).")
        print("  That is the ceiling on what could skip enrichment for skills.")
        print()
        print("  But enrichment fills more than skills, and skipping it costs those:")
        print(f"    would lose the board's blurb:        {f5['skip_loses_blurb']:>5}")
        print(f"    would lose the AI role label F1 uses: {f5['skip_loses_role']:>5}")
        print()
        if f5["skip_loses_role"]:
            print("  Note how Question 1 feeds this one. F1 screens on the AI's")
            print("  label today, so skipping enrichment breaks F1 for exactly the")
            print("  jobs it skips. Moving F1 onto role_type first would remove")
            print("  that obstacle -- which makes these two decisions one decision,")
            print("  in an order: role_type first, then the skip.")
            print()

    print(RULE)
    print("Counts only. Neither question is settled by a number -- open the")
    print("titles above and judge whether the disagreements are real.")


# ─── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Evidence for the two decisions parked by F7 and F5.",
    )
    parser.add_argument(
        "-d", "--dir", default=str(DEFAULT_DIR),
        help=f"Folder holding a run's saved files (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--sample", type=int, default=DEFAULT_SAMPLE,
        help=f"How many disagreeing titles to print (default: {DEFAULT_SAMPLE})",
    )
    args = parser.parse_args()

    base = Path(args.dir)
    leveled = load_jobs(base / LEVELED)
    excluded = load_jobs(base / EXCLUDED)

    if leveled is None:
        print(f"Could not read {base / LEVELED}.")
        print("Unzip a run's artifact over that folder first.")
        sys.exit(1)

    if excluded is None:
        print(f"Could not read {base / EXCLUDED}.")
        print("Question 1 needs it to know what F1 dropped.")
        sys.exit(1)

    if not leveled:
        print(f"{LEVELED} has no jobs in it. Nothing to measure.")
        sys.exit(1)

    report(leveled, excluded, args.sample)


if __name__ == "__main__":
    main()
