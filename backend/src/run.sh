##############################################################################
# Job Scraper Pipeline - One Command to Rule Them All                        #
##############################################################################
#
# PURPOSE:
#   Run the complete job scraping pipeline and generate:
#   - A combined CSV file with all jobs from OfferZen, Indeed, and PNet.
#   - A summary (job counts & sample titles) printed in the terminal.
#   - Optionally run tests before the pipeline to ensure code quality.
#
# ─── PREREQUISITES ──────────────────────────────────────────────────────────
#
#   First activate the virtual environment:
#     source venv/bin/activate   # Linux/Mac
#     venv\Scripts\activate      # Windows
#
#   Make the script executable (first time only):
#     chmod +x run.sh
#
# ─── USAGE ──────────────────────────────────────────────────────────────────
#
#   ./run.sh                    # Run with default settings (skip LinkedIn)
#   ./run.sh --skip-pnet        # Skip PNet (faster runs, ~2 min)
#   ./run.sh --skip-enrichment  # Skip AI enrichment (faster, no Claude API)
#   ./run.sh --skip-indeed      # Skip Indeed
#   ./run.sh --skip-offerzen    # Skip OfferZen
#   ./run.sh --scraper-only     # Only run scrapers, skip enrichment & sheets
#
# ─── TESTING OPTIONS ──────────────────────────────────────────────────────
#
#   ./run.sh --test             # Run all tests (unit + integration) before pipeline
#   ./run.sh --unit             # Run only unit tests before pipeline
#   ./run.sh --integration      # Run only integration tests before pipeline
#   ./run.sh --test --skip-pnet # Run tests, then pipeline (skipping PNet)
#
# ─── OPTIONS ───────────────────────────────────────────────────────────────
#
#   --skip-pnet         Skip PNet scraper (saves ~6-8 minutes)
#   --skip-enrichment   Skip AI enrichment (saves ~1-2 minutes)
#   --skip-indeed       Skip Indeed scraper
#   --skip-offerzen     Skip OfferZen scraper
#   --skip-linkedin     Skip LinkedIn (default, LinkedIn is disabled)
#   --scraper-only      Only run scrapers, skip enrichment and sheets
#   --test              Run all tests (unit + integration) before pipeline
#   --unit              Run only unit tests before pipeline
#   --integration       Run only integration tests before pipeline
#
# ─── OUTPUT ────────────────────────────────────────────────────────────────
#
#   - Individual JSON files: data/cache/{source}_jobs.json
#   - Combined CSV: data/cache/all_jobs.csv
#   - Terminal summary: job counts & sample titles per source
#
# ─── DEPENDENCIES ──────────────────────────────────────────────────────────
#
#   - Python 3.11+ with all required packages
#   - pandas (for CSV generation)
#   - pytest (for testing)
#   - Active virtual environment (venv)
#
# ─── EXAMPLES ──────────────────────────────────────────────────────────────
#
#   # Run tests, then full pipeline
#   ./run.sh --test
#
#   # Run only unit tests, then pipeline (skipping PNet for speed)
#   ./run.sh --unit --skip-pnet
#
#   # Run integration tests only, then pipeline
#   ./run.sh --integration --skip-linkedin
#
#   # Run all tests, then full pipeline (skip PNet for speed)
#   ./run.sh --test --skip-pnet
#
#   # Scraper-only mode with tests
#   ./run.sh --test --scraper-only --skip-pnet
#
##############################################################################

# ─── Parse flags ──────────────────────────────────────────────────────────────

RUN_TESTS=false
TEST_TYPE="all"  # all, unit, integration
PIPELINE_ARGS=""

for arg in "$@"; do
    case $arg in
        --test)
            RUN_TESTS=true
            TEST_TYPE="all"
            ;;
        --unit)
            RUN_TESTS=true
            TEST_TYPE="unit"
            ;;
        --integration)
            RUN_TESTS=true
            TEST_TYPE="integration"
            ;;
        *)
            PIPELINE_ARGS="$PIPELINE_ARGS $arg"
            ;;
    esac
done

# ─── Run tests (if requested) ────────────────────────────────────────────────

if [ "$RUN_TESTS" = true ]; then
    echo "🧪 Running tests before pipeline..."
    echo ""

    case $TEST_TYPE in
        unit)
            echo "🔬 Running unit tests..."
            pytest tests/unit/ -v
            ;;
        integration)
            echo "🔗 Running integration tests..."
            pytest tests/integration/ -v
            ;;
        all)
            echo "🔬🔗 Running all tests (unit + integration)..."
            pytest tests/ -v
            ;;
    esac

    if [ $? -ne 0 ]; then
        echo "❌ Tests failed. Pipeline aborted."
        exit 1
    fi

    echo "✅ All tests passed!"
    echo ""
fi

# ─── Run pipeline ─────────────────────────────────────────────────────────────

echo "🚀 Running job scraper pipeline..."
echo "📂 Working directory: $(pwd)"
echo ""

# Run the main pipeline
python -m src.main --spreadsheet-id DUMMY --skip-linkedin --skip-enrichment $PIPELINE_ARGS

# Check if pipeline succeeded
if [ $? -ne 0 ]; then
    echo "❌ Pipeline failed. Check errors above."
    exit 1
fi

# After pipeline finishes, generate CSV and summary
echo ""
echo "📊 Generating combined CSV and summary..."
python -c "
import json
from pathlib import Path
import pandas as pd

jobs_by_source = {}
all_jobs = []

for f in Path('data/cache').glob('*_jobs.json'):
    try:
        with open(f, encoding='utf-8') as fp:
            data = json.load(fp)
            jobs = data.get('jobs', [])
            source = f.stem.replace('_jobs', '')
            jobs_by_source[source] = jobs
            all_jobs.extend(jobs)
    except Exception as e:
        print(f'⚠️ Error reading {f.name}: {e}')

# ─── Save combined CSV ───
if all_jobs:
    df = pd.DataFrame(all_jobs)
    csv_path = 'data/cache/all_jobs.csv'
    df.to_csv(csv_path, index=False)
    print(f'✅ Combined {len(all_jobs)} jobs saved to {csv_path}')
    print(f'📋 Columns: {", ".join(df.columns[:5])}... (total {len(df.columns)} columns)')
else:
    print('⚠️ No jobs found to combine.')

# ─── Print summary ───
print('\n' + '='*60)
print('📊 JOB COUNT PER SOURCE')
print('='*60)
total = 0
for source, jobs in jobs_by_source.items():
    count = len(jobs)
    total += count
    print(f'{source.capitalize():<12} {count} jobs')
print(f'{"Total":<12} {total} jobs')
print('='*60)

# ─── Sample job titles per source ───
print('\n📋 SAMPLE JOBS BY SOURCE')
print('='*60)
for source, jobs in jobs_by_source.items():
    count = len(jobs)
    display_name = source.upper()
    print(f'\n--- {display_name} ({count}) ---')
    if count == 0:
        print('  (no jobs)')
    else:
        # Show up to 5 titles, truncating long titles
        for i, job in enumerate(jobs[:5], 1):
            title = job.get('title', 'Untitled')
            company = job.get('company', '')
            if len(title) > 60:
                title = title[:57] + '...'
            print(f'  {i}. {title} {company}')
        if count > 5:
            print(f'  ... and {count - 5} more')
print('='*60)
"

echo ""
echo "✅ Done! Summary printed above."
echo "📄 Full data available in: data/cache/all_jobs.csv"
echo "   head -5 data/cache/all_jobs.csv"