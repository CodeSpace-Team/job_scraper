"""
morning_check.py — read yesterday's run in one go
=================================================

The problem
-----------
Checking a run by hand means opening the GitHub log, scrolling four phases,
downloading the artifact, and then squinting at four JSON files to work out
whether the numbers agree with each other. That takes twenty minutes and it
is easy to miss the one number that moved.

What this does
--------------
Reads the files a run leaves behind and prints a single page: how many jobs
survived each stage, whether those numbers add up, and whether anything looks
wrong enough to stop and investigate.

It also answers the question you actually have most mornings -- **did my code
changes reach the runner?** Each feature leaves a fingerprint on the data it
touches. If F9 ran, jobs carry a duplicate count. If F2 ran, they carry a
level source. When a fingerprint is missing, the runner was on older code, and
no amount of reading the counts will tell you that.

Nothing here talks to Google Sheets or to GitHub. It reads files, so it is
safe to run as often as you like and it works offline.

Usage
-----
    # after unzipping the artifact over data/cache/
    python -m scripts.morning_check

    # or point it somewhere else
    python -m scripts.morning_check -d ~/Downloads/job-data-128
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_DIR = Path("data/cache")

SCRAPED = "combined_jobs.json"
ENRICHED = "combined_jobs_enriched.json"
LEVELED = "combined_jobs_leveled.json"
EXCLUDED = "excluded_jobs.json"
BOARD = "board_jobs.json"

FINGERPRINTS: Tuple[Tuple[str, str, str], ...] = (
    # (feature, field, which file it should appear in)
    ("F9 duplicates", "duplicate_count", LEVELED),
    ("F3 years", "years_source", LEVELED),
    ("F2 levels", "level_source", LEVELED),
    ("F2 levels", "ai_job_level", LEVELED),
    ("F1/F4 screen", "excluded_stage", EXCLUDED),
    ("F4 review flag", "needs_review", EXCLUDED),
    ("F7 tracks", "role_type", LEVELED),
    ("apply/stretch tiers", "tier", BOARD),
)
"""
Fields each feature leaves behind, and where to look for them.

This is how the script tells "the runner is on old code" apart from "the
run was quiet". A missing field is not a small number -- it is the step
never having happened.
"""

YEARS_TARGET = 40.0
"""The brief's target for how much of the years column should be filled."""


# ─── Reading the files ──────────────────────────────────────────────────────

def load(path: Path) -> Optional[List[Dict[str, Any]]]:
    """
    Load one of the run's saved job files.

    Args:
        path: Path to the JSON file.

    Returns:
        The list of jobs, or None when the file is missing or unreadable.
        None and an empty list mean different things here, so they are kept
        apart: missing means the phase never wrote, empty means it wrote
        nothing.
    """
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        print(f"  ! {path.name} is not readable JSON: {error}")
        return None

    if isinstance(raw, dict):
        return raw.get("jobs", [])
    if isinstance(raw, list):
        return raw
    return []


def count_of(jobs: Optional[List[Dict[str, Any]]]) -> str:
    """Render a count, or a dash when the file was not there at all."""
    return "—" if jobs is None else str(len(jobs))

