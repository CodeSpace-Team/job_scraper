# Build Notes

---

## F1 — Only tech jobs in the sheet

**Done:** 12 August 2026

### The problem

The sheet kept filling up with jobs that had nothing to do with tech — mining engineers, quantity surveyors, warehouse assistants. This happened because Indeed matches words like "engineer" and "developer" very loosely when it searches. Nothing in our code checked whether a job was actually a tech job before it went into the sheet.

### What we built

A step that looks at every job and decides "keep" or "drop" before anything is written. It runs after the AI has labelled the job, and before the sheet is updated.

It decides in four steps, stopping at the first one that applies:

1. Does the job title contain a word that means "not our kind of job"?
   (mining engineer, quantity surveyor, warehouse, receptionist...) → drop
2. Does the AI's role label look like a tech job? → keep
3. No usable role label, but the job title itself looks like a tech job? → keep
4. Nothing says this is a tech job → drop

Jobs that get dropped are not deleted. They go to a new **Exclude** tab in
the same spreadsheet, with the reason written next to them.

### Why we did it this way

**A plain "engineer" is not enough to be accepted.** That word on its own is exactly what let mining and civil engineers in. So the rules only accept "engineer" when a tech word sits in front of it — software engineer, cloud engineer, test engineer. "Engineer" by itself is rejected.

**The drop list names jobs, not industries.** This matters more than it sounds. If we blocked the word "mining", we would also throw away a real IT support job at a mining company. So we block "mining engineer", not "mining". Same idea with sales: we block "sales representative", but "Salesforce Developer" is safe because the word breaks differently.

**If the AI never labelled a job, we look at the title instead.** The AI step can be switched off, or run out of credit, or fail on a batch. Without this fallback, one bad AI day would quietly send an entire day of good jobs to the Exclude tab and leave the sheet empty. Checking the title keeps the sheet fed even when the AI is unavailable.

**Nothing is deleted, ever.** The brief asks for this, and it is the right call anyway. If the filter turns out to be too aggressive, the evidence is sitting in the Exclude tab. We also keep the role label and the job description on those rows, because later we may want to use them to teach the system what to exclude — and neither is recoverable once the job is gone.

**We wrote the run log to show the drops.** Every run prints how many jobs were dropped, split by which rule dropped them, plus the first ten dropped job titles. This means you can judge whether the filter is behaving without opening the spreadsheet at all.

### What we chose not to do

We did not use AI or fuzzy matching to decide this. Plain word rules are easy to read, easy to fix when they get something wrong, and they tell you exactly why a job was dropped. A smarter filter that cannot explain itself would be a step backwards here.

### How to check it is working

- **In the run log** (GitHub Actions), look for the `[PHASE 2.5]` section. It shows how many were kept and dropped, and a sample of the dropped ones.
- **In the spreadsheet**, open the Exclude tab. Every row has a Reason.
- **A false drop matters more than a leak.** If a real tech job is sitting in the Exclude tab, that is a graduate not seeing a job they could get. A stray non-tech job in the main sheet is only annoying.

### What the first live run showed

Run 127 on 13 August screened 255 jobs. The Exclude tab was created and filled correctly on the first attempt, and the dropped jobs read right: project managers, dispatch supervisors, admissions consultants, electrical engineers, a mechanical engineering intern, a quantity surveyor. Nothing obviously wrong in the sample.

One to keep an eye on: **"Development Engineer"** was dropped because the AI labelled it a Hardware Engineer. That could have been a software job. If more titles like it show up in the Exclude tab, the accept list needs widening.

### An unresolved oddity from that run

**The run's log and the run's own saved file disagree about how many jobs were dropped, and we have not worked out why.**

The log said 73 dropped (29 on the title list, 44 for no accepted role type), and said so in four separate places, including the line `save_jobs` prints immediately after writing the file. But the file that same run saved and uploaded contains **79** dropped jobs, and its list includes jobs the log's own sample shows were kept.

We checked the obvious things and ruled them out:

- Re-running the committed code over that run's scraped jobs gives 79, matching the saved file exactly — so the code is not the difference.
- The accept-list and the drop-list are byte-identical between the local copy and what was committed.
- The file was extracted fresh from the untouched artifact, so nothing local had overwritten it.

