"""
publish.py — the file the board reads (F6)
===========================================

The problem
-----------
The daily run only ever knows about today's jobs. A job board needs to show
everything currently open, and the only place that already holds that history
is the Google Sheet -- which also still carries ~5,000 rows scraped before F1
and F4 existed, none of them screened for tech relevance or seniority.
Publishing straight from the Sheet would put all of that back in front of
graduates, and reconstructing job records from the Sheet's flattened rows
loses information nothing else needs to lose.

What this does
---------------
Keeps ``frontend/jobs.json`` as its own running list, built up one day at a
time from jobs that have already been through the real pipeline -- screened,
deduplicated, leveled. Each run:

1. Loads whatever the board is currently showing.
2. Merges in today's kept jobs, matching against the board's own copy with
   the same key F9 already uses to catch a re-post.
3. Drops anything whose posting has aged out of the retention window --
   ads do not stay open forever, and neither should their row on the board.
4. Writes the result back, newest posting first.

Usage
-----
    from src.pipeline import publish

    counts = publish.publish(all_jobs)
    publish.log_publish(counts)
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.pipeline.dedupe import duplicate_key, is_comparable
from src.utils import log

JOBS_FILE = Path(__file__).resolve().parents[3] / "frontend" / "public" / "jobs.json"
"""
 Where the board reads from -- committed by CI, not the working repo.
 Inside frontend/public/, not frontend/ itself: that is the one directory
 Vite copies into the deployed build untouched, so anything outside it never
 reaches the live site at all.
 """

RETENTION_DAYS = 45
"""
How long a job stays on the board after its posting date.

Ads do not stay open indefinitely, and an unbounded board would just become
a second copy of the Sheet's own growing history -- exactly what this module
exists to avoid.
"""


def _best_date(job: Dict[str, Any]) -> str:
    """
    The date used to decide whether a job is still fresh enough to publish.

    Prefers the ad's own stated posting date. Falls back to the date this
    job was first added to the board, for the common case where a source
    does not state one at all -- OfferZen and PNet never do.
    """
    return str(job.get("date_posted") or job.get("date_added") or "")


def load_existing(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load whatever the board is currently showing.

    Args:
        path: Optional override for the jobs file (used by tests).

    Returns:
        The jobs currently on the board, or an empty list when there is no
        file yet (the first run) or it cannot be read.
    """
    target = Path(path) if path else JOBS_FILE
    if not target.exists():
        return []

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    return data.get("jobs", []) if isinstance(data, dict) else data


def merge(
    existing: Sequence[Dict[str, Any]],
    new_jobs: Sequence[Dict[str, Any]],
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Merge today's kept jobs into the board's running list.

    A new job matching one already on the board replaces it rather than
    adding a second copy, carrying over the original 'date_added' so the
    job's place in the retention window does not reset just because it
    enriched slightly differently today.

    Two ways to match, checked in that order:

    1. **The apply link.** Identical link, identical advert -- Indeed's
       ``jk`` is the posting's own id, so there is nothing to weigh up.
    2. **F9's title/company/city key**, for the same advert reached through
       two different links.

    The link check is not a nicety, it is what stops the board filling with
    the same job. F9's key needs both a title and a company to be trusted,
    and plenty of Indeed ads carry no company at all -- so an advert with a
    blank company matched nothing, every day, and was appended again on
    every run. On the live board that put one Power Platform post on six
    separate rows and an ABAP post on five. It also broke the *front end*:
    the board keys its cards by apply link, and React quietly mis-renders a
    list whose keys repeat, so the count said four jobs while thirty-two
    cards were on screen.

    A job with neither a link nor a comparable key is never matched and is
    always kept as its own row.

    Args:
        existing: The board's current jobs.
        new_jobs: Today's kept jobs, straight from screening.
        today: Override for "today" (used by tests).

    Returns:
        The merged list, existing jobs first, in their original order.
    """
    today_str = (today or date.today()).isoformat()

    by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    by_link: Dict[str, Dict[str, Any]] = {}
    merged: List[Dict[str, Any]] = list(existing)

    for job in existing:
        link = job.get("job_url") or ""
        if link:
            by_link.setdefault(link, job)
        key = duplicate_key(job)
        if is_comparable(key):
            by_key[key] = job

    for incoming in new_jobs:
        job = dict(incoming)
        link = job.get("job_url") or ""
        key = duplicate_key(job)

        old = by_link.get(link) if link else None
        if old is None and is_comparable(key):
            old = by_key.get(key)

        if old is not None:
            job["date_added"] = old.get("date_added", today_str)
            merged[merged.index(old)] = job
        else:
            job.setdefault("date_added", today_str)
            merged.append(job)

        if link:
            by_link[link] = job
        if is_comparable(key):
            by_key[key] = job

    return merged


def prune(
    jobs: Sequence[Dict[str, Any]],
    today: Optional[date] = None,
    retention_days: int = RETENTION_DAYS,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Drop jobs whose posting has aged out of the retention window.

    A job with no usable date at all -- posting date unstated and, somehow,
    no 'date_added' either -- is kept rather than guessed away. A parse
    failure is not evidence that a job is stale.

    Args:
        jobs: The merged job list.
        today: Override for "today" (used by tests).
        retention_days: How many days a job stays on the board.

    Returns:
        A (kept_jobs, dropped_count) tuple.
    """
    cutoff = (today or date.today()) - timedelta(days=retention_days)
    kept: List[Dict[str, Any]] = []
    dropped = 0

    for job in jobs:
        raw = _best_date(job)
        if not raw:
            kept.append(job)
            continue

        try:
            job_date = datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            kept.append(job)
            continue

        if job_date >= cutoff:
            kept.append(job)
        else:
            dropped += 1

    return kept, dropped


def save(jobs: Sequence[Dict[str, Any]], path: Optional[str] = None) -> None:
    """
    Write the board's jobs to disk, newest posting first.

    Args:
        jobs: The jobs to publish.
        path: Optional override for the jobs file (used by tests).
    """
    ordered = sorted(jobs, key=_best_date, reverse=True)

    target = Path(path) if path else JOBS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(ordered),
        "jobs": ordered,
    }
    target.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def publish(
    new_jobs: Sequence[Dict[str, Any]],
    path: Optional[str] = None,
    today: Optional[date] = None,
) -> Dict[str, int]:
    """
    Fold today's kept jobs into the board and write it back (F6).

    Args:
        new_jobs: Today's kept jobs, straight from screening.
        path: Optional override for the jobs file (used by tests).
        today: Override for "today" (used by tests).

    Returns:
        Counts for the run log: how many were already on the board, how
        many came in today, how many aged out, and the final total.
    """
    existing = load_existing(path)
    merged = merge(existing, new_jobs, today=today)
    kept, pruned = prune(merged, today=today)
    save(kept, path)

    return {
        "carried_over": len(existing),
        "from_today": len(new_jobs),
        "pruned": pruned,
        "published": len(kept),
    }


def log_publish(counts: Dict[str, int]) -> None:
    """Print the board's publish summary for the run log (F6)."""
    log(f"  board: {counts['published']} jobs published "
        f"({counts['carried_over']} carried over, {counts['from_today']} from today, "
        f"{counts['pruned']} pruned past {RETENTION_DAYS} days)")