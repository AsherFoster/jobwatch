from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import CompanyDetails
from jobwatch.pipeline.sync_companies import get_company, load_company_details
from jobwatch.task_kinds import LoadCompanyDetails
from jobwatch.test_scene import Scene, queued_tasks


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
    return sorted(task.company_id for task in queued_tasks(session, LoadCompanyDetails))


def test_creates_a_blank_row_and_queues_load_company_details(session):
    company = get_company(
        session, name="Acme", linkedin_slug="acme", logo="https://logo.test/acme.png"
    )

    assert company.name == "Acme"
    assert company.linkedin_slug == "acme"
    assert company.logo == "https://logo.test/acme.png"
    assert company.description == ""
    assert company.generated_at is None

    assert queued_company_ids(session) == [company.id]


def test_slug_match_returns_the_existing_row_despite_name_differences(session):
    first = get_company(session, name="Acme", linkedin_slug="acme")
    session.commit()

    # Same slug under a different name: no second row.
    second = get_company(session, name="Acme ApS", linkedin_slug="acme")

    assert second.id == first.id
    assert company_details(session).name == "Acme"
    assert queued_company_ids(session) == [first.id]


def test_never_matches_by_name_so_a_slugless_scrape_creates_a_duplicate(session):
    first = get_company(session, name="Acme")
    session.commit()
    second = get_company(session, name="Acme")

    assert second.id != first.id
    assert queued_company_ids(session) == [first.id, second.id]


@pytest.mark.asyncio
async def test_load_company_details_generates_description(session, scene: Scene, describe):
    company = scene.company_details(name="Acme", description="")

    await load_company_details(session, company.id)

    assert company.description == "Acme makes widgets"
    assert company.generated_at is not None
    assert describe == ["Acme"]


@pytest.mark.asyncio
async def test_load_company_details_does_not_redo_work_already_done(
    session, scene: Scene, describe
):
    company = scene.company_details(name="Acme", description="Acme makes widgets")

    await load_company_details(session, company.id)

    assert company.description == "Acme makes widgets"
    assert describe == []
