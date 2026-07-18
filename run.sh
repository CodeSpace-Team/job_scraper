##############################################################################
# Job Scraper Pipeline - One Command to Rule Them All                        #
##############################################################################
#
# PURPOSE:
#   Run the complete job scraping pipeline and generate a combined CSV file
#   with all jobs from OfferZen, Indeed, and PNet.
#
# USAGE:
# 1. Make it executable (first time only) 
# chmod +x run.sh
#   ./run.sh                    # Run with default settings (skip LinkedIn)
#   ./run.sh --skip-pnet        # Skip PNet (faster runs, ~2 min)
#   ./run.sh --skip-enrichment  # Skip AI enrichment (faster, no Claude API)
#   ./run.sh --skip-indeed      # Skip Indeed
#   ./run.sh --skip-offerzen    # Skip OfferZen
#
# OPTIONS:
#   --skip-pnet         Skip PNet scraper (saves ~6-8 minutes)
#   --skip-enrichment   Skip AI enrichment (saves ~1-2 minutes)
#   --skip-indeed       Skip Indeed scraper
#   --skip-offerzen     Skip OfferZen scraper
#   --skip-linkedin     Skip LinkedIn (default, LinkedIn is disabled)
#   --scraper-only      Only run scrapers, skip enrichment and sheets
#
# OUTPUT:
#   - Individual JSON files: data/cache/{source}_jobs.json
#   - Combined CSV: data/cache/all_jobs.csv
#   - Sample: head -5 data/cache/all_jobs.csv
#
# DEPENDENCIES:
#   - Python 3.11+ with all required packages
#   - pandas (for CSV generation)
#   - Active virtual environment (venv)
#
# EXAMPLES:
#   # Quick test run (only OfferZen + Indeed, ~2 min)
#   ./run.sh --skip-pnet
#
#   # Full run with all scrapers (10-12 min)
#   ./run.sh
#
#   # Scraper-only mode (no sheets, no AI)
#   ./run.sh --scraper-only --skip-pnet
#
##############################################################################

echo "🚀 Running job scraper pipeline..."
echo "📂 Working directory: $(pwd)"
echo ""

# Run the main pipeline
python -m src.main --spreadsheet-id DUMMY --skip-linkedin --skip-enrichment "$@"

# Check if pipeline succeeded
if [ $? -ne 0 ]; then
    echo "❌ Pipeline failed. Check errors above."
    exit 1
fi

# After pipeline finishes, combine all JSONs into a single CSV
echo ""
echo "📊 Generating combined CSV from all scraped jobs..."
python -c "
import json
import pandas as pd
from pathlib import Path

jobs = []
for f in Path('data/cache').glob('*_jobs.json'):
    try:
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
            jobs.extend(data.get('jobs', []))
    except Exception as e:
        print(f'⚠️ Error reading {f.name}: {e}')

if jobs:
    df = pd.DataFrame(jobs)
    csv_path = 'data/cache/all_jobs.csv'
    df.to_csv(csv_path, index=False)
    print(f'✅ Combined {len(jobs)} jobs saved to {csv_path}')
    print(f'📋 Columns: {", ".join(df.columns[:5])}... (total {len(df.columns)} columns)')
else:
    print('⚠️ No jobs found to combine.')
"

echo ""
echo "✅ Done! View your jobs:"
echo "   head -5 data/cache/all_jobs.csv"
echo "   Or open data/cache/all_jobs.csv in Excel/Google Sheets"