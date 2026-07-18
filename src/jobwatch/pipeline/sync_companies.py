from __future__ import annotations

import json
from dataclasses import dataclass

import structlog
from awa.bridge import insert_job_sync
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.job_sources.base import ScrapedJob
from jobwatch.job_sources.linkedin import linkedin_company_slug
from jobwatch.models import CompanyDetails, utcnow

log = structlog.get_logger()


@dataclass
class LoadCompanyDetails:
    """Generate the description for a CompanyDetails row created by get_company."""

    company_id: int


async def generate_company_description(company: str) -> str:
    # Imported lazily: google-genai is the optional [gemini] extra.
    from jobwatch.llm import gemini

    return await gemini.generate_company_description(company)


def get_company(session: Session, item: ScrapedJob) -> CompanyDetails:
    """Return the CompanyDetails row for this job's company, creating a blank
    one — and queuing `load_company_details` to fill it in — the first time a
    company is seen.

    An existing company is matched by its LinkedIn slug when the scrape
    provides one, falling back to a case-insensitive name match (which also
    backfills the slug on rows that predate it).
    """
    raw = json.loads(item.raw)
    slug = linkedin_company_slug(raw.get("company_url"))
    existing = None
    if slug:
        existing = session.scalar(
            select(CompanyDetails).where(CompanyDetails.linkedin_slug == slug)
        )
    if existing is None:
        existing = session.scalar(
            select(CompanyDetails).where(CompanyDetails.name.ilike(item.company))
        )
        if existing is not None and existing.linkedin_slug is None:
            existing.linkedin_slug = slug
    if existing is not None:
        return existing

    company = CompanyDetails(
        name=item.company, linkedin_slug=slug, logo=raw.get("company_logo") or None
    )
    session.add(company)
    session.flush()
    insert_job_sync(session, LoadCompanyDetails(company_id=company.id))
    return company


async def load_company_details(session: Session, company_id: int) -> None:
    """Generate a company's description, then stamp generated_at. A no-op if
    the description is already filled in, so a retry after a partial failure
    doesn't redo work that already succeeded."""
    company = session.get(CompanyDetails, company_id)
    assert company is not None

    if not company.description:
        company.description = await generate_company_description(company.name)
    company.generated_at = utcnow()
