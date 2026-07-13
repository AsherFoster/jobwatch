from __future__ import annotations

import httpx2
import pytest

from jobwatch.models import Job
from jobwatch.notify import DiscordNotifier


def make_jobs(n: int) -> list[Job]:
    return [
        Job(
            site="linkedin",
            external_id=str(i),
            title=f"Job {i}",
            company="Acme",
            location="Copenhagen",
            url=f"https://example.com/{i}",
        )
        for i in range(n)
    ]


@pytest.fixture
def capture_post(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return httpx2.Response(204, request=httpx2.Request("POST", url))

    monkeypatch.setattr(httpx2, "post", fake_post)
    return captured


def test_single_message_lists_jobs_and_review_link(capture_post):
    DiscordNotifier("https://discord.test/hook").send_matches(
        make_jobs(2), review_url="http://mymac:8000"
    )
    content = capture_post["json"]["content"]
    assert capture_post["url"] == "https://discord.test/hook"
    assert "2 new job matches" in content
    assert "Job 0" in content and "Job 1" in content
    assert "http://mymac:8000" in content


def test_long_lists_are_truncated(capture_post):
    DiscordNotifier("https://discord.test/hook").send_matches(
        make_jobs(15), review_url="http://mymac:8000"
    )
    content = capture_post["json"]["content"]
    assert "15 new job matches" in content
    assert "and 5 more" in content
