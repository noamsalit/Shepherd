"""Wave 5, UNIT lane: M15 — the retry-cap logic works at its own seam (spec D31).

**Label (test-plan M15): logic exists but is unreachable in production (M14);
this PASS is not evidence the product enforces the cap.**

The seam is `orchestration.admission.admit(..., retry=Retry(of, initiated_by))`
over a real `Store` (its own SQLite file under the run root, the product's
migrations) and the product's own `testkit.ScriptedRunner` as the pane driver
(no pane is opened: admission only lists panes). The lineage is built with the
store's own `link_retry`, the only writer of `retry_of`.

**How "attempts 1, 2, 3" is read** (D31: "capped at 2 master-initiated per
lineage"; `admission.MAX_MASTER_ATTEMPTS`'s docstring quotes it): an attempt is
a session in the lineage. Attempt 1 is the master's first spawn (nothing to be
a retry of yet); attempt 2 is a retry of it; attempt 3 is a retry of attempt 2.
Attempts 1 and 2 must be admitted and attempt 3 refused `retry_cap_reached`,
with `WAKE_RETRY_CAP_REACHED` +1.

Mutation PP-6 (`w5_PP6-M15-human-retry`): attempt 3 is asked for with
`initiated_by = user_ui` (a human retry, which D31 does not cap), so the
refusal clause must go false.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from shepherd.core.clock import utc_now
from shepherd.core.ids import new_ulid
from shepherd.core.runner import ProcState
from shepherd.core.states import Origin
from shepherd.orchestration.admission import Admitted, Retry, SpawnRefused, admit
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner

from ..mutations import active
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Recorder

MUT_PP6 = "w5_PP6-M15-human-retry"
ANOMALY = "wake_retry_cap_reached"  # core/anomalies.py AnomalyKind.WAKE_RETRY_CAP_REACHED


@pytest.fixture(scope="module")
def store(qa6_run: RunContext) -> Iterator[Store]:
    directory = qa6_run.run0 / f"m15-{os.getpid()}"
    directory.mkdir(mode=0o700, exist_ok=False)
    opened = open_store(directory / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def runner() -> ScriptedRunner:
    return ScriptedRunner(panes=(), proc=ProcState(alive=True, pid=None, exit_code=None, exit_signal=None,
                                                   observed_at=utc_now()), screen=b"")


def row(store: Store, workspace_id: str, cwd: Path, depth: int) -> str:
    """A master-spawned row, the way `spawn_owned_session` writes one (origin orchestrator)."""
    session_id = new_ulid()
    store.create_owned_session(session_id=session_id, engine_session_id=str(uuid4()), workspace_id=workspace_id, repo_id=None,
                               cwd=str(cwd), started_at=utc_now(), origin=Origin.ORCHESTRATOR, parent_session_id=None,
                               depth=depth, ephemeral=False, title="QA6 M15", title_source="user", handle=None,
                               model=None, effort=None)
    return session_id


def counted(store: Store) -> int:
    return int(store.list_anomaly_counts().get(ANOMALY, 0))


@scenario("M15")
def test_m15_the_retry_cap_logic_works_at_its_own_seam(store: Store, qa6_run: RunContext, rec: Recorder) -> None:
    rec.note("M15 label: logic exists but is unreachable in production (M14); this PASS is not evidence the product "
             "enforces the cap")
    alpha = Path(os.path.realpath(qa6_run.repos / "alpha"))
    project = store.create_project(name="QA6-M15", description=None)
    store.add_repo(workspace_id=project.id, root_path=str(alpha), name="alpha",
                   git_common_dir=str(alpha / ".git"), vcs_remote=None)
    driver = runner()
    before = counted(store)

    def ask(retry: Retry | None) -> Admitted | SpawnRefused:
        return admit(store=store, runner=driver, workspace_id=project.id, cwd=str(alpha), parent_session_id=None,
                     retry=retry)

    first = ask(None)
    rec.check("api.attempt1_admitted", isinstance(first, Admitted), "attempt 1 (the first spawn) admitted", first)
    x = row(store, project.id, alpha, 0)
    second = ask(Retry(of=x, initiated_by=Origin.ORCHESTRATOR))
    rec.check("api.attempt2_admitted", isinstance(second, Admitted), "attempt 2 (a master retry of it) admitted", second)
    r1 = row(store, project.id, alpha, 0)
    store.link_retry(r1, x)
    rec.equal("db.lineage_depth_two", 2, store.retry_chain_depth(r1))
    initiated_by = Origin.ORCHESTRATOR
    if active(MUT_PP6):
        initiated_by = Origin.USER_UI
        rec.note(f"QA6 MUTATION {MUT_PP6} APPLIED: attempt 3 asked with initiated_by={initiated_by.value}")
    third = ask(Retry(of=r1, initiated_by=initiated_by))
    rec.check("api.attempt3_refused_retry_cap", isinstance(third, SpawnRefused) and third.cap == "retry_cap_reached",
              "attempt 3 refused, cap retry_cap_reached", third)
    rec.equal("db.anomaly_plus_one", before + 1, counted(store))
    rec.finish()
