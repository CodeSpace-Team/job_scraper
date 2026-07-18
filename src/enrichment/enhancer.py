#!/usr/bin/env python3
"""
enhancer.py — AI-powered job enrichment via Anthropic Claude API
=================================================================

Enriches raw job listings with structured, AI-extracted metadata to make them
more useful for job seekers. Uses Claude Haiku (fast, cheap) to analyze
job descriptions and extract normalized fields.

What It Does:
--------------
For each job, Claude extracts:
    - primary_role: Normalized role category (e.g., "Backend Engineer")
    - must_have_skills: 3-8 key technical skills required
    - nice_to_have_skills: 2-5 bonus/preferred skills
    - experience_years: Years of experience required (integer)
    - job_level: intern | junior | mid | senior | lead | principal
    - blurb: 1-2 sentence summary of the role

Why Batch Processing?
---------------------
Processes jobs in batches (default 5 per API call) to:
    - Reduce API costs (fewer calls)
    - Improve throughput (parallel analysis)
    - Maintain context (Claude sees multiple jobs together)

Cost & Performance:
-------------------
- Model: Claude Haiku 4.5 (cheapest, ~$0.25/1M tokens)
- Batch size: 5 jobs per call
- Rate limit: ~60 requests/minute (1.5s delay between batches)
- Typical cost: ~$0.08 per 100 jobs (~$2.40/month at current volume)

Usage (Standalone):
-------------------
    python -m src.enrichment.enhancer -i offerzen_jobs.json -o enriched.json
    python -m src.enrichment.enhancer -i *.json --batch-size 10

Usage (Imported):
-----------------
    from src.enrichment import enhancer
    enriched = enhancer.enrich_batch(jobs, api_key, batch_size=5)

Environment Variables:
----------------------
    ANTHROPIC_API_KEY: Required. Get from https://console.anthropic.com

Error Handling:
---------------
    - If JSON parsing fails: Logs the error and keeps jobs un-enriched
    - If API call fails: Logs the error and keeps jobs un-enriched
    - If API key missing: Exits gracefully with error message

Idempotency:
------------
    - Checks for existing 'blurb' and 'primary_role' fields
    - Skips already-enriched jobs unless --force flag is used
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic library not installed. Run: pip install anthropic")
    sys.exit(1)


def log(msg: str) -> None:
    """
    Simple timestamped logging.

    Args:
        msg: Message to log to console
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_jobs(path: Path) -> List[Dict[str, Any]]:
    """
    Load jobs from a JSON file.

    Supports two formats:
        - {"jobs": [...]}  (preferred)
        - [...]            (flat list)

    Args:
        path: Path to JSON file

    Returns:
        List of job dictionaries (empty list if file is empty or invalid)
    """
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        log(f"  ✗ Invalid JSON in {path.name}: {e}")
        return []

    if isinstance(raw, dict):
        return raw.get('jobs', [])
    if isinstance(raw, list):
        return raw
    return []


