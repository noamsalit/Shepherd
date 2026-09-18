"""The golden lane's fixtures. `--update-golden` is explicit, never automatic."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from shepherd.store.db import Store, open_store


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="rewrite tests/golden/expected/sessions.json from a fresh replay",
    )


@pytest.fixture(scope="session", autouse=True)
def corpus_is_read_only() -> Iterator[str]:
    """The captures are evidence (T12): the whole lane runs between two hashes.

    Order-independent by construction — a test that rewrote a capture to go
    green would still be caught when the session ends.
    """
    from golden.corpus import corpus_digest

    before = corpus_digest()
    yield before
    assert corpus_digest() == before, "a test modified the probe corpus"


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "shepherd.sqlite3")
    try:
        yield opened
    finally:
        opened.close()
