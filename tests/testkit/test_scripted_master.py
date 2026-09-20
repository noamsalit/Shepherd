"""T17: `ScriptedMaster`, the `MasterRuntime` seam's `Scripted*` double (§14.2).

Four checks the plan names, and the rest exist because a double is only worth
what it refuses.

**The trap this file is written against.** A double that answers only the
members a test happens to call will pass a contract suite that only calls those
members — the suite then proves nothing about the sixth. So the member set is
**enumerated from the `Protocol`** (K19: a name set, never a count), the double
is asserted to answer *nothing else*, and `test_it_answers_nothing_but_the_seam`
goes red if a catch-all `__getattr__` is ever added to make a future suite pass.

**Absence is asserted after an arrival, never sampled.** The interrupt check
drives the interrupt from *inside* the consuming loop, at the event it names, so
the missing second tool call is bound to that interrupt rather than to whatever
the generator happened to have produced when the assertion ran (§T10-7's
survivor: a set asserted after a call that something earlier populated).
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shepherd.core.master import (
    MASTER_EVENT_KINDS,
    ExportedTool,
    MasterCapabilities,
    MasterEvent,
    MasterRefusal,
    MasterRuntime,
)
from shepherd.testkit.scripted_master import (
    SCRIPTED_CAPABILITIES,
    SCRIPTED_OCCURRED_AT,
    ScriptedMaster,
    Turn,
)

MODULE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "shepherd"
    / "testkit"
    / "scripted_master.py"
)


def protocol_members(protocol: type) -> set[str]:
    """The names a structural implementation must supply, read off the class.

    The same helper `tests/test_core_master.py` and `tests/runner/test_base.py`
    use; `typing.get_protocol_members` is 3.13 and this repo is 3.12.
    """
    return {
        name
        for name, value in vars(protocol).items()
        if callable(value) and not name.startswith("_")
    }


def public_callables(cls: type) -> set[str]:
    return {
        name
        for name, value in vars(cls).items()
        if callable(value) and not name.startswith("_")
    }


async def drain(stream: AsyncIterator[MasterEvent]) -> list[MasterEvent]:
    return [event async for event in stream]


def one_turn() -> ScriptedMaster:
    """§14.2's own example, verbatim."""
    return ScriptedMaster(
        [
            Turn(
                says="Two sessions need you.",
                calls=[
                    ("fleet_summary", {}),
                    ("kill_session", {"id": "ses_7f3k"}),
                ],
            )
        ]
    )


# --------------------------------------------------------------------------
# The seam's shape
# --------------------------------------------------------------------------


def test_scripted_master_satisfies_the_protocol() -> None:
    """Enumerated from `MasterRuntime` itself — a missed member is red here.

    A written-out list would pass a seam that grew a seventh member; the
    Protocol is the source of truth, and `close()` (DP9) is in it.
    """
    required = protocol_members(MasterRuntime)
    assert required, "the Protocol enumerated to nothing — this check is broken"
    missing = {name for name in required if not callable(getattr(ScriptedMaster, name, None))}
    assert missing == set(), missing


def test_it_answers_nothing_but_the_seam() -> None:
    """The double's own public callables are **exactly** the seam's.

    Two failures this binds: a member answered that the seam does not have
    (`mount_tools`, the D32 mistake §14.2 says a `ScriptedMaster` would have
    caught in an afternoon), and a catch-all that would let any future contract
    suite pass by answering everything.
    """
    assert public_callables(ScriptedMaster) == protocol_members(MasterRuntime)
    assert not hasattr(ScriptedMaster, "__getattr__")
    with pytest.raises(AttributeError):
        one_turn().mount_tools  # type: ignore[attr-defined]


def test_it_is_a_peer_and_not_a_parent() -> None:
    """§14.2: never a base class. Nothing inherits from it, and it inherits
    from nothing."""
    assert ScriptedMaster.__bases__ == (object,)
    assert ScriptedMaster.__subclasses__() == []


# --------------------------------------------------------------------------
# The script
# --------------------------------------------------------------------------


def test_a_turn_emits_its_events_in_order() -> None:
    """Text, then each scripted call in the order written, then the terminal.

    Goes red on reordering: the assertion is the whole sequence as a list, not
    a membership test.
    """
    events = asyncio.run(drain(one_turn().send("what needs me?")))
    assert [(event.kind, event.tool_name) for event in events] == [
        ("text", None),
        ("tool_call", "fleet_summary"),
        ("tool_call", "kill_session"),
        ("turn_ended", None),
    ]
    assert events[0].text == "Two sessions need you."
    assert events[2].payload == {"id": "ses_7f3k"}


def test_no_tool_result_is_invented_for_a_scripted_call() -> None:
    """§14.2's division of labour: the double emits the call, the **suite**
    decides what the call did. A `tool_result` here would be the double
    answering a question that belongs to the test."""
    events = asyncio.run(drain(one_turn().send("go")))
    assert [event.kind for event in events].count("tool_result") == 0


def test_every_event_is_ours_and_none_of_them_is_stamped_from_a_clock() -> None:
    """The kinds are ADR-M4-5's, and the stamp is a fixture's constant: a
    double that read the clock would be non-deterministic in the one place the
    suite compares events."""
    events = asyncio.run(drain(one_turn().send("go")))
    assert {event.kind for event in events} <= MASTER_EVENT_KINDS
    assert {event.occurred_at for event in events} == {SCRIPTED_OCCURRED_AT}


