"""The /settings page: criteria editing, saved searches, and the per-job reevaluate flow."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.criteria import set_criteria_text
from jobwatch.llm import Verdict
from jobwatch.models import Job, UserJobState, UserSearch
from jobwatch.web.app import app, get_session


class FakeLLM:
    model = "fake"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        return Verdict(score=5, reasoning="good fit")


@pytest.fixture
def client(session: Session, monkeypatch) -> TestClient:
    monkeypatch.setattr("jobwatch.web.app.make_llm_client", lambda: FakeLLM())

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


def _add_search(session: Session, search_term: str = "x", location: str = "y") -> int:
    search = UserSearch(search_term=search_term, location=location)
    session.add(search)
    session.commit()
    return search.id


def _searches(session: Session) -> list[tuple[str, str]]:
    rows = session.scalars(select(UserSearch).order_by(UserSearch.id))
    return [(s.search_term, s.location) for s in rows]


def test_adding_search_persists(client, session: Session):
    response = client.post(
        "/settings/searches",
        data={"search_term": "software engineer", "location": "Denmark"},
    )
    assert response.status_code == 200
    assert "Saved" in response.text

    assert _searches(session) == [("software engineer", "Denmark")]


def test_search_form_is_prefilled(client, session: Session):
    _add_search(session, search_term="SRE", location="Denmark")
    response = client.get("/settings")
    assert 'value="SRE"' in response.text
    assert 'value="Denmark"' in response.text


def test_updating_search_replaces_it(client, session: Session):
    _add_search(session, search_term="a")
    b_id = _add_search(session, search_term="b")
    client.post(
        f"/settings/searches/{b_id}",
        data={"search_term": "platform engineer", "location": "Remote"},
    )
    assert _searches(session) == [("a", "y"), ("platform engineer", "Remote")]


def test_deleting_search_removes_only_that_one(client, session: Session):
    a_id = _add_search(session, search_term="a")
    _add_search(session, search_term="b")
    response = client.post(f"/settings/searches/{a_id}/delete")
    assert response.status_code == 200
    assert _searches(session) == [("b", "y")]


def test_deleting_search_keeps_its_jobs(client, session: Session):
    search_id = _add_search(session)
    job_id = _add_job(session, search_id=search_id)
    client.post(f"/settings/searches/{search_id}/delete")

    job = session.get(Job, job_id)
    session.refresh(job)
    assert job is not None
    assert job.search_id is None


def test_unknown_search_id_404s(client, session: Session):
    _add_search(session)
    data = {"search_term": "x", "location": "y"}
    assert client.post("/settings/searches/999", data=data).status_code == 404
    assert client.post("/settings/searches/999/delete").status_code == 404


def test_job_list_renders(client):
    assert client.get("/?show=all").status_code == 200


def _add_job(
    session: Session,
    external_id: str = "1",
    title: str = "Backend Engineer",
    search_id: int | None = None,
) -> int:
    job = Job(
        site="linkedin",
        external_id=external_id,
        search_id=search_id,
        title=title,
        company="Acme",
        location="Copenhagen",
        url=f"https://example.com/{external_id}",
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


def _user_states(session: Session) -> list[UserJobState]:
    return list(session.scalars(select(UserJobState)))


def test_rating_persists_and_updates_in_place(client, session: Session):
    job_id = _add_job(session)

    response = client.put(f"/jobs/{job_id}/rating", data={"rating": "4"})
    assert response.status_code == 204
    assert client.get(f"/jobs/{job_id}").text.count("★") == 4

    client.put(f"/jobs/{job_id}/rating", data={"rating": "2"})

    states = _user_states(session)
    assert len(states) == 1
    assert states[0].job_id == job_id
    assert states[0].rating == 2


def test_rating_delete_clears(client, session: Session):
    job_id = _add_job(session)
    client.put(f"/jobs/{job_id}/rating", data={"rating": "3"})
    client.delete(f"/jobs/{job_id}/rating")

    assert _user_states(session)[0].rating is None


def test_rating_out_of_range_is_rejected(client, session: Session):
    job_id = _add_job(session)
    assert client.put(f"/jobs/{job_id}/rating", data={"rating": "6"}).status_code == 422
    assert client.put(f"/jobs/{job_id}/rating", data={"rating": "0"}).status_code == 422
    assert _user_states(session) == []


def test_bookmark_set_and_clear(client, session: Session):
    job_id = _add_job(session)

    assert client.put(f"/jobs/{job_id}/bookmark").status_code == 204
    assert _user_states(session)[0].bookmarked_at is not None

    assert client.delete(f"/jobs/{job_id}/bookmark").status_code == 204
    assert _user_states(session)[0].bookmarked_at is None


def test_bookmark_is_idempotent(client, session: Session):
    # A double-clicked Save button PUTs twice: the job stays bookmarked and
    # keeps the first click's timestamp.
    job_id = _add_job(session)

    client.put(f"/jobs/{job_id}/bookmark")
    first = _user_states(session)[0].bookmarked_at

    client.put(f"/jobs/{job_id}/bookmark")
    assert _user_states(session)[0].bookmarked_at == first


def test_applied_set_and_clear(client, session: Session):
    job_id = _add_job(session)

    client.put(f"/jobs/{job_id}/applied")
    assert _user_states(session)[0].applied_at is not None
    assert "Applied" in client.get(f"/jobs/{job_id}").text

    client.put(f"/jobs/{job_id}/applied")
    assert _user_states(session)[0].applied_at is not None

    client.delete(f"/jobs/{job_id}/applied")
    assert _user_states(session)[0].applied_at is None


def test_saved_tab_lists_only_bookmarked_jobs(client, session: Session):
    bookmarked_id = _add_job(session, external_id="1", title="Backend Engineer")
    _add_job(session, external_id="2", title="Frontend Engineer")
    client.put(f"/jobs/{bookmarked_id}/bookmark")

    response = client.get("/?show=saved")
    assert response.status_code == 200
    assert "Backend Engineer" in response.text
    assert "Frontend Engineer" not in response.text


def test_state_endpoints_404_on_missing_job(client):
    assert client.put("/jobs/999/rating", data={"rating": "3"}).status_code == 404
    assert client.delete("/jobs/999/rating").status_code == 404
    assert client.put("/jobs/999/bookmark").status_code == 404
    assert client.delete("/jobs/999/applied").status_code == 404