Six jobs out of 255, and the difference is toward dropping more rather than fewer, so nothing is at risk in the meantime. **How to settle it:** on the next run, compare the log's `Saved N jobs to data/cache/excluded_jobs.json` line against the number of jobs in that run's artifact. Matching means the 13 August download was a one-off; disagreeing again means something real, and we will have a second sample to work from.

### Still open

The target is "less than 5 out of every 100 new rows is a non-tech job". The first live run only added 22 new rows to the sheet, which is nowhere near enough to measure that properly. It needs a few more days of running before we can call it.

Worth deciding separately: the Jobs sheet still holds 5,312 rows from before this screen existed, and none of them were ever checked. The target only applies to new rows going forward, so the old non-tech jobs are still sitting in there. Cleaning up the history is not in the brief.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/__init__.py` | New folder for steps that run between scraping and writing |
| `src/pipeline/screening.py` | The keep-or-drop decision |
| `src/writers/sheets.py` | Added the Exclude tab writer |
| `src/core/orchestrator.py` | Runs the new step as Phase 2.5 |
| `tests/unit/test_screening.py` | Tests the decision, one job at a time |
| `tests/integration/test_screening_pipeline.py` | Tests the drop reaching the Exclude tab |

---

## F2 & F3 — Levels, and years of experience

**Done:** 12 August 2026 (levels amended 13 August, after the first live run)

### The problem

Two problems, solved by one piece of code because they read the same words.

The "Years Exp" column was nearly always empty. It only got filled when a job feed handed over a clean number, and most ads do not — they say it in a sentence, like "at least 3 years' experience" or "2-4 years in a similar role".

And the level ("junior", "senior") was whatever the AI decided that day. Graduates filter by level, so it needs to be right for the same reasons every time, not re-guessed on each run.

### What we built

Two steps that run after the AI and before the non-tech screen.

**Years of experience.** A text search for the common phrasings. The answer is always a number or nothing — never text — so the column can be sorted and filtered.

**Level.** A set of rules that decide in order, stopping at the first one that gives an answer:

1. The job title. "Senior .NET Developer" is senior; "Graduate Software Engineer" is entry level.
2. The years asked for. 0 is entry level, 1-2 junior, 3-4 mid, 5-7 senior, 8 or more is lead.
3. The description, but only where the level word sits right next to a role word — "senior developer", "graduate programme".
4. "unknown".

We also added a small tool, `python -m src.pipeline.qa`, that pulls 20 random jobs into a table you can read through and mark right or wrong. That is how the weekly check gets done.

### Why we did it this way

**A range records the lower number.** "2-4 years" is stored as 2. Someone with 2 years can apply, so 2 is the honest answer. Same when an ad asks for several different things — "5+ years in .NET, 3+ years in Azure" is stored as 3. Storing the higher number would push jobs out of reach that are actually open.

**A number only counts if the sentence is about experience.** This turned out to matter a lot. Ads are full of numbers followed by the word "years" that have nothing to do with the person applying — "3 year contract", "a 3 year degree", "we have been running for the last 8 years", "founded 25 years ago". Grabbing those would fill the column with nonsense, and because F4 drops jobs asking for 4 or more years, a wrong number means a graduate silently loses a job they could have got. A wrong number is worse than a blank.

**The title wins over everything.** Companies advertise "Junior Developer" and then ask for 5 years in the body. The title is what they will actually hire for, so it decides, and the job stays in the sheet where the graduate can judge for themselves.

**Where a title says two things, the lower one wins.** "Junior to Mid Developer" is a junior job, because the ad says a junior can apply. This cannot rescue a job that is genuinely senior: "Senior / Lead Developer" still comes out senior.

**The description rules are deliberately narrow.** This is the trap that would have done the most damage. Nearly every corporate ad mentions "senior management" or "senior stakeholders" somewhere. If a loose "senior" counted, a large share of ordinary IT support and junior jobs would be labelled senior and then dropped by F4. So the level word has to sit directly against a role word to count.

**We do not guess.** An ad that says nothing about level gets "unknown", not a made-up answer. This matters more than it sounds: F4 keeps unknowns, because ads that say nothing are often open to anyone. Guessing "mid" would be harmless; guessing "senior" throws the job away.

**Every job records why it got its level.** Each one saves which rule decided, the exact words it decided on, and how sure that makes us. F4 removes jobs based on this label, and a wrong label costs somebody a job they will never know existed. So every decision has to be checkable afterwards.

### What the first live run changed

We shipped this, then read the first real run of 255 jobs — and changed two things because of what we saw. Worth recording, because every test had passed and the code looked fine.

**We stopped using the AI as a fallback for the level.** Originally there was a fifth step: if none of the rules found an answer, take whatever the AI had said. On real data that step was deciding 81 of 255 levels, and 17 of those came out senior, lead or principal — which F4 was about to delete. Reading them back, the AI had called a plain "Test Analyst" a *lead*, and "Data Engineer", "AWS Cloud Engineer" and "ServiceNow Developer" *senior*. None of those titles says anything about seniority.

So the step is gone. The rule is now what the brief asked for in the first place: if the rules cannot tell, say unknown. A guess is not a good enough reason to take a job away from someone. The AI's opinion is still saved on the job as `ai_job_level` so the weekly check can compare the two, but it never decides anything.

**We taught the title rule about managers.** The AI had been quietly covering for a gap: our rules did not know that "manager", "VP", "director", "head of" or "staff engineer" means a job is out of reach in the first three years. Now they do. It catches 24 jobs on a normal day. We read all 24 — ten were genuine engineering management, two were staff engineers, and the rest were non-tech jobs F1 drops anyway. No false catches.

The two changes roughly cancel out in volume — 137 of 255 jobs sit above the cohort either way — but now **not one of those decisions rests on a guess**. Every drop can be traced back to words in the ad.

**One side effect worth knowing.** Jobs marked "unknown" went from 1 to 67 out of 255, about a quarter. That is not a fault. Those jobs were only ever labelled "mid" because the AI said so, and the ads themselves gave no level. Nothing changes about whether they reach the sheet — F4 keeps unknowns either way — but the board's level filter will be blank for about a quarter of jobs. The board's default view already treats an empty level as in scope, so this is fine. Do not read a high unknown count as a bug.

### What we chose not to do

**We did not add columns to the Jobs sheet.** The "why" information lives in the run's saved files and in the QA tool instead. The sheet writer decides whether to rebuild the sheet by counting columns, and that is the most breakable code in the project — not worth risking for information that the people doing the checking will read through the QA tool anyway.

**We did not let the AI decide the level at all.** Not even as a last resort. Rules give the same answer every time and can be explained; the AI can quietly change its mind between runs, and the first live run showed it getting real jobs wrong in the direction that costs a graduate an application.

**We are not chasing a full years column.** The target is about 4 in 10, and the first live run came in at 35%. Plenty of ads simply do not say, and the only way to hit 100% would be to invent numbers.

### How to check it is working

- **In the run log**, look for `[PHASE 2.4]`. It prints how much of the years column got filled, how many jobs landed on each level, and which rule decided each one. If a rule stops working, the breakdown shifts and you can see it without opening anything. There should never be a level decided by "ai" — if one appears, the fallback has crept back in.
- **Once a week**, run `python -m src.pipeline.qa`. It writes a table of 20 random jobs to `data/qa/`. Open each link, read the ad, mark the last column. The target is 18 out of 20. Keep the filled-in file — it is the record that the check was done.
- **The same tool reviews drops**: `python -m src.pipeline.qa -i data/cache/excluded_jobs.json`. It switches to asking whether anything was dropped that should have been kept.

### Still open

The 18-out-of-20 target is checked in the tests against 20 made-up ads, where it currently scores 20 out of 20 and fills 40% of the years column. Made-up ads are easier than real ones — the first live run filled 35%, which is close but a little under. The real level accuracy still needs a weekly check on live data before we call this finished.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/experience.py` | Reads the years of experience out of the ad |
| `src/pipeline/levels.py` | Works out the level, or says unknown |
| `src/pipeline/qa.py` | Builds the weekly 20-job review sheet |
| `src/core/orchestrator.py` | Runs both as Phase 2.4, before the screen |
| `tests/unit/test_experience.py` | 50 tests, mostly on numbers that must be ignored |
| `tests/unit/test_levels.py` | 71 tests, including the senior-management trap |
| `tests/integration/test_leveling_pipeline.py` | 16 tests on 20 realistic ads |