def kept_jobs(
    leveled: Optional[List[Dict[str, Any]]],
    excluded: Optional[List[Dict[str, Any]]],
    board: Optional[List[Dict[str, Any]]] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Work out which jobs actually reached the board.

    Prefers board_jobs.json, which the orchestrator writes straight after
    screening and which carries each job's tier. Falls back to subtraction
    for runs from before that file existed.

    combined_jobs_leveled.json is saved by the orchestrator *before*
    screening runs, so it never carries 'excluded_stage' -- checking that
    field on it always looks like screening never happened, even on a
    perfectly healthy run. The real kept set is whatever is left after
    subtracting excluded_jobs.json by web address.

    Args:
        leveled: Jobs after the level step, before screening.
        excluded: Jobs the screens dropped.

    Returns:
        The jobs that survived screening, or None if leveled is missing.
        If excluded is missing too, this is the full leveled list -- the
        best available answer, not a claim that nothing was dropped.
    """
    if board:
        return board

    if leveled is None:
        return None

    dropped_urls = {
        job.get("job_url") for job in (excluded or []) if job.get("job_url")
    }
    return [job for job in leveled if job.get("job_url") not in dropped_urls]


# ─── The checks ─────────────────────────────────────────────────────────────

def check_fingerprints(
    files: Dict[str, Optional[List[Dict[str, Any]]]],
) -> List[str]:
    """
    Check that each feature left its mark on the data.

    Args:
        files: The loaded job files, keyed by filename.

    Returns:
        A list of problem descriptions. Empty means every feature ran.
    """
    problems: List[str] = []

    for feature, field, filename in FINGERPRINTS:
        jobs = files.get(filename)
        if not jobs:
            continue
        if not any(field in job for job in jobs):
            problems.append(
                f"{feature}: no job in {filename} has '{field}' — "
                f"that step did not run"
            )

    return problems


def reconcile(
    leveled: Optional[List[Dict[str, Any]]],
    excluded: Optional[List[Dict[str, Any]]],
) -> List[str]:
    """
    Check the stage counts against each other.

    Everything leaving the level step either reaches the board or lands in
    the Exclude tab. If those do not add up, one of the files is from a
    different run, or a phase failed part-way through.

    Args:
        leveled: Jobs after the level step, before screening.
        excluded: Jobs the screens dropped.

    Returns:
        A list of problem descriptions.
    """
    if leveled is None or excluded is None:
        return ["cannot reconcile: a stage file is missing"]

    kept = kept_jobs(leveled, excluded)
    accounted_for = len(kept) + len(excluded) if kept is not None else 0

    if accounted_for != len(leveled):
        return [
            f"{len(leveled)} jobs in {LEVELED}, but {len(kept or [])} kept + "
            f"{len(excluded)} excluded = {accounted_for} by web address — "
            f"the two files disagree"
        ]

    return []


def check_no_ai_levels(leveled: Optional[List[Dict[str, Any]]]) -> List[str]:
    """
    Check the AI is not deciding levels again.

    The AI fallback was removed after the first live run, where it called a
    plain "Test Analyst" a lead. F4 deletes jobs on that label, so if 'ai'
    ever appears as a level source again, something has been reverted.

    Args:
        leveled: Jobs after the level step.

    Returns:
        A list of problem descriptions.
    """
    if not leveled:
        return []

    ai_decided = sum(1 for job in leveled if job.get("level_source") == "ai")
    if ai_decided:
        return [
            f"{ai_decided} jobs had their level decided by the AI — "
            f"the fallback removed in F2 has come back"
        ]

    return []


def check_duplicates_left(leveled: Optional[List[Dict[str, Any]]]) -> List[str]:
    """
    Re-run the duplicate check over what survived, to see if any got through.

    Args:
        leveled: Jobs after the level step.

    Returns:
        A list of problem descriptions.
    """
    if not leveled:
        return []

    try:
        from src.pipeline import dedupe
    except ImportError:
        return []

    _survivors, counts = dedupe.deduplicate(list(leveled))
    if counts["removed"]:
        return [
            f"{counts['removed']} duplicates are still in the data after "
            f"phase 1.5 — the dedupe step did not catch them"
        ]

    return []


# ─── The report ─────────────────────────────────────────────────────────────

def print_stages(files: Dict[str, Optional[List[Dict[str, Any]]]]) -> None:
    """Print how many jobs survived each stage."""
    leveled = files[LEVELED]
    excluded = files[EXCLUDED]

    kept = kept_jobs(leveled, excluded, files.get(BOARD))
    reaching_board = None if kept is None else len(kept)

    print("\nWHAT HAPPENED TO THE JOBS")
    print(f"  scraped, after duplicates removed  {count_of(files[SCRAPED])}")
    print(f"  enriched by the AI                 {count_of(files[ENRICHED])}")
    print(f"  levels and years worked out        {count_of(leveled)}")
    print(f"  dropped by the screens             {count_of(excluded)}")
    print(f"  REACHING THE BOARD                 "
          f"{'—' if reaching_board is None else reaching_board}")


def print_drops(excluded: Optional[List[Dict[str, Any]]]) -> None:
    """Print the breakdown of what was dropped and why."""
    if not excluded:
        return

    by_stage = Counter(job.get("excluded_stage", "?") for job in excluded)
    flagged = [job for job in excluded if job.get("needs_review")]

    print("\nWHY JOBS WERE DROPPED")
    for stage, count in by_stage.most_common():
        print(f"  {stage:<24} {count}")
    print(f"  {'flagged for review':<24} {len(flagged)}")

    if flagged:
        print("\n  The doubtful ones — read these first:")
        for job in flagged[:10]:
            print(f"    - {job.get('title', '?')[:55]}")
            print(f"      {job.get('excluded_reason', '')}")


def print_levels(
    leveled: Optional[List[Dict[str, Any]]],
    excluded: Optional[List[Dict[str, Any]]],
    board: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Print the level and years breakdown for jobs reaching the board."""
    if not leveled:
        return

    kept = kept_jobs(leveled, excluded, board)
    if not kept:
        return

    by_level = Counter(job.get("job_level") or "unknown" for job in kept)
    by_source = Counter(job.get("level_source") or "none" for job in kept)
    filled = sum(1 for job in kept if job.get("experience_years") is not None)
    rate = filled / len(kept) * 100

    print("\nWHAT REACHED THE BOARD LOOKS LIKE")

    # The tier is the decision now, so it goes first. Read on its own, the
    # level breakdown below is alarming and shouldn't be -- "unknown 45%,
    # mid 29%" is the stretch tier working exactly as designed, not the
    # leveling falling over.
    by_tier = Counter(job.get("tier") or "(not set)" for job in kept)
    if set(by_tier) != {"(not set)"}:
        for tier, count in by_tier.most_common():
            share = count / len(kept) * 100
            label = {
                "apply": "apply    (clearly in reach)",
                "stretch": "stretch  (worth a shot)",
            }.get(tier, tier)
            print(f"  {label:<30} {count:>4}  ({share:.0f}%)")
        print()
    else:
        print("  ⚠ no job carries a tier — the runner is on code older than")
        print("    the apply/stretch split, whatever the other numbers say")
        print()

    print("  by level, which is now working rather than deciding:")
    for level, count in by_level.most_common():
        share = count / len(kept) * 100
        print(f"    {level:<14} {count:>4}  ({share:.0f}%)")

    sources = ", ".join(f"{k} {v}" for k, v in by_source.most_common())
    print(f"\n  level decided by: {sources}")

    verdict = "on target" if rate >= YEARS_TARGET else "under the 40% target"
    print(f"  years of experience filled: {filled} of {len(kept)} "
          f"= {rate:.0f}%  ({verdict})")


def print_verdict(problems: List[str]) -> int:
    """
    Print the final verdict.

    Args:
        problems: Every problem the checks found.

    Returns:
        An exit code: 0 when the run looks fine, 1 when it does not.
    """
    print("\n" + "─" * 68)
    if not problems:
        print("NOTHING LOOKS WRONG. Every step ran and the numbers add up.")
        print("Still worth doing by eye: open the Exclude tab and read a few")
        print("of the drops. A number cannot tell you a real job was lost.")
        return 0

    print(f"{len(problems)} THING(S) TO LOOK AT:\n")
    for problem in problems:
        print(f"  ✗ {problem}")
    return 1


# ─── Entry Point ────────────────────────────────────────────────────────────

def main() -> int:
    """
    Read a run's saved files and print a one-page verdict.

    Returns:
        0 when the run looks fine, 1 when something needs looking at.
    """
    parser = argparse.ArgumentParser(
        description="Check yesterday's scraper run in one go.",
    )
    parser.add_argument(
        "-d", "--directory", default=str(DEFAULT_DIR),
        help=f"Where the run's JSON files are (default: {DEFAULT_DIR})",
    )
    args = parser.parse_args()

    folder = Path(args.directory)
    if not folder.exists():
        print(f"✗ {folder} does not exist.")
        print("  Download the run's artifact and unzip it there first.")
        return 1

    files = {
        name: load(folder / name)
        for name in (SCRAPED, ENRICHED, LEVELED, EXCLUDED, BOARD)
    }

    if all(jobs is None for jobs in files.values()):
        print(f"✗ No run files found in {folder}.")
        print("  Expected at least combined_jobs_leveled.json.")
        return 1

    print("=" * 68)
    print(f"MORNING CHECK — {folder}")
    print("=" * 68)

    print_stages(files)
    print_drops(files[EXCLUDED])
    print_levels(files[LEVELED], files[EXCLUDED], files.get(BOARD))

    problems: List[str] = []
    problems += check_fingerprints(files)
    problems += reconcile(files[LEVELED], files[EXCLUDED])
    problems += check_no_ai_levels(files[LEVELED])
    problems += check_duplicates_left(files[LEVELED])

    return print_verdict(problems)


if __name__ == "__main__":
    sys.exit(main())