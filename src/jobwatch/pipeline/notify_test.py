from __future__ import annotations

import httpx2
import pytest

from jobwatch.models import Company, Job
from jobwatch.pipeline.notify import DiscordNotifier, notify_new_matches
from jobwatch.test_scene import Scene


def make_jobs(n: int) -> list[Job]:
    return [
        Job(
            site="linkedin",
            external_id=str(i),
            title=f"Job {i}",
            company=Company(name="Acme"),
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


# The test config has no Discord webhook, so notify_new_matches runs against
# the real NullNotifier — nothing external to fake.


def test_notify_new_matches_announces_each_match_once(session, scene: Scene):
    match = scene.assessment(score=5).job
    scene.assessment(score=3)  # below the match threshold
    scene.assessment(score=5, notified=True)  # already announced
    scene.job()  # never assessed

    notified = notify_new_matches(session)

    assert [job.id for job in notified] == [match.id]
    assert match.notified_at is not None

    # Everything matched is now marked notified, so a second run sends nothing.
    assert notify_new_matches(session) == []
