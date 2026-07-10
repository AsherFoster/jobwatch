import pytest

from jobwatch.assess import generate_llm_verdict, parse_verdict
from jobwatch.models import Job


def make_job() -> Job:
    return Job(
        site="linkedin",
        external_id="1",
        search_name="test",
        title="Backend Engineer",
        company="Acme",
        location="Copenhagen",
        url="https://example.com/1",
        description="Python backend role",
    )


def test_parse_clean_json():
    verdict = parse_verdict('{"matched": true, "score": 8, "reasoning": "Good fit"}')
    assert verdict.matched is True
    assert verdict.score == 8
    assert verdict.reasoning == "Good fit"


def test_parse_json_with_surrounding_chatter():
    text = 'Sure! Here is my verdict:\n{"matched": false, "score": 2, "reasoning": "No"}\nDone.'
    verdict = parse_verdict(text)
    assert verdict.matched is False


def test_parse_clamps_score():
    assert parse_verdict('{"matched": true, "score": 99}').score == 10
    assert parse_verdict('{"matched": true, "score": -3}').score == 0


def test_parse_rejects_non_json():
    with pytest.raises(ValueError):
        parse_verdict("I could not decide.")


def test_generate_llm_verdict_survives_garbage_response():
    class GarbageLLM:
        model = "test"

        def complete(self, system: str, prompt: str) -> str:
            return "not json at all"

    verdict = generate_llm_verdict(GarbageLLM(), make_job(), "criteria")
    assert verdict.matched is False
    assert "unparseable" in verdict.reasoning.lower()


def test_generate_llm_verdict_passes_criteria_and_description():
    captured = {}

    class RecordingLLM:
        model = "test"

        def complete(self, system: str, prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"matched": true, "score": 7, "reasoning": "ok"}'

    verdict = generate_llm_verdict(RecordingLLM(), make_job(), "Positives: python")
    assert verdict.matched is True
    assert "Positives: python" in captured["prompt"]
    assert "Python backend role" in captured["prompt"]
