#!/usr/bin/env python3
"""
enrich_jobs.py — AI-powered job enrichment via Anthropic API
=============================================================
Enriches job listings with:
  - Normalized primary_role (e.g., "Backend Engineer")
  - must_have_skills and nice_to_have_skills (extracted from description)
  - experience_years (parsed from requirements)
  - job_level (junior/mid/senior/lead/principal)
  - blurb (1-2 sentence summary)

Processes jobs in batches to minimize API calls.

Usage:
    python enrich_jobs.py -i offerzen_jobs.json -o offerzen_jobs_enriched.json
    python enrich_jobs.py -i *.json  # Process all JSON files
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Missing: pip install anthropic")
    sys.exit(1)


def log(msg: str):
    """Simple logging."""
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_jobs(path: Path) -> list:
    """Load jobs from JSON file."""
    raw = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(raw, dict):
        return raw.get('jobs', [])
    if isinstance(raw, list):
        return raw
    return []


def save_jobs(jobs: list, path: Path):
    """Save enriched jobs to JSON."""
    path.write_text(
        json.dumps({"jobs": jobs}, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )


def needs_enrichment(job: dict) -> bool:
    """Check if job needs enrichment."""
    # If it has blurb and primary_role, likely already enriched
    if job.get('blurb') and job.get('primary_role'):
        return False
    # If missing key fields, needs enrichment
    if not job.get('must_have_skills') or not job.get('job_level'):
        return True
    return False


def enrich_batch(jobs: list, api_key: str, batch_size: int = 5) -> list:
    """
    Enrich jobs in batches using Claude API.
    
    Args:
        jobs: List of job dicts to enrich
        api_key: Anthropic API key
        batch_size: Jobs per API call (higher = fewer calls, but less accurate)
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
            log(f"  Response: {response_text[:500]}")
            # Add jobs without enrichment
            enriched.extend(batch)
            
        except Exception as e:
            log(f"  ✗ API error: {e}")
            # Add jobs without enrichment
            enriched.extend(batch)
        
        # Rate limiting: ~60 requests/minute max for Claude API
        time.sleep(1.5)
    
    return enriched


def main():
    parser = argparse.ArgumentParser(description="Enrich job listings with AI")
    parser.add_argument('-i', '--input', nargs='+', required=True,
                        help='Input JSON file(s) (supports wildcards)')
    parser.add_argument('-o', '--output', default=None,
                        help='Output file (default: input_enriched.json)')
    parser.add_argument('--batch-size', type=int, default=5,
                        help='Jobs per API call (default: 5)')
    parser.add_argument('--force', action='store_true',
                        help='Re-enrich already enriched jobs')
    args = parser.parse_args()
    
    # Get API key from environment
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        log("Error: ANTHROPIC_API_KEY environment variable not set")
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
            log(f"Loaded {len(jobs)} jobs")
            
            # Filter to jobs needing enrichment
            if not args.force:
                to_enrich = [j for j in jobs if needs_enrichment(j)]
                already_enriched = len(jobs) - len(to_enrich)
                if already_enriched:
                    log(f"Skipping {already_enriched} already-enriched jobs")
            else:
                to_enrich = jobs
            
            if not to_enrich:
                log("All jobs already enriched. Use --force to re-enrich.")
                continue
            
            log(f"Enriching {len(to_enrich)} jobs...")
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
            log(f"Saved {len(all_jobs)} enriched jobs to {output_path.name}")


if __name__ == '__main__':
    main()