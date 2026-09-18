"""The runner and engine vocabulary — one L1 module every other layer speaks.

`runner/`, `orchestration/`, `engines/`, `store/`, `toolsurface/` and `web/` all
name these types, so none of them defines a second copy: M1's F9/BLOCKER-T7b-1
lesson is that two structurally identical types are a split `mypy` only catches
where they happen to meet.

Vocabulary only — enums, frozen dataclasses and constants. No logic, no I/O, and
**no terminal-multiplexer word**: the words of the pane driver live in
`runner/`, one layer up, and a literal here would be that layer leaking down.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

#: `session.runner_handle` is a single TEXT column, so the three fields are
#: joined by one character no field may contain. `to_text` refuses rather than
#: emitting a string that would parse back as a different handle.
HANDLE_SEPARATOR = "|"


class PaneKind(StrEnum):
    """What the pane is showing, as the probe captures actually show it.

    Six members, and the write-policy table (T13) is total over
    `SessionState x PaneKind x Ownership x input_empty` — 96 keys. A seventh
    member makes that table partial without failing anything, which is why
    `test_pane_kind_is_the_six_the_captures_show` pins the product.

    `UNREADABLE` is principle 5 on the screen: a capture we could not classify is
    a value, never a guess.
    """

    TRUST_DIALOG = "trust_dialog"
    PERMISSION_DIALOG = "permission_dialog"
    PROMPT_READY = "prompt_ready"
    BUSY = "busy"
    DEAD = "dead"
    UNREADABLE = "unreadable"


class WriteDecision(StrEnum):
    """What the write policy decided — the **value** space, not a key factor.

    Three refusals rather than one `REFUSE`, because a reader is told a different
    thing by each: a dialog is waiting, there is no live terminal at all, or a
    draft is sitting in the input box. `CLEAR_THEN_SEND` is the capture-proven
    clearing form (`01b-after-ctrl-u.txt`), re-read before the send.
    """

    SEND_NOW = "send_now"
    CLEAR_THEN_SEND = "clear_then_send"
    QUEUE = "queue"
    REFUSE_DIALOG = "refuse_dialog"
    REFUSE_NO_PTY = "refuse_no_pty"
    REFUSE_INPUT_NOT_EMPTY = "refuse_input_not_empty"


@dataclass(frozen=True)
class RunnerHandle:
    """Where an owned session's pane lives, as one round-trippable string."""

    runner: str
    socket: str
    session_name: str

    def to_text(self) -> str:
        """The stored form. Raises `ValueError` on a field holding the separator."""
        parts = (self.runner, self.socket, self.session_name)
        for part in parts:
            if HANDLE_SEPARATOR in part:
                raise ValueError(
                    f"a runner handle field may not contain {HANDLE_SEPARATOR!r}: {part!r}"
                )
        return HANDLE_SEPARATOR.join(parts)

    @classmethod
    def from_text(cls, text: str) -> RunnerHandle:
        """The inverse. Raises `ValueError` on anything but three parts."""
        parts = text.split(HANDLE_SEPARATOR)
        if len(parts) != 3:
            raise ValueError(f"a runner handle has three fields, not {len(parts)}: {text!r}")
        return cls(runner=parts[0], socket=parts[1], session_name=parts[2])


@dataclass(frozen=True)
class ProcState:
    """What is known about the process behind a pane at one observation.

    `exit_signal` stays `None` on the evidence we have: the pane's dead-signal
    field was **empty even after SIGTERM** — the engine handled the signal and
    exited 143 — so the field exists to be read when a driver can supply it,
    never to be inferred from the exit code.
    """

    alive: bool
    pid: int | None
    exit_code: int | None
    exit_signal: int | None
    observed_at: str


@dataclass(frozen=True)
class PaneFields:
    """The per-pane format fields the session listing prints, as parsed values."""

    alternate_on: bool
    pane_dead: bool
    pane_dead_status: int | None
    pane_title: str | None
    width: int
    height: int
    pane_pid: int | None


