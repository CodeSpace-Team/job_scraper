"""
orchestrator.py — Pipeline orchestration for daily job scraping
================================================================
Runs the complete pipeline:
  1. Scrape jobs from all sources (OfferZen, Indeed, LinkedIn, PNet)
  2. Enrich with AI (extract skills, levels, blurbs)
  3. Work out each job's level and years of experience (F2, F3)
  4. Screen out non-tech jobs, keeping the drops with their reasons (F1)
  5. Write to Google Sheets (sorted, deduplicated)

Designed for GitHub Actions daily runs.

Usage:
    python -m src.main --spreadsheet-id "1abc123xyz"
    python -m src.main --spreadsheet-id "1abc123xyz" --skip-linkedin
"""

import argparse
import os
import sys
import time
from datetime import datetime

from src.scrapers import offerzen, indeed, linkedin

# PNet is optional - handle gracefully
try:
    from src.scrapers import pnet
    HAS_PNET = True
except ImportError:
    pnet = None  # Explicitly set to None to avoid linter warnings
    HAS_PNET = False

from src.enrichment import enhancer
from src.pipeline import experience, levels, screening
from src.writers import sheets
from src.utils import log, save_jobs


def main() -> None:
    """Run the complete job scraping pipeline."""
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
    sheet_url = None  # Initialize for summary

    log("=" * 70)
    log("STARTING DAILY JOB SCRAPING PIPELINE")
    log("=" * 70)

    # ── PHASE 1: SCRAPING ────────────────────────────────────────────────────

    log("\n[PHASE 1] SCRAPING JOB SOURCES...")

    # OfferZen
    if not args.skip_offerzen:
        log("\n--- OfferZen ---")
        try:
            offerzen_jobs = offerzen.scrape_offerzen()
            save_jobs(offerzen_jobs, "data/cache/offerzen_jobs.json")
            all_jobs.extend(offerzen_jobs)
            log(f"✓ OfferZen: {len(offerzen_jobs)} jobs")
        except Exception as e:
            log(f"✗ OfferZen error: {e}")

    # Indeed
    if not args.skip_indeed:
        log("\n--- Indeed ---")
        try:
            indeed_jobs = indeed.scrape_indeed(
                results_per_term=args.indeed_results,
                hours_old=720  # 30 days
            )
            save_jobs(indeed_jobs, "data/cache/indeed_jobs.json")
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
            linkedin_jobs = linkedin.scrape_linkedin(
                results_per_term=args.linkedin_results,
                hours_old=720  # 30 days
            )
            save_jobs(linkedin_jobs, "data/cache/linkedin_jobs.json")
            all_jobs.extend(linkedin_jobs)
            log(f"✓ LinkedIn: {len(linkedin_jobs)} jobs")
        except Exception as e:
            log(f"✗ LinkedIn error: {e}")
            log("  If you're seeing rate limit errors, consider:")
            log("  1. Using --skip-linkedin flag")
            log("  2. Reducing --linkedin-results (try 100-150)")
            log("  3. Running at a different time of day")

    # PNet (optional)
    if not args.skip_pnet and HAS_PNET and pnet is not None:
        log("\n--- PNet ---")
        try:
            pnet_jobs = pnet.scrape_pnet()
            save_jobs(pnet_jobs, "data/cache/pnet_jobs.json")
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

        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            log("✗ ERROR: ANTHROPIC_API_KEY not set. Skipping enrichment.")
            log("  Jobs will still be written to Sheets, but without AI enhancements.")
        else:
            save_jobs(all_jobs, "data/cache/combined_jobs.json")
            try:
                log("Enriching jobs with Claude AI...")
                enriched_jobs = enhancer.enrich_batch(
                    all_jobs,
                    api_key,
                    batch_size=5
                )
                save_jobs(enriched_jobs, "data/cache/combined_jobs_enriched.json")
                all_jobs = enriched_jobs
                log(f"✓ ENRICHMENT COMPLETE: {len(all_jobs)} jobs enriched")
            except Exception as e:
                log(f"✗ Enrichment error: {e}")
                log("  Continuing with un-enriched jobs...")
    else:
        log("\n[PHASE 2] ENRICHMENT SKIPPED (--skip-enrichment flag)")

    # ── PHASE 2.4: LEVELS AND YEARS (F2, F3) ─────────────────────────────────
    # Runs after enrichment so the rules get the last word over the AI, and
    # before screening because F4 will decide what to drop from these fields.

    log("\n[PHASE 2.4] WORKING OUT LEVELS AND YEARS OF EXPERIENCE...")

    all_jobs = experience.apply_experience(all_jobs)
    all_jobs = levels.apply_levels(all_jobs)

    experience.log_experience(all_jobs)
    levels.log_levels(all_jobs)

    save_jobs(all_jobs, "data/cache/combined_jobs_leveled.json")


    # ── PHASE 2.5: SCREENING (F1) ────────────────────────────────────────────

    log("\n[PHASE 2.5] SCREENING OUT NON-TECH JOBS...")

    all_jobs, excluded_jobs, screen_counts = screening.screen_jobs(all_jobs)
    screening.log_screening(screen_counts, excluded_jobs)

    save_jobs(excluded_jobs, "data/cache/excluded_jobs.json")

    if not all_jobs:
        log("\n✗ ERROR: every scraped job was screened out!")
        log("  This usually means enrichment failed and no titles matched.")
        log("  Check data/cache/excluded_jobs.json before trusting this run.")
        sys.exit(1)

    # ── PHASE 3: WRITE TO SHEETS ─────────────────────────────────────────────

    log("\n[PHASE 3] WRITING TO GOOGLE SHEETS...")

    try:
        sheet_url = sheets.write_to_sheet(
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
        save_jobs(all_jobs, "data/cache/combined_jobs_fallback.json")
        log("  Saved fallback copy to data/cache/combined_jobs_fallback.json")
        sys.exit(1)

    # ── PHASE 3.5: EXCLUDE TAB ───────────────────────────────────────────────
    # Handled separately from the Jobs write above. The Jobs sheet is the
    # deliverable; the Exclude tab is a record for review. If this fails, the
    # run has still done its job, so it warns rather than exiting.

    if excluded_jobs:
        try:
            write_count = sheets.write_exclude_tab(
                excluded_jobs,
                args.spreadsheet_id,
                "Exclude"
            )
            log(f"✓ EXCLUDE TAB UPDATED: {write_count} rows appended")
        except Exception as e:
            log(f"⚠ Could not write the Exclude tab: {e}")
            log("  The Jobs sheet is fine. The dropped jobs are still saved in")
            log("  data/cache/excluded_jobs.json.")

    # ── SUMMARY ──────────────────────────────────────────────────────────────

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    log("\n" + "=" * 70)
    log("PIPELINE COMPLETE")
    log("=" * 70)
    log(f"Total jobs: {len(all_jobs)}")
    dropped_non_tech = (screen_counts.get('dropped_title_blocklist', 0)
                        + screen_counts.get('dropped_role_not_accepted', 0))
    log(f"Excluded (non-tech):   {dropped_non_tech}")
    log(f"Excluded (too senior): {screen_counts.get('dropped_above_cohort', 0)}")
    log(f"Excluded (too senior): {screen_counts.get('dropped_above_cohort', 0)}")
    log(f"Time taken: {minutes}m {seconds}s")
    if sheet_url:
        log(f"Sheet URL: {sheet_url}")
    else:
        log("Sheet URL: Not available (write failed)")
    log("\nNext run: Tomorrow at the same time (via GitHub Actions)")
    log("=" * 70)


if __name__ == '__main__':
    main()