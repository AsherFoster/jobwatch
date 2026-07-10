"""The /criteria editor: default state, saving, and the per-job reevaluate flow."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from jobwatch.criteria import set_criteria_text
from jobwatch.models import Job
from jobwatch.web.app import app, get_session


class FakeLLM:
    model = "fake"

    def complete(self, system: str, prompt: str) -> str:
        return '{"matched": true, "score": 9, "reasoning": "good fit"}'


@pytest.fixture
def client(session: Session, monkeypatch) -> TestClient:
    monkeypatch.setattr("jobwatch.web.app.make_llm_client", lambda llm_config: FakeLLM())

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def test_criteria_page_starts_blank(client):
    response = client.get("/criteria")
    assert response.status_code == 200
    assert "<textarea" in response.text
    assert 'name="text" rows="14"' in response.text
    assert "></textarea>" in response.text  # empty: no seeded text between the tags


def test_saving_criteria_persists(client):
    # The client follows the 303 back to /criteria, which shows the saved text.
    response = client.post("/criteria", data={"text": "Positives: python."})
    assert response.status_code == 200
    assert "Saved" in response.text

    response = client.get("/criteria")
    assert "Positives: python." in response.text

    response = client.post("/criteria", data={"text": "Negatives: consultancies."})
    response = client.get("/criteria")
    assert "Negatives: consultancies." in response.text
    assert "Positives: python." not in response.text


def test_job_list_renders(client):
    assert client.get("/?show=all").status_code == 200


def _add_job(session: Session) -> int:
    job = Job(
        site="linkedin",
        external_id="1",
        search_name="test",
        title="Backend Engineer",
        company="Acme",
        location="Copenhagen",
        url="https://example.com/1",
        description="Python things",
        raw="{}",
    )
    session.add(job)
    session.commit()
    return job.id


def test_reassess_creates_new_verdict_and_keeps_old_as_history(client, session: Session):
    job_id = _add_job(session)

    response = client.post(f"/jobs/{job_id}/reassess")
    assert response.status_code == 200  # followed the redirect to the job page
    assert "current" in response.text

    set_criteria_text(session, "Completely different criteria")

    response = client.post(f"/jobs/{job_id}/reassess")
    assert response.status_code == 200

    job = session.get(Job, job_id)
    session.refresh(job)

    assert job is not None
    assert len(job.all_assessments) == 2
    active = [a for a in job.all_assessments if a.invalidated_at is None]
    assert len(active) == 1
    invalidated = [a for a in job.all_assessments if a.invalidated_at is not None]
    assert len(invalidated) == 1


def test_reassess_missing_job_404s(client):
    assert client.post("/jobs/999/reassess").status_code == 404
