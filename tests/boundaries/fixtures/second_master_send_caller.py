"""INERT FIXTURE — a second caller of `MasterRuntime.send()`, never imported.

P-M4-21's negative control. This file is **read as text and parsed as an AST**
by `tests/orchestration/test_master_turn.py::
test_the_single_caller_rule_detects_a_second_caller`. It is never on an import
path the suite executes and it runs nothing: per CLAUDE.md ("Mutations"), a
planted violation is an inert fixture, because a planted mutation is code that
runs and a directory does not contain an effect.

It stands for the exact improvisation ADR-M4-10 rejects: a second turn driver
written into the composition root because no component produced one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from shepherd.core.master import MasterEvent, MasterRuntime


async def drive_a_turn_from_the_composition_root(
    runtime: MasterRuntime, text: str
) -> AsyncIterator[MasterEvent]:
    """The second caller. One `.send(` is all the rule needs to see."""
    async for event in runtime.send(text):
        yield event
