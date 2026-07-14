from __future__ import annotations

from sqlalchemy import select

from jobwatch.models import CompanyDetails
from jobwatch.pipeline.sync_jobs import hours_to_search, linkedin_company_slug


def test_linkedin_company_slug():
    assert linkedin_company_slug("https://dk.linkedin.com/company/too-good-to-go") == (
        "too-good-to-go"
    )
    assert linkedin_company_slug("https://www.linkedin.com/company/Acme/") == "acme"
    assert linkedin_company_slug("https://linkedin.com/company/acme?trk=x") == "acme"
    assert linkedin_company_slug("https://example.com/company/acme") is None
    assert linkedin_company_slug("https://dk.linkedin.com/jobs/view/123") is None
    assert linkedin_company_slug("https://dk.linkedin.com/company/") is None
    assert linkedin_company_slug("") is None
    assert linkedin_company_slug(None) is None


def test_companies_match_by_linkedin_slug_despite_name_differences(session, monkeypatch):
    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    run(session, FakeLLM(), [scraped("1", company="Acme", raw=raw)], monkeypatch)

    details = session.scalars(select(CompanyDetails)).one()
    assert details.linkedin_slug == "acme"

    # Same slug under a different name and subdomain: no second row.
    raw = '{"company_url": "https://www.linkedin.com/company/acme"}'
    run(session, FakeLLM(), [scraped("2", company="Acme ApS", raw=raw)], monkeypatch)
    assert len(session.scalars(select(CompanyDetails)).all()) == 1


def test_name_match_backfills_missing_linkedin_slug(session, monkeypatch):
    run(session, FakeLLM(), [scraped("1")], monkeypatch)  # no company_url in raw
    assert session.scalars(select(CompanyDetails)).one().linkedin_slug is None

    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    run(session, FakeLLM(), [scraped("2", raw=raw)], monkeypatch)
    details = session.scalars(select(CompanyDetails)).one()
    assert details.linkedin_slug == "acme"


def test_hours_to_search_defaults_to_24_when_search_has_no_jobs(session):
    assert hours_to_search(session, add_search(session)) == 24


def test_hours_to_search_covers_the_gap_since_the_last_scrape(session, monkeypatch):
    run(session, FakeLLM(), [scraped("1")], monkeypatch)
    search = add_search(session)
    assert hours_to_search(session, search) == 1  # just scraped; minimum lookback

    job = session.scalars(select(Job)).one()
    job.scraped_at = utcnow() - timedelta(hours=5, minutes=30)
    session.commit()
    assert hours_to_search(session, search) == 6  # rounded up, no gap

    # A different search's jobs don't count.
    assert hours_to_search(session, add_search(session, "something else")) == 24
