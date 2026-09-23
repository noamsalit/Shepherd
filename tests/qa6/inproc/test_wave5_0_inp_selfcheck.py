"""INP self-check (not a scenario): the composition runs scripted calls through the real gate.

Runs first in INP #1's process (file order) and proves, before any M-scenario
relies on it, that `ToolCallingMaster` (1) is what `controld.build_master`
resolves to, (2) calls tools through `toolsurface.client.call` — so each call
leaves an audit row with `actor_kind` master — and (3) computes a later call's
arguments from an earlier call's result (P10's shape). It writes no record.
"""

from __future__ import annotations

import json

import pytest

from ..auditprobe import AuditProbe
from ..inp import Inp, patched
from ..inproc.master import Call, CallResult, Turn
from ..verdict import await_env

pytestmark = pytest.mark.qa6


def unassigned_from(results: object) -> dict[str, object]:
    if not isinstance(results, tuple) or not results or not isinstance(results[0], CallResult):
        raise AssertionError(f"no earlier result to compute from: {results!r}")
    listed = json.loads(results[0].text)
    projects = listed.get("projects") if isinstance(listed, dict) else None
    first = projects[0] if isinstance(projects, list) and projects else {}
    return {"project_id": str(first.get("project_id")) if isinstance(first, dict) else ""}


def test_inp_selfcheck_scripted_calls_go_through_the_gate(inp: Inp) -> None:
    assert patched(), "shepherd.daemons.controld.build_master is the ToolCallingMaster factory"
    assert inp.book.records and inp.book.records[-1].ended == "turn_ended", "the READY turn ended"
    assert inp.book.configured_tools, "the master's tool set was configured"
    audit = AuditProbe.for_instance(inp.root)
    mark = audit.mark()
    answer = inp.send_turn(Turn(says="QA6 self-check", calls=[Call("list_projects"), Call("get_project", unassigned_from)]))
    turn_id = answer.get("turn_id")
    record = await_env(lambda: next((r for r in inp.book.records if r.turn_id == turn_id and r.ended), None), 10.0,
                       "the self-check turn")
    assert [r.name for r in record.results] == ["list_projects", "get_project"], record.results
    assert not any(r.is_error for r in record.results), [r.text[:200] for r in record.results]
    assert record.results[1].args == {"project_id": "unassigned"}, "args computed from the earlier result"
    rows = await_env(lambda: [r for r in audit.since(mark) if r.get("tool") in ("list_projects", "get_project")] or None,
                     5.0, "audit rows for the master's calls")
    assert {r.get("actor_kind") for r in rows} == {"master"}, rows
    assert {r.get("correlation_id") for r in rows} == {turn_id}, "a turn's calls share its correlation id"
