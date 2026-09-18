"""`ScriptedRunner` — the `Runner` seam's `Scripted*` double (§14.2, D36).

A **concrete peer** of `LocalRunner`, never a base class: nothing inherits from
it, and every answer comes from the frozen fixtures it was constructed with — a
scripted `PaneState` sequence, one `ProcState`, one screen, and the panes it
owns. Every payload it is handed is recorded **byte for byte**.

**It is not a mock with call expectations.** No `assert_called_with`, no script
of expected calls, no way to fail a test by itself: `calls` is a record a test
may read, exactly as `writes` is. §14.2's `Scripted*` replays a script.

Ships with the package, in `testkit/` — deliberately not a layer in ADR-1's map.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from shepherd.core.runner import (
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
)
from shepherd.runner.base import ByteStream, PaneRef
from shepherd.runner.tmux_cmd import session_name

#: `RunnerHandle.runner`/`.socket`. A handle a scripted runner made says so, so a
#: stored one is never replayed against a real driver by accident — and the
#: socket is named rather than empty, because an empty field round-trips to
#: something no reader can act on.
RUNNER_NAME = "scripted"
SCRIPTED_SOCKET = "scripted"

#: The visible pane a fixture has, in rows. `160x45` is the geometry every
#: captured pane was observed at (`14-list-sessions-after-sigterm.txt`), and
#: `snapshot` needs it because its argument is a **scrollback depth**: the result
#: is that much scrollback *plus* the visible pane (T9-1).
SCRIPTED_VISIBLE_ROWS = 45


@dataclass
class _ScriptedStream:
    """The screen, once, and a `close()` that is idempotent."""

    screen: bytes
    closed: bool = False

    def chunks(self) -> Iterator[bytes]:
        if not self.closed:
            yield self.screen

    def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class ScriptedRunner:
    """The twelve `Runner` members, answered from fixtures.

    `panes` is a **sequence**: `pane()` walks it and the last entry repeats, so a
    test can script "trust dialog, then prompt ready" with no clock and no
    server. `LocalRunner`'s three extra injected fields (`spawn_argv`,
    `sink_dir`, `record_anomaly`, T8-1) have no counterpart here: nothing is
    spawned, nothing is piped to a file, and a fixture has no unknown to count.
    """

    panes: tuple[PaneState, ...]
    proc: ProcState
    screen: bytes
    owned_panes: tuple[PaneRef, ...] = ()
    visible_rows: int = SCRIPTED_VISIBLE_ROWS
    clients: int = 0
    writes: list[bytes] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    live: dict[str, PaneRef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for ref in self.owned_panes:
            self.live.setdefault(ref.session_name, ref)

    # ----- the fixture and the twelve members --------------------------------

    def _ref(self, handle: RunnerHandle, member: str) -> PaneRef:
        """The pane a handle names, or the one refusal a runner may raise.

        An unknown target is refused rather than defaulted: a fixture that
        invented a pane for any handle would let a caller pass this suite and
        fail against the real thing, which exits non-zero on an unknown target.
        """
        ref = self.live.get(handle.session_name)
        if ref is None:
            raise RunnerRefusal(
                f"no scripted pane named {handle.session_name!r}; this fixture knows "
                f"{sorted(self.live)!r}"
            )
        self.calls.append(member)
        return ref

    def start(self, spec: SessionSpec) -> RunnerHandle:
        name = session_name(spec.session_id)
        self.calls.append("start")
        self.live[name] = PaneRef(
            session_name=name, session_id=spec.session_id, pane_pid=self.proc.pid, dead=False
        )
        return RunnerHandle(runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=name)

    def attach(self, handle: RunnerHandle) -> ByteStream:
        self._ref(handle, "attach")
        return _ScriptedStream(screen=self.screen)

    def snapshot(self, handle: RunnerHandle, scrollback: int) -> bytes:
        """`scrollback` rows of history **plus the visible pane**, as bytes.

        T9-1, decided: the argument is the depth `LocalRunner` passes to the
        driver's own scrollback flag, so the row count of the answer is **not**
        derivable from it — a depth of 0 still returns the whole visible pane.
        This double used to return the last `scrollback` rows, which made the
        same argument mean two different things on the two implementations.
        """
        self._ref(handle, "snapshot")
        rows = self.screen.splitlines(keepends=True)
        return b"".join(rows[-(max(scrollback, 0) + self.visible_rows) :])

    def write(self, handle: RunnerHandle, data: bytes) -> None:
        """Recorded **exactly** as handed over: no decode, no strip, no newline.

        A double that normalised here would let a real byte-mangling driver pass
        the suite this member exists to make meaningful.
        """
        self._ref(handle, "write")
        self.writes.append(data)

    def attached_clients(self, handle: RunnerHandle) -> int:
        """The scripted client count — a fixture's answer, never an observation.

        `clients` is a constructor value so a test can script "a human is
        attached at a second terminal" (BLOCKER-T1-3) without a real client, and
        the default is `0`: a fixture nobody told about a human has none.
        """
        self._ref(handle, "attached_clients")
        return self.clients

    def clear_input(self, handle: RunnerHandle) -> None:
        """Recorded as a call, and **never** a write: `writes` stays untouched.

        The fixture does not edit its scripted panes: what the pane looks like
        after the clear is the next scripted `PaneState`, so a test can script
        the clear working *and* the clear failing (DP10's re-read) without the
        double deciding either outcome for it.
        """
        self._ref(handle, "clear_input")

    def resize(self, handle: RunnerHandle, cols: int, rows: int) -> None:
        self._ref(handle, "resize")

    def interrupt(self, handle: RunnerHandle) -> None:
        """What Ctrl-C would do — and never a write, so `writes` stays untouched."""
        self._ref(handle, "interrupt")

    def terminate(self, handle: RunnerHandle) -> None:
        """One session. The rest of the fixture's panes are still there."""
        ref = self._ref(handle, "terminate")
        del self.live[ref.session_name]

    def probe(self, handle: RunnerHandle) -> ProcState:
        """A pane the fixture no longer has is `alive=False`, never a refusal."""
        self.calls.append("probe")
        ref = self.live.get(handle.session_name)
        if ref is None:
            return replace(self.proc, alive=False, pid=None)
        return replace(self.proc, alive=not ref.dead, pid=ref.pane_pid)

    def pane(self, handle: RunnerHandle) -> PaneState:
        """The next scripted observation; the last one repeats."""
        seen = self.calls.count("pane")
        self._ref(handle, "pane")
        if not self.panes:
            raise RunnerRefusal("this fixture was given no pane state to replay")
        return self.panes[min(seen, len(self.panes) - 1)]

    def list_owned_panes(self) -> tuple[PaneRef, ...]:
        """The cap's population (N11) — the panes the fixture still has."""
        self.calls.append("list_owned_panes")
        return tuple(ref for _, ref in sorted(self.live.items()))
