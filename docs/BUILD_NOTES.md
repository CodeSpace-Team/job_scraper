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

> **Measured on 19 August, and it was failing** — 5 non-tech in a sample of 60, against a target of 3. See *Measuring F1 for the first time* at the end of these notes for what leaked, why, and what was fixed.

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

## F9 — The same job, posted twice

**Done:** 14 August 2026

### The problem

The same job kept landing in the sheet more than once, in two different ways.

Indeed re-posts an advert a few weeks later under a new web address. And a recruitment agency lists a role at the same time as the employer's own HR team, under two different company names. The only check we had was on the web address, and neither of those has the same address twice.

For someone reading the board, this is the difference between fifteen jobs and fifteen rows that turn out to be nine jobs.

### What we built

Three checks, each catching something the one before it cannot:

1. **Exact web address** — the same listing scraped twice in one run.
2. **Title + company + city** — the same advert re-posted at a new address.
3. **Title + city + the words of the advert** — the same job listed by an agency and by the employer.

Titles get tidied before comparing, because job boards staple decoration onto them: "(Remote)", "Ref: ABC123", "URGENT", a trailing city. Company names get their legal endings stripped, so "Acme" matches "Acme (Pty) Ltd".

It runs in two places. Straight after scraping, and again against the sheet when deciding what is new.

### Why we did it this way

**The agency check leaves the company name out on purpose.** That is the whole point of it — the company name is the one field that differs when an agency and an employer post the same role. So the words of the advert stand in for it instead. Agencies copy the employer's text across word for word often enough that this catches the common case.

**But the advert text has to be long enough to prove anything.** Two ads sharing a short blurb prove nothing; "Apply now, great opportunity" is not evidence. So there is a floor — a few paragraphs' worth — and anything shorter is never matched on. Without it, every job with a one-line description would collapse into every other one.

**The city stays in every check.** The same role genuinely open in Cape Town and in Johannesburg is two jobs, not one, and a graduate should see both. This was a deliberate call: it means we accept some duplicates from companies that post per-city, in exchange for never hiding a job that is actually in someone's town.

**A job missing its title or company is never treated as a duplicate.** An empty value matching another empty value is not evidence of anything. Left unchecked, a handful of records with blank companies would collapse into one and take real jobs with them.

**When two copies collide we keep the fuller one.** The longer description wins, and if they tie, the newer posting date does. The copy we keep should be the one with the most for a person to read.

**Doing it before the AI step saves money too.** An advert listed for three cities used to be enriched three times. Now it collapses to one first. That was not the reason for building it, but it is a real saving on every run.

### What we chose not to do

**No fuzzy matching.** No similarity scores, no thresholds. The brief asks for plain matching and it is the right call: fuzzy matching goes wrong quietly, and a graduate who never sees a real job because two adverts scored 0.87 has no way of knowing it happened. Plain rules can be read, explained, and fixed.

**We are not touching the thousands of rows already in the sheet.** The check applies to what comes in from now on. Cleaning up the history is a separate job and not in the brief.

### The limit, stated honestly

**An advert an agency has rewritten in its own words is not caught.** Different title wording, different company, different text — there is nothing left to match on without guessing. We know this and we are choosing to live with it, because the alternative is fuzzy matching and the cost of that falls on the wrong person.

### One thing that needed care

The company-name tidying nearly shipped with a bug that would have made it almost useless here. South African companies are usually written "Acme (Pty) Ltd" — with a bracket sitting between "pty" and "ltd". The pattern looked for those two words together, so the most common company format in the country went unmatched and left "pty" stuck to the name. A test caught it. Now "pty" is also listed on its own.

### How to check it is working

- **In the run log**, look for `[PHASE 1.5]`. It prints how many duplicates were removed and which check caught each one, then the unique count out of the scraped count.
- **Watch the third number.** If "same advert via another poster" starts removing a lot, that means adverts are sharing boilerplate text rather than being genuine duplicates, and the text floor needs raising. A handful a day is normal; dozens is a warning.
- **In the sheet**, the real test is whether the same title and company appear twice on different days. If one slips through, take the two rows to the tests — an example that got missed is worth more than another rule.

### Still open

We have not seen this run against live data yet. The counts from the first run are the thing to read: how many the address check catches on its own, and whether the other two are earning their place.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/dedupe.py` | The three checks, and the tidying they need |
| `src/writers/sheets.py` | Checks the sheet for a re-post before adding a row |
| `src/core/orchestrator.py` | Runs it as Phase 1.5, before the AI |
| `tests/unit/test_dedupe.py` | 47 tests, including the "(Pty) Ltd" case |

---

## F7 — Searching all seven role tracks

**Done:** 14 August 2026

### The problem

The scraper only ever searched Indeed for six phrases, all variations of "software developer" — Technical Support, DevOps/Cloud, QA/Testing, Business Analysis, Mobile and Security were never searched for at all, and neither were internship, learnership or graduate-programme phrasings. F4 showed the board only gets about 86 jobs a day and most are repeats — filtering was no longer the bottleneck, supply was, and six of the seven tracks graduates are meant to see were invisible to the pipeline the whole time.

### What we built

Two things, both from a new module, `roles.py`.

A fixed list of the seven tracks from the brief's appendix, and about 40 search terms grouped by track. Core terms — the two biggest tracks, software development and technical support — run every day; the rest alternate between even and odd days, so the whole set is covered every two days without running 40 searches on top of the six we already had, every single morning. A normal day now searches 32 terms instead of 6.

And a role classifier that gives every job exactly one of the seven tracks. It reads the title first, falls back to the description when the title says nothing, and only then falls back to whichever search term found the job — a hit from "it internship" is still counted as an IT job even when the ad's own title is just "2026 Programme".

### Why we did it this way

**The title is trusted first, and checked in a fixed order, most specific first.** "Software Test Engineer" is QA work, not Software development, and "Cloud Support Engineer" is DevOps/Cloud, not Technical Support — both share a word with a track they are not. Checking the more specific tracks first is what keeps them apart.

**It refuses to guess.** "Systems Engineer" says nothing about which of the seven tracks it is, and gets left undecided rather than assigned to whichever track happens to be checked last. The same rule F2 uses for level: an honest "don't know" is worth more than a wrong answer that looks confident.

**We did not let it touch the AI's own field.** F1's screening still reads `primary_role` — the AI's label — to decide keep or drop, and this module deliberately does not write to it. The new `role_type` field sits alongside it instead. This is the same caution F2 used before it dropped the AI's level guess: watch the two side by side on real jobs first, and only then decide whether the rules are solid enough to replace what F1 currently trusts. Swapping it in without that evidence would risk repeating the exact mistake F2 caught — the AI calling a plain "Test Analyst" a lead.

**The cadence spreads the load instead of running everything daily.** Forty searches a day would slow the run down and risk annoying Indeed for no real benefit — most of what a second daily run of the same term would find, F9's deduping would just throw away again. Splitting the set across two days gets full coverage without the cost.

### What we chose not to do

**We did not swap F1 over to the new role classification.** That is a separate, better-informed decision for later, once `role_type` has sat next to the AI's label on a few real days of jobs. Doing it now would mean trusting a rule we have only tested against made-up titles, on the same day we ship it — exactly the situation that burned us with F2's AI fallback.

**We did not run every search term every day.** The brief does not ask for that, and doing it would cost more in scraping time and AI enrichment for a benefit we do not think is there — most of the extra finds would be the same jobs the daily terms already caught.

### One thing that needed care

More search terms means more raw jobs scraped, which means more jobs sent to the AI for enrichment, which costs real money against CodeSpace's own Anthropic account. Working through the actual pricing (Claude Haiku 4.5, the model the enrichment step uses): a normal day before this shipped cost around $0.23. Our estimate for a normal day under the new term list comes out somewhere between $0.49 and $0.97 — against a $1 daily cap. That is close enough to be a real risk, not a rounding error, so the first few live runs need watching for cost as much as for coverage.

### How to check it is working

- **In the run log**, `[PHASE 1]` now prints how many terms are being searched that day. `[PHASE 2.4]` prints the role breakdown across all seven tracks, how many jobs got no track at all, and which rule decided each one (title, description, or search term).
- **Watch for a track stuck at zero.** If one of the seven tracks comes back empty run after run, that likely means its search terms need adjusting, not that the track has no jobs in South Africa right now.
- **Watch the AI enrichment cost** on the first few runs, given how close the estimate sits to the daily cap.

### Still open

**We have not seen this run against live data yet.** The 32-term cadence and the classifier are both built and tested against made-up titles; how well they hold up, and what the real enrichment cost turns out to be, needs a live run to know.

**F1 still runs on the AI's label, not on `role_type`.** Once there is a few days of the two sitting side by side in the run log, that becomes its own small decision — not blocked on anything else in F7.

> **Decided on 19 August: no.** Four fifths of the disagreements come from the search-term fallback, which never looks at the job — swapping would have put around 284 non-tech jobs in front of graduates. The caution above was right. See *Two decisions closed by counting*.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/roles.py` | The seven tracks, the search terms and their cadence, and the classifier |
| `src/scrapers/indeed.py` | Records which search term found each job |
| `src/core/orchestrator.py` | Feeds the day's terms to the scraper, and classifies role type in Phase 2.4 |
| `tests/unit/test_roles.py` | 42 tests, including the track-overlap cases and the `primary_role` boundary |

