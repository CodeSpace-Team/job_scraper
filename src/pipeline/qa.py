"""
qa.py — the weekly level check (F2)
====================================

Why this exists
---------------
F2's target is a sample of 20 random jobs each week, with at least 18 of them
correctly leveled. That needs a human to look at real jobs, so this builds
the thing they look at: a table of randomly chosen jobs showing the level we
gave, the words we based it on, and a blank column to mark right or wrong.

It reads the cache file the daily run leaves behind, so no database or
spreadsheet access is needed to do the check.

F4 uses the same tool. Pointed at ``excluded_jobs.json`` it shows why each
job was dropped, which is how we catch a job that was dropped by mistake --
the thing that matters most, since a graduate never sees it.

Usage
-----
    # The weekly level check
    python -m src.pipeline.qa

    # Review what got dropped
    python -m src.pipeline.qa -i data/cache/excluded_jobs.json

    # A bigger sample, saved somewhere specific
    python -m src.pipeline.qa --size 50 -o data/qa/big-check.md

Output
------
A markdown file under data/qa/, and the same table printed to the screen.
Fill in the last column, then record the score at the bottom of the file.
"""

import argparse
import random
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.utils import load_jobs, log


# ─── Constants ──────────────────────────────────────────────────────────────

DEFAULT_INPUT = "data/cache/combined_jobs_leveled.json"
"""The file the daily run leaves behind after levels are worked out."""

DEFAULT_SIZE = 20
"""The sample size the brief asks for."""

TARGET_CORRECT = 18
"""How many of the 20 need to be right for F2 to be passing."""

OUTPUT_DIR = "data/qa"
"""Where review sheets are saved."""


# ─── Helper Functions ───────────────────────────────────────────────────────

def sample_jobs(
    jobs: Sequence[Dict[str, Any]],
    size: int = DEFAULT_SIZE,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Pick a random handful of jobs to check.

    Args:
        jobs: All the jobs from the run.
        size: How many to pick. Returns everything if there are fewer.
        seed: Fixed seed, so a check can be repeated exactly. Leave unset
              for a genuinely random sample.

    Returns:
        The chosen jobs.
    """
    if not jobs:
        return []

    picker = random.Random(seed)
    return picker.sample(list(jobs), min(size, len(jobs)))


def _cell(value: Any, limit: int = 60) -> str:
    """
    Make a value safe to drop into a markdown table cell.

    Args:
        value: Any value.
        limit: Trim anything longer than this.

    Returns:
        A single-line string with pipes escaped.
    """
    if value is None:
        return ""

    text = str(value).replace("|", "/").replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def target_for(size: int) -> int:
    """
    Work out the pass mark for a sample of a given size.

    The brief sets 18 out of 20. Expressing that as a proportion keeps the
    target sensible when a bigger or smaller sample is taken.

    Args:
        size: How many jobs are in the sample.

    Returns:
        How many need to be right.
    """
    return round(size * TARGET_CORRECT / DEFAULT_SIZE)


def build_report(
    jobs: Sequence[Dict[str, Any]],
    total_jobs: int,
    source_file: str,
) -> str:
    """
    Build the markdown review sheet.

    Shows a Dropped and Reason column instead of the blank check column when
    the jobs came from the excluded file, since that is a different question:
    not "is this level right" but "should this have been dropped at all".

    Args:
        jobs: The sampled jobs.
        total_jobs: How many jobs the sample was drawn from.
        source_file: Which file it was drawn from.

    Returns:
        The review sheet as markdown.
    """
    today = date.today().isoformat()
    reviewing_drops = any(job.get("excluded_reason") for job in jobs)

    lines: List[str] = []
    lines.append(f"# Level check — {today}")
    lines.append("")
    lines.append(f"- Sample of **{len(jobs)}** jobs, drawn from {total_jobs} in `{source_file}`")

    if reviewing_drops:
        lines.append("- These jobs were **dropped**. The question is whether any of")
        lines.append("  them should have been kept — that is the expensive mistake,")
        lines.append("  because a graduate never sees a job that was wrongly dropped.")
        last_columns = ["Why it was dropped", "Wrongly dropped?"]
    else:
        lines.append(
            f"- Target: at least **{target_for(len(jobs))} of {len(jobs)}** "
            f"correctly leveled"
        )
        lines.append("- Open each link, read the ad, and mark the last column")
        last_columns = ["Why that number", "Correct?"]

    columns = ["#", "Job Title", "Level", "Why that level", "Years"] + last_columns
    lines.append("")
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(" :--- " for _ in columns) + "|")

    for index, job in enumerate(jobs, start=1):
        title = _cell(job.get("title"), 45)
        url = str(job.get("job_url", "") or "")
        linked = f"[{title}]({url})" if url else title

        level = _cell(job.get("job_level"), 15)
        source = _cell(job.get("level_source"), 12)
        evidence = _cell(job.get("level_evidence"), 40)
        why_level = f"{source}: {evidence}" if evidence else source

        years = job.get("experience_years")
        years_text = "" if years is None else str(years)
        why_years = _cell(job.get("years_evidence"), 40)

        last = _cell(job.get("excluded_reason"), 45) + " |  " if reviewing_drops else " "
        lines.append(
            f"| {index} | {linked} | {level} | {_cell(why_level, 50)} | "
            f"{years_text} | {why_years} |{last}|"
        )

    lines.append("")
    lines.append("## Score")
    lines.append("")

    if reviewing_drops:
        lines.append("Wrongly dropped: ___ of " + str(len(jobs)))
        lines.append("")
        lines.append("Any job marked wrongly dropped is a rule that needs fixing.")
        lines.append("Note the job and what the rule should have done instead:")
    else:
        lines.append(
            f"Correct: ___ of {len(jobs)}  (target {target_for(len(jobs))})"
        )
        lines.append("")
        lines.append("For anything marked wrong, note the job and what the level")
        lines.append("should have been, so the rules can be adjusted:")

    lines.append("")
    lines.append("- ")
    lines.append("")

    return "\n".join(lines)


# ─── Entry Point ────────────────────────────────────────────────────────────

def main() -> None:
    """Build a review sheet from a run's cache file."""
    parser = argparse.ArgumentParser(
        description="Build the weekly level check (F2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.pipeline.qa
    python -m src.pipeline.qa -i data/cache/excluded_jobs.json
    python -m src.pipeline.qa --size 50 --seed 7
        """,
    )
    parser.add_argument(
        "-i", "--input", default=DEFAULT_INPUT,
        help=f"Jobs file to sample from (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help=f"Where to save the review sheet (default: {OUTPUT_DIR}/level-sample-DATE.md)",
    )
    parser.add_argument(
        "--size", type=int, default=DEFAULT_SIZE,
        help=f"How many jobs to sample (default: {DEFAULT_SIZE})",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Fixed seed, to repeat an earlier sample exactly",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        log(f"ERROR: {input_path} not found.")
        log("Run the pipeline first, or point at a different file with -i.")
        sys.exit(1)

    jobs = load_jobs(input_path)
    if not jobs:
        log(f"No jobs found in {input_path}.")
        sys.exit(1)

    chosen = sample_jobs(jobs, size=args.size, seed=args.seed)
    report = build_report(chosen, total_jobs=len(jobs), source_file=str(input_path))

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(OUTPUT_DIR) / f"level-sample-{date.today().isoformat()}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(report)
    log(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()