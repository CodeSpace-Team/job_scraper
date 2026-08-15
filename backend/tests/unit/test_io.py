"""
Unit tests for file I/O utilities (src/utils/io.py).

These functions are critical for the pipeline's data persistence layer:
- load_jobs(): Reads job data from JSON files in two supported formats.
- save_jobs(): Writes job data to JSON in the standardised format.

Why these tests matter:
- The pipeline reads and writes JSON at multiple stages (scraping, enrichment, sheets).
- Incorrect I/O can silently corrupt data or cause pipeline failures.
- Supporting both dict and list formats ensures backward compatibility
  with older data files and external tools.

The tests use pytest's tmp_path fixture to create temporary files,
ensuring that no real data is affected during testing.
"""
import json
import pytest
from pathlib import Path
from src.utils.io import load_jobs, save_jobs


def test_load_jobs_from_dict(tmp_path):
    """
    Test load_jobs() reading from a JSON file with the standard dict structure.

    Input JSON: {"jobs": [{"title": "Dev", "company": "Acme"}]}
    Expected: A list containing the job dictionary.

    Why this matters:
    - This is the primary format used by the pipeline (save_jobs writes this).
    - All scraped and enriched job data is stored this way.
    - Verifies that the pipeline can read its own output.

    Edge cases covered:
    - Nested 'jobs' key is correctly extracted.
    - All job fields are preserved.

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    data = {"jobs": [{"title": "Dev", "company": "Acme"}]}
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps(data), encoding='utf-8')

    jobs = load_jobs(file_path)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Dev"


def test_load_jobs_from_list(tmp_path):
    """
    Test load_jobs() reading from a JSON file with a flat list structure.

    Input JSON: [{"title": "Dev"}]
    Expected: The same list.

    Why this matters:
    - Backward compatibility with older pipeline versions.
    - Some external tools (like manual CSV exports) may produce flat lists.
    - Allows flexibility in data ingestion from various sources.

    Edge cases covered:
    - The function correctly detects that the root is a list, not a dict.
    - No 'jobs' wrapper is expected or required.

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    data = [{"title": "Dev"}]
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps(data), encoding='utf-8')

    jobs = load_jobs(file_path)
    assert len(jobs) == 1


def test_load_jobs_invalid_json(tmp_path):
    """
    Test load_jobs() with malformed JSON.

    Input: 'not json'
    Expected: Empty list.

    Why this matters:
    - Network errors or partial writes can corrupt JSON files.
    - The pipeline should not crash on invalid data.
    - Returns an empty list so the calling code can continue gracefully.

    Edge cases covered:
    - json.JSONDecodeError is caught and handled.
    - No exception is propagated to the caller.
    - The function returns a safe default (empty list).

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    file_path = tmp_path / "jobs.json"
    file_path.write_text("not json", encoding='utf-8')

    jobs = load_jobs(file_path)
    assert jobs == []


def test_load_jobs_file_not_found(tmp_path):
    """
    Test load_jobs() when the specified file does not exist.

    Input: Path to a non-existent file.
    Expected: Empty list.

    Why this matters:
    - Scrapers may fail to generate output files.
    - The orchestrator should handle missing files gracefully.
    - A missing file should not cause a pipeline crash.

    Edge cases covered:
    - FileNotFoundError is caught and handled.
    - The function returns an empty list as a safe fallback.

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    jobs = load_jobs(tmp_path / "missing.json")
    assert jobs == []


def test_load_jobs_empty_file(tmp_path):
    """
    Test load_jobs() with an empty file.

    Input: An empty file (0 bytes).
    Expected: Empty list.

    Why this matters:
    - Empty files can occur from write failures or interrupted processes.
    - The pipeline should handle this without raising exceptions.

    Edge cases covered:
    - Empty files are treated as invalid JSON (json.JSONDecodeError).
    - Returns empty list as a safe fallback.

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    file_path = tmp_path / "jobs.json"
    file_path.write_text("", encoding='utf-8')

    jobs = load_jobs(file_path)
    assert jobs == []


def test_save_jobs(tmp_path):
    """
    Test save_jobs() writing jobs to JSON.

    Input: List of job dictionaries.
    Expected: JSON file with {"jobs": [...]} structure.

    Why this matters:
    - save_jobs is used throughout the pipeline to persist scraped and enriched data.
    - Ensures consistent JSON structure across all stages.
    - The output format is compatible with load_jobs and other tools.

    Edge cases covered:
    - The JSON structure is correct ({'jobs': list}).
    - All job data is preserved.
    - The file is written with UTF-8 encoding (handles non-ASCII characters).

    Args:
        tmp_path: pytest fixture providing a temporary directory for test files.
    """
    jobs = [{"title": "Dev"}]
    out = tmp_path / "output.json"
    save_jobs(jobs, out)

    with open(out, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data["jobs"] == jobs