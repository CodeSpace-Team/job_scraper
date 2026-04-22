#!/usr/bin/env python3
"""
main_scraper.py — Orchestrator for daily job scraping pipeline
===============================================================
Runs the complete pipeline:
  1. Scrape jobs from all sources (OfferZen, Indeed, LinkedIn, PNet)
  2. Enrich with AI (extract skills, levels, blurbs)
  3. Write to Google Sheets (sorted, deduplicated)

Designed for GitHub Actions daily runs.

Usage:
    python main_scraper.py --spreadsheet-id "1abc123xyz"
    python main_scraper.py --spreadsheet-id "1abc123xyz" --skip-linkedin
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Import scraper modules
import offerzen_scraper
import indeed_scraper
import linkedin_scraper_enhanced as linkedin_scraper
try:
    import pnet_scraper
    HAS_PNET = True
except ImportError:
    HAS_PNET = False

# Import enrichment and sheets modules
import enrich_jobs
import sheets_writer


def log(msg: str):
    """Logging with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def save_jobs(jobs: list, filename: str):
    """Save jobs to JSON file."""
    path = Path(filename)
    path.write_text(
        json.dumps({"jobs": jobs}, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    log(f"Saved {len(jobs)} jobs to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Daily job scraping pipeline")
    parser.add_argument('-s', '--spreadsheet-id', required=True,
                        help='Google Sheets ID (required)')
    parser.add_argument('--sheet-name', default='Jobs',
                        help='Worksheet name (default: Jobs)')
    parser.add_argument('--skip-offerzen', action='store_true',
                        help='Skip OfferZen scraper')
    parser.add_argument('--skip-indeed', action='store_true',
                        help='Skip Indeed scraper')
    parser.add_argument('--skip-linkedin', action='store_true',
                        help='Skip LinkedIn scraper (use if having rate limit issues)')
    parser.add_argument('--skip-pnet', action='store_true',
                        help='Skip PNet scraper')
    parser.add_argument('--skip-enrichment', action='store_true',
                        help='Skip AI enrichment (faster but less useful)')
    parser.add_argument('--linkedin-results', type=int, default=200,
                        help='LinkedIn results per term (default: 200, max 300)')
    parser.add_argument('--indeed-results', type=int, default=100,
                        help='Indeed results per term (default: 100)')
    args = parser.parse_args()
    
    start_time = time.time()
    all_jobs = []
    
    log("=" * 70)
    log("STARTING DAILY JOB SCRAPING PIPELINE")
    log("=" * 70)
    
    # ── PHASE 1: SCRAPING ────────────────────────────────────────────────────
    
    log("\n[PHASE 1] SCRAPING JOB SOURCES...")
    
    # OfferZen
    if not args.skip_offerzen:
        log("\n--- OfferZen ---")
        try:
            offerzen_jobs = offerzen_scraper.scrape_offerzen()
            save_jobs(offerzen_jobs, "offerzen_jobs.json")
            all_jobs.extend(offerzen_jobs)
            log(f"✓ OfferZen: {len(offerzen_jobs)} jobs")
        except Exception as e:
            log(f"✗ OfferZen error: {e}")
    
    # Indeed
    if not args.skip_indeed:
        log("\n--- Indeed ---")
        try:
            indeed_jobs = indeed_scraper.scrape_indeed(
                results_per_term=50,
                hours_old=720  # 30 days
            )
            save_jobs(indeed_jobs, "indeed_jobs.json")
            all_jobs.extend(indeed_jobs)
            log(f"✓ Indeed: {len(indeed_jobs)} jobs")
        except Exception as e:
            log(f"✗ Indeed error: {e}")
    
    # LinkedIn (with anti-bot protection)
    if not args.skip_linkedin:
        log("\n--- LinkedIn (Enhanced) ---")
        log("Note: LinkedIn scraper uses anti-detection measures")
        log("      This will take longer but reduces ban risk")
        try:
            linkedin_jobs = linkedin_scraper.scrape_linkedin(
                results_per_term=args.linkedin_results,
                hours_old=720  # 30 days
            )
            save_jobs(linkedin_jobs, "linkedin_jobs.json")
            all_jobs.extend(linkedin_jobs)
            log(f"✓ LinkedIn: {len(linkedin_jobs)} jobs")
        except Exception as e:
            log(f"✗ LinkedIn error: {e}")
            log("  If you're seeing rate limit errors, consider:")
            log("  1. Using --skip-linkedin flag")
            log("  2. Reducing --linkedin-results (try 100-150)")
            log("  3. Running at a different time of day")
    
    # PNet (optional)
    if not args.skip_pnet and HAS_PNET:
        log("\n--- PNet ---")
        try:
            pnet_jobs = pnet_scraper.scrape_pnet()
            save_jobs(pnet_jobs, "pnet_jobs.json")
            all_jobs.extend(pnet_jobs)
            log(f"✓ PNet: {len(pnet_jobs)} jobs")
        except Exception as e:
            log(f"✗ PNet error: {e}")
    
    if not all_jobs:
        log("\n✗ ERROR: No jobs scraped from any source!")
        log("Check error messages above and try again.")
        sys.exit(1)
    
    log(f"\n✓ SCRAPING COMPLETE: {len(all_jobs)} total jobs")
    
    # ── PHASE 2: ENRICHMENT ──────────────────────────────────────────────────
    
    if not args.skip_enrichment:
        log("\n[PHASE 2] AI ENRICHMENT...")
        
        # Check for API key
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            log("✗ ERROR: ANTHROPIC_API_KEY not set. Skipping enrichment.")
            log("  Jobs will still be written to Sheets, but without AI enhancements.")
        else:
            # Save combined jobs for enrichment
            save_jobs(all_jobs, "combined_jobs.json")
            
            try:
                log("Enriching jobs with Claude AI...")
                enriched_jobs = enrich_jobs.enrich_batch(
                    all_jobs,
                    api_key,
                    batch_size=5
                )
                save_jobs(enriched_jobs, "combined_jobs_enriched.json")
                all_jobs = enriched_jobs
                log(f"✓ ENRICHMENT COMPLETE: {len(all_jobs)} jobs enriched")
            except Exception as e:
                log(f"✗ Enrichment error: {e}")
                log("  Continuing with un-enriched jobs...")
    else:
        log("\n[PHASE 2] ENRICHMENT SKIPPED (--skip-enrichment flag)")
    
    # ── PHASE 3: WRITE TO SHEETS ─────────────────────────────────────────────
    
    log("\n[PHASE 3] WRITING TO GOOGLE SHEETS...")
    
    try:
        sheet_url = sheets_writer.write_to_sheet(
            all_jobs,
            args.spreadsheet_id,
            args.sheet_name
        )
        log(f"✓ SHEETS UPDATE COMPLETE")
        log(f"  Sheet URL: {sheet_url}")
    except Exception as e:
        log(f"✗ Sheets write error: {e}")
        log("  Make sure:")
        log("  1. GOOGLE_SHEETS_CREDS is set correctly")
        log("  2. Service account has access to the sheet")
        log("  3. Spreadsheet ID is correct")
        sys.exit(1)
    
    # ── SUMMARY ──────────────────────────────────────────────────────────────
    
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    
    log("\n" + "=" * 70)
    log("PIPELINE COMPLETE")
    log("=" * 70)
    log(f"Total jobs: {len(all_jobs)}")
    log(f"Time taken: {minutes}m {seconds}s")
    log(f"Sheet URL: {sheet_url}")
    log("\nNext run: Tomorrow at the same time (via GitHub Actions)")
    log("=" * 70)


if __name__ == '__main__':
    main()