"""The /criteria editor: seeding, saving, and the per-job reevaluate flow."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobwatch.config import Config, CriteriaConfig, SearchConfig
from jobwatch.criteria import set_criteria_text
from jobwatch.db import make_engine, make_session_factory
from jobwatch.models import Job
from jobwatch.web.app import create_app


class FakeLLM:
    model = "fake"

    def complete(self, system: str, prompt: str) -> str:
        return '{"matched": true, "score": 9, "reasoning": "good fit"}'


@pytest.fixture
def app_config(tmp_path) -> Config:
    return Config(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        searches=[SearchConfig(name="test", search_term="engineer", location="Denmark")],
        criteria=CriteriaConfig(text="Positives: python."),
    )


@pytest.fixture
def client(app_config, monkeypatch) -> TestClient:
    monkeypatch.setattr("jobwatch.web.app.make_llm_client", lambda llm_config: FakeLLM())
    return TestClient(create_app(app_config))


def test_criteria_page_seeds_from_config(client):
    response = client.get("/criteria")
    assert response.status_code == 200
    assert "Positives: python." in response.text


def test_saving_criteria_persists(client):
    # The client follows the 303 back to /criteria, which shows the saved text.
    response = client.post("/criteria", data={"text": "Negatives: consultancies."})
    assert response.status_code == 200
    assert "Saved" in response.text

    response = client.get("/criteria")
    assert "Negatives: consultancies." in response.text
    assert "Positives: python." not in response.text


def test_job_list_renders(client):
    assert client.get("/?show=all").status_code == 200


def _add_job(app_config) -> int:
    session_factory = make_session_factory(make_engine(app_config.database_url))
    with session_factory() as session:
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


def test_reassess_creates_new_verdict_and_keeps_old_as_history(client, app_config):
    job_id = _add_job(app_config)

    response = client.post(f"/jobs/{job_id}/reassess")
    assert response.status_code == 200  # followed the redirect to the job page
    assert "current" in response.text

    session_factory = make_session_factory(make_engine(app_config.database_url))
    with session_factory() as session:
        set_criteria_text(session, "Completely different criteria")

    response = client.post(f"/jobs/{job_id}/reassess")
    assert response.status_code == 200

    with session_factory() as session:
        job = session.get(Job, job_id)
        assert len(job.all_assessments) == 2
        active = [a for a in job.all_assessments if a.invalidated_at is None]
        assert len(active) == 1
        invalidated = [a for a in job.all_assessments if a.invalidated_at is not None]
        assert len(invalidated) == 1


def test_reassess_missing_job_404s(client):
    assert client.post("/jobs/999/reassess").status_code == 404
