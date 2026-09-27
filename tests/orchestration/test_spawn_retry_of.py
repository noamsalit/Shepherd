"""P5 / BC-15 — a master retry is **declared** with `retry_of` (§3 D70).

Before D70 nothing in `src/` called `Store.link_retry`, so D31's lineage cap
(`admission._retry_cap`, via `retry_chain_depth`) walked chains no production
path could build. Now the spawn itself declares what it retries: the new row is
linked to its predecessor, admission caps the declared lineage **before any row
is written** (Differences 7), and RD-2 refuses a second retry of one attempt,
which would otherwise start a sibling lineage the upward walk never sees.

**Seam: `spawn_owned_session`** over a real `Store` in `tmp_path`, with the
`test_spawn` helpers (the scripted runner, the injected clock). Every lineage
here is built by the shipped sequence — no `retry_of` is planted with SQL.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.states import Origin
from shepherd.orchestration.spawn import SpawnOutcome, SpawnRefused, spawn_owned_session
from shepherd.store.db import Store

from .test_spawn import (  # noqa: F401 — `store`, `root` and `workspace_id` are fixtures
    ready_pane,
    root,
    scripted,
    spawn,
    store,
    workspace_id,
)

CAP_ANOMALY = AnomalyKind.WAKE_RETRY_CAP_REACHED.value


def attempt(
    store: Store,
    workspace_id: str,
    root: Path,
    retry_of: str | None,
    origin: Origin = Origin.ORCHESTRATOR,
) -> SpawnOutcome | SpawnRefused:
    result, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        origin=origin,
        retry_of=retry_of,
    )
    return result


def spawned(result: SpawnOutcome | SpawnRefused) -> str:
    assert isinstance(result, SpawnOutcome), result
    return result.session_id


def cap_count(store: Store) -> int:
    return store.list_anomaly_counts().get(CAP_ANOMALY, 0)


def test_retry_of_is_required_at_the_call_site() -> None:
    """The `engine_config_home` precedent: "this is not a retry" is typed, not defaulted."""
    parameter = inspect.signature(spawn_owned_session).parameters["retry_of"]
    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_a_declared_retry_is_linked_to_its_predecessor(
    store: Store, workspace_id: str, root: Path
) -> None:
    """C-QR-9's first half: the link the spawn writes is the link the cap walks."""
    first = spawned(attempt(store, workspace_id, root, None))
    second = spawned(attempt(store, workspace_id, root, first))

    row = store.get_session(second)
    assert row is not None and row.retry_of == first
    assert store.retry_chain_depth(second) == 2
    first_row = store.get_session(first)
    assert first_row is not None and first_row.retry_of is None, "a first attempt has no link"


def test_the_attempt_that_exceeds_two_is_refused_and_counted_once(
    store: Store, workspace_id: str, root: Path
) -> None:
    """PP14: a declared lineage admits two master attempts; the third is refused
    `retry_cap_reached`, writes no row, and bumps the anomaly exactly once."""
    first = spawned(attempt(store, workspace_id, root, None))
    second = spawned(attempt(store, workspace_id, root, first))
    before_rows = len(store.list_sessions(workspace_id=workspace_id))
    before_cap = cap_count(store)
    assert before_rows == 2 and before_cap == 0  # arrival: two attempts, nothing counted yet

    third = attempt(store, workspace_id, root, second)

    assert isinstance(third, SpawnRefused), third
    assert third.cap == "retry_cap_reached"
    assert repr(second) in third.reason
    assert len(store.list_sessions(workspace_id=workspace_id)) == before_rows, "no row is written"
    assert cap_count(store) == before_cap + 1


def test_a_retry_of_an_unknown_session_is_refused_before_any_row(
    store: Store, workspace_id: str, root: Path
) -> None:
    """A lineage cannot start from a session that does not exist; no row, no cap."""
    missing = "01NOSUCHSESSION00000000000"
    result = attempt(store, workspace_id, root, missing)

    assert isinstance(result, SpawnRefused), result
    assert result.cap is None
    assert repr(missing) in result.reason and "no session" in result.reason
    assert store.list_sessions(workspace_id=workspace_id) == []
    assert cap_count(store) == 0


def test_a_second_retry_of_the_same_attempt_is_refused_naming_the_first(
    store: Store, workspace_id: str, root: Path
) -> None:
    """RD-2: two retries both declared "of X" would each walk up to depth 2 and
    bypass D31 forever. The second is refused, naming the retry that exists, and
    it is not a cap refusal: nothing is counted."""
    first = spawned(attempt(store, workspace_id, root, None))
    existing = spawned(attempt(store, workspace_id, root, first))

    sibling = attempt(store, workspace_id, root, first)

    assert isinstance(sibling, SpawnRefused), sibling
    assert sibling.cap is None
    assert "already retried" in sibling.reason
    assert repr(existing) in sibling.reason and repr(first) in sibling.reason
    assert len(store.list_sessions(workspace_id=workspace_id)) == 2
    assert cap_count(store) == 0


def test_a_human_retry_is_linked_and_not_capped(
    store: Store, workspace_id: str, root: Path
) -> None:
    """E-QR-14: D31 caps *master-initiated* attempts, so a human's third attempt
    starts — and is still linked, so the lineage stays whole."""
    first = spawned(attempt(store, workspace_id, root, None))
    second = spawned(attempt(store, workspace_id, root, first))

    third = spawned(attempt(store, workspace_id, root, second, origin=Origin.USER_UI))

    row = store.get_session(third)
    assert row is not None and row.retry_of == second
    assert store.retry_chain_depth(third) == 3
    assert cap_count(store) == 0