---

## F5 — One official skills list

**Done:** 15 August 2026

### The problem

Two problems, one file.

There was no single answer to "what does this skill get called?" A job feed might hand over "JS", the AI might write "ReactJS", and a graduate filtering the board by "React" would miss both. Nothing forced the sheet to speak one vocabulary.

And every job's skills were worked out by the AI, every time, even when the answer was sitting in plain sight in the title — "Junior JavaScript Developer" does not need an API call to know it wants JavaScript. The 14 August billing scare (F7's extra search terms pushing enrichment close to CodeSpace's own $1 daily cap) made that waste harder to ignore.

### What we built

One file, `skills.json`, at the repository root — 130 skills, each with its official name, a category, and every spelling we know it goes by. It is the only skills list in the project; the keyword matcher, the AI-output tidy-up, and eventually the sheet and the board's own skill picker all read names through it.

A free, offline keyword matcher that runs over the job title and description before the AI ever sees the job, as a new Phase 1.7. It records what it found on `must_have_skills`, and two new fields: `skills_source` (did this come from a keyword match, the AI, or nothing at all) and `needs_ai_skills` (did the keyword match find fewer than three skills).

A canonicaliser that maps any spelling to the official one — "JS" becomes "JavaScript", "reactjs" becomes "React" — applied both to what the keyword matcher finds and, after enrichment runs, to whatever the AI wrote. Whichever one supplied the final answer, it comes out the same way.

### Why we did it this way

**Short acronyms only match in capitals.** JS, SQL, AWS and REST are common enough as ordinary words or word-fragments that matching them case-insensitively would light up on nonsense — "the rest of the team" is not a REST APIs hit. Anything five letters or fewer, all capitals, matches case-sensitively; everything else does not need to.

**Punctuation-heavy names keep their shape.** C#, .NET, CI/CD and Node.js all need characters either side of a match to not count as a boundary, or the match either fails outright or clips off the part that matters.

**A few names only count with a nearby context word.** "Go" and "Swift" are both real English words and real technology names. "You will build apps in Swift with UIKit experience" counts; "Taylor Swift is playing this weekend" does not. Both need a technical word — develop, engineer, API, framework, and the like — within about sixty characters before they count as a match.

**"Go" does not match on its own name at all.** Even with the context check, "Go" is too common a word to trust bare — "go the extra mile", "go-getters who close deals" would both light it up. Its aliases (Golang, Go Lang) carry the matching instead.

**Canonicalisation runs on the AI's output too, not just the keyword matches.** If only the keyword matcher were tidied, the sheet would show "JavaScript" from a keyword match sitting next to "JS" from the AI on a different row — the exact problem this feature exists to fix, just moved one step later.

### What we chose not to do

**We are not skipping AI enrichment for anything, yet.** The whole reason F5 exists is to cut down what gets sent to the AI, and it would have been easy to wire `needs_ai_skills` straight into a skip. We are deliberately not doing that today: as put when we scoped this, cost reduction is "a separate decision for later, that would depend if skip enrichment actual provide enough room for keyword matching." So for now every job still goes through enrichment exactly as before — F5 only records `needs_ai_skills` and `skills_source` alongside the result, so that once there is real data on how much the keyword matcher is finding on its own, the skip decision can be made with evidence instead of a guess. This is the same discipline F2 and F7 used before them.

### One thing that needed care

The first version of the AI-output tidy-up decided whether to relabel a job's `skills_source` as `"ai"` by checking whether it was **not already** `"keyword"`. That is circular — once the keyword matcher had labelled a job `"keyword"`, that check could never flip it, even after the AI had gone on to overwrite `must_have_skills` outright with its own list. Enrichment does not touch `skills_source` when it succeeds, only `must_have_skills`, so the label would have quietly kept lying about where a job's skills actually came from on every job the keyword matcher had already found something for.

Caught before shipping, while writing the tests for it rather than on a live run. The fix checks for `blurb` instead — the one field only enrichment ever sets, whether or not a job already had a `skills_source`. No blurb means enrichment never touched the job, and whatever the keyword matcher had already put there survives untouched.

### How to check it is working

- **In the run log**, `[PHASE 1.7]` prints the keyword fill rate before the AI runs at all — how many jobs already have enough skills without costing anything. `[PHASE 2.4]` prints it again after enrichment and the tidy-up, broken down by source: keyword, ai, or none.
- **Watch the "keyword" share over a few real days.** That number is the evidence the deferred cost decision needs — the higher it climbs, the more room there is to start skipping enrichment for jobs it already covers.
  > **This does not work, and cannot.** Enrichment runs for every job and always writes a blurb, so the tidy-up relabels every job `ai` and the keyword share is pinned at zero. Read `needs_ai_skills` instead, which is set before enrichment and never overwritten. See *Two decisions closed by counting*.
- **In the sheet**, `must_have_skills` should never show two spellings of the same thing across different rows. If "JS" ever appears instead of "JavaScript", something is reaching the sheet without going through this module.

### Still open

**We have not seen this run against live data yet.** The matcher and the tidy-up are both tested against made-up ads and a full pipeline smoke test, not a real day's worth of postings.

**The cost-reduction decision is still open, on purpose.** Once there are a few real days of `skills_source` and `needs_ai_skills` in the run log, that becomes its own decision — whether keyword matching alone is finding enough to skip the AI for some jobs, and by how much it would cut the daily bill.

> **Counted on 19 August: the saving is real (53% of jobs) but locked.** Those jobs also depend on enrichment for the board's blurb and the role label F1 screens on. See *Two decisions closed by counting*.

### Files

| File | What it does |
| :--- | :--- |
| `skills.json` | The one official skills list — 130 skills, names and aliases |
| `src/pipeline/skills.py` | The keyword matcher, the canonicaliser, and the AI-output tidy-up |
| `src/core/orchestrator.py` | Runs keyword matching as Phase 1.7, before the AI, and tidies the AI's output in Phase 2.4 |
| `tests/unit/test_skills.py` | 40 tests, including the three `skills_source` scenarios the bug fix depends on |

---
## F6 — The job board

