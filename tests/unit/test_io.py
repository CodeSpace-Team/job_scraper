"""
Unit tests for file I/O utilities (src/utils/io.py).

Tests:
- load_jobs(): reads JSON with {'jobs': [...]} or flat list format.
- save_jobs(): writes JSON in the expected format.
"""
import json
import pytest
from pathlib import Path
from src.utils.io import load_jobs, save_jobs


def test_load_jobs_from_dict(tmp_path):
    """Load jobs from JSON with {'jobs': [...]} structure."""
    data = {"jobs": [{"title": "Dev", "company": "Acme"}]}
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps(data), encoding='utf-8')

    jobs = load_jobs(file_path)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Dev"


def test_load_jobs_from_list(tmp_path):
    """Load jobs from flat JSON list."""
    data = [{"title": "Dev"}]
    file_path = tmp_path / "jobs.json"
    file_path.write_text(json.dumps(data), encoding='utf-8')

    jobs = load_jobs(file_path)
    assert len(jobs) == 1


def test_load_jobs_invalid_json(tmp_path):
    """Invalid JSON returns empty list."""
    file_path = tmp_path / "jobs.json"
    file_path.write_text("not json", encoding='utf-8')

    jobs = load_jobs(file_path)
    assert jobs == []


def test_load_jobs_file_not_found(tmp_path):
    """Missing file returns empty list."""
    jobs = load_jobs(tmp_path / "missing.json")
    assert jobs == []


def test_load_jobs_empty_file(tmp_path):
    """Empty file returns empty list."""
    file_path = tmp_path / "jobs.json"
    file_path.write_text("", encoding='utf-8')

    jobs = load_jobs(file_path)
    assert jobs == []


def test_save_jobs(tmp_path):
    """Save jobs to JSON with {'jobs': [...]} format."""
    jobs = [{"title": "Dev"}]
    out = tmp_path / "output.json"
    save_jobs(jobs, out)

    with open(out, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data["jobs"] == jobs