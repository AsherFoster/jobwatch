from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import CompanyDetails
from jobwatch.pipeline.sync_companies import ensure_company_details
from jobwatch.test_scene import Scene


@pytest.fixture
def describe(monkeypatch) -> list[str]:
    """Replace the Gemini call with a canned description; returns the list of
    company names it was asked to describe."""
    calls: list[str] = []

    async def fake(company: str) -> str:
        calls.append(company)
        return f"{company} makes widgets"

    monkeypatch.setattr("jobwatch.pipeline.sync_companies.generate_company_description", fake)
    return calls


def company_details(session: Session) -> CompanyDetails:
    return session.scalars(select(CompanyDetails)).one()


@pytest.mark.asyncio
async def test_creates_details_for_a_new_company(session, scene: Scene, describe):
    raw = (
        '{"company_url": "https://dk.linkedin.com/company/acme",'
        ' "company_logo": "https://logo.test/acme.png"}'
    )
    await ensure_company_details(session, scene.scraped_job(external_id="1", raw=raw))
    session.commit()

    details = company_details(session)
    assert details.name == "Acme"
    assert details.linkedin_slug == "acme"
    assert details.logo == "https://logo.test/acme.png"
    assert details.description == "Acme makes widgets"


@pytest.mark.asyncio
async def test_known_company_is_not_regenerated(session, scene: Scene, describe):
    await ensure_company_details(session, scene.scraped_job(external_id="1"))
    session.commit()
    await ensure_company_details(session, scene.scraped_job(external_id="2"))

    assert describe == ["Acme"]


@pytest.mark.asyncio
async def test_companies_match_by_linkedin_slug_despite_name_differences(
    session, scene: Scene, describe
):
    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    await ensure_company_details(
        session, scene.scraped_job(external_id="1", company="Acme", raw=raw)
    )
    session.commit()

    # Same slug under a different name and subdomain: no second row.
    raw = '{"company_url": "https://www.linkedin.com/company/acme"}'
    await ensure_company_details(
        session, scene.scraped_job(external_id="2", company="Acme ApS", raw=raw)
    )
    session.commit()

    assert company_details(session).name == "Acme"


@pytest.mark.asyncio
async def test_name_match_backfills_missing_linkedin_slug(session, scene: Scene, describe):
    # raw has no company_url
    await ensure_company_details(session, scene.scraped_job(external_id="1"))
    session.commit()
    assert company_details(session).linkedin_slug is None

    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    await ensure_company_details(session, scene.scraped_job(external_id="2", raw=raw))
    session.commit()

    assert company_details(session).linkedin_slug == "acme"


@pytest.mark.asyncio
async def test_failed_generation_creates_no_row_so_the_next_job_retries(
    session, scene: Scene, monkeypatch
):
    attempts = 0

    async def flaky(company: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("gemini down")
        return f"{company} makes widgets"

    monkeypatch.setattr("jobwatch.pipeline.sync_companies.generate_company_description", flaky)

    await ensure_company_details(session, scene.scraped_job(external_id="1"))
    assert session.scalars(select(CompanyDetails)).all() == []

    await ensure_company_details(session, scene.scraped_job(external_id="2"))
    session.commit()
    assert company_details(session).description == "Acme makes widgets"
