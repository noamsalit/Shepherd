"""Wave 4, SUB lane: O3 — the three recursion caps at their boundaries (spec O54).

Its own instance: the total cap counts **panes on the socket** (admission.py
`_caps`), so a shared instance's other panes would move the boundary. 22 shim
panes are started and each resolves PROMPT_READY in about a second (W5).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from ..instance import db_rows
from ..pool import InstancePool
from ..sandbox import RunContext
from ..scenario import scenario
from ..verdict import Recorder, observe
from .test_wave4_0_support import Owned, frames, kill, open_owned, owned_panes, spawn

#: spec O54, verbatim numbers (independent of the product's constants).
DEPTH_CAP, CHILDREN_CAP, TOTAL_CAP = 3, 5, 20


@pytest.fixture(scope="module")
def caps(pool: InstancePool, qa6_run: RunContext) -> Iterator[Owned]:
    env = open_owned(pool, qa6_run, "O3")
    try:
        yield env
    finally:
        env.stream.close()


@scenario("O3")
def test_o3_the_three_recursion_caps_at_their_boundaries(caps: Owned, rec: Recorder) -> None:
    env = caps
    made: list[str] = []
    mark, amark = env.stream.mark(), env.audit.mark()
    calls = 0

    def admitted(label: str, parent: str | None = None) -> str | None:
        nonlocal calls
        calls += 1
        answer = spawn(env, title=f"QA6 O3 {label}", parent=parent)
        rec.check(f"api.{label}_spawned", answer.spawned, "spawned:true", answer.data)
        if answer.session_id is not None and answer.spawned:
            made.append(answer.session_id)
        return answer.session_id if answer.spawned else None

    def refused(label: str, cap: str, number: int, parent: str | None = None) -> None:
        nonlocal calls
        calls += 1
        answer = spawn(env, title=f"QA6 O3 {label}", parent=parent)
        refusal = str(answer.data.get("refusal") or "")
        rec.check(f"api.{label}_refused_{cap}", answer.data.get("spawned") is False and answer.data.get("cap") == cap
                  and cap in refusal and str(number) in refusal,
                  f"{{spawned:false, cap:{cap!r}}} with a readable refusal naming {cap} and {number}", answer.data)
        if answer.session_id is not None and answer.spawned:
            made.append(answer.session_id)

    try:
        chain0 = admitted("depth0")
        chain1 = admitted("depth1", chain0) if chain0 else None
        chain2 = admitted("depth2", chain1) if chain1 else None
        if chain2 is not None:
            refused("depth3", "depth", DEPTH_CAP, chain2)
        parent = admitted("parent")
        children = [admitted(f"child{i}", parent) for i in range(1, CHILDREN_CAP + 1)] if parent else []
        if parent is not None and all(children):
            refused("child6", "children_per_session", CHILDREN_CAP, parent)
        index = 0
        while len(owned_panes(env)) < TOTAL_CAP and index < TOTAL_CAP:
            index += 1
            if admitted(f"fill{index}") is None:
                break
        rec.equal("tmux.twenty_before_the_21st", TOTAL_CAP, len(owned_panes(env)))
        refused("total21", "total_owned_panes", TOTAL_CAP)
        rec.equal("tmux.exactly_twenty_at_the_end", TOTAL_CAP, len(owned_panes(env)))
        live = db_rows(env.controld.db, "SELECT COUNT(*) AS n FROM session WHERE ownership = 'owned' AND ended_at IS NULL")
        rec.equal("db.twenty_live_owned_rows", TOTAL_CAP, live[0]["n"])
        spawned_frames = frames(env.stream, mark, "session.spawned")
        rec.equal("stream.one_spawned_frame_per_admitted", len(made), len(spawned_frames))
        rec.equal("logs.one_spawn_row_per_call", calls, len(env.audit.records_for(amark, "spawn_session")))
    finally:
        for session_id in made:
            kill(env, session_id)
    gone, _ = observe(lambda: (not owned_panes(env)) or None, 10.0)
    rec.check("cleanup.every_pane_killed_through_the_product", bool(gone), "no owned pane left", owned_panes(env))
    rec.finish()
