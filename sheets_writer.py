#!/usr/bin/env python3
"""
sheets_writer.py — Write enriched jobs to Google Sheets
========================================================
Writes job data to a Google Sheet with:
  - Auto-sorting (newest first)
  - Deduplication
  - Formatted columns
  - Stable public URL

Requires:
  - pip install gspread oauth2client
  - GOOGLE_SHEETS_CREDS environment variable (service account JSON)
  - Sheet must be shared with service account email

Usage:
    python sheets_writer.py -i *_enriched.json -s "1abc123..." --sheet-name "Jobs"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    print("Missing: pip install gspread oauth2client")
    sys.exit(1)


def log(msg: str):
    """Simple logging."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_jobs(path: Path) -> list:
    """Load jobs from JSON file."""
    raw = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(raw, dict):
        return raw.get('jobs', [])
    if isinstance(raw, list):
        return raw
    return []


def authenticate_sheets(creds_json: str) -> gspread.Client:
    """Authenticate with Google Sheets API using service account."""
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # Parse creds from JSON string
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    return client


def format_job_row(job: dict) -> list:
    """Convert job dict to spreadsheet row."""
    # Helper to safely get values
    def get(key, default=""):
        val = job.get(key, default)
        return str(val) if val is not None else default
    
    # Format skills as bullet list
    must_skills = get('must_have_skills', '')
    if must_skills:
        must_skills = "• " + must_skills.replace(", ", "\n• ")
    
    nice_skills = get('nice_to_have_skills', '')
    if nice_skills:
        nice_skills = "• " + nice_skills.replace(", ", "\n• ")
    
    # Format salary
    salary_str = ""
    salary_min = job.get('salary_min')
    salary_max = job.get('salary_max')
    currency = get('salary_currency', '').upper()
    if salary_min or salary_max:
        if salary_min and salary_max:
            salary_str = f"{currency} {salary_min:,.0f} - {salary_max:,.0f}"
        elif salary_min:
            salary_str = f"{currency} {salary_min:,.0f}+"
        elif salary_max:
            salary_str = f"Up to {currency} {salary_max:,.0f}"
    
    return [
        get('date_posted'),                    # Date Posted
        get('title'),                          # Job Title
        get('company'),                        # Company
        get('primary_role'),                   # Role Category
        get('location'),                       # Location
        get('workplace_policy').title(),       # Remote/Hybrid/Office
        must_skills,                           # Required Skills
        nice_skills,                           # Nice-to-Have Skills
        get('experience_years'),               # Years Experience
        get('job_level').title(),              # Level
        get('employment_type').title(),        # Employment Type
        salary_str,                            # Salary Range
        get('blurb'),                          # Summary
        get('source').title(),                 # Source
        get('job_url'),                        # Apply Link
    ]


def write_to_sheet(jobs: list, spreadsheet_id: str, sheet_name: str = "Jobs"):
    """
    Write jobs to Google Sheet with formatting and sorting.
    
    Args:
        jobs: List of job dicts
        spreadsheet_id: Google Sheets ID (from URL)
        sheet_name: Name of worksheet (default: "Jobs")
    """
    # Get credentials from environment
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDS')
    if not creds_json:
        log("Error: GOOGLE_SHEETS_CREDS environment variable not set")
        sys.exit(1)
    
    log("Authenticating with Google Sheets...")
    client = authenticate_sheets(creds_json)
    
    # Open spreadsheet
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        log(f"Opened spreadsheet: {spreadsheet.title}")
    except Exception as e:
        log(f"Error opening spreadsheet: {e}")
        log("Make sure the sheet is shared with your service account email")
        sys.exit(1)
    
    # Get or create worksheet
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        log(f"Using existing worksheet: {sheet_name}")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=15)
        log(f"Created new worksheet: {sheet_name}")
    
    # Deduplicate jobs by URL
    seen_urls = set()
    unique_jobs = []
    for job in jobs:
        url = job.get('job_url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)
        elif not url:
            # Jobs without URL (shouldn't happen, but handle gracefully)
            unique_jobs.append(job)
    
    log(f"Writing {len(unique_jobs)} unique jobs (from {len(jobs)} total)...")
    
    # Sort by date (newest first)
    unique_jobs.sort(
        key=lambda j: j.get('date_posted', '0000-00-00'),
        reverse=True
    )
    
    # Prepare header row
    headers = [
        "Date Posted", "Job Title", "Company", "Role Category", "Location",
        "Work Policy", "Required Skills", "Nice-to-Have Skills", 
        "Years Exp", "Level", "Type", "Salary", "Summary", "Source", "Apply Link"
    ]
    
    # Prepare data rows
    rows = [headers] + [format_job_row(job) for job in unique_jobs]
    
    # Clear existing data
    worksheet.clear()
    
    # Write all data at once (more efficient than row-by-row)
    worksheet.update(rows, value_input_option='USER_ENTERED')
    
    log(f"✓ Wrote {len(unique_jobs)} jobs to sheet")
    
    # Format header row
    worksheet.format('A1:O1', {
        'textFormat': {'bold': True},
        'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2},
        'horizontalAlignment': 'LEFT',
        'textFormat': {'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
    })
    
    # Freeze header row
    worksheet.freeze(rows=1)
    
    # Auto-resize columns
    worksheet.columns_auto_resize(0, 14)
    
    # Format date column
    worksheet.format('A2:A1000', {'numberFormat': {'type': 'DATE', 'pattern': 'yyyy-mm-dd'}})
    
    # Wrap text in description columns
    worksheet.format('G2:H1000', {'wrapStrategy': 'WRAP'})  # Skills
    worksheet.format('M2:M1000', {'wrapStrategy': 'WRAP'})  # Summary
    
    log("✓ Applied formatting")
    
    # Get sheet URL
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    log(f"\nSheet URL: {sheet_url}")
    log(f"Public sharing: Make sure sheet is set to 'Anyone with the link can view'")
    
    return sheet_url


def main():
    parser = argparse.ArgumentParser(description="Write enriched jobs to Google Sheets")
    parser.add_argument('-i', '--input', nargs='+', required=True,
                        help='Input enriched JSON file(s)')
    parser.add_argument('-s', '--spreadsheet-id', required=True,
                        help='Google Sheets ID (from URL)')
    parser.add_argument('--sheet-name', default='Jobs',
                        help='Worksheet name (default: Jobs)')
    args = parser.parse_args()
    
    base = Path.cwd()
    
    # Load all jobs from all input files
    all_jobs = []
    for pattern in args.input:
        # Support glob patterns
        matched = list(base.glob(pattern)) if '*' in pattern or '?' in pattern else []
        if matched:
            paths = matched
        else:
            paths = [base / pattern]
        
        for path in paths:
            if not path.exists():
                log(f"Warning: {path} not found, skipping")
                continue
            
            jobs = load_jobs(path)
            log(f"Loaded {len(jobs)} jobs from {path.name}")
            all_jobs.extend(jobs)
    
    if not all_jobs:
        log("Error: No jobs found in input files")
        sys.exit(1)
    
    log(f"\nTotal jobs loaded: {len(all_jobs)}")
    
    # Write to sheet
    write_to_sheet(all_jobs, args.spreadsheet_id, args.sheet_name)
    
    log("\n✓ Done!")


if __name__ == '__main__':
    main()
