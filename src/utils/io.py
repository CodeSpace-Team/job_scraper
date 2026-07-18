import json
from pathlib import Path
from src.utils.logging import log

def save_jobs(jobs, output_file, write_csv=False, source_name=""):
    """Save jobs to JSON and optionally CSV."""
    output_path = Path(output_file)

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