@dataclass(frozen=True)
class PaneState:
    """One classified observation of a pane.

    `input_text` is **draft text only**. Ghost text — the placeholder the TUI
    renders in the same box — is a separate field by construction (E-M3-5), so
    no caller can mistake a placeholder for something the user typed.
    """

    kind: PaneKind
    fields: PaneFields
    input_text: str
    ghost_text: str | None
    dialog_text: str | None


@dataclass(frozen=True)
class SessionSpec:
    """§6's "a session is (engine, provider, credential, runner, project, task)",
    narrowed to what M3 resolves before a spawn."""

    session_id: str
    engine_session_id: str
    cwd: str
    brief: str | None
    title: str | None
    model: str | None
    effort: str | None
    engine: str
    runner: str
    env: Mapping[str, str]


@dataclass(frozen=True)
class EngineCapabilities:
    """§6's capability record. `can_spawn` is the degrade when no pane driver is
    reachable at all (D-5): the engine is still usable, it just cannot be
    started for you."""

    can_spawn: bool
    can_steer: bool
    can_fork: bool
    can_set_title: bool
    has_hooks: bool
    effort_ladder: tuple[str, ...]
    transcript_format: Literal["jsonl", "sqlite", "none"]


@dataclass(frozen=True)
class TerminalFrame:
    """A frame on the terminal stream. A `closed` frame always carries a reason
    (E-M3-29) — a stream that stops without saying why is the unknown principle
    5 forbids."""

    kind: Literal["snapshot", "live", "closed"]
    data: bytes
    reason: str | None


class RunnerRefusal(Exception):
    """The one refusal a runner raises upward.

    Every entry point turns a failure into this or into a counted degrade, so a
    caller has two cases to handle rather than an open set of exceptions.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


#: How often a spawn is polled while it comes up, and how long it may take
#: before `starting` becomes a stop (§8 line 988's own number for the second).
SPAWN_POLL_INTERVAL_S = 0.25
SPAWN_TIMEOUT_S = 60.0

#: §11's recursion caps, verbatim. `MAX_TOTAL_OWNED_SESSIONS` counts **panes**,
#: not rows — see T11 and T12's reconcile: a row whose pane is gone is not a
#: session holding a slot.
MAX_SESSION_DEPTH = 3
MAX_CHILDREN_PER_SESSION = 5
MAX_TOTAL_OWNED_SESSIONS = 20

#: The **measured** largest accepted single argv word in bytes, not a round
#: number: 16325 is the smallest rejected one in the same capture. The limit is
#: on the client-to-server message, not on the platform's `ARG_MAX`.
TMUX_COMMAND_LIMIT_B = 16324

class SpawnArgv(Protocol):
    """An engine's spawn words, told how many bytes of frame will precede them.

    The engine-to-driver seam, at L1 because each side implements one half of it.
    The measured ceiling above is on the **whole** client-to-server message,
    and the pane driver prepends its own words — plus two per environment
    variable, from an unbounded `SessionSpec.env` — to whatever the engine
    returns. An engine counting only its own argv accepted a command the driver
    could not send, and was told `command too long` (T10-R2). This is
    `capabilities(pane_driver_available=)` pointing the other way: the driver's
    fact, injected into the engine, because neither can see the other's words.
    """

    def __call__(self, spec: SessionSpec, *, frame_bytes: int) -> list[str]: ...



def command_size(argv: Sequence[str]) -> int:
    """The command's size on the wire: UTF-8 **bytes** plus one separator per gap.

    Never characters: a brief of multibyte text is up to four times `len()`.

    It lives here, beside the limit it is measured against, because **two**
    layers now need it and neither may import the other's: the engine measures
    its own argv, and the pane driver measures the frame it prepends. T10-R2 put
    it in `engines/claude_code/spawn.py`'s `__all__` — which it still is,
    re-exported — but `runner/` importing an engine module is the §5.0 leak T8-1
    refused for `spawn_argv`, and this is wire arithmetic over a word list, not
    engine vocabulary. The duplication alternative is worse: the two sides of one
    budget agreeing is the whole point.
    """
    return sum(len(word.encode("utf-8")) for word in argv) + max(len(argv) - 1, 0)
