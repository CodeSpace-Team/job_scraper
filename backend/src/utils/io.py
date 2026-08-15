"""
io.py — File I/O utilities for job data
"""

import json
from pathlib import Path
from typing import List, Dict, Any

from src.utils.logging import log


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
    except (json.JSONDecodeError, FileNotFoundError) as e:
        log(f"  ✗ Error loading {path.name}: {e}")
        return []

    if isinstance(raw, dict):
        return raw.get('jobs', [])
    if isinstance(raw, list):
        return raw
    return []


def save_jobs(jobs, output_file, write_csv=False, source_name=""):
    """Save jobs to JSON and optionally CSV."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"jobs": jobs}, f, indent=2, ensure_ascii=False)

    log(f"Saved {len(jobs)} jobs to {output_path}")

    if write_csv:
        try:
            import pandas as pd
            df = pd.DataFrame(jobs)
            csv_path = output_path.with_suffix('.csv')
            df.to_csv(csv_path, index=False, encoding='utf-8')
            log(f"Saved CSV to {csv_path}")
        except ImportError:
            log("pandas not installed, skipping CSV")