---

## F4 — Only jobs a graduate could actually get

**Done:** 14 August 2026

### The problem

The sheet was carrying jobs nobody in their first three years of work could get. Senior roles, team leads, ads asking for six years. A graduate opening the sheet had to wade through them to find anything they could actually apply for.

### What we built

A second screen, running straight after the non-tech one. A job is dropped if:

- its level is senior, lead or principal, **or**
- the ad asks for four or more years

Everything else stays. Dropped jobs go to the same Exclude tab, marked `F4 above cohort` in the Stage column so the two screens can be told apart.

### Why we did it this way

**Jobs that say nothing about seniority are kept.** This is the most important rule in F4 and the easiest to get wrong. About a quarter of what we scrape gives no clue about level, and those ads are usually open to anyone. Dropping them would throw away exactly the jobs this tool exists to find. So silence means keep, not drop.

**The non-tech screen runs first.** When a job fails both, "not a tech job" is the more useful thing to record. A Senior Quantity Surveyor belongs in the Exclude tab as a surveyor, not as a senior.

**Four years is the line, not five.** The brief says drop anything asking for four or more, so three years still counts as our cohort. Both sides of that line are pinned by tests, because it is exactly the kind of boundary that quietly drifts when somebody tidies the code later.

**Doubtful drops are flagged rather than hidden.** Most drops rest on a word in the title or a number the ad states outright. Two paths are softer: a level read from a phrase buried in the body text, and a years figure that came from a job feed rather than the ad's own wording. Those get marked in a new **Needs Review** column on the Exclude tab, so the weekly check can go straight to the doubtful ones instead of reading all of them. On real data that was 2 out of 169 drops.

