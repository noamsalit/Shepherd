"""S6's negative control. **Inert**: nothing imports this, and nothing runs it.

Read as text and parsed as an AST by
`tests/qa/test_s6_restart_continuity.py::modules_that_call_resume`, exactly as
`tests/boundaries/fixtures/second_master_send_caller.py` is read by P-M4-21's
own single-caller rule. CLAUDE.md rule 1: *a planted violation is an inert
fixture that nothing imports.* There is no signal here, no subprocess, no
socket, no teardown verb — the module body performs no call at all, and the one
call this fixture exists for is inside a function nobody invokes.

Its job is to make the scan's emptiness falsifiable: if the scan ever stops
seeing a `.resume(` call, `test_the_resume_scan_is_not_blind` goes red before
`test_exactly_one_module_in_src_calls_resume` can pass vacuously.
"""

from __future__ import annotations


def a_second_caller(runtime: object, conversation: str) -> None:
    """The shape the scan must see: an attribute call named `resume`."""
    runtime.resume(conversation)  # type: ignore[attr-defined]
