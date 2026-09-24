"""BC-31: a blank project name is refused, on create and on rename.

Seam: `invoke()` with the shipped chokepoint installed, HTTP-free — the same
path `web/routes.py` and the master reach the verbs by. The refusal is the verb
family's one negative shape (`{verb}: False`, `project: None`, `refused: …`),
and the stored name is read back through `get_project`, never through SQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from chokepoint_fixture import install_test_chokepoint

from shepherd.store.db import Store, open_store
from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.tools_projects import register_project_tools
from shepherd.toolsurface.tools_projects_delete import refuses_every_kill
from shepherd.toolsurface.types import Audience, CallerContext

HUMAN = CallerContext(audience=Audience.HUMAN, caller_id="web", correlation_id="cid-blank")

BLANKS = ("", "   ", "\t\n ")


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    install_test_chokepoint()
    register_project_tools(store=opened, kill=refuses_every_kill, publish=lambda event: None)
    try:
        yield opened
    finally:
        opened.close()


def answer(name: str, args: dict[str, object]) -> dict[str, object]:
    result = invoke(name, args, HUMAN)
    assert result.ok is True, result.error
    assert isinstance(result.data, dict)
    return result.data


def project_names(store: Store) -> list[str]:
    return sorted(workspace.name for workspace in store.list_workspaces())


@pytest.mark.parametrize("blank", BLANKS)
def test_a_whitespace_create_is_refused(store: Store, blank: str) -> None:
    before = project_names(store)

    created = answer("create_project", {"name": blank})

    assert created["created"] is False
    assert created["project"] is None
    assert isinstance(created["refused"], str) and created["refused"]
    assert project_names(store) == before


@pytest.mark.parametrize("blank", BLANKS)
def test_a_whitespace_rename_is_refused(store: Store, blank: str) -> None:
    made = answer("create_project", {"name": "api"})
    project = made["project"]
    assert isinstance(project, dict)
    project_id = project["project_id"]

    renamed = answer("rename_project", {"project_id": project_id, "name": blank})

    assert renamed["renamed"] is False
    assert renamed["project"] is None
    assert isinstance(renamed["refused"], str) and renamed["refused"]
    fetched = answer("get_project", {"project_id": project_id})
    assert isinstance(fetched["project"], dict)
    assert fetched["project"]["name"] == "api"


def test_a_name_with_surrounding_space_is_still_accepted(store: Store) -> None:
    """The negative control: only an all-blank name is refused. Normalising a
    stored name is out of scope, so ` api ` is stored as sent."""
    created = answer("create_project", {"name": " api "})

    assert created["created"] is True
    assert isinstance(created["project"], dict)
    assert created["project"]["name"] == " api "
