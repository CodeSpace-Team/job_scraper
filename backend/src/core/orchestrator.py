"""
orchestrator.py — Pipeline orchestration for daily job scraping
================================================================
Runs the complete pipeline:
  1. Scrape jobs from all sources (OfferZen, Indeed, LinkedIn, PNet)
  2. Remove duplicates and re-posts (F9)
  3. Enrich with AI (extract skills, levels, blurbs)
  4. Work out each job's level and years of experience (F2, F3)
  5. Screen out non-tech and above-cohort jobs, with reasons (F1, F4)
  6. Write to Google Sheets
  7. Publish the board's jobs.json (F6)

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
from src.pipeline import dedupe, experience, levels, publish, roles, screening, skills
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
    # 50, not 100. F7 took a normal day from 6 search terms to 32, and the
    # 15 August run enriched 987 jobs at 100 results/term -- about $0.99
    # against CodeSpace's $1/day cap on its own Anthropic key, real money
    # with essentially no room for a heavier day. Halving this buys margin
    # without touching which terms run; it will fall hardest on the terms
    # that were already returning close to the cap, which on that run were
    # the original software-development ones -- exactly the tracks F9's
    # dedupe was already finding the most overlap in.
    parser.add_argument('--indeed-results', type=int, default=50,
                        help='Indeed results per term (default: 50)')
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
            todays_terms = [t.phrase for t in roles.terms_for_today()]
            log(f"  Searching {len(todays_terms)} terms across all seven tracks (F7)")
            indeed_jobs = indeed.scrape_indeed(
                search_terms=todays_terms,
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

    # ── PHASE 1.5: DUPLICATES (F9) ───────────────────────────────────────────
    # Before enrichment, so the same advert listed for three cities is not
    # sent to the AI three times.

    log("\n[PHASE 1.5] REMOVING DUPLICATES...")
    all_jobs, dupe_counts = dedupe.deduplicate(all_jobs)
    dedupe.log_dedupe(dupe_counts)

    # ── PHASE 1.7: SKILLS MATCHING (F5) ──────────────────────────────────────
    # Free, offline keyword matching, before enrichment. Two reasons to run
    # it here rather than after: the AI's own prompt shows it what this step
    # already found ("Current skills: ..."), which gives it something to
    # confirm or extend instead of starting blank; and a job whose feed
    # never carried a skills field at all still enters enrichment with
    # something in it. Nothing is skipped on the strength of this yet --
    # 'needs_ai_skills' is recorded on every job so there is a real, dated
    # record to decide that from later, the same way F7's role_type sits
    # next to the AI's label before anyone decides to trust it over it.

    log("\n[PHASE 1.7] MATCHING SKILLS BY KEYWORD...")
    all_jobs = skills.apply_keyword_skills(all_jobs)
    skills.log_fill_rate(all_jobs)

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

    # ── PHASE 2.4: LEVELS, YEARS, ROLE TYPE AND SKILLS (F2, F3, F5, F7) ──────
    # Runs after enrichment so the rules get the last word over the AI, and
    # before screening because F4 will decide what to drop from these fields.
    # Role type is classified here too, so it can sit next to the AI's own
    # role label ('primary_role') in the run log -- screening still reads
    # the AI's label for now, this is only being watched alongside it.
    # Skills get tidied here too: enrichment overwrites 'must_have_skills'
    # outright when it runs, so the keyword matcher's spellings and its
    # record of where the field's value actually came from both need
    # re-checking against whatever enrichment just did.

    log("\n[PHASE 2.4] WORKING OUT LEVELS, YEARS, ROLE TYPE AND SKILLS...")

    all_jobs = experience.apply_experience(all_jobs)
    all_jobs = levels.apply_levels(all_jobs)
    all_jobs = roles.apply_roles(all_jobs)
    for job in all_jobs:
        skills.normalise_ai_skills(job)

    experience.log_experience(all_jobs)
    levels.log_levels(all_jobs)
    roles.log_roles(all_jobs)
    skills.log_fill_rate(all_jobs)

    save_jobs(all_jobs, "data/cache/combined_jobs_leveled.json")

    # ── PHASE 2.5: SCREENING (F1) ────────────────────────────────────────────

    log("\n[PHASE 2.5] SCREENING OUT NON-TECH JOBS...")

    all_jobs, excluded_jobs, screen_counts = screening.screen_jobs(all_jobs)
    screening.log_screening(screen_counts, excluded_jobs)

    save_jobs(excluded_jobs, "data/cache/excluded_jobs.json")

    # What survived, with its tier on it. combined_jobs_leveled.json is
    # written above, before screening, so it has neither the tier nor any
    # idea which jobs were kept -- the morning check had to subtract one
    # file from the other to guess, and the QA sampler was drawing its
    # twenty jobs from all 642 scraped, so most of a review went on jobs
    # that never reached anybody.
    save_jobs(all_jobs, "data/cache/board_jobs.json")

    if not all_jobs:
        log("\n✗ ERROR: every scraped job was screened out!")
        log("  This usually means enrichment failed and no titles matched.")
        log("  Check data/cache/excluded_jobs.json before trusting this run.")
        sys.exit(1)

    # ── PHASE 3: WRITE TO SHEETS ─────────────────────────────────────────────
    # A failure here does not end the run early. It used to -- write_to_sheet
    # raised SystemExit directly on failure, which is invisible to a plain
    # "except Exception", so it skipped straight past this handler, past the
    # Exclude tab below, and past the summary. That is how a run finished all
    # its real work and still walked away with nothing written anywhere: a
    # single dropped connection to Google took the whole run down with it.
    # Now a failure here is recorded and the run carries on -- the Exclude
    # tab and the summary still deserve their chance to run.

    log("\n[PHASE 3] WRITING TO GOOGLE SHEETS...")

    sheet_url = None
    jobs_write_failed = False

    try:
        sheet_url = sheets.write_to_sheet(
            all_jobs,
            args.spreadsheet_id,
            args.sheet_name
        )
        log(f"✓ SHEETS UPDATE COMPLETE")
        log(f"  Sheet URL: {sheet_url}")
    except Exception as e:
        jobs_write_failed = True
        log(f"✗ Sheets write error: {e}")
        log("  Make sure:")
        log("  1. GOOGLE_SHEETS_CREDS is set correctly")
        log("  2. Service account has access to the sheet")
        log("  3. Spreadsheet ID is correct")
        save_jobs(all_jobs, "data/cache/combined_jobs_fallback.json")
        log("  Saved fallback copy to data/cache/combined_jobs_fallback.json")

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

    # ── PHASE 3.7: PUBLISH THE BOARD (F6) ────────────────────────────────────
    # Independent of the Sheets write above -- frontend/jobs.json is its own
    # running file, not a copy of the Sheet, so it has nothing to wait on and
    # nothing to lose if Sheets is down. A failure here warns rather than
    # exits, same reasoning as the Exclude tab: the run has already done its
    # real work by this point.

    log("\n[PHASE 3.7] PUBLISHING THE BOARD...")

    try:
        publish_counts = publish.publish(all_jobs)
        publish.log_publish(publish_counts)
    except Exception as e:
        log(f"⚠ Could not publish the board: {e}")
        log("  The Jobs sheet is fine. frontend/jobs.json was not updated this run.")

    # ── SUMMARY ──────────────────────────────────────────────────────────────

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    log("\n" + "=" * 70)
    log("PIPELINE COMPLETE")
    log("=" * 70)
    log(f"Total jobs: {len(all_jobs)}")
    log(f"Duplicates removed:    {dupe_counts['removed']}")
    dropped_non_tech = (screen_counts.get('dropped_title_blocklist', 0)
                        + screen_counts.get('dropped_role_not_accepted', 0))
    log(f"Excluded (non-tech):   {dropped_non_tech}")
    log(f"Excluded (not software): {screen_counts.get('dropped_off_track', 0)}")
    log(f"Excluded (too senior): {screen_counts.get('dropped_above_cohort', 0)}")
    log(f"Time taken: {minutes}m {seconds}s")
    if sheet_url:
        log(f"Sheet URL: {sheet_url}")
    else:
        log("Sheet URL: Not available (write failed)")
    log("\nNext run: Tomorrow at the same time (via GitHub Actions)")
    log("=" * 70)

    # The Jobs sheet not being updated is still a run that needs a red X in
    # GitHub Actions -- but only now, after every step that could still
    # salvage something from the run has had its turn.
    if jobs_write_failed:
        log("\n⚠ The Jobs sheet was NOT updated this run.")
        log("  A rescue copy of today's jobs is saved in")
        log("  data/cache/combined_jobs_fallback.json")
        sys.exit(1)


if __name__ == '__main__':
    main()