"""
Unit tests for catching the same job posted twice (F9).

Two things have to hold, and they pull in opposite directions:

    1. Adverts that really are the same collapse to one, even when the web
       address differs and the title carries different decoration.
    2. Adverts that merely look similar are left alone. Collapsing two
       different jobs loses one of them silently, which is the worse
       mistake -- a graduate never learns the job existed.
"""

import pytest

from src.pipeline.dedupe import (
    MIN_DESCRIPTION_FOR_MATCHING,
    agency_key,
    deduplicate,
    description_fingerprint,
    duplicate_key,
    is_comparable,
    key_from_row,
    log_dedupe,
    normalise,
    normalise_city,
    normalise_company,
    normalise_title,
)


def job(title="Software Developer", company="Acme", city="Cape Town",
        url=None, description="", date_posted="2026-08-13"):
    """Build a job dictionary for a test case."""
    return {
        "title": title,
        "company": company,
        "city": city,
        "location": f"{city}, South Africa",
        "job_url": url or f"https://za.indeed.com/viewjob?jk={abs(hash((title, company, city)))}",
        "description_snippet": description,
        "date_posted": date_posted,
    }


# ─── Tidying up ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("  Cape   TOWN, ", "cape town"),
    ("Johannesburg", "johannesburg"),
    ("", ""),
    (None, ""),
])
def test_values_are_tidied_for_comparison(value, expected):
    assert normalise(value) == expected


@pytest.mark.parametrize("title,expected", [
    ("Junior Developer (Remote)", "junior developer"),
    ("Junior Developer - Cape Town", "junior developer"),
    ("Junior Developer (Hybrid - 3 days)", "junior developer"),
    ("URGENT: Junior Developer", "junior developer"),
    ("Junior Developer Ref: ABC123", "junior developer"),
    ("  JUNIOR   DEVELOPER  ", "junior developer"),
])
def test_the_decoration_boards_add_is_stripped(title, expected):
    """All of these are the same advert wearing a different hat."""
    assert normalise_title(title) == expected


@pytest.mark.parametrize("company,expected", [
    ("Acme Solutions (Pty) Ltd", "acme solutions"),
    ("Acme Solutions Limited", "acme solutions"),
    ("ACME SOLUTIONS", "acme solutions"),
    ("Acme Solutions", "acme solutions"),
])
def test_legal_suffixes_do_not_split_a_company(company, expected):
    assert normalise_company(company) == expected


def test_the_city_falls_back_to_the_location_string():
    """Not every scraper separates the city out."""
    assert normalise_city({"location": "Durban, KwaZulu-Natal, South Africa"}) == "durban"
    assert normalise_city({"city": "Durban"}) == "durban"
    assert normalise_city({}) == ""


# ─── What counts as comparable ──────────────────────────────────────────────

def test_a_job_missing_its_title_or_company_is_not_comparable():
    """
    An empty key is not evidence that two jobs are the same. Collapsing on
    one would quietly throw away real listings.
    """
    assert is_comparable(duplicate_key(job())) is True
    assert is_comparable(duplicate_key(job(title=""))) is False
    assert is_comparable(duplicate_key(job(company=""))) is False


def test_a_missing_city_is_still_comparable():
    """Plenty of remote ads give no city; title and company are enough."""
    assert is_comparable(duplicate_key(job(city=""))) is True


# ─── Collapsing real duplicates ─────────────────────────────────────────────

def test_the_same_advert_under_two_addresses_collapses():
    """The re-post case the brief is actually about."""
    jobs = [
        job(url="https://za.indeed.com/viewjob?jk=aaa"),
        job(url="https://za.indeed.com/viewjob?jk=bbb"),
    ]
    unique, counts = deduplicate(jobs)

    assert len(unique) == 1
    assert counts["by_title_company_city"] == 1
    assert counts["removed"] == 1


def test_the_same_address_twice_collapses():
    jobs = [job(url="https://x/1"), job(url="https://x/1")]
    unique, counts = deduplicate(jobs)

    assert len(unique) == 1
    assert counts["by_url"] == 1