def save_jobs(jobs: List[Dict[str, Any]], path: Path) -> None:
    """
    Save enriched jobs to a JSON file.

    Args:
        jobs: List of job dictionaries
        path: Output file path
    """
    path.write_text(
        json.dumps({"jobs": jobs}, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


def needs_enrichment(job: Dict[str, Any]) -> bool:
    """
    Check if a job needs AI enrichment.

    A job is considered "enriched" if it has both:
        - 'blurb' field (AI-generated summary)
        - 'primary_role' field (AI-normalized role)

    Also enriches if key fields are missing (must_have_skills, job_level).

    Args:
        job: Job dictionary to check

    Returns:
        True if job needs enrichment, False otherwise
    """
    # Already has AI enrichment
    if job.get('blurb') and job.get('primary_role'):
        return False

    # Missing required fields
    if not job.get('must_have_skills') or not job.get('job_level'):
        return True

    return False


def enrich_batch(
    jobs: List[Dict[str, Any]],
    api_key: str,
    batch_size: int = 5
) -> List[Dict[str, Any]]:
    """
    Enrich a batch of jobs using Claude API.

    Args:
        jobs: List of job dicts to enrich
        api_key: Anthropic API key
        batch_size: Jobs per API call (default: 5)
                   - Higher = cheaper, but may reduce accuracy
                   - Lower = more accurate, but more expensive

    Returns:
        List of enriched job dicts (same length as input)

    Note:
        If enrichment fails for a batch, those jobs are returned
        unchanged (un-enriched) so the pipeline can continue.

    Rate Limiting:
        Sleeps 1.5 seconds between batches to stay under
        Anthropic's ~60 requests/minute limit.
    """
    client = anthropic.Anthropic(api_key=api_key)
    enriched = []

    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        log(f"Enriching jobs {i+1}-{min(i+batch_size, len(jobs))} of {len(jobs)}...")

        # Build prompt with batch of jobs
        jobs_text = []
        for idx, job in enumerate(batch):
            job_str = f"""
Job {idx+1}:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description snippet: {job.get('description_snippet', '')[:1000]}
Current skills: {job.get('must_have_skills', '')}
"""
            jobs_text.append(job_str)

        prompt = f"""Analyze these {len(batch)} South African tech job listings and extract structured data for each.

{chr(10).join(jobs_text)}

For each job, provide:
1. primary_role: Normalized role category (e.g., "Backend Engineer", "Data Scientist", "DevOps Engineer", "Full Stack Developer")
2. must_have_skills: 3-8 key technical skills required (comma-separated)
3. nice_to_have_skills: 2-5 bonus skills mentioned (comma-separated)
4. experience_years: Years of experience required (integer, or null if not specified)
5. job_level: One of: intern, junior, mid, senior, lead, principal (or empty string if unclear)
6. blurb: 1-2 sentence summary of the role

Respond with ONLY valid JSON (no markdown):
{{
  "jobs": [
    {{
      "job_id": 1,
      "primary_role": "Backend Engineer",
      "must_have_skills": "Python, Django, PostgreSQL, REST APIs",
      "nice_to_have_skills": "Docker, AWS, Redis",
      "experience_years": 3,
      "job_level": "mid",
      "blurb": "Backend engineer role building scalable APIs for fintech platform."
    }},
    ...
  ]
}}"""

        response_text = ""  # Initialize to avoid linter warnings
        try:
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            response_text = re.sub(r'^```json\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)

            enrichment_data = json.loads(response_text)
            enriched_jobs = enrichment_data.get('jobs', [])

            # Merge enrichment data back into original jobs
            for job, enrichment in zip(batch, enriched_jobs):
                job['primary_role'] = enrichment.get('primary_role', job.get('primary_role', ''))
                job['must_have_skills'] = enrichment.get('must_have_skills', job.get('must_have_skills', ''))
                job['nice_to_have_skills'] = enrichment.get('nice_to_have_skills', job.get('nice_to_have_skills', ''))
                job['experience_years'] = enrichment.get('experience_years', job.get('experience_years'))
                job['job_level'] = enrichment.get('job_level', job.get('job_level', ''))
                job['blurb'] = enrichment.get('blurb', job.get('blurb', ''))
                enriched.append(job)

            log(f"  ✓ Enriched {len(batch)} jobs")

        except json.JSONDecodeError as e:
            log(f"  ✗ JSON parse error: {e}")
            if response_text:
                log(f"  Response preview: {response_text[:200]}...")
            # Add jobs without enrichment so pipeline continues
            enriched.extend(batch)

        except Exception as e:
            log(f"  ✗ API error: {e}")
            # Add jobs without enrichment so pipeline continues
            enriched.extend(batch)

        # Rate limiting: ~60 requests/minute max for Claude API
        time.sleep(1.5)

    return enriched


def main() -> None:
    """
    Command-line entry point for standalone enrichment.
    """
    parser = argparse.ArgumentParser(
        description="Enrich job listings with AI using Claude",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.enrichment.enhancer -i offerzen_jobs.json
    python -m src.enrichment.enhancer -i *.json --batch-size 10
    python -m src.enrichment.enhancer -i jobs.json --force --output all_enriched.json

Environment:
    ANTHROPIC_API_KEY must be set in environment
        """
    )
    parser.add_argument(
        '-i', '--input', nargs='+', required=True,
        help='Input JSON file(s) (supports wildcards like *.json)'
    )
    parser.add_argument(
        '-o', '--output', default=None,
        help='Output file (default: input_enriched.json)'
    )
    parser.add_argument(
        '--batch-size', type=int, default=5,
        help='Jobs per API call (default: 5, range: 3-10 recommended)'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='Re-enrich already enriched jobs (skip idempotency check)'
    )
    args = parser.parse_args()

    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        log("ERROR: ANTHROPIC_API_KEY environment variable not set")
        log("Get your API key from: https://console.anthropic.com")
        sys.exit(1)

    base = Path.cwd()

    # Process each input file
    for pattern in args.input:
        # Support glob patterns
        matched = list(base.glob(pattern)) if '*' in pattern or '?' in pattern else []
        if matched:
            paths = matched
        else:
            paths = [base / pattern]

        for input_path in paths:
            if not input_path.exists():
                log(f"Warning: {input_path} not found, skipping")
                continue

            log(f"\nProcessing {input_path.name}...")

            jobs = load_jobs(input_path)
            if not jobs:
                log(f"  No jobs found in {input_path.name}")
                continue

            log(f"  Loaded {len(jobs)} jobs")

            # Filter to jobs needing enrichment
            if not args.force:
                to_enrich = [j for j in jobs if needs_enrichment(j)]
                already_enriched = len(jobs) - len(to_enrich)
                if already_enriched:
                    log(f"  Skipping {already_enriched} already-enriched jobs (use --force to re-enrich)")
            else:
                to_enrich = jobs
                log(f"  Force mode: re-enriching all {len(to_enrich)} jobs")

            if not to_enrich:
                log("  All jobs already enriched. Use --force to re-enrich.")
                continue

            log(f"  Enriching {len(to_enrich)} jobs...")
            enriched = enrich_batch(to_enrich, api_key, batch_size=args.batch_size)

            # Merge back with already-enriched jobs
            if not args.force:
                already_ok = [j for j in jobs if not needs_enrichment(j)]
                all_jobs = already_ok + enriched
            else:
                all_jobs = enriched

            # Determine output path
            if args.output:
                output_path = base / args.output
            else:
                output_path = input_path.parent / f"{input_path.stem}_enriched.json"

            save_jobs(all_jobs, output_path)
            log(f"  Saved {len(all_jobs)} jobs to {output_path.name}")
            log(f"  ✓ Done with {input_path.name}")


if __name__ == '__main__':
    main()