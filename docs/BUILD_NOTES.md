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
- **In the sheet**, `must_have_skills` should never show two spellings of the same thing across different rows. If "JS" ever appears instead of "JavaScript", something is reaching the sheet without going through this module.

### Still open

**We have not seen this run against live data yet.** The matcher and the tidy-up are both tested against made-up ads and a full pipeline smoke test, not a real day's worth of postings.

**The cost-reduction decision is still open, on purpose.** Once there are a few real days of `skills_source` and `needs_ai_skills` in the run log, that becomes its own decision — whether keyword matching alone is finding enough to skip the AI for some jobs, and by how much it would cut the daily bill.

### Files

| File | What it does |
| :--- | :--- |
| `skills.json` | The one official skills list — 130 skills, names and aliases |
| `src/pipeline/skills.py` | The keyword matcher, the canonicaliser, and the AI-output tidy-up |
| `src/core/orchestrator.py` | Runs keyword matching as Phase 1.7, before the AI, and tidies the AI's output in Phase 2.4 |
| `tests/unit/test_skills.py` | 40 tests, including the three `skills_source` scenarios the bug fix depends on |

---

## F6 — The job board

**Done:** 15 August 2026

### The problem

Everything built so far — F1 through F5, F7, F9 — only ever reached one place: a Google Sheet the CodeSpace team can read but no graduate ever sees. All of that screening, leveling, deduping and skill-matching work had no public audience to show it to.

### What we built

Two halves.

**The data half.** A new module, `publish.py`, keeps `frontend/public/jobs.json` as its own running list — separate from the Sheet's history, which still carries thousands of rows scraped before F1 and F4 existed and were never screened for tech relevance or seniority. Each day's run merges in today's screened, deduplicated, leveled jobs, matching against what is already on the board with the same title/company/city key F9 already uses, so a job scraped again the next day replaces its old row instead of duplicating. Anything whose posting has aged past 45 days drops off on its own.

**The board itself.** A Vite + React + Tailwind CSS single-page app in `frontend/`, fetching `jobs.json` and rendering it as a searchable, filterable list — checkboxes for role type, level, work policy, skills and source, a cap on years of experience asked for, and free text search across title, company, blurb and description. Selecting several values inside one filter is OR ("React or Python"); different filters combine with AND ("Software track AND entry level AND (React or Python)").

The daily GitHub Action now commits `frontend/public/jobs.json` after every run — independent of whether the Sheets write succeeds — so Netlify redeploys the board automatically.

### Why we did it this way

**`jobs.json` is not a copy of the Sheet.** The Sheet still holds roughly 5,000 rows from before F1 and F4 existed, none of them screened. Publishing straight from the Sheet would put all of that back in front of graduates, undoing the whole point of that screening. So the board keeps its own running list instead, built only from jobs that have already been through the real pipeline.

**Filter options are read from the real data, not hand-maintained.** `extractFacets()` works out which role types, levels, skills and sources actually appear on the board and only offers those — skills ranked by how often they appear, so the most useful ones surface first. The filter panel can never drift from what is actually on the board, and never shows an option with nothing behind it.

**The retention window keeps the board honest.** Job ads do not stay open forever. Without a cutoff, the board would just become a second, slower-growing copy of the Sheet's own history. 45 days is the working number for now.

**Salary is shown, not filtered on.** Checked the real job data before deciding, the same way F2/F3 checked real years-of-experience data before trusting it: OfferZen and PNet never populate `salary_min`/`salary_max` at all, and only Indeed sometimes does, when the ad states it. Not enough real fill-rate to justify a filter people would expect to actually narrow their search.

### What we chose not to do

**We did not read the Sheet back to rebuild `jobs.json`.** Reconstructing full job records from the Sheet's flattened rows is lossy, and would also mean re-solving the "5,000 unscreened legacy rows" problem on every single run instead of once.

**We did not stand up a backend or API for the board.** `jobs.json` is a static file, fetched once on page load. That is what "publish jobs.json" in the brief actually asks for, and it is free to host.

### One thing that needed care — twice

**The `public/` convention.** The first version of `publish.py` wrote to `frontend/jobs.json`. Vite and Netlify only deploy files sitting inside `frontend/public/` — anything outside it never reaches the live site at all. Caught before any frontend code was written, by doing a real production build and confirming `jobs.json` actually landed in `dist/`, not by assumption.

**A locale bug in the salary formatter.** `Number.toLocaleString()` with no explicit locale formats thousands separators according to whatever locale the machine running it resolves — a comma on one machine, a space on another. The tests passed in the environment that built the feature and failed on the machine that actually runs the project, which is exactly the kind of thing a second machine catches that the first one cannot. Fixed by pinning the locale explicitly (`'en-US'`) so the output is the same everywhere, matching the comma the backend's own `format_salary()` always writes to the Sheet.

### How to check it is working

- **In the run log**, `[PHASE 3.7]` prints the board's publish summary: how many jobs were carried over, how many came in today, how many aged out, and the final total.
- **Backend tests**: `pytest -q` from `backend/` — 24 tests on `publish.py`, 100% coverage.
- **Frontend tests**: `npm test` from `frontend/` — 36 tests across the filter/search logic, the display formatters, and the page itself.
- **Visually**: once Netlify is connected, open the live URL and check search and the filter panel actually narrow the list.

### Still open

**The Netlify site is not connected yet.** `netlify.toml` sits at the repo root with the build settings already in it, so linking the repo should be all that is needed — no manual base directory/build command/publish directory configuration.

**No live run has gone through Phase 3.7 yet.** The first real `frontend/public/jobs.json` lands on the next scheduled run; today's board is running on a hand-written sample.

**The salary filter is deferred**, pending real fill-rate data from a live run.

**F1, F2/F3 and F4 still need verifying against a live run** — a pre-existing open item, not new to F6, but worth doing once there is a live board to see the result on.

### Files

| File | What it does |
| :--- | :--- |
| `backend/src/pipeline/publish.py` | Merges, dedupes and prunes the board's running `jobs.json` |
| `backend/tests/unit/test_publish.py` | 24 tests |
| `backend/src/core/orchestrator.py` | Runs publishing as Phase 3.7 |
| `.github/workflows/daily-scrape.yml` | Commits and pushes `jobs.json` after each run |
| `netlify.toml` | Netlify build config, at the repo root |
| `frontend/src/lib/filters.js` | The board's search and filter rules, and its facet extraction |
| `frontend/src/lib/format.js` | Salary, years and level display formatting |
| `frontend/src/App.jsx`, `frontend/src/components/`, `frontend/src/hooks/useJobs.js` | The page itself — search bar, filter panel, job cards, data fetching |

---

