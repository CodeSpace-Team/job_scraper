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

F1 uses it too, in ``--check tech`` mode. F1's target is "fewer than 5 in
every 100 rows reaching the sheet is a non-tech job", and no count can
answer that on its own: deciding whether a job really is a tech job needs a
person to read the ad. So this builds that sheet as well.

That mode needs both files, because no run saves the kept jobs on their own.
"Kept" is everything in the leveled file that does not appear in the
excluded file, so both get read and one subtracted from the other.

Usage
-----
    # The weekly level check
    python -m src.pipeline.qa

    # Review what got dropped
    python -m src.pipeline.qa -i data/cache/excluded_jobs.json

    # F1's non-tech rate, over the jobs that actually reached the sheet
    python -m src.pipeline.qa --check tech

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

DEFAULT_EXCLUDED = "data/cache/excluded_jobs.json"
"""The dropped jobs, needed to work out which jobs were kept."""

TECH_TARGET_RATE = 0.05
"""
F1 passes when fewer than 5 in every 100 rows reaching the sheet is non-tech.

Held as a rate rather than a count because the honest sample size for it is
not 20. At 20 jobs the only measurable answers are 0%, 5%, 10% -- a single
wrong job is exactly the pass mark, so one unlucky draw decides it. The
report says so rather than pretending 20 settles the question.
"""

OUTPUT_DIR = "data/qa"
"""Where review sheets are saved."""

MODE_LEVEL = "level"
MODE_DROPS = "drops"
MODE_TECH = "tech"


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


def job_identity(job: Dict[str, Any]) -> str:
    """
    A stable identity for matching one job across two of a run's files.

    The web address is what the pipeline dedupes on, so it is what lines up
    between the leveled file and the excluded file. Jobs without one fall
    back to title and company -- weaker, but better than quietly dropping
    them out of the comparison.

    Args:
        job: Job dictionary.

    Returns:
        A key that is the same in both files for the same job.
    """
    url = str(job.get("job_url", "") or "").strip()
    if url:
        return url
    return f"{job.get('title', '')}|{job.get('company', '')}".strip().lower()


def kept_jobs(
    leveled: Sequence[Dict[str, Any]],
    excluded: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Work out which jobs actually reached the sheet.

    No run saves this list. The leveled file holds everything the pipeline
    handled, screening happens after it is written, and the excluded file
    holds only what was dropped -- so the kept jobs are the difference.

    Args:
        leveled: Every job the run handled, from combined_jobs_leveled.json.
        excluded: Every job the screens dropped, from excluded_jobs.json.

    Returns:
        The jobs that survived both screens, in their original order.
    """
    dropped = {job_identity(job) for job in excluded}
    return [job for job in leveled if job_identity(job) not in dropped]


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


def build_tech_report(
    jobs: Sequence[Dict[str, Any]],
    total_jobs: int,
    source_file: str,
) -> str:
    """
    Build F1's non-tech review sheet.

    A different question from the other two, and the only one that measures
    a target the brief states as a rate. The reviewer is asked one thing per
    job: is this actually a tech job? Anything answered "no" is a job F1 let
    through that it should have caught.

    Both labels the pipeline holds are shown -- the AI's `primary_role`,
    which is what F1 screened on, and F7's `role_type`, which is what the
    board's own filter shows a graduate. They can disagree, and when a job
    turns out to be non-tech it is worth seeing which of them was fooled.

    Args:
        jobs: The sampled jobs, drawn from the kept ones.
        total_jobs: How many jobs reached the sheet in this run.
        source_file: Which files the sample was drawn from.

    Returns:
        The review sheet as markdown.
    """
    today = date.today().isoformat()
    allowed = int(len(jobs) * TECH_TARGET_RATE)

    lines: List[str] = []
    lines.append(f"# Non-tech check (F1) — {today}")
    lines.append("")
    lines.append(
        f"- Sample of **{len(jobs)}** jobs, drawn from the {total_jobs} that "
        f"reached the sheet"
    )
    lines.append(f"- Source: `{source_file}`")
    lines.append(
        f"- Target: fewer than **{TECH_TARGET_RATE:.0%}** non-tech, so at most "
        f"**{allowed} of {len(jobs)}**"
    )
    lines.append("- One question per job: **is this actually a tech job?**")
    lines.append("  Mark `no` for anything that is not. Everything else, leave blank.")
    lines.append("")

    if 0 < len(jobs) < 40:
        step = 1 / len(jobs)
        lines.append(
            f"> A sample of {len(jobs)} measures a {TECH_TARGET_RATE:.0%} target "
            f"only roughly — one wrong job moves the result by {step:.0%}. "
            f"Either take a bigger sample (`--size 60`) or add several weeks "
            f"of these together before calling the target met or missed."
        )
        lines.append("")

    columns = [
        "#", "Job Title", "Company", "AI called it", "Board shows", "Non-tech?",
    ]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(" :--- " for _ in columns) + "|")

    for index, job in enumerate(jobs, start=1):
        title = _cell(job.get("title"), 45)
        url = str(job.get("job_url", "") or "")
        linked = f"[{title}]({url})" if url else title

        company = _cell(job.get("company"), 28)
        ai_label = _cell(job.get("primary_role"), 30) or "(none)"

        track = _cell(job.get("role_type"), 24) or "(none)"
        source = _cell(job.get("role_source"), 12)
        board = f"{track} ({source})" if source else track

        lines.append(
            f"| {index} | {linked} | {company} | {ai_label} | {board} |  |"
        )

    lines.append("")
    lines.append("## Score")
    lines.append("")
    lines.append(f"Non-tech: ___ of {len(jobs)}   (target: at most {allowed})")
    lines.append("")
    lines.append("For each one marked non-tech, note the job and which word should")
    lines.append("have caught it — that is what turns a miss into a blocklist entry:")
    lines.append("")
    lines.append("- ")
    lines.append("")

    return "\n".join(lines)


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
        "--check", choices=[MODE_LEVEL, MODE_TECH], default=MODE_LEVEL,
        help="Which question to build a sheet for. 'level' is F2's weekly "
             "check, and switches itself to reviewing drops when pointed at "
             "the excluded file. 'tech' is F1's non-tech rate over the jobs "
             "that reached the sheet (default: level)",
    )
    parser.add_argument(
        "-x", "--excluded", default=DEFAULT_EXCLUDED,
        help=f"Dropped jobs, used by --check tech to work out which jobs "
             f"were kept (default: {DEFAULT_EXCLUDED})",
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

    source = str(input_path)
    prefix = "level-sample"

    if args.check == MODE_TECH:
        excluded_path = Path(args.excluded)
        if not excluded_path.exists():
            log(f"ERROR: {excluded_path} not found.")
            log("--check tech needs it to work out which jobs were kept.")
            sys.exit(1)

        jobs = kept_jobs(jobs, load_jobs(excluded_path) or [])
        if not jobs:
            log("Every job in this run was dropped. Nothing reached the sheet.")
            sys.exit(1)

        source = f"{input_path} minus {excluded_path}"
        prefix = "tech-sample"

    chosen = sample_jobs(jobs, size=args.size, seed=args.seed)

    if args.check == MODE_TECH:
        report = build_tech_report(chosen, total_jobs=len(jobs), source_file=source)
    else:
        report = build_report(chosen, total_jobs=len(jobs), source_file=source)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = Path(OUTPUT_DIR) / f"{prefix}-{date.today().isoformat()}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(report)
    log(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
