"""P5 / BC-15 — a master retry is **declared** with `retry_of` (§3 D70).

Before D70 nothing in `src/` called `Store.link_retry`, so D31's lineage cap
(`admission._retry_cap`, via `retry_chain_depth`) walked chains no production
path could build. Now the spawn itself declares what it retries: the new row is
linked to its predecessor, admission caps the declared lineage **before any row
is written** (Differences 7), and RD-2 refuses a second retry of one attempt,
which would otherwise start a sibling lineage the upward walk never sees.

**Seam: `spawn_owned_session`** over a real `Store` in `tmp_path`, with the
`test_spawn` helpers (the scripted runner, the injected clock). Every lineage
here is built by the shipped sequence — no `retry_of` is planted with SQL. An
attempt's pane **exits** (`dead_pane`), so each predecessor is `stopped` by the
spawn's own poll: only a stopped attempt in the same project can be retried.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.fold_types import FoldDelta
from shepherd.core.states import Origin, Ownership, SessionState
from shepherd.orchestration.spawn import SpawnOutcome, SpawnRefused, spawn_owned_session
from shepherd.store.db import Store
from shepherd.store.models import StoreError

from .test_spawn import (  # noqa: F401 — `store`, `root` and `workspace_id` are fixtures
    ExplodingRunner,
    dead_pane,
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
    runner: object | None = None,
) -> SpawnOutcome | SpawnRefused:
    """One spawn whose pane exits, so the attempt ends `stopped` and can be retried."""
    result, _ = spawn(
        store=store,
        runner=runner if runner is not None else scripted(panes=[dead_pane()]),
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
    """RD-2 for a human: two retries both declared "of X" would each walk up to
    depth 2 and start sibling lineages. The second is refused, naming the retry
    that exists and advising a retry of that one — which a human may take, since
    D31 caps only the master. It is not a cap refusal: nothing is counted."""
    first = spawned(attempt(store, workspace_id, root, None, origin=Origin.USER_UI))
    existing = spawned(attempt(store, workspace_id, root, first, origin=Origin.USER_UI))

    sibling = attempt(store, workspace_id, root, first, origin=Origin.USER_UI)

    assert isinstance(sibling, SpawnRefused), sibling
    assert sibling.cap is None
    assert "already retried" in sibling.reason and "retry that one instead" in sibling.reason
    assert repr(existing) in sibling.reason and repr(first) in sibling.reason
    assert len(store.list_sessions(workspace_id=workspace_id)) == 2
    assert cap_count(store) == 0


def test_a_master_sibling_retry_of_a_full_lineage_names_the_human_and_is_counted(
    store: Store, workspace_id: str, root: Path
) -> None:
    """RD-2 for the master (§3 D70 refinement): "retry that one instead" would
    send it straight into D31's cap, because X and r1 already fill a lineage of
    two. The refusal says the lineage has used its attempts, names the human as
    the next step, carries the cap, and bumps the cap's own anomaly once."""
    first = spawned(attempt(store, workspace_id, root, None))
    existing = spawned(attempt(store, workspace_id, root, first))

    sibling = attempt(store, workspace_id, root, first)

    assert isinstance(sibling, SpawnRefused), sibling
    assert sibling.cap == "retry_cap_reached"
    assert "already retried" in sibling.reason and repr(existing) in sibling.reason
    assert "human" in sibling.reason
    assert "retry that one instead" not in sibling.reason, "advice that cannot succeed"
    assert len(store.list_sessions(workspace_id=workspace_id)) == 2, "no row is written"
    assert cap_count(store) == 1


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


# ----- REM-FIX: only a started attempt joins the lineage; only a stopped one is retried


