"""The /settings page: criteria editing, saved searches, and the per-job reevaluate flow."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.llm import Verdict
from jobwatch.models import Job, User, UserJobState, UserSearch
from jobwatch.test_scene import Scene, scene
from jobwatch.web.app import app, get_session


class FakeLLM:
    model = "fake"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        return Verdict(
            score=5,
            reasoning="good fit",
            summary="good job",
            summary_positives="it's a job",
            summary_negatives="it's a job",
        )


@pytest.fixture
def user(scene: Scene) -> User:
    return scene.user(criteria_text="")


@pytest.fixture
def client(session: Session, user: User, monkeypatch) -> TestClient:
    monkeypatch.setattr("jobwatch.web.app.make_llm_client", lambda: FakeLLM())

    def override_get_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    client.cookies.set("user_id", str(user.id))
    return client


def test_no_user_cookie_redirects_to_user_picker(client):
    client.cookies.delete("user_id")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/users"

    response = client.get("/users")
    assert response.status_code == 200
    assert "Create" in response.text


def test_creating_user_selects_it(client, session: Session):
    client.cookies.delete("user_id")
    response = client.post("/users", data={"name": "Beth"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"

    beth = session.scalars(select(User).where(User.name == "Beth")).one()
    assert response.cookies["user_id"] == str(beth.id)


def test_selecting_user_sets_cookie(client, session: Session, user: User):
    response = client.post("/user", data={"user_id": str(user.id)}, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies["user_id"] == str(user.id)


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


def _searches(session: Session) -> list[tuple[str, str]]:
    rows = session.scalars(
        select(UserSearch).where(UserSearch.deleted_at.is_(None)).order_by(UserSearch.id)
    )
    return [(s.search_term, s.location) for s in rows]


def test_adding_search_persists(client, session: Session):
    response = client.post(
        "/settings/searches",
        data={"search_term": "software engineer", "location": "Denmark"},
    )
    assert response.status_code == 200
    assert "Saved" in response.text

    assert _searches(session) == [("software engineer", "Denmark")]


def test_search_form_is_prefilled(client, session: Session, user: User, scene: Scene):
    scene.user_search(user=user, search_term="SRE", location="Denmark")
    response = client.get("/settings")
    assert 'value="SRE"' in response.text
    assert 'value="Denmark"' in response.text


def test_updating_search_replaces_it(client, session: Session, user: User, scene: Scene):
    scene.user_search(user=user, search_term="a", location="y")
    search_b = scene.user_search(user=user, search_term="b", location="y")
    client.post(
        f"/settings/searches/{search_b.id}",
        data={"search_term": "platform engineer", "location": "Remote"},
    )
    assert _searches(session) == [("a", "y"), ("platform engineer", "Remote")]


def test_deleting_search_removes_only_that_one(client, session: Session, user: User, scene: Scene):
    search_a = scene.user_search(user=user, search_term="a", location="y")
    scene.user_search(user=user, search_term="b", location="y")
    response = client.post(f"/settings/searches/{search_a.id}/delete")
    assert response.status_code == 200
    assert _searches(session) == [("b", "y")]


def test_deleting_search_keeps_its_jobs(client, session: Session, user: User, scene: Scene):
    search = scene.user_search(user=user)
    job = scene.job(search=search)
    client.post(f"/settings/searches/{search.id}/delete")

    session.refresh(job)
    session.refresh(search)
    assert job.search_id == search.id  # the job keeps its attribution
    assert search.deleted_at is not None  # but the search itself is gone


def test_unknown_search_id_404s(client, session: Session, user: User, scene: Scene):
    scene.user_search(user=user)
    data = {"search_term": "x", "location": "y"}
    assert client.post("/settings/searches/999", data=data).status_code == 404
    assert client.post("/settings/searches/999/delete").status_code == 404


def test_deleted_search_404s_on_update_or_delete(client, user: User, scene: Scene):
    search = scene.user_search(user=user)
    client.post(f"/settings/searches/{search.id}/delete")

    data = {"search_term": "x", "location": "y"}
    assert client.post(f"/settings/searches/{search.id}", data=data).status_code == 404
    assert client.post(f"/settings/searches/{search.id}/delete").status_code == 404


def test_job_list_renders(client):
    assert client.get("/?show=all").status_code == 200


def test_reassess_creates_new_verdict_and_keeps_old_as_history(
    client, session: Session, user: User, scene: Scene
):
    job = scene.job()

    response = client.post(f"/jobs/{job.id}/reassess")
    assert response.status_code == 200  # followed the redirect to the job page
    assert "Reevaluate" in response.text  # an active assessment is now shown

    user.criteria_text = "Completely different criteria"
    session.commit()

    response = client.post(f"/jobs/{job.id}/reassess")
    assert response.status_code == 200

    session.refresh(job)

    assert len(job.assessments) == 2
    active = [a for a in job.assessments if a.invalidated_at is None]
    assert len(active) == 1
    invalidated = [a for a in job.assessments if a.invalidated_at is not None]
    assert len(invalidated) == 1


def test_reassess_missing_job_404s(client):
    assert client.post("/jobs/999/reassess").status_code == 404


def _user_states(session: Session) -> list[UserJobState]:
    return list(session.scalars(select(UserJobState)))


def test_rating_persists_and_updates_in_place(client, session: Session, scene: Scene):
    job = scene.job()

    response = client.put(f"/jobs/{job.id}/rating", data={"rating": "4"})
    assert response.status_code == 204
    assert client.get(f"/jobs/{job.id}").text.count("⭐") == 4

    client.put(f"/jobs/{job.id}/rating", data={"rating": "2"})

    states = _user_states(session)
    assert len(states) == 1
    assert states[0].job_id == job.id
    assert states[0].rating == 2


def test_rating_delete_clears(client, session: Session, scene: Scene):
    job = scene.job()
    client.put(f"/jobs/{job.id}/rating", data={"rating": "3"})
    client.delete(f"/jobs/{job.id}/rating")

    assert _user_states(session)[0].rating is None


def test_rating_out_of_range_is_rejected(client, session: Session, scene: Scene):
    job = scene.job()
    assert client.put(f"/jobs/{job.id}/rating", data={"rating": "6"}).status_code == 422
    assert client.put(f"/jobs/{job.id}/rating", data={"rating": "0"}).status_code == 422
    assert _user_states(session) == []


@pytest.mark.parametrize(
    "endpoint,attr", [("bookmark", "bookmarked_at"), ("applied", "applied_at")]
)
def test_toggle_state_set_and_clear(client, session: Session, scene: Scene, endpoint, attr):
    job = scene.job()

    assert client.put(f"/jobs/{job.id}/{endpoint}").status_code == 204
    assert getattr(_user_states(session)[0], attr) is not None

    assert client.delete(f"/jobs/{job.id}/{endpoint}").status_code == 204
    assert getattr(_user_states(session)[0], attr) is None


@pytest.mark.parametrize(
    "endpoint,attr", [("bookmark", "bookmarked_at"), ("applied", "applied_at")]
)
def test_toggle_state_is_idempotent(client, session: Session, scene: Scene, endpoint, attr):
    # A double-clicked button PUTs twice: the state stays set and keeps the
    # first click's timestamp.
    job = scene.job()

    client.put(f"/jobs/{job.id}/{endpoint}")
    first = getattr(_user_states(session)[0], attr)

    client.put(f"/jobs/{job.id}/{endpoint}")
    assert getattr(_user_states(session)[0], attr) == first


def test_applied_shown_on_job_page(client, scene: Scene):
    job = scene.job()
    client.put(f"/jobs/{job.id}/applied")
    assert "Applied" in client.get(f"/jobs/{job.id}").text


def test_saved_tab_lists_only_bookmarked_jobs(client, scene: Scene):
    search = scene.user_search()
    bookmarked = scene.job(search=search, title="Backend Engineer")
    scene.job(search=search, title="Frontend Engineer")
    client.put(f"/jobs/{bookmarked.id}/bookmark")

    response = client.get("/?show=saved")
    assert response.status_code == 200
    assert "Backend Engineer" in response.text
    assert "Frontend Engineer" not in response.text


def test_state_endpoints_404_on_missing_job(client):
    assert client.put("/jobs/999/rating", data={"rating": "3"}).status_code == 404
    assert client.delete("/jobs/999/rating").status_code == 404
    assert client.put("/jobs/999/bookmark").status_code == 404
    assert client.delete("/jobs/999/applied").status_code == 404
