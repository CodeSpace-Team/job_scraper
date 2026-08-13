"""
sheets.py — Google Sheets Writer for Job Data
==============================================

Writes enriched job data to a Google Sheet with professional formatting.

Features:
---------
- Append-only updates (never overwrites existing data)
- Automatic deduplication by URL
- Migration from old 15-column format to new 16-column format
- Formatted columns (date, currency, wrapped text)
- Sorted by Date Added (newest first)
- Teal header with white bold text
- Frozen header row
- Auto-resized columns

Data Flow:
----------
1. Read existing sheet → extract existing URLs
2. Filter new jobs (URL not in existing sheet)
3. Append new jobs with timestamp
4. Apply formatting and sorting

Columns (16 columns):
--------------------
A: Date Added to Sheet    |  I: Nice-to-Have Skills
B: Date Job Posted        |  J: Years Exp
C: Job Title              |  K: Level
D: Company                |  L: Type
E: Role Category          |  M: Salary
F: Location               |  N: Summary
G: Work Policy            |  O: Source
H: Required Skills        |  P: Apply Link

Requirements:
-------------
- GOOGLE_SHEETS_CREDS env var (service account JSON)
- Sheet must be shared with service account email
- Sheet ID from URL

Dependencies:
-------------
- gspread: Google Sheets API client
- oauth2client: Service account authentication

Environment:
------------
    GOOGLE_SHEETS_CREDS: JSON string of service account credentials

Usage (Standalone):
-------------------
    python -m src.writers.sheets -i data/cache/enriched.json -s "1abc123..."

Usage (Imported):
-----------------
    from src.writers import sheets
    sheets.write_to_sheet(jobs, spreadsheet_id, sheet_name="Jobs")
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple, Union

from src.pipeline.dedupe import is_comparable, key_from_row, duplicate_key
from src.utils import log

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    log("ERROR: gspread or oauth2client not installed.")
    log("Run: pip install gspread oauth2client")
    sys.exit(1)


# ─── Constants ──────────────────────────────────────────────────────────────

# 16-column header for Google Sheet
HEADERS: List[str] = [
    "Date Added to Sheet",
    "Date Job Posted",
    "Job Title",
    "Company",
    "Role Category",
    "Location",
    "Work Policy",
    "Required Skills",
    "Nice-to-Have Skills",
    "Years Exp",
    "Level",
    "Type",
    "Salary",
    "Summary",
    "Source",
    "Apply Link",
]

EXCLUDE_HEADERS: List[str] = [
    "Date Excluded",
    "Stage",
    "Reason",
    "Job Title",
    "Company",
    "Role Label",
    "Location",
    "Source",
    "Apply Link",
    "Description",
    "Needs Review",
]
"""
Columns for the Exclude tab (F1, F4).

The role label and the description are carried deliberately: the brief wants
the dropped rows to be usable later as training data for what to exclude, and
neither is recoverable once the job is gone.

Needs Review marks a drop that rests on softer evidence -- a level read from
the body text rather than the title, or a years figure that came from a feed
rather than the ad's own words. Filter on it to spot wrong drops quickly.
"""

SHEET_SCOPES: List[str] = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]


# ─── Helper Functions ──────────────────────────────────────────────────────

def _safe_job_get(job: Dict[str, Any], key: str, default: str = "") -> str:
    """
    Safely get a value from a job dictionary, converting None to default.

    Args:
        job: Job dictionary
        key: Key to look up
        default: Default value if key is missing or value is None

    Returns:
        String value (always a string)
    """
    val = job.get(key, default)
    return str(val) if val is not None else default


def load_jobs(path: Path) -> List[Dict[str, Any]]:
    """
    Load jobs from a JSON file.

    Supports two formats:
        - {"jobs": [...]}  (preferred)
        - [...]            (flat list)

    Args:
        path: Path to JSON file

    Returns:
        List of job dictionaries (empty list if file is invalid)
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


def authenticate_sheets(creds_json: str) -> gspread.Client:
    """
    Authenticate with Google Sheets API using service account credentials.

    Args:
        creds_json: JSON string containing service account credentials

    Returns:
        Authenticated gspread client

    Raises:
        json.JSONDecodeError: If credentials JSON is invalid
        Exception: If authentication fails
    """
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SHEET_SCOPES) # type: ignore
    return gspread.authorize(creds) #type: ignore