def test_a_refused_start_does_not_consume_the_lineage(
    store: Store, workspace_id: str, root: Path
) -> None:
    """A retry whose `runner.start` refuses (a transient tmux timeout) ends its
    row `refused` and is **not** linked, so X's lineage is untouched: the next
    retry of X starts as a master retry — neither RD-2 nor the cap refuses it."""
    x = spawned(attempt(store, workspace_id, root, None))

    refused = attempt(store, workspace_id, root, x, runner=ExplodingRunner())
    assert isinstance(refused, SpawnRefused), refused
    refused_rows = [r for r in store.list_sessions(workspace_id=workspace_id) if r.id != x]
    assert len(refused_rows) == 1 and refused_rows[0].stop_reason == "refused"
    assert refused_rows[0].retry_of is None, "a start that never happened is not an attempt"
    assert store.retried_by(x) is None

    again = attempt(store, workspace_id, root, x)

    row = store.get_session(spawned(again))
    assert row is not None and row.retry_of == x
    assert cap_count(store) == 0


def test_a_link_the_store_refuses_ends_the_row_refused(
    store: Store, workspace_id: str, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every failure is a `SpawnRefused`, never a raise: a `StoreError` from
    `link_retry` ends the new row `refused` (D73) and is answered in one sentence."""
    x = spawned(attempt(store, workspace_id, root, None))

    def refuse(session_id: str, retry_of: str) -> None:
        raise StoreError(f"no session {retry_of!r} for {session_id!r} to be a retry of")

    monkeypatch.setattr(store, "link_retry", refuse)
    result = attempt(store, workspace_id, root, x)

    assert isinstance(result, SpawnRefused), result
    assert result.cap is None and repr(x) in result.reason
    row = next(r for r in store.list_sessions(workspace_id=workspace_id) if r.id != x)
    assert row.state is SessionState.STOPPED and row.stop_reason == "refused"
    assert row.retry_of is None


def test_a_retry_of_a_live_session_is_refused_before_any_row(
    store: Store, workspace_id: str, root: Path
) -> None:
    """A retry is another attempt at a **stopped** session; a live one is still
    its own attempt. Refused before admission: no row, no anomaly."""
    live, _ = spawn(
        store=store,
        runner=scripted(panes=[ready_pane()]),
        workspace_id=workspace_id,
        cwd=str(root / "repo"),
        retry_of=None,
    )
    x = spawned(live)

    result = attempt(store, workspace_id, root, x)

    assert isinstance(result, SpawnRefused), result
    assert result.cap is None and repr(x) in result.reason and "stopped" in result.reason
    assert len(store.list_sessions(workspace_id=workspace_id)) == 1
    assert cap_count(store) == 0


def test_a_retry_of_another_projects_session_is_refused_before_any_row(
    store: Store, workspace_id: str, root: Path, tmp_path: Path
) -> None:
    """A lineage stays in its project: a retry naming another project's attempt is
    refused before admission, naming that attempt. No row, no anomaly."""
    other_root = tmp_path / "elsewhere"
    (other_root / "repo").mkdir(parents=True)
    other = store.create_project(name="elsewhere", description=None)
    store.add_repo(
        workspace_id=other.id, root_path=str(other_root), name="elsewhere",
        git_common_dir=str(other_root / ".git"), vcs_remote=None,
    )
    x = spawned(attempt(store, other.id, other_root, None))

    result = attempt(store, workspace_id, root, x)

    assert isinstance(result, SpawnRefused), result
    assert result.cap is None and repr(x) in result.reason and "project" in result.reason
    assert store.list_sessions(workspace_id=workspace_id) == []
    assert cap_count(store) == 0


def test_a_master_retry_of_an_attached_session_is_linked_and_not_capped(
    store: Store, workspace_id: str, root: Path
) -> None:
    """E-QR-14's attached half: an attached (not owned) stopped session is a
    lineage of one, so the master's retry of it starts, is linked, and counts nothing."""
    attached = store.register_session(
        "eng-attached", workspace_id, None, str(root / "repo"), "2026-09-17T09:00:00Z",
        Origin.EXTERNAL, Ownership.ATTACHED,
    )
    store.apply_fold_delta(
        attached.id, FoldDelta(state=SessionState.STOPPED, last_event_at="2026-09-17T09:30:00Z")
    )

    result = attempt(store, workspace_id, root, attached.id)

    row = store.get_session(spawned(result))
    assert row is not None and row.retry_of == attached.id
    assert cap_count(store) == 0
