from __future__ import annotations

from jobwatch.job_sources.linkedin import linkedin_company_slug


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
