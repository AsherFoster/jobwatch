from __future__ import annotations

import json

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.models import CompanyDetails
from jobwatch.pipeline.sync_jobs import ScrapedJob, linkedin_company_slug

log = structlog.get_logger()


async def generate_company_description(company: str) -> str:
    # Imported lazily: google-genai is the optional [gemini] extra.
    from jobwatch.llm import gemini

    return await gemini.generate_company_description(company)


async def ensure_company_details(session: Session, item: ScrapedJob) -> None:
    """Create a CompanyDetails row for this job's company, unless one exists.

    An existing company is matched by its LinkedIn slug when the scrape
    provides one, falling back to a case-insensitive name match (which also
    backfills the slug on rows that predate it). A failed generation is
    logged and skipped — no row is created, so the next job from that
    company retries."""
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
        return
    try:
        description = await generate_company_description(item.company)
    except Exception:
        log.exception("Description generation failed", company=item.company)
        return
    logo = raw.get("company_logo") or None
    session.add(
        CompanyDetails(name=item.company, linkedin_slug=slug, logo=logo, description=description)
    )
