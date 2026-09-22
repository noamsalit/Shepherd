"""The shared project fixture holds its promise, and is the only copy of itself."""

from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest
from project_fixture import the_project

from shepherd.store.db import Store, open_store

TESTS_ROOT = Path(__file__).resolve().parent


@pytest.fixture()
def store(tmp_path: Path) -> typing.Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def test_the_project_is_the_same_project_every_time(store: Store) -> None:
    """Four calls, one project — the property the four `seed()` helpers need.

    The control is the second name: asking for a *different* project does
    create one, so this is idempotence and not a helper that refuses to make
    anything. The seeded `Unassigned` is counted too, because a fresh database
    is no longer empty of projects (N1/E21).
    """
    first = the_project(store)
    assert [the_project(store) for _ in range(3)] == [first, first, first]
    other = the_project(store, "payments")
    assert other != first
    assert sorted(w.name for w in store.list_workspaces()) == [
        "Unassigned",
        "payments",
        "shepherd",
    ]


def test_no_suite_defines_its_own_copy_of_the_project_helper() -> None:
    """A fixture copied into two files is two things that can drift — and the
    drift was already paid for: the copy is *why* the other two `seed()`
    helpers were missed, since a reader who greps for the repair's name finds
    only the files that already have it.
    """
    definitions = [
        str(path.relative_to(TESTS_ROOT))
        for path in TESTS_ROOT.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.FunctionDef) and node.name == "the_project"
    ]
    assert definitions == ["project_fixture.py"]
