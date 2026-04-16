# GitHub Actions Job Scraper - Setup Guide

Complete guide to set up automated daily job scraping that writes to Google Sheets.

## 📋 Overview

This solution scrapes South African tech jobs from multiple sources daily and publishes them to a Google Sheet. It runs automatically on GitHub Actions (free for private repos).

**What it does:**
1. Scrapes jobs from OfferZen, Indeed, LinkedIn, and PNet
2. Enriches jobs with AI (extracts skills, levels, summaries)
3. Writes to Google Sheets (sorted newest first, deduplicated)
4. Runs daily at 8 AM SAST automatically

**Sources:**
- **OfferZen**: SA tech-specific, high quality (~50-150 jobs)
- **Indeed**: Large volume, good coverage (~200-500 jobs)
- **LinkedIn**: Comprehensive but rate-limited (~200-400 jobs)
- **PNet**: SA general jobs board (~100-300 jobs)

---

## 🚀 Quick Start (30 minutes)

### Step 1: Create Google Sheet

1. Go to [sheets.google.com](https://sheets.google.com)
2. Create a new spreadsheet
3. Name it "Bootcamp Job Board"
4. Copy the Spreadsheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/1abc123xyz.../edit
                                              ^^^^^^^^^ 
                                              This is your ID
   ```
5. Save this ID - you'll need it later

---

### Step 2: Set Up Google Cloud Service Account

1. **Go to Google Cloud Console**: https://console.cloud.google.com

2. **Create a Project**:
   - Click "Select a project" → "New Project"
   - Name: "Job Scraper"
   - Click "Create"

3. **Enable Google Sheets API**:
   - In left menu: "APIs & Services" → "Library"
   - Search: "Google Sheets API"
   - Click it, then click "Enable"

4. **Create Service Account**:
   - Left menu: "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "Service Account"
   - Name: "job-scraper-bot"
   - Click "Create and Continue"
   - Skip optional fields, click "Done"

5. **Create Service Account Key**:
   - Click on the service account you just created
   - Go to "Keys" tab
   - "Add Key" → "Create new key"
   - Choose "JSON"
   - Download the JSON file (keep it safe!)

6. **Copy Service Account Email**:
   - In the service account details, copy the email address
   - Format: `job-scraper-bot@your-project.iam.gserviceaccount.com`

---

### Step 3: Share Google Sheet with Service Account

1. Open your Google Sheet from Step 1
2. Click "Share" button (top right)
3. Paste the service account email
4. Set permission to "Editor"
5. Uncheck "Notify people"
6. Click "Share"

---

### Step 4: Get Anthropic API Key

1. Go to: https://console.anthropic.com
2. Sign up or log in
3. Go to "API Keys"
4. Click "Create Key"
5. Name it "Job Scraper"
6. Copy the key (starts with `sk-ant-...`)
7. **Important**: Save it securely - you can't see it again!

**Cost estimate**: ~$1-3/month for enriching 500-1000 jobs daily

---

### Step 5: Create GitHub Repository

1. Go to GitHub and create a new **private** repository
2. Name it something like "job-scraper"
3. Initialize with a README (optional)
4. **Important**: Make it PRIVATE (free accounts get 2,000 minutes/month for private repos)

---

### Step 6: Add Secrets to GitHub

1. Go to your repository
2. Click "Settings" → "Secrets and variables" → "Actions"
3. Click "New repository secret" for each:

**Secret 1: ANTHROPIC_API_KEY**
- Name: `ANTHROPIC_API_KEY`
- Value: Your API key from Step 4 (starts with `sk-ant-...`)

**Secret 2: GOOGLE_SHEETS_CREDS**
- Name: `GOOGLE_SHEETS_CREDS`
- Value: Copy-paste the **entire contents** of the JSON file from Step 2
  ```json
  {
    "type": "service_account",
    "project_id": "your-project-123456",
    "private_key_id": "abc123...",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...",
    ...
  }
  ```
  ⚠️ **Copy the ENTIRE JSON** (all curly braces, quotes, everything)

**Secret 3: SPREADSHEET_ID**
- Name: `SPREADSHEET_ID`
- Value: The spreadsheet ID from Step 1

---

### Step 7: Upload Code to GitHub

#### Option A: Via Web Interface (Easiest)

1. Download all the Python files from this conversation
2. In your GitHub repo, click "Add file" → "Upload files"
3. Upload these files:
   - `main_scraper.py`
   - `scraper_utils.py`
   - `offerzen_scraper.py`
   - `indeed_scraper.py`
   - `linkedin_scraper_enhanced.py`
   - `pnet_scraper.py`
   - `enrich_jobs.py`
   - `sheets_writer.py`
   - `requirements.txt`
4. Create folder `.github/workflows/` and upload:
   - `daily-scrape.yml`
5. Commit the files

#### Option B: Via Git Command Line

```bash
# Clone your repo
git clone https://github.com/yourusername/job-scraper.git
cd job-scraper

# Copy all the Python files to this directory
# Then:
git add .
git commit -m "Initial commit: Job scraper pipeline"
git push
```

---

### Step 8: Set Up LinkedIn Account (CRITICAL!)

⚠️ **LinkedIn is aggressive with rate limiting. Follow these steps carefully:**

#### Phase 1: Account Creation (Day 1)

1. **Create a dedicated LinkedIn account** (NOT your personal one):
   - Use a realistic name (e.g., "Sarah Chen" not "Bot Account")
   - Add a professional photo (use AI-generated if needed)
   - Use a real email address (not temporary)
   - Complete signup with phone verification

2. **Complete your profile thoroughly**:
   - Add work history (can be fictional but realistic)
   - List relevant skills (Python, JavaScript, etc.)
   - Write a brief "About" section
   - Add education
   - Aim for "Intermediate" profile strength minimum

#### Phase 2: Build Trust (Days 2-14)

3. **Connect with people organically**:
   - Send 5-10 connection requests per day
   - Target SA tech professionals, recruiters
   - Include personalized messages
   - Goal: 50+ connections before scraping

4. **Normal browsing behavior**:
   - Login daily from the same IP
   - Browse job listings manually
   - Visit company pages
   - Like/comment on a few posts
   - Join 2-3 relevant groups

5. **Wait 1-2 weeks before scraping**:
   - LinkedIn flags new accounts that immediately scrape
   - Build up account history first
   - Patience here = avoiding bans later

#### Phase 3: Start Scraping (Day 15+)

6. **Conservative first runs**:
   - Start with `--linkedin-results 50` (very low)
   - Run manually for first week
   - Check for any warnings/blocks
   - Gradually increase to 100, then 150, then 200

7. **Scraping best practices**:
   - Only run once per day
   - Same time every day (8 AM SAST)
   - Don't scrape from personal computer with same account
   - Let GitHub Actions handle it (different IPs)

#### If You Get Rate Limited

8. **Recovery steps**:
   - Account might get temporarily blocked (24-48 hours)
   - Don't try to scrape during block period
   - When unblocked, reduce to `--linkedin-results 50`
   - Consider using `--skip-linkedin` flag

9. **Nuclear option**:
   - Skip LinkedIn entirely: `--skip-linkedin`
   - Other sources (OfferZen + Indeed + PNet) = ~700 jobs
   - Still plenty for bootcamp students

#### Anti-Detection Features (Already Implemented)

✅ Random delays (2-8 seconds between requests)
✅ Rotating user agents (5 different browsers)
✅ Rate limiting (30 requests/minute max)
✅ Exponential backoff on errors
✅ Human-like request patterns
✅ Session persistence

---

### Step 9: Test the Pipeline

1. Go to your GitHub repository
2. Click "Actions" tab
3. Click "Daily Job Scraper" workflow
4. Click "Run workflow" dropdown
5. **IMPORTANT for first run**: Check "Skip LinkedIn scraping" (test other sources first)
6. Click "Run workflow"
7. Watch it run (takes ~5-10 minutes without LinkedIn)
8. Check your Google Sheet - jobs should appear!

**Second test** (after LinkedIn account is ready):
1. Run workflow again
2. Leave "Skip LinkedIn" unchecked
3. Monitor for rate limit errors

**Troubleshooting:**
- If it fails, click on the failed run to see logs
- Common issues:
  - Secrets not set correctly (re-check Step 6)
  - Service account not shared with sheet (re-check Step 3)
  - LinkedIn rate limiting (use `--skip-linkedin` flag)

---

## 🔧 Configuration Options

### Adjust LinkedIn Scraping

Edit `.github/workflows/daily-scrape.yml`:

```yaml
# Conservative (recommended for first month)
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --linkedin-results 100"

# Skip LinkedIn entirely
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --skip-linkedin"

# Aggressive (use only after account is established)
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --linkedin-results 200"
```

### Change Schedule

Edit the cron schedule:

```yaml
schedule:
  - cron: '0 6 * * *'  # 6 AM UTC = 8 AM SAST
  # Change to:
  - cron: '0 22 * * *'  # 10 PM UTC = 12 AM SAST (midnight)
  - cron: '30 14 * * 1-5'  # 2:30 PM UTC, Monday-Friday only
```

Use https://crontab.guru to generate schedules

---

## 💰 Cost Breakdown

**Free:**
- GitHub Actions: 2,000 minutes/month (your pipeline uses ~240 min/month = 12%)
- Google Sheets API: Free
- OfferZen/Indeed/PNet scraping: Free

**Paid:**
- Anthropic API (Claude): ~$1-3/month for 500-1000 jobs daily
  - Can skip with `--skip-enrichment` flag to make it 100% free
  - Jobs will still work, just won't have AI-extracted skills/levels

**Total: $0-3/month** (free if you skip enrichment)

---

## 📊 Google Sheet Setup

### Make Sheet Public

1. Open your Google Sheet
2. Click "Share" → "Change to anyone with the link"
3. Set to "Viewer"
4. Copy the public link
5. Share this link with bootcamp students

### Sheet Columns

The sheet will have these columns:
- Date Posted
- Job Title
- Company
- Role Category (Backend Engineer, Data Scientist, etc.)
- Location
- Work Policy (Remote/Hybrid/Office)
- Required Skills
- Nice-to-Have Skills
- Years Experience
- Level (Junior/Mid/Senior)
- Employment Type (Full-time/Contract/etc.)
- Salary Range
- Summary (AI-generated 1-2 sentence blurb)
- Source (OfferZen/Indeed/LinkedIn/PNet)
- Apply Link

---

## 🛡️ LinkedIn Anti-Ban Strategy Summary

**Account Setup** (Days 1-14):
- Create realistic profile with photo
- Add work history, skills, education
- Connect with 50+ people organically
- Browse LinkedIn normally daily
- **NO SCRAPING** during this period

**Initial Scraping** (Days 15-30):
- Start with 50 results per term
- Manual runs first week
- Monitor for blocks/warnings
- Gradually increase to 100-150

**Steady State** (Month 2+):
- 150-200 results per term
- Once daily at same time
- Let GitHub Actions handle it
- Monitor weekly for issues

**If Rate Limited**:
- Reduce to 50 results
- Skip LinkedIn for 48 hours
- Or use `--skip-linkedin` permanently

**Already Implemented**:
- Random delays (2-8s)
- Rate limiting (30 req/min)
- Rotating user agents
- Exponential backoff
- Human-like patterns

---

## 📧 Monitoring

### GitHub Notifications

Enable email alerts:
- Settings → Notifications → Actions → Enable

You'll get emailed if workflow fails.

### Weekly Checks

Check once a week:
1. Actions tab → Verify green checkmarks
2. Google Sheet → Verify job counts
3. Spot check a few job links

### Monthly Review

- Check Anthropic API costs
- Verify all sources working
- Prune old jobs if sheet > 1000 rows

---

## 🔄 Maintenance

### When Scrapers Break

**JobSpy library issues:**
```bash
# Update JobSpy if scrapers fail
pip install --upgrade python-jobspy
```

**LinkedIn persistent blocks:**
- Switch to `--skip-linkedin` in workflow
- Create new dedicated account
- Wait 2 weeks before scraping

**API changes:**
- OfferZen/PNet: Check if API endpoints changed
- Check JobSpy GitHub for updates

---

## 🎓 For Bootcamp Students

### Share Instructions

Give students:
1. **Public sheet link**
2. **How to use**:
   - Filter by location (Cape Town, JHB, etc.)
   - Filter by level (Junior, Mid, Senior)
   - Filter by skills (Python, React, etc.)
   - Sort by date for newest jobs
   - Click "Apply Link" to apply

3. **What to expect**:
   - Updates daily at 8 AM SAST
   - Jobs from last 30 days
   - 500-1000 jobs total
   - Multiple sources combined

---

## 🆘 Troubleshooting

### "No jobs scraped from any source"
- Check GitHub Actions logs
- JobSpy might be down temporarily
- Try running again in 1 hour

### "ANTHROPIC_API_KEY not set"
- Re-add secret in GitHub Settings
- Ensure no spaces before/after key
- Key must start with `sk-ant-`

### "Error opening spreadsheet"
- Re-share sheet with service account
- Check SPREADSHEET_ID is correct
- Verify GOOGLE_SHEETS_CREDS JSON is complete

### "LinkedIn rate limiting"
- Expected on first few runs
- Use `--skip-linkedin` flag
- Or reduce `--linkedin-results` to 50
- Wait 24 hours between attempts

### "Jobs not appearing"
- Check workflow has green checkmark
- Look at workflow logs for errors
- Verify spreadsheet ID matches
- Check service account has edit access

---

## 📝 File Checklist

Your repo should have:

```
job-scraper/
├── .github/
│   └── workflows/
│       └── daily-scrape.yml              ← GitHub Actions workflow
├── main_scraper.py                        ← Main orchestrator
├── scraper_utils.py                       ← Shared utilities
├── offerzen_scraper.py                   ← OfferZen scraper
├── indeed_scraper.py                     ← Indeed scraper
├── linkedin_scraper_enhanced.py          ← LinkedIn (anti-ban)
├── pnet_scraper.py                       ← PNet scraper
├── enrich_jobs.py                        ← AI enrichment
├── sheets_writer.py                      ← Google Sheets writer
├── requirements.txt                       ← Python dependencies
└── SETUP_GUIDE.md                        ← This guide
```

---

## ✅ Success Checklist

Before going live:

- [ ] Google Sheet created and shared with service account
- [ ] All 3 secrets added to GitHub (ANTHROPIC_API_KEY, GOOGLE_SHEETS_CREDS, SPREADSHEET_ID)
- [ ] All Python files uploaded to repo
- [ ] GitHub Actions workflow file in `.github/workflows/`
- [ ] LinkedIn account created (if using LinkedIn)
- [ ] LinkedIn account aged 2 weeks (if using LinkedIn)
- [ ] Test run completed successfully
- [ ] Jobs visible in Google Sheet
- [ ] Sheet set to public (anyone with link can view)
- [ ] Public link shared with students

---

## 🎉 You're Done!

The pipeline will now run every day at 8 AM SAST automatically.

**What happens daily:**
1. 6 AM UTC: GitHub Actions starts
2. Scrapes ~500-1000 jobs from all sources
3. Enriches with AI (extracts skills, levels, etc.)
4. Writes to Google Sheet (sorted newest first)
5. Students wake up to fresh jobs!

**Your only job:** Check it weekly to make sure it's working.

Need help? Check the Actions tab logs - they show exactly what went wrong.

---

## 🔐 Security Reminder

- ✅ All secrets in GitHub Secrets (never in code)
- ✅ Repo is private
- ✅ Service account JSON only in GitHub
- ✅ API keys never committed to Git
- ✅ Google Sheet is view-only for public

**Happy job hunting for your bootcamp grads! 🚀**