def format_salary(job: Dict[str, Any]) -> str:
    """
    Format salary information as a human-readable string.

    Args:
        job: Job dictionary with salary_min, salary_max, salary_currency

    Returns:
        Formatted salary string (e.g., "ZAR 50,000 - 80,000")
    """
    salary_min = job.get('salary_min')
    salary_max = job.get('salary_max')
    currency = _safe_job_get(job, 'salary_currency', '').upper()

    if not salary_min and not salary_max:
        return ""

    if salary_min and salary_max:
        return f"{currency} {salary_min:,.0f} - {salary_max:,.0f}"
    if salary_min:
        return f"{currency} {salary_min:,.0f}+"
    if salary_max:
        return f"Up to {currency} {salary_max:,.0f}"

    return ""


def format_skills(skills: str) -> str:
    """
    Format a comma-separated skill list as a bulleted list.

    Args:
        skills: Comma-separated skill strings

    Returns:
        Bulleted list (e.g., "• Python\n• Django")
    """
    if not skills:
        return ""
    return "• " + skills.replace(", ", "\n• ")


def format_job_row(job: Dict[str, Any], date_added: Optional[str] = None) -> List[str]:
    """
    Convert a job dictionary to a spreadsheet row (16 columns).

    Args:
        job: Job dictionary
        date_added: Timestamp when job was added (defaults to now)

    Returns:
        List of 16 strings representing the row
    """
    if date_added is None:
        date_added = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Format skills
    must_skills = format_skills(_safe_job_get(job, 'must_have_skills'))
    nice_skills = format_skills(_safe_job_get(job, 'nice_to_have_skills'))

    # Format salary
    salary_str = format_salary(job)

    return [
        date_added,                                    # A: Date Added
        _safe_job_get(job, 'date_posted'),            # B: Date Posted
        _safe_job_get(job, 'title'),                  # C: Job Title
        _safe_job_get(job, 'company'),                # D: Company
        _safe_job_get(job, 'primary_role'),           # E: Role Category
        _safe_job_get(job, 'location'),               # F: Location
        _safe_job_get(job, 'workplace_policy').title(),  # G: Work Policy
        must_skills,                                  # H: Required Skills
        nice_skills,                                  # I: Nice-to-Have Skills
        _safe_job_get(job, 'experience_years'),       # J: Years Exp
        _safe_job_get(job, 'job_level').title(),      # K: Level
        _safe_job_get(job, 'employment_type').title(), # L: Type
        salary_str,                                   # M: Salary
        _safe_job_get(job, 'blurb'),                  # N: Summary
        _safe_job_get(job, 'source').title(),         # O: Source
        _safe_job_get(job, 'job_url'),                # P: Apply Link
    ]

def format_exclude_row(
    job: Dict[str, Any],
    date_excluded: Optional[str] = None,
) -> List[str]:
    """
        Convert an excluded job into an Exclude tab row.

    Args:
        job: Job dictionary carrying 'excluded_stage' and 'excluded_reason'.
        date_excluded: Timestamp of the drop (defaults to now).

    Returns:
        One string per column in EXCLUDE_HEADERS.
    """
    if date_excluded is None:
        date_excluded = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    return [
        date_excluded,                                    # A: Date Excluded
        _safe_job_get(job, 'excluded_stage'),             # B: Stage
        _safe_job_get(job, 'excluded_reason'),            # C: Reason
        _safe_job_get(job, 'title'),                      # D: Job Title
        _safe_job_get(job, 'company'),                    # E: Company
        _safe_job_get(job, 'primary_role'),               # F: Role Label
        _safe_job_get(job, 'location'),                   # G: Location
        _safe_job_get(job, 'source').title(),             # H: Source
        _safe_job_get(job, 'job_url'),                    # I: Apply Link
        _safe_job_get(job, 'description_snippet')[:500],  # J: Description
        "YES" if job.get('needs_review') else "",          # K: Needs Review
    ]
    


