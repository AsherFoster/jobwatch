from __future__ import annotations

import pytest
from google.genai import errors

from jobwatch.llm import RateLimited
from jobwatch.llm.gemini import DEFAULT_RETRY_DELAY, GeminiClient, gemini_retry_delay
from jobwatch.test_scene import Scene

RETRY_INFO = {
    "@type": "type.googleapis.com/google.rpc.RetryInfo",
    "retryDelay": "39s",
}


def quota_error(details: list[dict] | None = None, wrapped: bool = True) -> errors.APIError:
    body = {
        "code": 429,
        "message": "You exceeded your current quota.",
        "status": "RESOURCE_EXHAUSTED",
        "details": details if details is not None else [RETRY_INFO],
    }
    return errors.APIError(429, {"error": body} if wrapped else body)


def test_retry_delay_parsed_from_retry_info():
    assert gemini_retry_delay(quota_error()) == 39.0


def test_retry_delay_handles_unwrapped_error_json():
    assert gemini_retry_delay(quota_error(wrapped=False)) == 39.0


def test_retry_delay_parses_fractional_seconds():
    error = quota_error(details=[{**RETRY_INFO, "retryDelay": "1.5s"}])
    assert gemini_retry_delay(error) == 1.5


def test_retry_delay_defaults_when_retry_info_missing():
    assert gemini_retry_delay(quota_error(details=[])) == DEFAULT_RETRY_DELAY
    assert gemini_retry_delay(errors.APIError(429, "not json")) == DEFAULT_RETRY_DELAY


@pytest.mark.asyncio
async def test_assess_job_converts_429_to_rate_limited(session, scene: Scene, monkeypatch):
    client = GeminiClient(model="gemini-test", api_key="test-key")

    async def raise_quota_error(**kwargs):
        raise quota_error()

    monkeypatch.setattr(client._client.aio.interactions, "create", raise_quota_error)

    with pytest.raises(RateLimited) as exc_info:
        await client.assess_job(scene.job(), "criteria")
    assert exc_info.value.retry_after == 39.0
