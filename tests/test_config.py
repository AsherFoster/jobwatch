from pathlib import Path

from jobwatch.config import load_config

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert config.searches[0].name == "swe-denmark"
    assert config.llm.provider == "ollama"
    assert config.notify.discord is not None
    assert "Positives" in config.criteria.text


def test_fingerprint_changes_with_criteria_and_model():
    config = load_config(EXAMPLE)
    base = config.criteria.fingerprint("qwen3:8b")
    assert base == config.criteria.fingerprint("qwen3:8b")
    assert base != config.criteria.fingerprint("other-model")

    config.criteria.text += " Also: no consultancies."
    assert base != config.criteria.fingerprint("qwen3:8b")
