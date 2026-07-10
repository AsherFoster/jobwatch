import json
import sys
from dataclasses import field
from types import ModuleType, SimpleNamespace
from typing import Any, cast

import pytest

from jobwatch.config import LLMConfig
from jobwatch.llm import AppleFMClient, make_llm_client


def install_stub_fm(monkeypatch, respond_result) -> list:
    """Install a fake apple_fm_sdk module; returns the list of created sessions."""
    stub = cast(Any, ModuleType("apple_fm_sdk"))
    sessions = []

    def generable(description=None):
        def wrap(cls):
            cls._generable_description = description
            return cls

        return wrap

    def guide(description=None, **constraints):
        return field(default=None, metadata={"description": description, **constraints})

    class LanguageModelSession:
        def __init__(self, instructions=None):
            self.instructions = instructions
            sessions.append(self)

        async def respond(self, prompt, *, generating=None):
            self.prompt = prompt
            self.generating = generating
            return respond_result

    stub.generable = generable
    stub.guide = guide
    stub.LanguageModelSession = LanguageModelSession
    monkeypatch.setitem(sys.modules, "apple_fm_sdk", stub)
    return sessions


def test_apple_fm_complete_returns_verdict_json(monkeypatch):
    result = SimpleNamespace(matched=True, score=7, reasoning="Good fit")
    sessions = install_stub_fm(monkeypatch, result)

    client = AppleFMClient()
    response = client.complete("You screen job postings.", "## Job posting\nBackend Engineer")

    assert json.loads(response) == {"matched": True, "score": 7, "reasoning": "Good fit"}
    (session,) = sessions
    assert session.instructions == "You screen job postings."
    assert session.prompt == "## Job posting\nBackend Engineer"
    assert session.generating is client._verdict_type


def test_apple_fm_requires_optional_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "apple_fm_sdk", None)
    with pytest.raises(RuntimeError, match="uv sync --extra apple-fm"):
        AppleFMClient()


def test_make_llm_client_dispatches_apple_fm(monkeypatch):
    install_stub_fm(monkeypatch, None)
    client = make_llm_client(LLMConfig(provider="apple_fm"))
    assert isinstance(client, AppleFMClient)
    assert client.model == "apple-fm"


def test_make_llm_client_rejects_unknown_provider():
    with pytest.raises(ValueError):
        make_llm_client(LLMConfig(provider="nope"))
