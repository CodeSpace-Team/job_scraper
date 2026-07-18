#!/usr/bin/env python3
"""
main.py — CLI Entry Point for the Job Scraper Pipeline
=======================================================

This is the main entry point for the job scraping pipeline.
It delegates all argument parsing and orchestration to the
orchestrator module.

Usage:
    python -m src.main --spreadsheet-id "1abc123..."
    python -m src.main --spreadsheet-id "1abc123..." --skip-linkedin --skip-enrichment

Environment Variables:
    ANTHROPIC_API_KEY: Required for AI enrichment (optional)
    GOOGLE_SHEETS_CREDS: Required for Google Sheets writing

Note:
    This file simply delegates to src.core.orchestrator.
    All CLI arguments are defined and parsed in orchestrator.main().
"""

from src.core.orchestrator import main as orchestrator_main


def main() -> None:
    """
    Run the job scraping pipeline.

    This function delegates to the orchestrator's main() function,
    which handles all argument parsing, logging, and orchestration.
    """
    orchestrator_main()


if __name__ == "__main__":
    main()