def test_the_second_send_replays_the_second_turn() -> None:
    """The cursor advances; the script is not one turn repeated."""
    master = ScriptedMaster([Turn(says="first"), Turn(says="second")])
    first = asyncio.run(drain(master.send("a")))
    second = asyncio.run(drain(master.send("b")))
    assert [event.text for event in first if event.kind == "text"] == ["first"]
    assert [event.text for event in second if event.kind == "text"] == ["second"]
    assert master.sent == ["a", "b"]


def test_a_turn_past_the_end_of_the_script_is_refused() -> None:
    """A fixture that repeated its last turn forever would answer a question it
    was never given — and a caller could pass this suite having sent twice as
    many turns as it was scripted for."""
    master = ScriptedMaster([Turn(says="only one")])
    asyncio.run(drain(master.send("a")))
    with pytest.raises(MasterRefusal, match="1 turn"):
        asyncio.run(drain(master.send("b")))


# --------------------------------------------------------------------------
# DP9 — the sixth member, and the one with teeth
# --------------------------------------------------------------------------


def test_send_after_close_is_refused() -> None:
    """DP9's whole reason: goes red if `close()` is a no-op."""
    master = one_turn()
    master.close()
    with pytest.raises(MasterRefusal, match="closed"):
        asyncio.run(drain(master.send("anything")))


def test_close_is_idempotent() -> None:
    """§6's `close()` docstring: shutdown must be able to call it after an
    already-failed turn."""
    master = one_turn()
    master.close()
    master.close()
    assert master.closed is True


# --------------------------------------------------------------------------
# Interrupt — an arrival, then an absence
# --------------------------------------------------------------------------


def test_an_interrupt_mid_turn_ends_the_turn_in_flight() -> None:
    """The interrupt is driven **from inside the loop**, at a named arrival.

    §T10-7's survivor is the reason: asserting the tail of a stream after the
    fact does not bind it to the interrupt if the stream was already finished
    when the assertion ran. Here the first tool call's *arrival* is the
    synchronisation point — asserted, not commented — and only then is the
    second call's absence meaningful.
    """
    master = one_turn()
    seen: list[MasterEvent] = []

    async def drive() -> None:
        async for event in master.send("go"):
            seen.append(event)
            if event.kind == "tool_call" and event.tool_name == "fleet_summary":
                master.interrupt()

    asyncio.run(drive())

    arrived = [(event.kind, event.tool_name) for event in seen]
    assert ("tool_call", "fleet_summary") in arrived, arrived
    assert ("tool_call", "kill_session") not in arrived, arrived
    assert arrived[-1] == ("turn_ended", None)
    assert seen[-1].payload == {"interrupted": True}
    assert master.interrupts == 1


def test_an_uninterrupted_turn_says_so_on_its_terminal_event() -> None:
    """The negative control for the row above: without the interrupt the same
    fixture runs to the end and the terminal event says `interrupted: False`."""
    events = asyncio.run(drain(one_turn().send("go")))
    assert events[-1].payload == {"interrupted": False}


# --------------------------------------------------------------------------
# The observation channel — a record a test may read, never an expectation
# --------------------------------------------------------------------------


def test_configure_records_the_tools_and_the_prompt_exactly() -> None:
    tools = (
        ExportedTool(name="fleet_summary", description="the fleet", input_schema={}),
    )
    master = one_turn()
    master.configure(tools, "  the frozen prompt\n")
    assert master.configured_tools == tools
    assert master.system_prompt == "  the frozen prompt\n"


def test_resume_records_the_opaque_id() -> None:
    master = one_turn()
    master.resume("ses_opaque")
    assert master.resumed == ["ses_opaque"]


def test_capabilities_are_a_fixtures_answer_and_can_be_scripted() -> None:
    """The default is honest about a script — it owns no history and compacts
    nothing — and a test that needs a different record hands one over."""
    assert one_turn().capabilities() == SCRIPTED_CAPABILITIES
    assert SCRIPTED_CAPABILITIES.owns_history is False
    scripted = MasterCapabilities(
        billing_mode="seat",
        owns_history=True,
        owns_compaction=True,
        supports_parallel_tool_calls=True,
        context_window=42,
    )
    assert ScriptedMaster([], capabilities=scripted).capabilities() == scripted


# --------------------------------------------------------------------------
# Nothing spawned, no clock read
# --------------------------------------------------------------------------

#: The four the plan names. Each is a way for a "deterministic, in
#: milliseconds, no process spawned" double to stop being any of those.
FORBIDDEN_MODULES: frozenset[str] = frozenset({"subprocess", "socket", "time", "datetime"})


def forbidden_imports(source: str) -> set[str]:
    """Every name in `FORBIDDEN_MODULES` this source imports, by AST.

    A property over the parse, not a substring search: `subprocess` in a
    docstring is prose, and `import subprocess as sp` is the spelling a grep
    for `subprocess.` misses.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found |= {node.module.split(".")[0]}
    return found & FORBIDDEN_MODULES


def test_it_spawns_nothing_and_reads_no_clock() -> None:
    assert forbidden_imports(MODULE_SOURCE.read_text(encoding="utf-8")) == set()


def test_the_scan_bites() -> None:
    """The paired positive control, over an **inert string** — never a file the
    suite imports (CLAUDE.md, 2026-09-17). A check with no proof that it can go
    red is the defect the check exists to catch."""
    planted = "import subprocess as sp\nfrom datetime import UTC\nimport asyncio\n"
    assert forbidden_imports(planted) == {"subprocess", "datetime"}
