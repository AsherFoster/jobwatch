"""The /settings page: criteria editing, saved searches, and the per-job reevaluate flow."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from jobwatch.criteria import set_criteria_text
from jobwatch.models import Job
from jobwatch.search_jobs import SearchConfig
from jobwatch.searches import get_searches, set_searches
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


def test_settings_page_starts_blank(client):
    response = client.get("/settings")
    assert response.status_code == 200
    assert "<textarea" in response.text
    assert 'name="text" rows="14"' in response.text
    assert "></textarea>" in response.text  # empty: no seeded text between the tags
    assert "No searches configured" in response.text


def test_old_criteria_url_redirects_to_settings(client):
    response = client.get("/criteria", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/settings"


def test_saving_criteria_persists(client):
    # The client follows the 303 back to /settings, which shows the saved text.
    response = client.post("/settings/criteria", data={"text": "Positives: python."})
    assert response.status_code == 200
    assert "Saved" in response.text

    response = client.get("/settings")
    assert "Positives: python." in response.text

    response = client.post("/settings/criteria", data={"text": "Negatives: consultancies."})
    response = client.get("/settings")
    assert "Negatives: consultancies." in response.text
    assert "Positives: python." not in response.text


def test_adding_search_persists(client, session: Session):
    response = client.post(
        "/settings/searches",
        data={"name": "swe-dk", "search_term": "software engineer", "location": "Denmark"},
    )
    assert response.status_code == 200
    assert "Saved" in response.text

    assert get_searches(session) == [
        SearchConfig(name="swe-dk", search_term="software engineer", location="Denmark")
    ]


def test_search_form_is_prefilled(client, session: Session):
    set_searches(
        session,
        [SearchConfig(name="sre-dk", search_term="SRE", location="Denmark", results_wanted=20)],
    )
    response = client.get("/settings")
    assert 'value="sre-dk"' in response.text
    assert 'value="SRE"' in response.text
    assert 'value="20"' in response.text


def test_updating_search_replaces_it(client, session: Session):
    set_searches(
        session,
        [
            SearchConfig(name="a", search_term="x", location="y"),
            SearchConfig(name="b", search_term="x", location="y"),
        ],
    )
    client.post(
        "/settings/searches/1",
        data={
            "name": "b2",
            "search_term": "platform engineer",
            "location": "Remote",
            "results_wanted": "50",
            "hours_old": "48",
        },
    )
    assert get_searches(session) == [
        SearchConfig(name="a", search_term="x", location="y"),
        SearchConfig(
            name="b2",
            search_term="platform engineer",
            location="Remote",
            results_wanted=50,
            hours_old=48,
        ),
    ]


def test_deleting_search_removes_only_that_one(client, session: Session):
    set_searches(
        session,
        [
            SearchConfig(name="a", search_term="x", location="y"),
            SearchConfig(name="b", search_term="x", location="y"),
        ],
    )
    response = client.post("/settings/searches/0/delete")
    assert response.status_code == 200
    assert get_searches(session) == [SearchConfig(name="b", search_term="x", location="y")]


def test_search_index_out_of_range_404s(client, session: Session):
    set_searches(session, [SearchConfig(name="a", search_term="x", location="y")])
    data = {"name": "a", "search_term": "x", "location": "y"}
    assert client.post("/settings/searches/1", data=data).status_code == 404
    assert client.post("/settings/searches/1/delete").status_code == 404


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
