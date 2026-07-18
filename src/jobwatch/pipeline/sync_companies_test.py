from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import CompanyDetails
from jobwatch.pipeline.sync_companies import LoadCompanyDetails, get_company, load_company_details
from jobwatch.test_scene import Scene, queued_task_args, scene


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


def queued_company_ids(session: Session) -> list[int]:
    return sorted(args["company_id"] for args in queued_task_args(session, LoadCompanyDetails))


def test_creates_a_blank_row_and_queues_load_company_details(session, scene: Scene):
    raw = (
        '{"company_url": "https://dk.linkedin.com/company/acme",'
        ' "company_logo": "https://logo.test/acme.png"}'
    )
    company = get_company(session, scene.scraped_job(external_id="1", raw=raw))

    assert company.name == "Acme"
    assert company.linkedin_slug == "acme"
    assert company.logo == "https://logo.test/acme.png"
    assert company.description == ""
    assert company.generated_at is None

    assert queued_company_ids(session) == [company.id]


def test_known_company_is_returned_without_queueing(session, scene: Scene):
    first = get_company(session, scene.scraped_job(external_id="1"))
    session.commit()
    second = get_company(session, scene.scraped_job(external_id="2"))

    assert second.id == first.id
    assert queued_company_ids(session) == [first.id]


def test_companies_match_by_linkedin_slug_despite_name_differences(session, scene: Scene):
    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    first = get_company(session, scene.scraped_job(external_id="1", company="Acme", raw=raw))
    session.commit()

    # Same slug under a different name and subdomain: no second row.
    raw = '{"company_url": "https://www.linkedin.com/company/acme"}'
    second = get_company(session, scene.scraped_job(external_id="2", company="Acme ApS", raw=raw))

    assert second.id == first.id
    assert company_details(session).name == "Acme"
    assert queued_company_ids(session) == [first.id]


def test_name_match_backfills_missing_linkedin_slug(session, scene: Scene):
    # raw has no company_url
    first = get_company(session, scene.scraped_job(external_id="1"))
    session.commit()
    assert first.linkedin_slug is None

    raw = '{"company_url": "https://dk.linkedin.com/company/acme"}'
    second = get_company(session, scene.scraped_job(external_id="2", raw=raw))

    assert second.id == first.id
    assert company_details(session).linkedin_slug == "acme"
    assert queued_company_ids(session) == [first.id]


@pytest.mark.asyncio
async def test_load_company_details_generates_description(session, scene: Scene, describe):
    company = scene.company_details(name="Acme", description="")
    session.flush()

    await load_company_details(session, company.id)

    assert company.description == "Acme makes widgets"
    assert company.generated_at is not None
    assert describe == ["Acme"]


@pytest.mark.asyncio
async def test_load_company_details_does_not_redo_work_already_done(
    session, scene: Scene, describe
):
    company = scene.company_details(name="Acme", description="Acme makes widgets")
    session.flush()

    await load_company_details(session, company.id)

    assert company.description == "Acme makes widgets"
    assert describe == []