**Done:** 15 August 2026 (verified against a live run, restyled to CodeSpace's branding, and polished with sorting/search, 16 August 2026)

### The problem

Everything built so far — F1 through F5, F7, F9 — only ever reached one place: a Google Sheet the CodeSpace team can read but no graduate ever sees. All of that screening, leveling, deduping and skill-matching work had no public audience to show it to.

### What we built

Two halves.

**The data half.** A new module, `publish.py`, keeps `frontend/public/jobs.json` as its own running list — separate from the Sheet's history, which still carries thousands of rows scraped before F1 and F4 existed and were never screened for tech relevance or seniority. Each day's run merges in today's screened, deduplicated, leveled jobs, matching against what is already on the board with the same title/company/city key F9 already uses, so a job scraped again the next day replaces its old row instead of duplicating. Anything whose posting has aged past 45 days drops off on its own.

**The board itself.** A Vite + React + Tailwind CSS single-page app in `frontend/`, fetching `jobs.json` and rendering it as a searchable, filterable, sortable list — checkboxes for role type, level, work policy, skills and source, a cap on years of experience asked for, and free text search across title, company, blurb and description. Selecting several values inside one filter is OR ("React or Python"); different filters combine with AND ("Software track AND entry level AND (React or Python)"). Each card also shows the ad's own posting date, or the date the board first added it when the ad states none.

**CodeSpace's own branding.** The board's colours and logo were pulled from codespace.co.za rather than left as a generic default palette — a muted teal, a warm near-black header carrying the real CodeSpace logo, and a pale mint used for skill chips, echoing the highlighted-phrase style on their own site.

**Sorting, a searchable skills list, and a working "clear all filters" button.** Sort by newest, oldest, or fewest years required — kept in its own `lib/sort.js`, since ordering and filtering are different questions worth testing apart. The skills checkbox list, which can run well past the 20 shown by default on a real day, now has a small search box to find one by typing instead of scrolling. And there is finally a way to recover from a filter combination that returns nothing: a single "clear all filters" control, driven by a new `hasActiveFilters()` check.

The daily GitHub Action now commits `frontend/public/jobs.json` after every run — independent of whether the Sheets write succeeds — so Netlify redeploys the board automatically.

### Why we did it this way

**`jobs.json` is not a copy of the Sheet.** The Sheet still holds roughly 5,000 rows from before F1 and F4 existed, none of them screened. Publishing straight from the Sheet would put all of that back in front of graduates, undoing the whole point of that screening. So the board keeps its own running list instead, built only from jobs that have already been through the real pipeline.

**Filter options are read from the real data, not hand-maintained.** `extractFacets()` works out which role types, levels, skills and sources actually appear on the board and only offers those — skills ranked by how often they appear, so the most useful ones surface first. The filter panel can never drift from what is actually on the board, and never shows an option with nothing behind it.

**The retention window keeps the board honest.** Job ads do not stay open forever. Without a cutoff, the board would just become a second, slower-growing copy of the Sheet's own history. 45 days is the working number for now.

**The job date shows a date, never a time.** The pipeline runs once a day, so every job added in the same run would show an identical, meaningless time if one were invented. A plain date — the ad's own posting date, or the day the board first saw the job — is the honest amount of precision the data actually supports.

**Salary is shown, not filtered on.** Checked the real job data before deciding, the same way F2/F3 checked real years-of-experience data before trusting it: OfferZen and PNet never populate `salary_min`/`salary_max` at all, and only Indeed sometimes does, when the ad states it. The first live run made this a certainty rather than a guess — zero of the 653 jobs scraped that day had a salary figure at all. Not a close call; there is nothing to filter on yet.

**Sort options are the ones a graduate would actually use.** Newest and oldest are the obvious pair, and "fewest years required first" surfaces the jobs someone with the least experience can most easily qualify for — a more useful third option than, say, alphabetical by company.

### What we chose not to do

**We did not read the Sheet back to rebuild `jobs.json`.** Reconstructing full job records from the Sheet's flattened rows is lossy, and would also mean re-solving the "5,000 unscreened legacy rows" problem on every single run instead of once.

**We did not stand up a backend or API for the board.** `jobs.json` is a static file, fetched once on page load. That is what "publish jobs.json" in the brief actually asks for, and it is free to host.

### What the first live run showed

The first real run reached the board with 182 jobs, out of 653 scraped and screened — F1, F2/F3 and F4 all behaving as designed on live data (matching the numbers those features were built against: no level ever decided by the AI, years of experience filled at 40%, exactly on the target F2/F3 set).

One real problem surfaced only once the board was live: the six sample jobs seeded into `frontend/public/jobs.json` for local development were still showing on the deployed site, mixed in with real listings, after the first live run. `publish()` merges rather than replaces — a new job only overwrites an existing one when its title/company/city key matches, and the fake sample companies never matched anything real, so they just sat there, well within the 45-day retention window. Fixed with a one-off cleanup script to strip the seeded entries out of the committed file; every merge from that point on only ever builds on real data.

### One thing that needed care — four times

**The `public/` convention.** The first version of `publish.py` wrote to `frontend/jobs.json`. Vite and Netlify only deploy files sitting inside `frontend/public/` — anything outside it never reaches the live site at all. Caught before any frontend code was written, by doing a real production build and confirming `jobs.json` actually landed in `dist/`, not by assumption.

**A locale bug in the salary formatter.** `Number.toLocaleString()` with no explicit locale formats thousands separators according to whatever locale the machine running it resolves — a comma on one machine, a space on another. The tests passed in the environment that built the feature and failed on the machine that actually runs the project, which is exactly the kind of thing a second machine catches that the first one cannot. Fixed by pinning the locale explicitly (`'en-US'`), and the same fix was applied up front to the date formatter added afterward rather than waiting to be caught twice.

**Seeded sample data outliving its purpose.** Covered above — the fix was a one-off cleanup, not a code change, since `publish()` itself was behaving exactly as designed.

**Two "clear all filters" buttons at once.** The first version of the empty-results state added its own clear-filters button, not realising the filter panel already shows a persistent one whenever a filter is active — so the exact moment meant to demonstrate the fix (a filter combination returning nothing) rendered two identical buttons side by side. Caught by a test asserting on the button's text, which failed with "found multiple elements" the moment both were on screen together. Fixed by removing the duplicate; the empty state now just points at the one button that was already there.

### How to check it is working

- **In the run log**, `[PHASE 3.7]` prints the board's publish summary: how many jobs were carried over, how many came in today, how many aged out, and the final total.
- **Backend tests**: `pytest -q` from `backend/` — 24 tests on `publish.py`, 100% coverage.
- **Frontend tests**: `npm test` from `frontend/` — 62 tests across the filter/search/sort logic, the display formatters, the filter panel's own interactive behaviour, and the page itself.
- **Visually**: the live Netlify URL — search, sort, and the filter panel (including the skills search box and clear-filters button) should all behave as expected, and every card should show a plain posting or added date. Checked on both desktop and mobile viewports; the layout stacks cleanly on a phone with no changes needed.

### Still open

**The salary filter stays out.** Settled, not deferred — zero fill-rate on the first live run makes this a closed question until the data itself changes, not an open one to revisit soon.

**Netlify is currently a manual deploy, not the GitHub-connected one.** Org access to connect Netlify directly to `CodeSpace-Team/job_scraper` is pending from Emma; until then, the board is kept current with a manual `git pull` → `npm run build` → drag `dist/` to Netlify each morning, rather than deploying automatically on every push.

### Files

| File | What it does |
| :--- | :--- |
| `backend/src/pipeline/publish.py` | Merges, dedupes and prunes the board's running `jobs.json` |
| `backend/tests/unit/test_publish.py` | 24 tests |
| `backend/src/core/orchestrator.py` | Runs publishing as Phase 3.7 |
| `.github/workflows/daily-scrape.yml` | Commits and pushes `jobs.json` after each run |
| `netlify.toml` | Netlify build config, at the repo root |
| `frontend/tailwind.config.js` | CodeSpace's brand colours as named Tailwind tokens |
| `frontend/src/lib/filters.js` | The board's search and filter rules, facet extraction, and `hasActiveFilters()` |
| `frontend/src/lib/sort.js` | Newest/oldest/fewest-years-required ordering |
| `frontend/src/lib/format.js` | Salary, years, level and date display formatting |
| `frontend/src/components/FilterPanel.jsx` | The filter panel, including the searchable skills list and clear-filters button |
| `frontend/src/App.jsx`, `frontend/src/components/`, `frontend/src/hooks/useJobs.js` | The rest of the page — search bar, sort control, job cards, data fetching |

---
## Surviving a bad day at Google

**Done:** 18 August 2026

### The problem

Twice now, on two different days, a run has done everything right and still put nothing in the Sheet.

The first time it was a dropped connection — "Connection reset by peer" — and 240 jobs that had been scraped, screened and leveled went nowhere because of one network blip. That was fixed at the time: the connection is retried, and if it fails anyway the run saves a rescue copy and carries on to the Exclude tab and the board instead of stopping dead.

The second time was this:

```
[06:53:48] Authenticating with Google Sheets...
[06:53:49] ✗ Sheets write error: Could not open spreadsheet:
           APIError: [503]: The service is currently unavailable.
```

One second between those two lines. The retry added for the first failure never fired at all.

The reason is a detail that is easy to miss: gspread reports a Google-side outage as its own `APIError`, which is not a `ConnectionError`. The retry only covered network errors, so a 503 sailed straight past it as though no retry existed. 661 jobs scraped and enriched, 183 screened and kept, eighteen minutes of work — and the Jobs tab did not move.

What is worth recording is everything that *did* survive, because that part was the earlier fix working exactly as designed. The Exclude tab, written moments later, went through. The board published its 183 jobs and the run committed `jobs.json`. A rescue copy of all 183 landed in `combined_jobs_fallback.json`. The run still reported red, so the failure was not hidden. Only the Jobs tab was stale, and only for that day.

### What we built

The retry now covers gspread's `APIError` as well — but only for the statuses that mean the problem is at Google's end: 429, 500, 502, 503 and 504. Four attempts, three seconds apart and doubling, which covers about twenty-one seconds of outage.

Getting that right needed something the retry decorator could not previously do. gspread reports *everything* as `APIError`: a 503 outage and a 403 "this sheet was never shared with the service account" arrive as the same class, and the class alone cannot tell them apart. So `@retry` gained an optional `should_retry` — instead of only asking what class an exception is, a caller can now look inside it and answer per exception.

### Why we did it this way

**A permanent failure is still reported immediately.** A 400, 403 or 404 fails on the first attempt, exactly as before. This is the half of the change that was easy to get wrong: catching `APIError` and retrying all of it would mean a genuine setup mistake — the kind someone hits on their very first run, before the sheet has been shared — takes four attempts and twenty seconds to report, with the real reason buried under retry noise. Retrying a problem that retrying cannot fix does not make the system more robust; it just makes it slower to tell you the truth.

**The status is read twice.** gspread takes the status out of the JSON error body Google returns, and falls back to storing -1 when that body is not valid JSON — which is precisely what a plain HTML error page from a load balancer during an outage looks like. So the response's own status code is used as a second opinion. An outage is the moment when tidy JSON is least likely to arrive, which is exactly the moment this has to work.

**Twenty-one seconds, not six.** The old window was three attempts two seconds apart. Against an eighteen-minute run, waiting a little longer costs nothing, and it is only ever spent on runs that were failing anyway.

### What we chose not to do

**We did not retry the whole Sheet write — only the opening of it.** Appending rows is not safe to blindly repeat: the check for what is already in the sheet happens before the append, not during it, so a retry after a partly-completed append could write the same jobs twice. Opening a spreadsheet reads nothing and changes nothing, which is what makes it safe to try again.

**We did not add any new alerting.** The run already exits red and the workflow's own failure notification already fires. The gap was never in noticing; it was that a failure worth one more attempt was not getting one.

### One thing that needed care

**A type hint that was a promise the code could not keep.** The `should_retry` option was first annotated as taking a `BaseException` — meaning "this predicate must handle any exception at all". But a predicate written for a specific API only handles *that* API's error class, which is narrower. A type checker rejects that, and correctly: a function that accepts less than promised cannot stand in for one that accepts more.

The fix was not to annotate the callers, which would only have moved the same complaint to the call site. The honest hint is `Callable[..., bool]`: whatever the predicate receives is always one of the classes the caller listed in `exceptions`, but that connection between two separate arguments cannot be expressed, and naming any concrete type there would be wrong in one direction or the other.

Caught by Pylance on the laptop that runs the project, not by the tests, which passed throughout — the same way the locale bug in F6's salary formatter surfaced. A second machine keeps finding things the first one cannot.

### How to check it is working

- **Tests**: `python -m pytest tests/unit/test_retry.py tests/unit/test_sheets_retry.py -q` from `backend/` — 25 tests, covering every status that is retried, every status that is not, and the growing gaps between attempts.
- **In the run log, on a bad day**: Phase 3 taking a few seconds longer than usual and then succeeding is a retry that worked. The same `✗ Sheets write error` line appearing after about twenty seconds instead of one is an outage that outlasted four attempts.
- **On a good day there is nothing to see**, which is the point. This code only does anything when Google is having trouble.

### Still open

**Whether this would have saved the run it was written for is a fair question, and the answer is probably.** The outage cleared quickly enough that the Exclude tab write seconds later went through — that is the best available evidence that a second attempt three seconds on would have found Google back up. It is evidence, not proof.

**The Jobs tab is the one thing with no automatic recovery.** If all four attempts fail, `combined_jobs_fallback.json` holds the day's jobs but nothing replays it — the write would be re-run by hand. Whether that is worth automating depends on how often this actually happens: twice in the project's life so far, both times transient, both times cleared on their own. Not enough evidence yet to justify building a replay step.

### Files

| File | What it does |
| :--- | :--- |
| `backend/src/utils/retry.py` | The `should_retry` option — deciding per exception, not per exception type |
| `backend/src/writers/sheets.py` | Which statuses are Google's problem, and reading the status out of two places |
| `backend/tests/unit/test_retry.py` | 7 tests, 3 of them on the new option |
| `backend/tests/unit/test_sheets_retry.py` | 18 tests, covering both what is retried and what deliberately is not |

---
## Measuring F1 for the first time

**Done:** 19 August 2026

### The problem

F1's target has been written down since the day it shipped: *fewer than 5 in every 100 rows reaching the sheet is a non-tech job*. It had never been measured. The first live run only added 22 new rows, far too few to judge, and after that it quietly stayed on the "still open" list for a week while everything else got attention.

That is a comfortable place for a target to sit. Nobody had to find out whether the filter that decides what a graduate sees was actually working.

### What we built

A third mode on the weekly review tool, `python -m src.pipeline.qa --check tech`. It samples the jobs that reached the sheet and asks one question about each: **is this actually a tech job?**

Getting the population right was most of the work. No run saves the kept jobs anywhere. The leveled file holds everything the pipeline handled, screening happens after it is written, and the excluded file holds only the drops — so "what reached the sheet" has to be worked out as one minus the other, matched by web address. Get that subtraction wrong and F1's pass rate gets measured over the very jobs F1 rejected, which would flatter it beyond recognition. Most of the new tests point at that one function.

The sheet also flags which adverts are worth opening. A job whose title matches F1's accept list on its own — "Full Stack Java Developer" — settles itself. A job whose title says nothing tech is on the sheet purely on the AI's say-so, and that is where a person is needed. Those rows sort to the top.

### What it found

A sample of 60, drawn from the 171 jobs that reached the sheet on 19 August. Five were confirmed non-tech by reading the adverts:

| Job | Employer | What the AI called it |
| :--- | :--- | :--- |
| GTM Operations Analyst | Mimecast | Data Analyst |
| HSE Data Insights Advisor | BP | Data Analyst |
| Junior Actuarial Analyst | King Price Insurance | Data Analyst |
| Quality Assurance Supervisor | AVI (food and consumer goods) | Quality Assurance Manager |
| Junior Product Developer | SMD Technologies (consumer electronics) | Product Developer |

Five in sixty is 8%, against a target of three. **F1 was failing, and had been the whole time.**

Look at the third column. Three separate jobs — sales operations, health and safety, and insurance actuarial work — all arrived at F1 wearing the same badge: *Data Analyst*. F1 accepts a bare data analyst, so all three walked through.

That is the same mistake F1's own source file warns about, four lines above the accept list:

> *a bare "engineer" is deliberately NOT accepted — that is the exact looseness that let mining and civil engineers through*

F1 learned that lesson for *engineer* and never applied it to anything else. *Analyst*, *developer* and *quality assurance* are the same kind of word: occupational nouns that every industry uses, meaning something different in each. A developer writes software in tech and recipes in food. Quality assurance is test automation in tech and hygiene compliance in manufacturing.

### What we fixed

**Three blocklist entries, for the three that came in as "Data Analyst".** The titles were the honest signal in every case — *GTM Operations*, *HSE*, *Actuarial* — and the title blocklist runs before the AI's label is ever consulted. `hse` sat beside `sheq` and `occupational health`, which were already there; only that spelling was missing.

**A fourth for the consumer-goods product developer**, and a fifth thing that turned out not to be an F1 problem at all.

**The Quality Assurance Supervisor needed no F1 change.** Nothing in that title says food — only the employer does — so no title blocklist could ever have caught it. But it did not need catching on those grounds: a supervisor supervises, which is not a job anyone holds in their first three years. F2's above-cohort title rule already knew about manager, head of, VP and director; `supervisor` was simply missing from the list. Added there, F4 now drops it on level regardless of industry, and catches every other supervisor role too.

After both changes, all five are caught and every confirmed-tech job in the sample still reaches the sheet.

### Why we did it this way

**Two of the new entries name the role, not the field.** Bare "actuarial" would drop an *Actuarial Systems Developer*, and bare "product developer" would drop a *Software Product Developer* — both real software jobs at employers who are not software companies. So the blocklist takes `actuarial analyst` and its siblings, and excuses the tech-qualified product developers by name:

```python
r"(?<!software )(?<!digital )(?<!technical )product developer",
```

That is the same shape the accept list already uses in refusing a bare "engineer" while taking "software engineer". Both halves of both rules are pinned by tests, because the failure mode of over-blocking is invisible: a graduate never learns about the job they did not see.

**The measurement samples 60, not 20.** The other two weekly checks use 20, and for a "18 out of 20" target that is exactly right. It cannot work here. A 5% target measured over 20 jobs can only ever produce 0%, 5% or 10% — one wrong job *is* the pass mark, so a single unlucky draw decides whether F1 passes. The sheet prints a warning saying so whenever the sample is under 40.

**The check needs a person, and always will.** F1 screens on the AI's label. Asking the AI to grade F1's output is asking it to mark its own homework — and this project already learned in F2 what the AI's labels are worth, when it called a plain "Test Analyst" a *lead* and F4 was about to delete it. The whole point of this target is to catch what those labels get wrong.

### What we chose not to do

**We did not tighten the accept list.** Removing bare "data analyst" would have caught three of the five in one line. It would also have dropped *Data Analyst (Power BI / SQL)* and *Graduate Data Analyst (AI and Analytics)*, both confirmed real in the same sample. Blocking the specific non-tech roles costs nothing; loosening what counts as a tech job costs real listings.

**We did not try to catch the food-company QA job from its title.** It is genuinely impossible — "Quality Assurance Supervisor" is a perfectly plausible software title. Reaching it would need the description or the employer's industry, and F4 got there by a better route anyway.

### One thing that needed care

**Reading a title is not reading the advert, and I got two wrong.** Working through the sample by title and employer, *Business Process Specialist* at Linde and *Technical Developer – Fresh Foods* at Shoprite both read as obviously non-tech. Both turned out to be real software jobs on opening the advert — Shoprite staffs developers to its divisions, and "technical developer" there means what it says.

Two false accusations out of seven. If either had been acted on without the advert being read, the fix would have started dropping genuine jobs, and nothing downstream would ever have reported it. Both are now pinned by tests so a later widening of the blocklist cannot quietly start dropping them.

The triage that decides which adverts to open has the same limitation, and it is worth stating plainly: it flagged 4 of the 5 real leaks, and missed the food-company QA job entirely because "quality assurance" is in F1's accept list. It is useful for ordering the reading, not for deciding what to skip.

### How to check it is working

- **Run it** after unzipping a run's artifact: `python -m src.pipeline.qa --check tech --size 60` from `backend/`. It writes `data/qa/tech-sample-DATE.md`.
- **Open the ones marked `look`** — those are on the sheet for a reason weaker than their own title. Skim the rest; do not skip them.
- **Keep the filled-in file.** It is the record that the check was done, the same as the weekly level samples.
- **Tests**: `pytest -q` from `backend/` — 489 across the project, including the five real leaks and the two jobs wrongly suspected.

### Still open

**The 0-in-60 result cannot be trusted yet.** That number is measured on the sample the fix was built from, which always flatters. The honest confirmation is another `--check tech --size 60` against a fresh run — different jobs, no circularity. Worth doing in a few days.

**Whether data analytics is in scope at all is a question for CodeSpace, not a bug.** A *Graduate Data Analyst* at a logistics company came up in the sample and was kept. None of the brief's seven tracks is "Data", so whether that job belongs on the board is a scoping decision for Emma rather than something F1 got wrong.

**The same class of leak almost certainly remains.** Five were found by reading sixty adverts. The mechanism — bare occupational nouns accepted regardless of industry — is general, and there is no reason to think these five were the only ones. Each measurement will find a few more; that is what the check is for.

---

## Two decisions closed by counting

**Done:** 19 August 2026

### The problem

Two decisions had been left deliberately open, both waiting on real data rather than on an argument.

F7 built a rules-based role classifier and then refused to let F1 screen on it, on the grounds that the only evidence was made-up titles. F5 built a free keyword skills matcher and recorded `needs_ai_skills` next to every job, but deliberately did not act on it, because the saving was a guess until there were real days to count.

Both were the right call at the time. Both had been sitting open for a week with the data quietly accumulating, and neither was going to close itself.

### What we built

A read-only script, `python -m scripts.decision_check`, that reads a run's own artifact and answers both with counts. Like `morning_check`, it touches nothing and works offline.

### What it found: F1 should not screen on role_type

Over 671 jobs, F1's keep-or-drop and F7's classifier agree on 380 of them — 57%. The interesting number is the 284 that F1 dropped but the classifier calls tech, and where those tracks came from:

| Where the classifier got the track | Jobs |
| :--- | ---: |
| The search term that found the job | 227 (80%) |
| The description | 54 (19%) |
| The title | 3 (1%) |

Four fifths of the disagreements come from a tier that never looks at the job. `search_term` means "Indeed returned this for a technical support search, so call it Technical Support" — which is how a waiter at a Protea Hotel and a warehouse coordinator both acquired tech tracks. That fallback exists to rescue vague titles like "2026 Programme". On real data it instead launders Indeed's loose matching into a confident label, which is the exact failure F1 exists to prevent.

Had we made the swap, roughly 284 non-tech jobs would have gone in front of graduates. **F7's refusal to wire it in without evidence was right, and this is the run that proves it.**

The useful half of that table: the title tier disagreed with F1 only three times out of 284. The classification rules are not the problem — the fallbacks are.

### What it found: the enrichment saving is real but locked

Keyword matching alone found enough skills for 357 of 671 jobs — 53%. That is the ceiling on what could skip AI enrichment, and it is a genuine half-the-bill saving.

It cannot be taken. Enrichment does not only fill skills; it writes the blurb the board shows and the `primary_role` that F1 screens on. All 357 depend on both. Skipping enrichment breaks F1 for precisely the jobs it skips — and the decision above means F1 cannot move off `primary_role` onto `role_type`, which was the only route to unblocking it.

So the two questions turned out to be one question with an order, and the first answer closes the second.

### Why we did it this way

**`role_type` stays as a label, not a gate.** It is still recorded, still shown on the board, and still worth having. It is simply not fit to decide whether a graduate sees a job.

**Counting first, arguing second.** Both of these could have been settled by a confident opinion in either direction, and both opinions would have been wrong: the classifier looked good enough to trust, and the enrichment saving looked easy to take. Thirty lines of counting changed both answers.

### One thing that needed care

**The metric F5's notes tell you to watch can never move.** They say to watch the "keyword" share of `skills_source` over a few real days. On this run it read: `ai` 526, `none` 145, `keyword` 0.

That is not a bad day. Enrichment runs for every job and always writes a blurb, and the tidy-up step relabels a job's source as `ai` whenever a blurb is present — correctly, since the AI's list is what survives. So the keyword share is structurally pinned at zero and always will be, as long as every job goes through enrichment.

The number that actually works is `needs_ai_skills`, which is set before enrichment and never overwritten. The guidance in F5's entry should be read as pointing at that instead.

### How to check it is working

- `python -m scripts.decision_check` from `backend/`, after unzipping a run's artifact. Both questions, one page.
- **The number to watch on question one** is the `search_term` share of the disagreements. If it ever drops sharply, the classifier's fallbacks have been tightened and the swap becomes worth re-examining.

### Still open

**The board's role filter is unreliable for some live listings, and that is a separate problem.** The 284 mislabelled jobs never reach the board, because F1 drops them. But `role_type` is what the board's own filter runs on, and in a sample of 60 kept jobs about 10 got their track from the search term. A *RevOps Data Analyst* showed as **Security** because the employer is a security company and the word is all over the description; two *Data Engineers* showed as **DevOps/Cloud** purely because of which search found them. Smaller than the F1 problem and worth fixing after it.

**The enrichment skip is closed until something changes.** Either F1 moves off the AI's label — which needs the classifier's fallbacks fixed first — or the cost pressure returns. Neither is true today. If the bill ever bites, there is a middle path that does not need either: keep enrichment for every job but send a shorter request for the 357 that already have skills, asking only for the blurb and the role label.

### Files

| File | What it does |
| :--- | :--- |
| `backend/src/pipeline/qa.py` | The three weekly checks, including F1's non-tech mode and its triage |
| `backend/tests/unit/test_qa.py` | 27 tests, mostly on working out which jobs reached the sheet |
| `backend/src/pipeline/screening.py` | Five new blocklist entries, two of them naming the role rather than the field |
| `backend/tests/unit/test_screening.py` | The five real leaks, and the two jobs wrongly suspected |
| `backend/src/pipeline/levels.py` | `supervisor` added to the above-cohort title rule |
| `backend/tests/unit/test_levels.py` | The supervisor case, and the lowest-rung rule still winning |
| `backend/scripts/decision_check.py` | Counts the evidence for the two decisions F7 and F5 parked |

---

## Scope — entry level and junior software roles only

### The problem

Emma opened the board, ticked **Software development** and **entry level**, and the first result was a *Graduate Intern: Data Analytics*. Of the four the filter found, one was a real match. Her words: "By this, things are still a way off done."

Three separate things were wrong, and each of them alone was enough to produce that screen.

**1. Jobs were being given a track by the search phrase that found them.** Indeed matches loosely, so a search for "technical support" returns waiters and warehouse coordinators — and every one of them was stamped Technical Support without anything having read the job. Measured on live data: of 284 jobs where the role classifier disagreed with F1's own screening, 227 — four fifths — had got their track from the search term alone.

**2. A technology mentioned anywhere in the body text was being read as the job's track.** An *HPE ATP Compute Solutions Certified Engineer* — infrastructure work — came out as Software development because its description said "Python" somewhere in 1500 characters.

**3. The board was carrying levels and tracks nobody asked for.** Mid-level roles, and every tech track, when CodeSpace teaches software development.

### What changed

**The search term no longer decides anything.** A job's track now comes from its own title, or failing that from a phrase in its own body text that *names a role* — "software developer", "test analyst". A technology is not a role: a job mentioning Python is no more a software job than a job mentioning Excel is an accountancy one. Bare "developer" is out too, because "you will work alongside our developers" describes the team, not the vacancy.

**A third screen decides scope.** Only `Software development` reaches the sheet and the board. Every other track is still scraped, still enriched, still classified — and filed on the Exclude tab under its own stage, so widening the scope later is one constant (`PUBLISHED_ROLE_TYPES`) and a re-run.

**Only two levels ship.** Entry level and junior. Mid is out.

### The reversal worth naming

**Unknowns used to be kept and are now dropped.** The old reasoning was that an ad which says nothing about level is not evidence the job is out of reach — still true of any single ad. What it produced in aggregate was a board 183 of 377 filled with jobs nobody had leveled, which is the opposite of what somebody filtering for entry level wants. A job that cannot show it is entry level or junior does not ship. Every such drop is flagged `needs_review`, so the weekly QA pass can measure what it costs rather than assume.

### The bug underneath "Developer Level 2"

The single job Emma named turned out to be its own defect, and not in the screening at all.

The ad said: *"brings together over 300 years of combined gaming experience"*. F3's number pattern was `\d{1,2}` with nothing guarding either end, so it matched the **"00"** in "300" — and the word "experience" sat right there to confirm it. Zero years is entry level. The whole chain then ran correctly on a number that was never in the ad. The same sentence shape did it again on Absa's *"with over 100 years of rich history"*, twice.

Two fixes, both needed. The number pattern now refuses to match part of a longer number. And a company's own age is rejected outright — "of rich history", "of combined experience", "in business", "of excellence" — because the sentence is about the employer, not the applicant.

### What it does to the board

Run over the live board as published on 21 August: **377 jobs in, 20 out.**

| Dropped by | Jobs |
| :--- | ---: |
| Not software (162 with no track at all, 132 on another tech track) | 294 |
| Above the cohort — mid, senior, or no level established | 59 |
| Non-tech title (F1, unchanged) | 4 |
| **Reaching the board** | **20** |

All 20 are real entry level or junior software developer jobs. Read against `date_added`, the 377 was six days of scraping including a backfill, so the honest steady-state figure is roughly **one to three new qualifying jobs a day**.

That is the trade, stated plainly: the board is now correct and thin, where it was full and wrong. Widening it is two constants, and the evidence for which way to widen is on the Exclude tab.

### How to check it is working

- **In the run log**, the screening summary now has a line for `dropped as not software` alongside the F1 and F4 lines.
- **On the Exclude tab**, the Stage column distinguishes `scope not software` from `F4 above cohort`, so "we are missing good jobs" and "we are showing wrong jobs" can be told apart without opening a single ad.
- **On the board**, the role filter should offer one option and the level filter two. If a third level appears, a job reached the board without going through the screen.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/screening.py` | `PUBLISHED_ROLE_TYPES`, `PUBLISHED_LEVELS`, and the new scope screen |
| `src/pipeline/roles.py` | Track comes from the ad's own words; the search-term tier is gone |
| `src/pipeline/experience.py` | Digit guards on the number pattern, and the company-age rejection |
| `tests/unit/test_screening.py` | The scope screen, and the unknown-level reversal |
| `tests/integration/test_leveling_pipeline.py` | "Developer Level 2" pinned end to end |

---

## The count said four, the board drew thirty-two

### The problem

The other half of Emma's report, and the half that was not about screening at all: *"The filter showed 4 matching jobs yet many cards displayed, and the first was Graduate Intern: Data Analytics."*

This did not reproduce on a made-up set of jobs. It reproduced on the first try against the real board, and it turned out to be two defects stacked on each other.

**Twenty-one of the 377 rows were the same advert as another row.** One Microsoft Power Platform post was on six rows, an ABAP Developer on five, an HPE ATP engineer on four — one row per day the pipeline had run.

The publisher merges each day's jobs into the running `jobs.json` using F9's title/company/city key, and F9 will not match on a key it cannot trust: it needs a title **and** a company. Plenty of Indeed ads carry no company at all. Those matched nothing, every day, and were appended again on every run. The board was not accumulating jobs, it was accumulating copies.

**The board keys its cards by apply link.** Twenty-one rows shared a link with another row, so twenty-one keys were repeated. React does not raise an error on repeated keys — it mis-reconciles them. On a filter change it left stale cards in the DOM. The count, which reads the filtered array directly, was telling the truth the whole time; the cards were not.

Measured on the live board, before and after:

| | count line | cards drawn |
| :--- | ---: | ---: |
| No filters | 377 of 377 | 377 |
| Software development | 106 of 377 | **127** |
| …and entry level | 4 of 377 | **32** |

After the fix every row of that table reads 377/377, 106/106, 4/4 — and the four cards are exactly the four Emma listed in her email. The filtering was never wrong. The screen was.

### What changed

**The publisher matches on the apply link first**, then falls back to F9's key. Indeed's `jk` is the posting's own id, so an identical link is an identical advert and there is nothing to weigh up. F9's key still catches the same advert reached through two different links.

**The board's card key no longer assumes the link is unique.** The index goes into the key, so it is unique whatever arrives. The publisher no longer creates those rows, but a key must not depend on data being clean in order to work — that dependency is what turned a data bug into a wrong number on a client's screen.

### What this does not fix

The twenty-one duplicate rows already on the board stay there until they age out of the 45-day window. The card key fix means they render honestly — the count and the cards agree — but the same advert still appears more than once. Clearing them is a one-off rewrite of `jobs.json`, deliberately not done as part of this change.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/publish.py` | `merge` matches on the apply link before F9's key |
| `frontend/src/App.jsx` | Card key includes the index, so repeated links cannot desync the list |
| `tests/unit/test_publish.py` | The five-day pile-up, pinned |
| `frontend/src/App.test.jsx` | Cards drawn must equal the count claimed |

---

## Apply or stretch — what a junior can actually take

### The problem

The narrow rules worked, and that was the problem. The first live run under them added **one job**. Reading the Exclude tab showed what they were throwing away: *Junior Data Analyst*, *Full Stack Developer*, *Software Engineer – GoLang* — jobs a CodeSpace graduate could plausibly get, dropped for reasons that did not survive a second look.

Three of them, from Monde's own read of the tab:

**Ads that ask for a related qualification.** "BSc Computer Science or related" is something a CodeSpace graduate *satisfies*. Reading it as a barrier is backwards.

**Ads that name a stack.** Docker, Kubernetes, Go, Shopify. A junior learns these, and AI has collapsed how long that takes. Most companies now write AI skills into the ad themselves.

**Ads that ask for three years.** A developer two years in reads that line, checks the requirements listed underneath, meets them, and applies. Employers write the years line as a filter and hire on the requirements.

### The principle

**Gate on what the ad demands, not on what it is called.** The old design asked two label questions — is this software, is this junior — and labels are exactly what had been going wrong all week. The question that matters is whether somebody three years out of CodeSpace could get the job.

That splits requirements in two. Real gates: four or more years, senior/lead/principal in the title, credentials outside the field, a clearance. Not gates: the stack named, the qualification asked for, silence about level, or the word "Intermediate".

### Three tiers instead of keep-or-drop

| Tier | Rule |
| :--- | :--- |
| **apply** | On track, entry level or junior, asking two years or fewer |
| **stretch** | On track, mid asking three years or fewer — or no level established at all |
| neither | Four or more years, or senior/lead/principal in any form |

Every kept job carries `tier` and `tier_reason`. The gate that does not move is seniority.

**The stretch tier is the whole redesign.** Under the two-way rule the board dropped 31 software jobs whose ads never mentioned a level — thrown out for lack of proof rather than for evidence against — and 28 more asking for exactly three years.

### Scope: five tracks, not one

Core is software development and mobile. Adjacent and also published: **Data & BI**, QA/testing, and low-code — jobs a graduate who can build things plausibly takes first. Out: technical support, security, DevOps. All genuinely technical, none of them where this course leads; a service desk leads to infrastructure, not development.

**Data & BI did not exist as a track.** The taxonomy had seven types from the brief and none of them was data, which is why *Junior Data Analyst* and *Graduate Data Analyst (AI and Analytics)* came out of F7 with no track at all — and the scope screen reads no track as "not our kind of work". 24 of the 29 data jobs on the live board had no role type. The taxonomy was wrong, not the jobs. It is the eighth now.

### Freshness: 7 days, floored at 5

The window drops from 45 days to 7 — a graduate wants what is open now, and a month-old advert on a job board mostly wastes an afternoon.

But **never sooner than five days after we first found it**, and that floor is not a nicety. 37% of the ads we scrape are *already* more than seven days old the moment we first see them; the median is four days old at first sighting. A strict window bins better than a third of every day's find on the day it arrives — ads that are open, taking applications, and that nobody has been shown yet. The cost is that some adverts linger up to twelve days. That is the cheaper mistake.

### Read the ad before opening it

The card gained a **View description** button next to Apply. Without it a student had the one-line blurb and nothing else, so the only way to learn what a job actually asked for was to click Apply, land on the employer's site, and discover there that it wanted five years.

The description was already on the card — 3000 characters of it, on 369 of 378 jobs — it simply was not being shown.

It needed cleaning first. 350 of 378 adverts use markdown `**` to mark their section headings and about half carry backslash escapes the source site left in, so shown raw an ad opens with `***Job title*** ... \& Gap Analysis`. Those markers are the ad's own structure, so they are rendered as real headings rather than stripped. Rendered as text segments, never as HTML: the text is scraped, and `dangerouslySetInnerHTML` would put whatever an employer typed straight into the page.

### What it does to the board

Run over the live board of 22 August, 378 jobs:

| | Jobs |
| :--- | ---: |
| Passing the tiers | 154 — 45 apply, 109 stretch |
| **On the board, inside the 7-day window** | **66 — 18 apply, 48 stretch** |

Against 20 under the narrow rules, and one new job on the run that morning. The spec projected 65; the code produced 66.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/screening.py` | The three tiers, and the five published tracks |
| `src/pipeline/roles.py` | Data & BI, the eighth track |
| `src/pipeline/publish.py` | 7-day window with the 5-day floor |
| `frontend/src/components/JobCard.jsx` | View description, next to Apply |
| `frontend/src/lib/format.js` | Cleaning the scraper's marks out of an advert |

---

## Ask first, then match — the board stops guessing

### The problem

Monde, reading the board: *"companies will just label a job as junior without proper information in the description or skills required for that job. Lets not guess, but match what the user has selected."*

The numbers on a real 66-job board say the same thing:

| Where the level label came from | Jobs |
| :--- | ---: |
| Nothing at all — no evidence | 29 |
| A years figure read from the ad | 27 |
| The company's own word in the title | 10 |

**Forty-four percent of the board carried no evidence of its own level.** Only three jobs rested on a title word with nothing to back it — *Junior Process Developer*, *Junior Data Analyst* — but those three are the shape of the problem, and typing "Junior" into a title costs an employer nothing.

Opening the board with a list of those jobs, ordered by date, is presenting labels we do not trust as though we did.

### What changed

**The board opens empty.** A student picks the kind of work, where they are, and the skills they already have, then presses *Search for jobs*. Nothing is shown before that. The search button is disabled until there is a track or a level to search on — skills alone would mean the whole board sorted, which is the everything-at-once screen this replaces.

**Level is matched on the ad's own number, not its adjective.** Selecting *junior* means "ads asking up to three years"; *entry level* means "up to one". An ad that calls itself junior and then asks for five years does not come back from a junior search. An ad that states no number cannot be ruled out on level, so it stays in — flagged as unstated, so the student knows to read it.

**Skills rank, they never filter.** Every job that passes track and level is shown; the ones sharing the most skills come first. A seven-day board holds a few dozen jobs, and if ticking React and Docker removed everything else a student would see two results or none — and a student who sees "no matches" concludes there are no jobs.

**Every card says what its match rests on.** *Asks for 2 years* · *Matches 4 of your 6 skills: Python, SQL, Git, React* — or, honestly, *The ad does not say what level it wants*. Having worked around the labels, the card cannot then ask to be trusted on the same footing as them.

**The level badge is gone from the card.** It was the pipeline's own guess, and it contradicted the search that found the job: a student who asked for junior work saw "Mid" stamped on the first result, directly above a line saying the ad asks for three years. The line is the true thing. Only the badge went; the level is still derived, still on the record, still what F4 screens on.

### What did not change

The keyword box and the sort control are still there — they moved into the results, since there is nothing to keyword-search or re-order before a search has happened. Sorting gained *Best match first* and defaults to it.

`FilterPanel` is deleted rather than left unused. `SearchForm` replaces it.

### How to check it is working

- **Open the board.** No jobs. A prompt, a form, and a count of what is open.
- **Search software development at junior.** On the 22 August board that returns 30 of 66, top result *Java Developer (Intermediate)* — reached because the ad says three years, not because anything called it junior.
- **Tick a skill you do not have.** The count must not drop. If it does, skills have become a filter again.

### Files

| File | What it does |
| :--- | :--- |
| `frontend/src/lib/match.js` | The matching rules, and the evidence each match rests on |
| `frontend/src/components/SearchForm.jsx` | What a student tells us before any jobs are shown |
| `frontend/src/App.jsx` | Empty until searched; keyword and sort moved into the results |
| `frontend/src/components/JobCard.jsx` | The match note, and no level badge |

---

## Three fixes off the first real run of the tiers

Run 137 was the first daily run under the apply/stretch tiers. The morning check said the numbers added up, and reading it properly found three things anyway.

### 1. A QA job thrown away, and what it says about F1 and F7

The check's "doubtful ones" list — the drops flagged for review — opened with titles like *Software Quality Analyst*. Traced:

```
F1:  kept    (title:tech_analyst)   ← F1 says this is a tech job
F7:  (none)                          ← F7 cannot name its track
→ dropped by the scope screen
```

QA is in scope. That was a QA job thrown away because **F1 can accept a job on the AI's role label, while F7 only ever reads the ad**. Where they disagree, and the scope screen now drops whatever F7 could not name, the disagreement costs a job.

The first instinct was to widen F7 until it agreed with F1. Measuring it killed that idea. 137 of 378 jobs on the live board are F1-yes / F7-silent, and reading the list shows most of it is **F1 being loose, not F7 being narrow**:

| Title | Kept by F1 because |
| :--- | :--- |
| ESG Country Analyst | the AI called it `tech_analyst` |
| Client Services Specialist | the AI called it `support` |
| Support Centre Consultant: Irrigation | the AI called it `support` |
| Cancellation & Retention Specialist | the AI called it `support` |

Widening F7 to agree would import that looseness and undo the reason the scope screen exists. So the disagreement is now **printed in the run log rather than designed away** — ten titles a day, the ones worth reading — and the two real misses in it got their own rules:

- `Software Quality Analyst` → QA. Qualified tightly: the first version allowed "product" and "controller" and promptly claimed *Product Quality Controller*, which is a factory floor. A bare "Quality Analyst" is as often manufacturing as it is a test team.
- `Data Analytics` → Data & BI. The rule read `data analyst`, and analytics is not analyst, so *Graduate Intern: Data Analytics* appeared twice on the board with no track at all.

157 jobs now pass, against 154 before. The remaining 137 unnamed titles are the review queue, and that is the honest state of it.

### 2. The morning check reported levels, not tiers

The tier is the decision now. Read on its own, the level breakdown is alarming and should not be — "unknown 45%, mid 29%" is the stretch tier working exactly as designed, not the leveling falling over. The check leads with the tier and treats level as working rather than deciding:

```
WHAT REACHED THE BOARD LOOKS LIKE
  stretch  (worth a shot)         110  (70%)
  apply    (clearly in reach)      47  (30%)

  by level, which is now working rather than deciding:
    unknown          67  (43%)
```

This needed a file that did not exist. `combined_jobs_leveled.json` is saved *before* screening, so it carries no tier and no idea which jobs were kept — the check had been subtracting the excluded file from it to guess. The run now saves `board_jobs.json` straight after screening, and a run without one says so plainly rather than reporting silence as health.

(While in there: `WHAT HAPPENED TO THE JOBS` was being printed twice, which is visible in run 137's output.)

### 3. The level review was reading the wrong twenty jobs

The QA sampler drew from all 642 jobs the run touched. Fifteen of run 137's twenty rows were a *Wakeboarding Crew* instructor, a *Physics and Mathematics Teacher*, a *Medical Officer* and an *ACCA Trainee Accountant* — jobs nobody would ever be shown. A review pass is somebody reading twenty adverts by hand; it belongs on the jobs a graduate actually sees.

It now samples `board_jobs.json`. `-i data/cache/combined_jobs_leveled.json` still gets the old behaviour, which remains the right file when the question is how well F2 levels in general rather than how good the board is.

### Files

| File | What it does |
| :--- | :--- |
| `src/pipeline/roles.py` | The two new rules, and the unnamed-titles list in the run log |
| `src/core/orchestrator.py` | Saves `board_jobs.json` after screening |
| `scripts/morning_check.py` | Leads with tiers; reads the board file; header printed once |
| `src/pipeline/qa.py` | Level review samples the board by default |

---

## Run 142 — a red X, and a run that arrived at eight in the evening

### The failure: a name collision cost a whole run

Run 142 ended with exit code 1. The reason in the log:

```
[18:29:09] ✗ Sheets write error: Could not open spreadsheet:
           ('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))
[18:29:09] Saved 83 jobs to data/cache/combined_jobs_fallback.json
```

Both lines carry the same timestamp, and that is the whole story. Opening the spreadsheet is wrapped in a retry with `tries=4, delay=3.0, backoff=2.0` — a real retry would have taken twenty-one seconds. It failed in the same second it started, so the retry never fired.

Why it never fired:

```
requests.exceptions.ConnectionError  ->  RequestException  ->  OSError
builtin ConnectionError                                    ->  OSError
```

**They are siblings, not parent and child.** gspread talks to Google through requests and raises requests' version; the decorator caught the builtin. The `except` clause read as though it covered a dropped connection and covered nothing at all.

The Exclude tab wrote successfully three seconds later, on the same credentials to the same spreadsheet, so this was a transient blip and a single retry would have saved the run.

**Why the tests did not catch it.** `test_a_dropped_connection_is_retried` raises `ConnectionResetError` — a builtin, and a genuine subclass of the builtin `ConnectionError`. It passed for weeks while proving the retry worked on an exception the code never sees. The new test raises what gspread actually raises, and fails against the old tuple.

The fix catches `requests.exceptions.RequestException` — the whole family: connection resets, timeouts, DNS failures, chunked-encoding errors. The builtins stay, since a plain socket error can still surface from lower down.

### Everything else in that run worked

Worth recording, because the log looks alarming and mostly is not. The Anthropic workspace hit its usage limit, so all 133 enrichment batches failed — every job went through with no AI role label at all. The pipeline still put 83 jobs on the board, because F1 falls back to the title and F7 only ever reads the ad. The board published, the Exclude tab wrote, the artifact uploaded. One phase of five failed and the run still delivered.

### The run that arrived at eight in the evening

The schedule was `0 6 * * *` — 08:00 South Africa. What actually happened:

| Run | Started (SAST) | Late by |
| :--- | :--- | ---: |
| 23 Aug | 08:34 | 34m |
| 24 Aug | 08:50 | 50m |
| 25 Aug | 08:39 | 39m |
| 26 Aug | 08:40 | 40m |
| 27 Aug | **19:16** | **11h 16m** |
| 28 Aug | **20:08** | **12h 08m** |

GitHub queues scheduled workflows on a best-effort basis and delays them under load — and the heaviest load is the top of every hour, which is exactly where this sat. The 34-to-50-minute baseline was that contention all along; the two evening runs were the same mechanism on a bad day.

Moved to `37 4 * * *` — 06:37 SAST. An odd minute avoids the stampede, and starting earlier means an hour or two of queueing still lands before the working day.

**This buys margin, not a guarantee.** GitHub promises no accuracy on schedules and may drop a scheduled run entirely. If the run ever has to be reliably early, it needs an external trigger calling `workflow_dispatch` rather than a cron in the workflow.

### Files

| File | What it does |
| :--- | :--- |
| `src/writers/sheets.py` | Retries the connection error gspread actually raises |
| `tests/unit/test_sheets_retry.py` | The real exception, and the rest of the requests family |
| `.github/workflows/daily-scrape.yml` | Off the hour, and earlier |

---