def test_decoration_does_not_hide_a_duplicate():
    jobs = [
        job(title="Junior Developer", url="https://x/1"),
        job(title="Junior Developer (Remote)", url="https://x/2"),
        job(title="URGENT: Junior Developer - Cape Town", url="https://x/3"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 1


def test_a_legal_suffix_does_not_hide_a_duplicate():
    jobs = [
        job(company="Acme Solutions", url="https://x/1"),
        job(company="Acme Solutions (Pty) Ltd", url="https://x/2"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 1


# ─── Leaving different jobs alone ───────────────────────────────────────────

def test_the_same_role_in_two_cities_stays_as_two():
    """
    Two cities means two jobs a graduate might apply to separately. The
    brief mentions this as a source of duplicates, but the honest reading
    is that a Cape Town job and a Durban job are different jobs.
    """
    jobs = [
        job(city="Cape Town", url="https://x/1"),
        job(city="Durban", url="https://x/2"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 2


def test_different_titles_at_the_same_company_stay():
    jobs = [
        job(title="Junior Developer", url="https://x/1"),
        job(title="Senior Developer", url="https://x/2"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 2


def test_the_same_title_at_different_companies_stays():
    jobs = [
        job(company="Acme", url="https://x/1"),
        job(company="Globex", url="https://x/2"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 2


def test_jobs_with_no_title_are_never_collapsed_together():
    jobs = [
        job(title="", company="", url="https://x/1"),
        job(title="", company="", url="https://x/2"),
    ]
    unique, _counts = deduplicate(jobs)
    assert len(unique) == 2


# ─── Which copy survives ────────────────────────────────────────────────────

def test_the_fuller_record_is_the_one_kept():
    """Two copies of an advert are rarely equally complete."""
    thin = job(url="https://x/1", description="Apply now.")
    full = job(url="https://x/2", description="A long and detailed advert. " * 10)

    unique, _counts = deduplicate([thin, full])
    assert len(unique) == 1
    assert unique[0]["description_snippet"] == full["description_snippet"]


def test_the_newer_posting_breaks_a_tie():
    older = job(url="https://x/1", date_posted="2026-08-01")
    newer = job(url="https://x/2", date_posted="2026-08-13")

    unique, _counts = deduplicate([older, newer])
    assert unique[0]["date_posted"] == "2026-08-13"


def test_the_kept_job_records_how_many_it_absorbed():
    jobs = [job(url=f"https://x/{i}") for i in range(4)]
    unique, _counts = deduplicate(jobs)

    assert len(unique) == 1
    assert unique[0]["duplicate_count"] == 3


def test_the_first_copy_keeps_its_place_in_the_list():
    """Swapping in a fuller record must not reorder the run."""
    jobs = [
        job(title="Alpha Developer", url="https://x/1"),
        job(title="Beta Developer", url="https://x/2", description="short"),
        job(title="Beta Developer", url="https://x/3", description="a much longer advert"),
        job(title="Gamma Developer", url="https://x/4"),
    ]
    unique, _counts = deduplicate(jobs)

    assert [j["title"] for j in unique] == [
        "Alpha Developer", "Beta Developer", "Gamma Developer"
    ]


# ─── Matching against the sheet ─────────────────────────────────────────────

def test_a_sheet_row_produces_the_same_key_as_a_job():
    """
    The sheet stores a full location string rather than a city, so the two
    have to be rebuilt into the same shape before they can be compared.
    """
    scraped = job(title="Junior Developer", company="Acme", city="Cape Town")
    row = {
        "Job Title": "Junior Developer (Remote)",
        "Company": "Acme (Pty) Ltd",
        "Location": "Cape Town, Western Cape, South Africa",
    }
    assert key_from_row(row) == duplicate_key(scraped)


def test_an_unrelated_sheet_row_produces_a_different_key():
    scraped = job(title="Junior Developer", company="Acme", city="Cape Town")
    row = {
        "Job Title": "Junior Developer",
        "Company": "Globex",
        "Location": "Cape Town, South Africa",
    }
    assert key_from_row(row) != duplicate_key(scraped)


# ─── Counting and reporting ─────────────────────────────────────────────────

def test_nothing_disappears_without_being_counted():
    jobs = [
        job(url="https://x/1"),
        job(url="https://x/1"),                       # same address
        job(url="https://x/2"),                       # same key
        job(title="Other Developer", url="https://x/3"),
    ]
    unique, counts = deduplicate(jobs)

    assert counts["input"] == 4
    assert counts["output"] == len(unique)
    assert counts["output"] + counts["removed"] == counts["input"]


def test_an_empty_run_is_safe():
    unique, counts = deduplicate([])
    assert unique == []
    assert counts["input"] == 0
    assert counts["removed"] == 0


def test_running_it_twice_removes_nothing_more():
    jobs = [job(url="https://x/1"), job(url="https://x/2")]
    once, _counts = deduplicate(jobs)
    twice, counts = deduplicate(once)

    assert len(twice) == len(once)
    assert counts["removed"] == 0


def test_log_dedupe_reports_the_count(capsys):
    """F9's done-when: the log shows the count."""
    _unique, counts = deduplicate([job(url="https://x/1"), job(url="https://x/2")])
    log_dedupe(counts)

    output = capsys.readouterr().out
    assert "duplicates removed: 1" in output
    assert "same title/company/city" in output
    assert "unique jobs: 1 of 2" in output



# ─── The agency case ────────────────────────────────────────────────────────
# A recruitment agency and the employer's own HR team both list the same
# role, under two different company names. The title/company/city key cannot
# see it, because company is exactly the field that differs.

ADVERT = (
    "We are looking for a developer to join our platform team in Cape Town. "
    "You will build and maintain our customer-facing web application using "
    "React and Node.js, working closely with designers and product managers. "
    "Matric plus a relevant qualification. Own transport preferred. "
    "We offer a competitive package and hybrid working arrangements."
)


def test_the_advert_text_identifies_the_job_when_the_company_does_not():
    """
    The employer posts as "Acme", the agency posts as "Talent Partners".
    Same advert, same city, so it is the same job.
    """
    employer = job(company="Acme", url="https://x/1", description=ADVERT)
    agency = job(company="Talent Partners", url="https://x/2", description=ADVERT)

    unique, counts = deduplicate([employer, agency])

    assert len(unique) == 1
    assert counts["by_same_advert_text"] == 1
    assert counts["by_title_company_city"] == 0     # company differs, so this pass missed it


def test_the_agency_pass_survives_small_formatting_differences():
    """Whitespace and capitals are tidied before the texts are compared."""
    employer = job(company="Acme", url="https://x/1", description=ADVERT)
    agency = job(company="Talent Partners", url="https://x/2",
                 description="  " + ADVERT.upper().replace(". ", ".  ") + "  ")

    unique, _counts = deduplicate([employer, agency])
    assert len(unique) == 1


def test_a_short_advert_never_identifies_a_job():
    """
    "Apply now" is not evidence. Two jobs sharing a one-line blurb are not
    the same job, and collapsing them would lose a real listing.
    """
    short = "Apply now. Great opportunity."
    assert description_fingerprint({"description_snippet": short}) == ""

    one = job(title="Developer", company="Acme", url="https://x/1", description=short)
    two = job(title="Developer", company="Globex", url="https://x/2", description=short)

    unique, _counts = deduplicate([one, two])
    assert len(unique) == 2


def test_an_advert_at_the_length_boundary_counts():
    text = "a" * MIN_DESCRIPTION_FOR_MATCHING
    assert description_fingerprint({"description_snippet": text}) != ""

    text = "a" * (MIN_DESCRIPTION_FOR_MATCHING - 1)
    assert description_fingerprint({"description_snippet": text}) == ""


def test_no_description_at_all_is_never_matched_on():
    one = job(company="Acme", url="https://x/1", description="")
    two = job(company="Globex", url="https://x/2", description="")

    unique, _counts = deduplicate([one, two])
    assert len(unique) == 2


def test_the_same_advert_in_two_cities_still_stays_as_two():
    """City stays in the key, so the two-cities rule is not undone."""
    cape = job(city="Cape Town", company="Acme", url="https://x/1", description=ADVERT)
    durban = job(city="Durban", company="Talent Partners", url="https://x/2",
                 description=ADVERT)

    unique, _counts = deduplicate([cape, durban])
    assert len(unique) == 2


def test_different_adverts_at_different_companies_stay():
    """The whole point of using the text is that different text means different job."""
    one = job(company="Acme", url="https://x/1", description=ADVERT)
    two = job(company="Globex", url="https://x/2",
              description=ADVERT.replace("React and Node.js", "Java and Spring Boot"))

    unique, _counts = deduplicate([one, two])
    assert len(unique) == 2


def test_a_trimmed_copy_is_not_collapsed():
    """
    The honest limit of plain matching. When an agency rewrites or trims the
    advert rather than copying it, the texts differ and the two stay as two.
    Catching those would need fuzzy similarity, which the brief rules out --
    and which fails in the direction that silently loses real jobs.
    """
    copied = job(company="Talent Partners", url="https://x/1", description=ADVERT)
    trimmed = job(company="Acme", url="https://x/2",
                  description=ADVERT + " Full benefits and medical aid.")

    unique, _counts = deduplicate([copied, trimmed])
    assert len(unique) == 2


def test_the_newer_copy_wins_when_the_advert_is_identical():
    """Between two word-for-word copies, keep the more recent posting."""
    older = job(company="Talent Partners", url="https://x/1",
                description=ADVERT, date_posted="2026-08-01")
    newer = job(company="Acme", url="https://x/2",
                description=ADVERT, date_posted="2026-08-13")

    unique, _counts = deduplicate([older, newer])
    assert len(unique) == 1
    assert unique[0]["date_posted"] == "2026-08-13"


def test_the_agency_key_leaves_company_out():
    employer = job(company="Acme", description=ADVERT)
    agency = job(company="Talent Partners", description=ADVERT)
    assert agency_key(employer) == agency_key(agency)


def test_all_three_passes_are_counted_separately():
    jobs = [
        job(url="https://x/1", description=ADVERT),
        job(url="https://x/1", description=ADVERT),                      # same address
        job(url="https://x/2", description=ADVERT),                      # same company key
        job(company="Talent Partners", url="https://x/3", description=ADVERT),  # agency
        job(title="Unrelated Role", url="https://x/4", description=ADVERT),
    ]
    unique, counts = deduplicate(jobs)

    assert counts["by_url"] == 1
    assert counts["by_title_company_city"] == 1
    assert counts["by_same_advert_text"] == 1
    assert counts["removed"] == 3
    assert counts["output"] + counts["removed"] == counts["input"]
    assert len(unique) == 2


def test_the_log_reports_the_agency_count(capsys):
    _unique, counts = deduplicate([
        job(company="Acme", url="https://x/1", description=ADVERT),
        job(company="Talent Partners", url="https://x/2", description=ADVERT),
    ])
    log_dedupe(counts)

    output = capsys.readouterr().out
    assert "same advert via another poster" in output