"""P5 / BC-15 — `spawn_session` carries `retry_of` through `invoke()` (§3 D70).

**Seam: `invoke()`**, the one a consumer and the master's tool loop both cross,
over a real `Store` with a MASTER caller context. Before D70 the schema had no
`retry_of` property, so a master could not declare a retry at all, and the
lineage D31 caps was never written by any production path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import SessionState
from shepherd.store.db import Store

from .test_tools_m3 import (  # noqa: F401 — `store`, `root`, `workspace_id`, `make_world` are fixtures
    MASTER,
    World,
    make_world,
    payload,
    root,
    store,
    workspace_id,
)


def spawn_as_master(workspace_id: str, root: Path, retry_of: str | None) -> dict[str, object]:
    args: dict[str, object] = {"workspace_id": workspace_id, "cwd": str(root / "repo")}
    if retry_of is not None:
        args["retry_of"] = retry_of
    return payload("spawn_session", args, MASTER)


def stop(store: Store, session_id: object) -> None:
    """The attempt ends, as the hook lane would record it: only a stopped session is retried."""
    assert isinstance(session_id, str)
    store.apply_fold_delta(
        session_id, FoldDelta(state=SessionState.STOPPED, last_event_at="2026-09-17T11:00:00Z")
    )


def test_spawn_session_carries_retry_of_through_invoke(
    make_world: Callable[..., World], store: Store, workspace_id: str, root: Path
) -> None:
    """The declared chain end to end at L4: X, its retry r1 (linked to X), the
    retry of r1 refused at the cap, and a second retry of X refused naming r1 —
    at the cap too, since the lineage is full, and pointing at the human."""
    make_world()
    first = spawn_as_master(workspace_id, root, None)
    assert first["spawned"] is True
    x = first["session_id"]
    assert isinstance(x, str)
    stop(store, x)

    retry = spawn_as_master(workspace_id, root, x)
    assert retry["spawned"] is True, retry
    r1 = retry["session_id"]
    assert isinstance(r1, str)
    row = store.get_session(r1)
    assert row is not None and row.retry_of == x
    assert row.origin == "orchestrator"
    stop(store, r1)

    capped = spawn_as_master(workspace_id, root, r1)
    assert capped["spawned"] is False and capped["cap"] == "retry_cap_reached", capped

    sibling = spawn_as_master(workspace_id, root, x)
    assert sibling["spawned"] is False and sibling["cap"] == "retry_cap_reached", sibling
    refusal = sibling["refusal"]
    assert isinstance(refusal, str) and "already retried" in refusal and r1 in refusal
    assert "human" in refusal
