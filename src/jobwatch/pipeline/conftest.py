"""Wires the declarative Scene builder (see jobwatch.test_scene) to the
per-test session."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from jobwatch.test_scene import Scene


@pytest.fixture
def scene(session: Session) -> Scene:
    return Scene(session)
