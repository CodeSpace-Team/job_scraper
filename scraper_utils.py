#!/usr/bin/env python3
"""
scraper_utils.py — Shared utilities for all job scrapers
"""

import json
import re
from datetime import datetime
from pathlib import Path

SA_KEYWORDS = ["south africa", "cape town", "johannesburg", "durban", "pretoria", "gauteng"]


def log(msg: str):
    """Simple logging with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def clean_text(text, max_len=None):
    """Clean and normalize text."""
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r'\s+', ' ', text)
    if max_len and len(text) > max_len:
        text = text[:max_len].strip()
    return text


def parse_date(date_input):
    """
    Parse various date formats and return (date_str, time_str).
    Returns ("YYYY-MM-DD", "HH:MM:SS") or ("YYYY-MM-DD", "") if no time.
    """
    if not date_input:
        return "", ""
    
    date_str = str(date_input)
    
    # Try ISO format first (2024-01-15T10:30:00Z)
    iso_match = re.match(r'(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}:\d{2})', date_str)
    if iso_match:
        return iso_match.group(1), iso_match.group(2)
    
    # Date only (2024-01-15)
    date_match = re.match(r'(\d{4}-\d{2}-\d{2})', date_str)
    if date_match:
        return date_match.group(1), ""
    
    # Try common datetime formats
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d",
    ]:
        try:
            dt = datetime.strptime(date_str[:26], fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S") if "%H" in fmt else ""
        except (ValueError, TypeError):
            continue
    
    return "", ""


def parse_date_for_sort(date_str, time_str=""):
    """
    Convert date_str and time_str to a sortable datetime string.
    Returns ISO format for sorting: "YYYY-MM-DDTHH:MM:SS"
    """
    if not date_str:
        return "0000-00-00T00:00:00"
    
    date_part = date_str[:10]
    time_part = time_str[:8] if time_str else "00:00:00"
    
    return f"{date_part}T{time_part}"


def save_jobs(jobs, output_file, write_csv=False, source_name=""):
    """Save jobs to JSON and optionally CSV."""
    output_path = Path(output_file)
    
    # Save JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"jobs": jobs}, f, indent=2, ensure_ascii=False)
    
    log(f"Saved {len(jobs)} jobs to {output_path}")
    
    # Save CSV if requested
    if write_csv:
        try:
            import pandas as pd
            df = pd.DataFrame(jobs)
            csv_path = output_path.with_suffix('.csv')
            df.to_csv(csv_path, index=False, encoding='utf-8')
            log(f"Saved CSV to {csv_path}")
        except ImportError:
            log("pandas not installed, skipping CSV")
