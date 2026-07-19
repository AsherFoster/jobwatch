from __future__ import annotations

from awa.bridge import insert_job_sync
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import CompanyDetails, utcnow
from jobwatch.task_kinds import LoadCompanyDetails


async def generate_company_description(company: str) -> str:
    # Imported lazily: google-genai is the optional [gemini] extra.
    from jobwatch.llm import gemini

    return await gemini.generate_company_description(company)


def get_company(
    session: Session, *, name: str, linkedin_slug: str | None = None, logo: str | None = None
) -> CompanyDetails:
    """Return the CompanyDetails row for a company, creating a blank one — and
    queuing `load_company_details` to fill it in — the first time a company is
    seen.

    An existing company is matched by its LinkedIn slug when one is provided,
    falling back to a case-insensitive name match (which also backfills the
    slug on rows that predate it).
    """
    existing = None
    if linkedin_slug:
        existing = session.scalar(
            select(CompanyDetails).where(CompanyDetails.linkedin_slug == linkedin_slug)
        )
    if existing is None:
        existing = session.scalar(select(CompanyDetails).where(CompanyDetails.name.ilike(name)))
        if existing is not None and existing.linkedin_slug is None:
            existing.linkedin_slug = linkedin_slug
    if existing is not None:
        return existing

    company = CompanyDetails(name=name, linkedin_slug=linkedin_slug, logo=logo)
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
