"""The `Runner` seam: §6's eight members, `pane()`, `list_owned_panes()`, and the
two the router decided during M3 — `clear_input` and `attached_clients`.

The seam is asserted **by name and by signature**, not by "a class exists": the
whole reason M3 declares a Protocol before any driver is written is that four
tracks are going to code against it in parallel, and a member that quietly
changes shape under them is the split `mypy` only catches where they happen to
meet (M1's F9/BLOCKER-T7b-1).

`list_owned_panes` is the tenth member and it is the one that counts **panes**
rather than rows (N11, ADR-M3-4): `MAX_TOTAL_OWNED_SESSIONS` is a cap on live
panes, and a row whose pane is gone is not a session holding a slot.

The eleventh and twelfth arrived with captures behind them, not with a
refactor: `clear_input` because D45's clearing step presses a key the byte
channel cannot express (T13-2), and `attached_clients` because P3 caught a
human's keystrokes being submitted inside Shepherd's own prompt (BLOCKER-T1-3).
"""

from __future__ import annotations

import dataclasses
import inspect
import typing

from shepherd.core.runner import PaneState, ProcState, RunnerHandle, SessionSpec
from shepherd.runner.base import ByteStream, PaneRef, Runner

#: (name, parameter names after `self`, return annotation) — the seam, written
#: out so a change to it is a change to this table and therefore a decision.
EXPECTED: tuple[tuple[str, tuple[str, ...], object], ...] = (
    ("start", ("spec",), RunnerHandle),
    ("attach", ("handle",), ByteStream),
    ("snapshot", ("handle", "scrollback"), bytes),
    ("write", ("handle", "data"), None),
    ("resize", ("handle", "cols", "rows"), None),
    ("interrupt", ("handle",), None),
    ("terminate", ("handle",), None),
    ("probe", ("handle",), ProcState),
    ("pane", ("handle",), PaneState),
    ("list_owned_panes", (), tuple[PaneRef, ...]),
    ("clear_input", ("handle",), None),
    ("attached_clients", ("handle",), int),
)


def protocol_members(protocol: type) -> set[str]:
    """The names a Protocol declares, read off its own body.

    `typing.get_protocol_members` is 3.13; this repo is 3.12 (`pyproject.toml`).
    Reading `vars()` is the same answer without the private `typing` helper, and
    it fails loudly if a member is ever added as a class attribute by accident.
    """
    return {name for name in vars(protocol) if not name.startswith("_")}


def test_the_runner_seam_is_exactly_twelve_members() -> None:
    """Twelve, and the count is asserted — a thirteenth is a plan change, not a patch.

    The eleventh is `clear_input` (T13-2, decided by the router): D45's clearing
    step presses a **named key**, and `write(handle, data: bytes)` is the hex
    byte channel — the captured clearing step (`gap-fill/keys-claude-…/steps.log`
    l.7) used the key name, and the hex form delivering the same control byte is
    not captured. It is named for its **intent**, exactly as `interrupt` is named
    for what it means rather than for the key it presses, so no free-text key
    vocabulary crosses the seam (T8-3's shape).

    The twelfth is `attached_clients` (BLOCKER-T1-3, decided by the router): a
    human attached at a second client types **into the prompt Shepherd submits**,
    captured in P3. It is a caller-side precondition, counted and deferred on —
    not a fifth field of the write-policy key, which stays pure and total over
    values at 96 keys.

    `snapshot`'s parameter is `scrollback` (T9-1, decided): a **depth**, not a
    row count, and the signature is where that decision is visible to the four
    tracks coding against this seam.
    """
    assert protocol_members(Runner) == {name for name, _, _ in EXPECTED}
    assert len(EXPECTED) == 12


def test_every_member_has_the_signature_the_plan_published() -> None:
    hints = {name: typing.get_type_hints(getattr(Runner, name)) for name, _, _ in EXPECTED}
    for name, parameters, returns in EXPECTED:
        member = getattr(Runner, name)
        signature = inspect.signature(member)
        assert tuple(signature.parameters)[1:] == parameters, name
        # `get_type_hints` normalises a `-> None` annotation to `NoneType`.
        expected = type(None) if returns is None else returns
        assert hints[name]["return"] == expected, name


def test_a_byte_stream_is_chunks_and_close() -> None:
    """The terminal seam is two members: the frames, and the way to stop them.

    `TerminalFrame` carries the `closed` reason (E-M3-29); the stream itself only
    has to be stoppable, so a driver that cannot express anything richer than a
    file object can still satisfy it.
    """
    assert protocol_members(ByteStream) == {"chunks", "close"}


def test_a_pane_ref_is_one_owned_pane_on_the_socket() -> None:
    """Four fields, frozen, and the session id is carried separately from the name.

    The name is `shepherd_<id>` by construction, but a consumer that had to
    re-derive the id by slicing the name would be re-implementing
    `tmux_cmd.session_name` at every call site — and the slice is wrong the first
    time the prefix changes.
    """
    assert dataclasses.is_dataclass(PaneRef)
    assert PaneRef.__dataclass_params__.frozen is True
    fields = {field.name: field.type for field in dataclasses.fields(PaneRef)}
    assert set(fields) == {"session_name", "session_id", "pane_pid", "dead"}
    hints = typing.get_type_hints(PaneRef)
    assert hints["session_name"] is str
    assert hints["session_id"] is str
    assert hints["pane_pid"] == int | None
    assert hints["dead"] is bool


def test_the_seam_names_no_multiplexer() -> None:
    """`Runner` is the seam, not the tmux driver.

    `runner/local.py` (T8) is where a particular multiplexer's words belong. A
    member called `send_keys` or a parameter called `socket` here would make every
    other layer speak tmux, which is the leak `core/runner.py` already refuses one
    level down.
    """
    import ast
    from pathlib import Path

    from shepherd.runner import base

    source = Path(base.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    words = ("send-keys", "capture-pane", "-L", "kill-session")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            for word in words:
                assert word not in node.value, node.value
    for name, parameters, _ in EXPECTED:
        assert "socket" not in parameters, name
        assert "tm" + "ux" not in name, name
