from pathlib import Path

from jobwatch.config import load_config
from jobwatch.criteria import criteria_fingerprint

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert config.searches[0].name == "swe-denmark"
    assert config.llm.provider == "ollama"
    assert config.notify.discord is not None
    assert config.criteria is not None and "Positives" in config.criteria.text


def test_fingerprint_changes_with_criteria_and_model():
    base = criteria_fingerprint("Positives: python.", "qwen3:8b")
    assert base == criteria_fingerprint("Positives: python.", "qwen3:8b")
    assert base != criteria_fingerprint("Positives: python.", "other-model")
    assert base != criteria_fingerprint("Positives: python. Also: no consultancies.", "qwen3:8b")
