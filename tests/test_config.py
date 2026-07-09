from pathlib import Path

from jobwatch.config import load_config

EXAMPLE = Path(__file__).parent.parent / "config.example.toml"


def test_example_config_loads():
    config = load_config()
    assert config.searches[0].name == "swe-denmark"
    assert config.llm.provider == "ollama"
    assert config.notify.discord is not None
