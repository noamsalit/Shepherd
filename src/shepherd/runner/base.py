"""The `Runner` seam — §6's D36, declared before any driver exists.

One interface, twelve members, no multiplexer word anywhere in it. Four M3 tracks
code against this Protocol in parallel, so it is written down once and asserted
member by member (`tests/runner/test_base.py`): two structurally similar
interfaces are a split `mypy` only catches where they happen to meet, which is
M1's F9/BLOCKER-T7b-1 lesson.

**The vocabulary is `core/runner.py`'s** (T2) — `RunnerHandle`, `SessionSpec`,
`PaneState`, `ProcState`, `RunnerRefusal`. Nothing is redefined here.

**Every member may raise `RunnerRefusal` and nothing else.** A caller has two
cases — a value, or one refusal — rather than an open set of driver exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from shepherd.core.runner import PaneState, ProcState, RunnerHandle, SessionSpec


class ByteStream(Protocol):
    """A terminal stream: the chunks, and the way to stop them.

    Deliberately two members. A driver that can only hand back a file-like object
    still satisfies it, and the richer framing — `TerminalFrame`'s `closed`
    reason (E-M3-29) — is composed one layer up rather than demanded here.
    """

    def chunks(self) -> Iterator[bytes]:
        """Frames, in order, until the stream closes."""
        ...

    def close(self) -> None:
        """Stop reading. Idempotent: closing a closed stream is not an error."""
        ...


@dataclass(frozen=True)
class PaneRef:
    """One owned pane, as the driver can see it without classifying the screen.

    The session id is carried beside the name rather than sliced back out of it:
    the name is `shepherd_<id>` by construction, and every caller re-deriving that
    by string surgery is a second copy of `tmux_cmd.session_name`, wrong the first
    time the prefix moves.

    `pane_pid` is `None` when the driver could not read it — a value, never a
    guess (principle 5) — and `dead` is the pane's own flag, not an inference
    from the pid.
    """

    session_name: str
    session_id: str
    pane_pid: int | None
    dead: bool


class Runner(Protocol):
    """Where an owned session's terminal lives, and what may be done to it.

    §6's eight members plus `pane()` and `list_owned_panes()` (N11, ADR-M3-4),
    plus the two the router decided during M3: `clear_input` (T13-2) and
    `attached_clients` (BLOCKER-T1-3).

    `list_owned_panes` is the tenth and it exists because `MAX_TOTAL_OWNED_SESSIONS`
    counts **panes**: a stored row whose pane is gone is not a session holding a
    slot, so the cap can only be read from the driver. The eleventh and twelfth
    are both named for what they **mean** rather than for what they press or
    read, which is the rule `interrupt` set: a seam that spoke keys or format
    strings would let any string reach the driver (T8-3).
    """

    def start(self, spec: SessionSpec) -> RunnerHandle:
        """Spawn the session's process in a new pane and return where it lives."""
        ...

    def attach(self, handle: RunnerHandle) -> ByteStream:
        """Follow the pane's output from now on."""
        ...

    def snapshot(self, handle: RunnerHandle, scrollback: int) -> bytes:
        """`scrollback` rows of history **plus the visible pane**, as bytes.

        T9-1, decided: the argument is a **depth**, not a length. The prose used
        to say "the last `lines` rendered rows" while the driver asked for that
        much scrollback *and* got the whole screen with it — measured live,
        `snapshot(handle, 40)` returned **45** rows on a 45-row pane — and
        acceptance clause 10 pins the driver's form, not the row count ("the
        bytes the real capture with a scrollback depth of 2000 returned"). So the
        driver was right and the prose was wrong.

        **No caller may derive a row count from the argument.** A diff between two
        snapshots or a fixed-height render has to measure the bytes it got back;
        the depth says how far back to reach, never how much comes out.

        Bytes, never decoded here: the escapes are the terminal's and this seam
        does not get to interpret them.
        """
        ...

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        """Send bytes to the pane. The *policy* of whether to send is not here."""
        ...

    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None:
        """Set the pane's geometry."""
        ...

    def interrupt(self, handle: RunnerHandle) -> None:
        """What a user pressing Ctrl-C would do — never a signal to a pid."""
        ...

    def terminate(self, handle: RunnerHandle) -> None:
        """End this one session. One session, never the server."""
        ...

    def probe(self, handle: RunnerHandle) -> ProcState:
        """What is known about the process behind the pane, at one observation."""
        ...

    def pane(self, handle: RunnerHandle) -> PaneState:
        """One classified observation of the screen (N11)."""
        ...

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        """Every pane this runner owns, live or dead — the cap's population (N11)."""
        ...

    def attached_clients(self, handle: RunnerHandle) -> int:
        """How many terminal clients are attached to this pane **right now**.

        The twelfth member, and it exists because P3 captured the damage: with a
        human attached at a second client and typing, a programmatic writer's
        submit sent *the human's keystrokes inside Shepherd's own prompt*
        (`p3-concurrent-…/09-round3-submitted.txt`). tmux serialises one write;
        it does not serialise a sequence.

        A **count**, not a flag: "two people are watching" and "one is" are
        different facts about the same pane, and a boolean throws the difference
        away before a caller or a UI can use it.

        Named for its intent rather than for the listing it reads, exactly as
        `clear_input` and `interrupt` are — no driver vocabulary and no free-text
        format string crosses the seam.

        **It narrows a race; it does not close one.** A human can type between
        this observation and any later keystroke, and no arrangement of checks in
        this design closes that window — closing it needs an atomic
        read-modify-submit on the prompt, which the driver does not offer. A
        caller defers on a non-zero count and **counts the residual**; nothing
        here may be documented or tested as making a write safe.
        """
        ...

    def clear_input(self, handle: RunnerHandle) -> None:
        """Empty the input line, as a user clearing a half-typed prompt would.

        D45's clearing step, and the eleventh member (T13-2). It is **not**
        expressible through `write`: that member is the opaque byte channel, and
        the captured clearing step pressed a *named key* (`steps.log` l.7 of the
        M3 key-semantics gap-fill probe, with `01-after-raw-up.txt` ->
        `01b-after-ctrl-u.txt` showing the box going from a recalled prompt to
        empty — the capture folder is named after the model that produced it, so
        it is cited by file name rather than by path, T13-3). The byte form of the same
        control character is **not** captured, and K1 forbids asserting a shape
        no capture shows.

        Named for its **intent**, exactly as `interrupt` is: what it means, not
        what it presses. A generic key channel would put a free-text key name on
        the seam, which is T8-3's shape — a value reaching the driver with no
        closed set constraining it.

        **The clear is not a guarantee**: a caller re-reads the pane afterwards
        and only then decides, so a clear that did not work is a refusal rather
        than a message typed onto somebody's draft (DP10).
        """
        ...
