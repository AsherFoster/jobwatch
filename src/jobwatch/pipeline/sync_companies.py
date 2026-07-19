from __future__ import annotations

from awa.bridge import insert_job_sync
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import Company, utcnow
from jobwatch.task_kinds import EnrichCompany


def get_or_create_company(
    session: Session, *, name: str, linkedin_slug: str | None = None, logo: str | None = None
) -> Company:
    """Return the CompanyDetails row for a company, creating a blank one — and
    queuing `load_company_details` to fill it in — when none exists.

    Companies are matched by LinkedIn slug only, never by name: a slugless
    scrape creates a new row even if the name matches an existing one.
    Duplicates can be merged later; rows wrongly unified on a shared name
    would have to be untangled.
    """
    if linkedin_slug:
        existing = session.scalar(select(Company).where(Company.linkedin_slug == linkedin_slug))
        if existing is not None:
            return existing

    company = Company(name=name, linkedin_slug=linkedin_slug, logo=logo)
    session.add(company)
    session.flush()
    insert_job_sync(session, EnrichCompany(company_id=company.id))
    return company


async def enrich_company(session: Session, company_id: int) -> None:
    """Generate a company's description, then stamp generated_at. A no-op if
    the description is already filled in, so a retry after a partial failure
    doesn't redo work that already succeeded."""
    # Imported lazily: google-genai is the optional [gemini] extra.
    from jobwatch.llm import gemini

    company = session.get(Company, company_id)
    assert company is not None

    if not company.description:
        company.description = await gemini.generate_company_description(company.name)
    company.generated_at = utcnow()