**Nothing is deleted.** Same as F1. Every dropped job keeps its full record and its reason.

### What we chose not to do

**We did not drop jobs on an AI guess.** That was settled the day before, in F2 — the AI is no longer allowed to decide a level, because it had called a plain "Test Analyst" a lead. F4 inherits that. Every drop it makes traces back to words in the ad.

### One thing that needed care

The Exclude tab already existed with 10 columns and 73 rows before the Needs Review column was added. Writing an eleventh value into a ten-column grid fails outright, so the writer now widens the tab and rewrites its header row when it finds an older one — once, on the first run after this change. Existing rows keep everything they had and simply show a blank in the new column, which is correct: they were all F1 drops, and F1 does not flag for review.

### How to check it is working

- **In the run log**, `[PHASE 2.5]` now shows four counts: the two F1 rules, the F4 count, and how many were flagged for review. The sample of dropped jobs names which screen dropped each one, with `[REVIEW]` against the doubtful ones.
- **In the Exclude tab**, filter Stage to `F4 above cohort` to see only this screen's drops, or filter Needs Review to YES to see only the doubtful ones.
- **Once a week**, `python -m src.pipeline.qa -i data/cache/excluded_jobs.json` builds a table asking "should any of these have been kept?".

### What the numbers look like

Replayed over the 255 jobs from the 13 August run:

| Stage | Jobs |
| :--- | ---: |
| Scraped | 255 |
| Dropped as non-tech (F1) | 79 |
| Dropped as above the cohort (F4) | 90 |
| **Reaching the board** | **86** |

Of the 90 F4 drops, 88 were on level and 2 on years. Only 2 of the 169 total drops were flagged for review.

### Still open

**The board only gets about 86 jobs a day, and most are repeats.** The sheet already holds thousands of jobs, so a day's run usually adds only ten or twenty genuinely new rows. Filtering is no longer the problem — supply is. That makes F7, which searches for the tracks we currently miss entirely, more urgent than its position in the list suggests.

**59% of what reaches the board has no level at all.** Expected, and not a fault: those ads simply do not say. But it means the board's level filter will be blank for most jobs, and the default view has to treat "no level" as in scope.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/screening.py` | Added the F4 screen alongside F1 |
| `src/writers/sheets.py` | Needs Review column, and a one-off header repair for the tab |
| `src/core/orchestrator.py` | Summary splits the two kinds of exclusion |
| `tests/unit/test_screening.py` | 29 more tests — the four-year boundary, unknowns kept, review flags |
| `tests/integration/test_screening_pipeline.py` | F4 on real ads, plus the header migration |

---