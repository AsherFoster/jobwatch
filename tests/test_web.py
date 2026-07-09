"""The /criteria editor: seeding from config, saving, and re-assessment fallout."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jobwatch.config import Config, CriteriaConfig, SearchConfig
from jobwatch.web.app import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    config = Config(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        searches=[SearchConfig(name="test", search_term="engineer", location="Denmark")],
        criteria=CriteriaConfig(text="Positives: python."),
    )
    return TestClient(create_app(config, with_scheduler=False))


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
