"""The registry and the ring are module-global by ADR-7, so each test starts clean."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from shepherd.toolsurface.registry import reset_registry
from shepherd.toolsurface.stream import reset_stream


@pytest.fixture(autouse=True)
def clean_toolsurface() -> Iterator[None]:
    reset_registry()
    reset_stream()
    yield
    reset_registry()
    reset_stream()
