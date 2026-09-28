"""INP lane conftest: the session-scoped `inp` composition (qa6/inp.py).

Import-inert: the composition module is imported inside the fixture, so the
default pytest lane (which collects this directory and deselects it) imports
nothing heavy and starts nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from ..inp import Inp
    from ..sandbox import RunContext


@pytest.fixture(scope="session")
def inp(qa6_run: RunContext) -> Iterator[Inp]:
    """The one INP composition of this pytest process (T3: one per process)."""
    from ..inp import session

    yield from session(qa6_run)
