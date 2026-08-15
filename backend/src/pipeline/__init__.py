"""
pipeline — processing steps that run between scraping and writing.

The daily run is a chain of small, testable steps. Each one takes jobs in,
returns jobs out, and records what it decided on the job dictionary itself,
so the run log and the Exclude tab can explain every decision afterwards.

Current steps:
    screening — decides keep or drop for each job before it reaches the
                sheet (F1)
"""