def deduplicate_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate jobs by URL.

    Jobs without a URL are kept (but won't be deduplicated).

    Args:
        jobs: List of job dictionaries

    Returns:
        List of unique jobs
    """
    seen_urls: Set[str] = set()
    unique: List[Dict[str, Any]] = []

    for job in jobs:
        url = job.get('job_url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(job)
        elif not url:
            # Jobs without URL - keep them (they might be valid)
            unique.append(job)

    return unique


# ─── Main Writer ────────────────────────────────────────────────────────────

def write_to_sheet(
    jobs: List[Dict[str, Any]],
    spreadsheet_id: str,
    sheet_name: str = "Jobs"
) -> str:
    """
    Write enriched jobs to a Google Sheet with formatting.

    Args:
        jobs: List of job dictionaries
        spreadsheet_id: Google Sheets ID (from URL)
        sheet_name: Name of worksheet (default: "Jobs")

    Returns:
        URL of the updated spreadsheet

    Raises:
        SystemExit: If credentials are missing or authentication fails
        Exception: If sheet operations fail

    Note:
        This is an append-only operation. Existing jobs are never overwritten.
        Deduplication is based on the 'job_url' field.
    """
    # ── Authentication ──
    creds_json = os.environ.get('GOOGLE_SHEETS_CREDS')
    if not creds_json:
        log("ERROR: GOOGLE_SHEETS_CREDS environment variable not set")
        log("Get credentials from Google Cloud Console -> Service Accounts")
        sys.exit(1)

    log("Authenticating with Google Sheets...")
    client = authenticate_sheets(creds_json)

    # ── Open Spreadsheet ──
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        log(f"Opened spreadsheet: {spreadsheet.title}")
    except Exception as e:
        log(f"ERROR: Could not open spreadsheet: {e}")
        log("Make sure the sheet is shared with your service account email")
        sys.exit(1)

    # ── Get or Create Worksheet ──
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        log(f"Using existing worksheet: {sheet_name}")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=16)
        log(f"Created new worksheet: {sheet_name}")

    # ── Deduplicate and Sort ──
    unique_jobs = deduplicate_jobs(jobs)
    log(f"Processing {len(unique_jobs)} unique jobs (from {len(jobs)} total)...")

    unique_jobs.sort(
        key=lambda j: j.get('date_posted', '0000-00-00'),
        reverse=True
    )

    # ── Check for Migration (old 15-column format) ──
    needs_migration = False
    # ── Read Existing URLs ──
    existing_urls: Set[str] = set()
    existing_keys: Set[Tuple[str, str, str]] = set()
    existing_data: List[List[str]] = []

    try:
        existing_headers = worksheet.row_values(1)
        needs_migration = (len(existing_headers) == 15 and existing_headers[0] == "Date Posted")

        if needs_migration:
            log("⚠️  Detected old 15-column format - migrating to new 16-column format...")

            all_values = worksheet.get_all_values()
            if len(all_values) > 1:
                existing_data = all_values[1:]  # Skip header

                for row in existing_data:
                    if len(row) >= 15 and row[14]:  # Column O (index 14)
                        existing_urls.add(str(row[14]).strip())

                log(f"  Found {len(existing_data)} existing jobs to migrate")
            else:
                existing_data = []
                existing_urls = set()

            # Clear and rewrite with new headers
            worksheet.clear()
            worksheet.update([HEADERS], value_input_option='USER_ENTERED') # type: ignore

            # Migrate existing data
            if existing_data:
                migration_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                migrated_rows = [
                    [migration_timestamp] + row for row in existing_data
                ]
                worksheet.append_rows(migrated_rows, value_input_option='USER_ENTERED') # type: ignore
                log(f"  ✓ Migrated {len(migrated_rows)} existing jobs")

            existing_count = len(existing_data)

        else:
            # Normal read of existing data
            try:
                records = worksheet.get_all_records()
                existing_urls = {
                    str(row.get('Apply Link', '')).strip()
                    for row in records
                    if row.get('Apply Link')
                }
                                # The same key the F9 step uses, rebuilt from the rows already
                # in the sheet. This is what catches a re-post: an advert from
                # weeks ago reappearing under a fresh web address would sail
                # past the Apply Link check and land as a second row.
                existing_keys = {
                    key for key in (key_from_row(row) for row in records)
                    if is_comparable(key)
                }
                existing_count = len(records)
            except Exception:
                existing_urls = set()
                existing_keys = set()
                existing_count = 0

    except Exception:
        # Empty sheet or error reading
        existing_urls = set()
        existing_count = 0
        needs_migration = False

    # ── Filter New Jobs ──
    # A job is new only if neither its web address nor its title/company/city
    # already appears in the sheet (F9).
    new_jobs = []
    reposts = 0

    for job in unique_jobs:
        if str(job.get('job_url', '')).strip() in existing_urls:
            continue
        key = duplicate_key(job)
        if is_comparable(key) and key in existing_keys:
            reposts += 1
            continue
        new_jobs.append(job)

    log(f"Found {existing_count} existing jobs in sheet")
    if reposts:
        log(f"Skipped {reposts} re-posts already in the sheet under another link")
    log(f"Identified {len(new_jobs)} new jobs to add")

    # ── Write to Sheet ──
    has_existing = existing_count > 0

    if not has_existing and not needs_migration:
        # First run: write everything with headers
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        rows = [HEADERS] + [format_job_row(job, now) for job in unique_jobs]
        worksheet.update(rows, value_input_option='USER_ENTERED') # type: ignore
        log(f"✓ Wrote {len(unique_jobs)} jobs (initial load)")
    else:
        # Append only new jobs
        if new_jobs:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_rows = [format_job_row(job, now) for job in new_jobs]
            worksheet.append_rows(new_rows, value_input_option='USER_ENTERED') # type: ignore
            log(f"✓ Appended {len(new_jobs)} new jobs")
        else:
            log("✓ No new jobs to append")

    # ── Formatting ──
    # Header: teal background, white bold text
    worksheet.format('A1:P1', {
        'textFormat': {
            'bold': True,
            'fontSize': 11,
            'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
        },
        'backgroundColor': {'red': 0, 'green': 0.6, 'blue': 0.5},
        'horizontalAlignment': 'LEFT'
    })

    # Freeze header row
    worksheet.freeze(rows=1)

    # Auto-resize columns
    worksheet.columns_auto_resize(0, 15)

    # Date formatting
    worksheet.format('A2:A1000', {
        'numberFormat': {'type': 'DATE_TIME', 'pattern': 'yyyy-mm-dd hh:mm:ss'}
    })
    worksheet.format('B2:B1000', {
        'numberFormat': {'type': 'DATE', 'pattern': 'yyyy-mm-dd'}
    })

    # Skills and Summary: wrap text
    worksheet.format('H2:I1000', {'wrapStrategy': 'WRAP'})
    worksheet.format('N2:N1000', {'wrapStrategy': 'WRAP'})

    # Sort by Date Added (Column A) descending
    worksheet.sort((1, 'des'))

    log("✓ Applied formatting and sorting")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    log(f"\n✓ Sheet updated successfully!")
    log(f"URL: {sheet_url}")

    return sheet_url

def write_exclude_tab(
    jobs: List[Dict[str, Any]],
    spreadsheet_id: str,
    sheet_name: str = "Exclude"
) -> int:
    """
    Append excluded jobs to the Exclude tab (F1).

    Dropped jobs are never deleted. They are appended here with the reason
    they were dropped, so the filter can be reviewed and the rows can later
    be used to train on what to exclude.

    Append-only and deduplicated by Apply Link, exactly like the Jobs tab, so
    re-running the pipeline on the same day does not double up the rows.

    Args:
        jobs: Excluded job dictionaries, carrying 'excluded_reason'.
        spreadsheet_id: Google Sheets ID (from URL).
        sheet_name: Worksheet name (default: "Exclude").

    Returns:
        The number of rows actually appended.

    Raises:
        SystemExit: If credentials are missing.
    """
    if not jobs:
        log("No excluded jobs to write.")
        return 0

    creds_json = os.environ.get('GOOGLE_SHEETS_CREDS')
    if not creds_json:
        log("ERROR: GOOGLE_SHEETS_CREDS environment variable not set")
        sys.exit(1)

    client = authenticate_sheets(creds_json)
    spreadsheet = client.open_by_key(spreadsheet_id)

    # ── Get or Create Worksheet ──
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        log(f"Using existing worksheet: {sheet_name}")
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name, rows=2000, cols=len(EXCLUDE_HEADERS)
        )
        worksheet.update([EXCLUDE_HEADERS], value_input_option='USER_ENTERED')  # type: ignore
        log(f"Created new worksheet: {sheet_name}")

    # ── Repair the Header Row ──
    # The tab may predate a column being added -- the Needs Review column
    # arrived with F4, after the tab already held F1's drops. Existing rows
    # keep their values and simply have the new column blank; the header row
    # has to name it so that reading by header, and every future append,
    # stay lined up.
    if worksheet.col_count < len(EXCLUDE_HEADERS):
        worksheet.resize(cols=len(EXCLUDE_HEADERS))

    try:
        current_headers = worksheet.row_values(1)
    except Exception:
        current_headers = []

    if current_headers and list(current_headers) != EXCLUDE_HEADERS:
        worksheet.update([EXCLUDE_HEADERS], value_input_option='USER_ENTERED')  # type: ignore
        log(f"Updated the '{sheet_name}' header row "
            f"({len(current_headers)} -> {len(EXCLUDE_HEADERS)} columns)")

    # ── Read Existing URLs ──

    # ── Read Existing URLs ──
    existing_urls: Set[str] = set()
    try:
        for row in worksheet.get_all_records():
            url = str(row.get('Apply Link', '')).strip()
            if url:
                existing_urls.add(url)
    except Exception:
        # Empty tab, or a header row that has not been written yet.
        existing_urls = set()

    # ── Append New Rows Only ──
    new_jobs = [
        job for job in jobs
        if str(job.get('job_url', '')).strip() not in existing_urls
    ]

    if not new_jobs:
        log("✓ No new excluded jobs to append")
        return 0

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows = [format_exclude_row(job, now) for job in new_jobs]
    worksheet.append_rows(rows, value_input_option='USER_ENTERED')  # type: ignore

    # ── Formatting ──
    last_col = chr(ord('A') + len(EXCLUDE_HEADERS) - 1)
    worksheet.format(f'A1:{last_col}1', {
        'textFormat': {
            'bold': True,
            'fontSize': 11,
            'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}
        },
        'backgroundColor': {'red': 0.7, 'green': 0.25, 'blue': 0.25},
        'horizontalAlignment': 'LEFT'
    })
    worksheet.freeze(rows=1)

    log(f"✓ Appended {len(new_jobs)} excluded jobs to '{sheet_name}'")
    return len(new_jobs)


# ─── Standalone Entry Point ────────────────────────────────────────────────

def main() -> None:
    """
    Command-line entry point for standalone sheet writer.
    """
    parser = argparse.ArgumentParser(
        description="Write enriched jobs to Google Sheets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.writers.sheets -i data/cache/enriched.json -s "1abc123..."
    python -m src.writers.sheets -i *.json -s "1abc123..." --sheet-name "Jobs"

Environment:
    GOOGLE_SHEETS_CREDS must be set in environment

Note:
    Requires service account credentials in GOOGLE_SHEETS_CREDS.
    Sheet must be shared with the service account email.
        """
    )
    parser.add_argument(
        '-i', '--input', nargs='+', required=True,
        help='Input enriched JSON file(s) (supports wildcards)'
    )
    parser.add_argument(
        '-s', '--spreadsheet-id', required=True,
        help='Google Sheets ID (from URL)'
    )
    parser.add_argument(
        '--sheet-name', default='Jobs',
        help='Worksheet name (default: Jobs)'
    )
    args = parser.parse_args()

    base = Path.cwd()

    # Load all jobs from all input files
    all_jobs: List[Dict[str, Any]] = []

    for pattern in args.input:
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
            if jobs:
                log(f"Loaded {len(jobs)} jobs from {path.name}")
                all_jobs.extend(jobs)
            else:
                log(f"  No jobs found in {path.name}")

    if not all_jobs:
        log("Error: No jobs found in input files")
        sys.exit(1)

    log(f"\nTotal jobs loaded: {len(all_jobs)}")

    # Write to sheet
    write_to_sheet(all_jobs, args.spreadsheet_id, args.sheet_name)

    log("\n✓ Done!")


if __name__ == '__main__':
    main()