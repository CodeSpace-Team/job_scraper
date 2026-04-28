#!/usr/bin/env python3
"""
sheets_writer.py — Write enriched jobs to Google Sheets
========================================================
Writes job data to a Google Sheet with:
  - Auto-sorting (newest first)
  - Deduplication
  - Formatted columns
  - Date Added to Sheet tracking
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


def format_job_row(job: dict, date_added: str = None) -> list:
    """Convert job dict to spreadsheet row.
    
    Args:
        job: Job dictionary
        date_added: Timestamp when job was added to sheet (defaults to now)
    """
    if date_added is None:
        date_added = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
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
        date_added,                            # Date Added to Sheet (Column A)
        get('date_posted'),                    # Date Job Posted (Column B)
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
        get('job_url'),                        # Apply Link (Column P) - THE ACTUAL URL!
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
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=16)
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
    
    log(f"Processing {len(unique_jobs)} unique jobs (from {len(jobs)} total)...")
    
    # Sort by date (newest first)
    unique_jobs.sort(
        key=lambda j: j.get('date_posted', '0000-00-00'),
        reverse=True
    )
    
    # Prepare header row (16 columns)
    headers = [
        "Date Added to Sheet", "Date Job Posted", "Job Title", "Company", "Role Category", 
        "Location", "Work Policy", "Required Skills", "Nice-to-Have Skills", 
        "Years Exp", "Level", "Type", "Salary", "Summary", "Source", "Apply Link"
    ]
    
    # STEP 1 — Check if sheet needs migration (old 15-column format)
    try:
        existing_headers = worksheet.row_values(1)
        needs_migration = (len(existing_headers) == 15 and existing_headers[0] == "Date Posted")
        
        if needs_migration:
            log("⚠️  Detected old 15-column format - migrating to new 16-column format...")
            
            # Read all existing data (skip header row)
            all_values = worksheet.get_all_values()
            if len(all_values) > 1:
                existing_data = all_values[1:]  # Skip header
                
                # Extract URLs from old column 15 (Apply Link)
                existing_urls = set()
                for row in existing_data:
                    if len(row) >= 15 and row[14]:  # Column O (index 14) in old format
                        existing_urls.add(str(row[14]).strip())
                
                log(f"  Found {len(existing_data)} existing jobs to migrate")
            else:
                existing_data = []
                existing_urls = set()
            
            # Clear the entire sheet
            worksheet.clear()
            
            # Write new headers
            worksheet.update([headers], value_input_option='USER_ENTERED')
            
            # Migrate existing data (add Date Added column at the start)
            if existing_data:
                migration_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                migrated_rows = []
                for row in existing_data:
                    # Prepend the Date Added timestamp to shift everything right
                    migrated_row = [migration_timestamp] + row
                    migrated_rows.append(migrated_row)
                
                worksheet.append_rows(migrated_rows, value_input_option='USER_ENTERED')
                log(f"  ✓ Migrated {len(migrated_rows)} existing jobs")
            
            existing = len(existing_data)
        else:
            # Normal read of existing data
            try:
                existing = worksheet.get_all_records()
                existing_urls = set(str(row.get('Apply Link', '')).strip() for row in existing if row.get('Apply Link'))
            except:
                existing = []
                existing_urls = set()
    except:
        # Empty sheet or error reading
        existing = []
        existing_urls = set()
        needs_migration = False

    # STEP 2 — Filter only new jobs
    new_jobs = [job for job in unique_jobs if str(job.get('job_url', '')).strip() not in existing_urls]

    # existing can be either a list (normal read) or an int (after migration)
    existing_count = len(existing) if isinstance(existing, list) else existing
    log(f"Found {existing_count} existing jobs in sheet")
    log(f"Identified {len(new_jobs)} new jobs to add")

    # STEP 3 — Write logic
    has_existing = (isinstance(existing, list) and len(existing) > 0) or (isinstance(existing, int) and existing > 0)
    
    if not has_existing and not needs_migration:
        # First run → write everything with headers
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = [headers] + [format_job_row(job, now) for job in unique_jobs]
        worksheet.update(rows, value_input_option='USER_ENTERED')
        log(f"✓ Wrote {len(unique_jobs)} jobs (initial load)")
    else:
        # Append only new jobs
        if new_jobs:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_rows = [format_job_row(job, now) for job in new_jobs]
            worksheet.append_rows(new_rows, value_input_option='USER_ENTERED')
            log(f"✓ Appended {len(new_jobs)} new jobs")
        else:
            log("✓ No new jobs to append")

    # FORMATTING
    # Header row: teal background, white bold text
    worksheet.format('A1:P1', {
        'textFormat': {'bold': True, 'fontSize': 11, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
        'backgroundColor': {'red': 0, 'green': 0.6, 'blue': 0.5},  # Teal
        'horizontalAlignment': 'LEFT'
    })

    # Freeze header row
    worksheet.freeze(rows=1)
    
    # Auto-resize columns
    worksheet.columns_auto_resize(0, 15)

    # Date formatting
    worksheet.format('A2:A1000', {'numberFormat': {'type': 'DATE_TIME', 'pattern': 'yyyy-mm-dd hh:mm:ss'}})
    worksheet.format('B2:B1000', {'numberFormat': {'type': 'DATE', 'pattern': 'yyyy-mm-dd'}})
    
    # Skills columns: wrap text
    worksheet.format('H2:I1000', {'wrapStrategy': 'WRAP'})
    
    # Summary column: wrap text
    worksheet.format('N2:N1000', {'wrapStrategy': 'WRAP'})

    # Sort by Date Added to Sheet (Column A) descending (newest first)
    worksheet.sort((1, 'des'))

    log("✓ Applied formatting and sorting")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    log(f"\n✓ Sheet updated successfully!")
    log(f"URL: {sheet_url}")

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