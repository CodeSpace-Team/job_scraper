# Quick Start Reference Card

## 🚀 30-Minute Setup

### 1. Google Sheet (5 min)
- Create sheet at sheets.google.com
- Copy spreadsheet ID from URL

### 2. Google Cloud (10 min)
- console.cloud.google.com → New Project
- Enable Google Sheets API
- Create service account → Download JSON key
- Share sheet with service account email

### 3. Anthropic API (2 min)
- console.anthropic.com → Create API key
- Copy key (starts with sk-ant-...)

### 4. GitHub Repo (3 min)
- Create PRIVATE repo
- Upload all .py files
- Upload .github/workflows/daily-scrape.yml

### 5. GitHub Secrets (5 min)
Settings → Secrets → Add:
- `ANTHROPIC_API_KEY` = your API key
- `GOOGLE_SHEETS_CREDS` = entire JSON file contents
- `SPREADSHEET_ID` = sheet ID from step 1

### 6. LinkedIn Account (2 min setup + 2 weeks aging)
- Create dedicated account
- Complete profile
- Wait 2 weeks before enabling
- Start with --skip-linkedin flag

### 7. Test Run (5 min)
- Actions tab → Run workflow
- Check "Skip LinkedIn" for first test
- Verify jobs appear in sheet

---

## 💰 Costs

- GitHub Actions: FREE (2,000 min/month, you use ~240)
- Google Sheets: FREE
- Anthropic API: $1-3/month (optional, use --skip-enrichment for $0)

**Total: $0-3/month**

---

## ⚙️ Daily Workflow

```
6:00 AM UTC (8 AM SAST)
  ↓
GitHub Actions starts
  ↓
Scrape OfferZen (50-150 jobs)
  ↓
Scrape Indeed (200-500 jobs)
  ↓
Scrape LinkedIn (0-400 jobs) ← skip if rate limited
  ↓
Scrape PNet (100-300 jobs)
  ↓
AI enrichment (extract skills, levels)
  ↓
Write to Google Sheet (dedupe, sort newest first)
  ↓
Done! Students have fresh jobs
```

---

## 🛡️ LinkedIn Protection

**Already Implemented:**
- Random delays (2-8 seconds)
- Rate limiting (30 req/min)
- Rotating user agents
- Exponential backoff
- Human-like patterns

**Your Job:**
- Create dedicated account (not personal)
- Age 2 weeks before scraping
- Start with 50 results, increase slowly
- Use --skip-linkedin if problems

---

## 🔧 Common Commands

**Skip LinkedIn:**
```yaml
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --skip-linkedin"
```

**Reduce LinkedIn (conservative):**
```yaml
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --linkedin-results 100"
```

**Skip AI enrichment (free):**
```yaml
CMD="python main_scraper.py --spreadsheet-id $SPREADSHEET_ID --skip-enrichment"
```

---

## 📊 Expected Results

| Source | Jobs/Day | Quality | Rate Limit Risk |
|--------|----------|---------|-----------------|
| OfferZen | 50-150 | ⭐⭐⭐⭐⭐ | None |
| Indeed | 200-500 | ⭐⭐⭐⭐ | Low |
| LinkedIn | 200-400 | ⭐⭐⭐⭐ | **High** ⚠️ |
| PNet | 100-300 | ⭐⭐⭐ | None |
| **Total** | **500-1000** | | |

Without LinkedIn: **~700 jobs/day** (still plenty!)

---

## 🆘 Emergency Fixes

**Pipeline fails?**
→ Check Actions tab logs for error

**LinkedIn blocked?**
→ Add --skip-linkedin flag in workflow

**No jobs appearing?**
→ Verify all 3 secrets are set correctly

**Google Sheets error?**
→ Re-share sheet with service account email

---

## 📱 Share With Students

Public sheet link format:
```
https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit?usp=sharing
```

Set to: "Anyone with the link can **view**"

Tell them:
- ✅ New jobs added daily at 8 AM
- ✅ Filter by location, skills, level
- ✅ Click "Apply Link" to apply
- ✅ Jobs from last 30 days

---

## ✅ Success Checklist

- [ ] Sheet created & service account has access
- [ ] All 3 GitHub secrets added
- [ ] All files uploaded to repo
- [ ] Test run successful (with --skip-linkedin)
- [ ] LinkedIn account created & aging
- [ ] Sheet set to public view
- [ ] Link shared with students
- [ ] Weekly monitoring scheduled

---

**Read SETUP_GUIDE.md for full details**
