"""The one contract suite every `Runner` implementation passes (T5, T8, T9).

§14.2's rule applied to the seam M3 creates: a `Protocol` earns a `Scripted*`
double and **one** suite, and a new implementation is done when it passes the
suite that already exists. Two implementations run here — `LocalRunner` (the
tmux driver, T8) and `ScriptedRunner` (a concrete peer that answers from frozen
fixtures, never a base class) — and the point is that the seam has **one
meaning**, not two implementations that happen to work.

**The rows are written once.** `ROWS` is a table of assertion functions over the
`Runner` interface alone; `test_contract_row` runs every row against every
fixture-backed implementation, and the **live** lane runs the *same functions*
against a real tmux server on the throwaway socket `shepherd-m3-live`. That is
what keeps the fixtures honest: a `ScriptedTmux` that drifted from tmux would
pass the default lane and fail the live one.

**Real-server rows are skipped, never faked** — `test_hostplatform_contract.py`'s
shape, where `MacHost`'s real-host rows skip on Linux rather than being answered
by a fixture pretending to be a Mac. A skip that silently becomes the normal case
is a suite that tests nothing, so `test_the_server_rows_skip_with_a_visible_reason`
asserts the **count** of skipped rows and that each reason names the socket.

**Case counts are asserted, not assumed** (T6's `DEGRADED_CASES`, T8's 13585):
`test_the_contract_loop_runs_the_case_count_it_states` collects this module in a
subprocess and asserts the ids it found, so a generator change cannot shrink the
loop to zero in silence.

Every fixture value is re-keyed from a real capture named in `data-schemas.md`:
the listing rows from `14-list-sessions-after-sigterm.txt` (§ line 2692) and the
screen from `01-trust-dialog.ansi` (§ line 2107).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.core.anomalies import Anomaly
from shepherd.core.runner import (
    PaneFields,
    PaneKind,
    PaneState,
    ProcState,
    RunnerHandle,
    RunnerRefusal,
    SessionSpec,
)
from shepherd.host.base import DetachedLaunch
from shepherd.runner.base import PaneRef, Runner
from shepherd.runner.local import CommandResult, LocalRunner, make_run_argv
from shepherd.runner.pane import FIELD_SEPARATOR, parse_pane_fields, read_pane
from shepherd.runner.tmux_cmd import (
    DEFAULT_SOCKET,
    FORBIDDEN_SOCKET,
    VERSION_ARGV,
    check_tmux_argv,
    permitted_commands,
    permitted_sockets,
    session_name,
)
from shepherd.testkit.scripted_runner import ScriptedRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = REPO_ROOT / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z"

#: Two owned sessions, so "terminate ends **one** session" has something to be
#: true about. Crockford ULIDs: `tmux_cmd.session_name` refuses anything else.
SESSION_A = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
SESSION_B = "01JBQ8Z9XKME5RT3VWNY6P0DFH"
NAME_A = f"shepherd_{SESSION_A}"
NAME_B = f"shepherd_{SESSION_B}"

#: `^shepherd_<ULID>$` — the population `MAX_TOTAL_OWNED_SESSIONS` counts (N11).
OWNED_NAME_RE = re.compile(r"^shepherd_[0-9A-HJKMNP-TV-Z]{26}$")

#: `probe_a` of `14-list-sessions-after-sigterm.txt` (data-schemas.md l.2692),
#: re-keyed to an owned name: alive, alternate screen on, 160x45, pid 4041880.
#: The seven `PANE_FORMAT` fields, in `PANE_FORMAT` order.
ALIVE_TAIL = "1|0||✳ shp-probe-title-1|160|45|4041880"
#: `01-trust-dialog-fmt.txt`: the trust screen is **not** on the alternate screen.
TRUST_TAIL = "0|0||✳ Claude Code|160|45|4041880"

#: The `capture-pane -e -p` bytes of the workspace-trust screen (data-schemas.md
#: l.2107). Real ANSI, never decoded by a runner.
TRUST_SCREEN = (RUN / "01-trust-dialog.ansi").read_bytes()

#: What tmux itself says when the server is gone (`socket-precheck.txt` l.1) and
#: when a session is (`15-list-sessions-after-kill.txt` is the after-state).
NO_SERVER_STDERR = b"no server running on /tmp/tmux-0/shepherd-runner"

#: A payload chosen to break every normalisation a double might be tempted by: a
#: leading dash (C4), a NUL, a bare CR, a byte that is not UTF-8 at all, and no
#: trailing newline.
BYTE_PAYLOAD = b"-\x00\r\xffnot utf-8 \xe2\x9c\xb3"

NOW = "2026-09-17T10:00:00.000000+00:00"

LIVE_SOCKET = "shepherd-m3-live"
#: What the exec site in this suite may ever contact. `permitted_sockets` refuses
#: the user's own socket at construction, so this line is itself a check.
PERMITTED = permitted_sockets(DEFAULT_SOCKET, LIVE_SOCKET)

#: T8-3's command allow-list for this exec site. `cat` is the runner's own
#: (`pipe-pane -o -t <target> 'cat >> <sink>'`) and is the only program this
#: product composes into a tmux command argument.
COMMANDS = permitted_commands("cat")
#: Set by `test_the_server_rows_skip_with_a_visible_reason`'s subprocess so the
#: skip path is exercised deterministically, with no tmux anywhere near it.
NO_SERVER_ENV = "SHEPHERD_CONTRACT_NO_SERVER"

#: The clearing step's key name, `steps.log` l.7 (`send-keys -t =shepherd_kc: C-u`).
#: Spelled here rather than imported from the driver: a suite that read the key
#: out of the module under test would agree with whatever that module sends.
CLEAR_KEY = "C-u"

#: The interrupt's key name (D43: `Escape`, never a signal). Spelled here for the
#: same reason `CLEAR_KEY` is: a suite that read the key out of the module under
#: test would agree with whatever that module sends.
INTERRUPT_KEY = "Escape"


def spec_for(session_id: str) -> SessionSpec:
    return SessionSpec(
        session_id=session_id,
        engine_session_id="71757dd1-5375-4801-b467-7898a0bc1194",
        cwd=str(REPO_ROOT),
        brief=None,
        title=None,
        model=None,
        effort=None,
        engine="stub",
        runner="contract",
        env={},
    )


def pane_fields(tail: str) -> PaneFields:
    return parse_pane_fields(tail)


def trust_pane() -> PaneState:
    """One real classified observation, from the real capture."""
    anomalies: list[Anomaly] = []
    return read_pane(TRUST_SCREEN, pane_fields(TRUST_TAIL), anomalies)


# ----- the two fixture-backed implementations ---------------------------------


class ScriptedTmux:
    """A scripted `run_argv`: the fixture `LocalRunner` is driven against.

    **Not a mock with expectations** — it records every argv it was handed and
    answers from a table of pane rows, so a test can say "the operation reached
    its step" *before* it says "and nothing else happened". The table changes
    only the way tmux's does: `new-session` adds a row, `kill-session` removes
    one (E-M3-17 — the row and its exit status go together), and a verb aimed at
    a session that is not in the table exits non-zero, which is what turns into
    `RunnerRefusal` one layer up.

    The live lane runs the same contract rows against the real thing, so a drift
    between this table and tmux is caught there rather than believed here.
    """

    #: What `list-clients -t <target>` prints for a pane a human is attached to,
    #: one line per client — tmux's own shape. **Two**, so a driver that answered
    #: "is anyone attached" as a boolean, or with a hardcoded 1, fails the row
    #: that reads the count (BLOCKER-T1-3).
    CLIENT_LINES: tuple[str, ...] = (
        "/dev/pts/3: 0 [180x45 xterm-256color] (utf8)",
        "/dev/pts/7: 0 [80x24 screen-256color] (utf8)",
    )

    def __init__(self, rows: dict[str, str]) -> None:
        self.rows = dict(rows)
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> CommandResult:
        self.calls.append(list(argv))
        # An argv that lost its socket is *answered*, not crashed on: the row's
        # own `check_tmux_argv` is what must refuse it, and a harness that raised
        # first would turn a guard failure into a harness failure (M10).
        words = argv[argv.index(DEFAULT_SOCKET) + 1 :] if DEFAULT_SOCKET in argv else argv[1:]
        verb = words[0]
        named = self._named(words)
        if verb == "list-sessions":
            if not self.rows:
                return CommandResult(rc=1, stdout=b"", stderr=NO_SERVER_STDERR)
            listing = "".join(
                f"{name}{FIELD_SEPARATOR}{tail}\n" for name, tail in sorted(self.rows.items())
            )
            return CommandResult(rc=0, stdout=listing.encode("utf-8"), stderr=b"")
        if verb == "new-session":
            self.rows[words[words.index("-s") + 1]] = ALIVE_TAIL
            return CommandResult(rc=0, stdout=b"", stderr=b"")
        if named is not None and named not in self.rows:
            return CommandResult(
                rc=1, stdout=b"", stderr=f"can't find session: {named}".encode("utf-8")
            )
        if verb == "kill-session" and named is not None:
            del self.rows[named]
        if verb == "capture-pane":
            return CommandResult(rc=0, stdout=TRUST_SCREEN, stderr=b"")
        if verb == "list-clients":
            listed = "".join(f"{line}\n" for line in self.CLIENT_LINES)
            return CommandResult(rc=0, stdout=listed.encode("utf-8"), stderr=b"")
        return CommandResult(rc=0, stdout=b"", stderr=b"")

    @staticmethod
    def _named(words: list[str]) -> str | None:
        """The session a `-t =<name>:` target addresses, if the argv has one."""
        if "-t" not in words:
            return None
        return words[words.index("-t") + 1][1:-1]


def key_presses(calls: list[list[str]], key: str) -> int:
    """How many `send-keys` argvs pressed `key` **by name** rather than as bytes.

    The observation channel for a key press is the argv it went out as, and the
    `-H` exclusion is the point: `send-keys -H 15` would deliver the same control
    character and is **not** the captured form (`steps.log` l.7), so a driver
    that "cleared" through the byte channel counts zero here.
    """
    return sum(
        1 for argv in calls if "send-keys" in argv and "-H" not in argv and key in argv
    )


def hex_writes(calls: list[list[str]]) -> tuple[bytes, ...]:
    """Every `send-keys -H` payload, reassembled from the argv it went out as.

    The observation channel for a driver is the argv it built: `write` is
    byte-exact iff the hex words decode back to what the caller handed over.
    """
    found: list[bytes] = []
    for argv in calls:
        if "send-keys" in argv and "-H" in argv:
            words = argv[argv.index("-t") + 2 :]
            found.append(bytes(int(word, 16) for word in words))
    return tuple(found)


@dataclass(frozen=True)
class Implementation:
    """One driver, plus the two channels a contract row observes it through."""

    name: str
    runner: Runner
    #: What the pane was actually handed, in order.
    writes: Callable[[], tuple[bytes, ...]]
    #: Every argv it caused a process to be started with. Empty for a fixture —
    #: and the suite asserts that emptiness rather than skipping past it.
    argvs: Callable[[], tuple[tuple[str, ...], ...]]
    #: How many times the input line was cleared through the eleventh member
    #: (T13-2). A third observation channel beside `writes` and `argvs`, for the
    #: same reason `writes` is one: "it did not write" is satisfied just as well
    #: by a member that did nothing, so the row asserts the clear **arrived**
    #: before it asserts no payload followed it.
    cleared: Callable[[], int]
    #: How many times the pane was interrupted, observed on the channel each
    #: driver really uses — the `send-keys <Escape>` argv for `LocalRunner`, the
    #: recorded member name for `ScriptedRunner`. A fourth channel for the third
    #: channel's reason: `probe(...).alive is True` is satisfied exactly as well
    #: by an interrupt that never ran, and the contract suite stayed green with
    #: `ScriptedRunner.interrupt` gutted to `return None` until this existed.
    interrupts: Callable[[], int]
    #: How many terminal clients the fixture has attached to the pane. The value
    #: is scripted, so the row asserts the seam **reports what the driver saw**
    #: rather than a constant (BLOCKER-T1-3).
    clients: int
    answers_from_a_fixture: bool


def build_local(anomalies: list[Anomaly] | None = None) -> Implementation:
    """`LocalRunner` over a scripted `run_argv`. No tmux server anywhere."""
    sink = collected(anomalies)
    scripted = ScriptedTmux({})
    runner = LocalRunner(
        socket=DEFAULT_SOCKET,
        run_argv=scripted,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: NOW,
        # `SpawnArgv` (T10-R2): the engine is told how many bytes of ours precede
        # its words, because tmux's ceiling is on the whole client-to-server
        # message. A pane running `cat` needs none of that and says so.
        spawn_argv=lambda spec, *, frame_bytes: ["cat"],
        record_anomaly=sink,
        sink_dir=Path("/tmp/shepherd-contract-sinks"),
    )
    return Implementation(
        name="LocalRunner",
        runner=runner,
        writes=lambda: hex_writes(scripted.calls),
        argvs=lambda: tuple(tuple(argv) for argv in scripted.calls),
        cleared=lambda: key_presses(scripted.calls, CLEAR_KEY),
        interrupts=lambda: key_presses(scripted.calls, INTERRUPT_KEY),
        clients=len(ScriptedTmux.CLIENT_LINES),
        answers_from_a_fixture=False,
    )


def build_scripted(anomalies: list[Anomaly] | None = None) -> Implementation:
    """`ScriptedRunner` over the same captures, answering from fixtures."""
    runner = ScriptedRunner(
        panes=(trust_pane(),),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=TRUST_SCREEN,
        clients=len(ScriptedTmux.CLIENT_LINES),
    )
    return Implementation(
        name="ScriptedRunner",
        runner=runner,
        writes=lambda: tuple(runner.writes),
        argvs=lambda: (),
        cleared=lambda: runner.calls.count("clear_input"),
        interrupts=lambda: runner.calls.count("interrupt"),
        clients=len(ScriptedTmux.CLIENT_LINES),
        answers_from_a_fixture=True,
    )


def collected(anomalies: list[Anomaly] | None) -> Callable[[Anomaly], None]:
    sink = anomalies if anomalies is not None else []
    return sink.append


BUILDERS: tuple[Callable[[], Implementation], ...] = (build_local, build_scripted)
BUILDER_IDS: tuple[str, ...] = ("LocalRunner", "ScriptedRunner")


@pytest.fixture(params=BUILDERS, ids=BUILDER_IDS)
def implementation(request: pytest.FixtureRequest) -> Iterator[Implementation]:
    build = request.param
    yield build()


# ----- the rows ---------------------------------------------------------------


def until(predicate: Callable[[], bool], seconds: float = 5.0) -> bool:
    """Poll a screen that a real pty fills asynchronously. Instant for a fixture."""
    deadline = time.monotonic() + seconds
    while True:
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def started(impl: Implementation) -> tuple[RunnerHandle, RunnerHandle]:
    """Two owned sessions, through the seam, on every implementation."""
    return impl.runner.start(spec_for(SESSION_A)), impl.runner.start(spec_for(SESSION_B))


def row_handle_round_trip(impl: Implementation) -> None:
    """A handle names the session it started and survives the store's TEXT column."""
    handle, _ = started(impl)
    assert handle.session_name == NAME_A
    assert handle.runner.strip() != ""
    assert handle.socket.strip() != ""
    assert RunnerHandle.from_text(handle.to_text()) == handle


def row_write_is_byte_exact(impl: Implementation) -> None:
    """Arrival first, then exactness: a count that never grew proves nothing."""
    handle, _ = started(impl)
    before = impl.writes()
    impl.runner.write(handle, BYTE_PAYLOAD)
    after = impl.writes()
    assert len(after) == len(before) + 1, "the write never reached the pane at all"
    assert after[-1] == BYTE_PAYLOAD
    impl.runner.write(handle, b"second")
    assert impl.writes()[-2:] == (BYTE_PAYLOAD, b"second")


def row_interrupt_is_not_a_write(impl: Implementation) -> None:
    """D43/N14: Ctrl-C is a key, never a signal — and never a stray `Enter`.

    **Arrival first, and it is an arrival.** This row used to say "arrival
    first" in a *comment* and then assert `probe(...).alive is True`, which an
    interrupt that never ran satisfies exactly: the contract suite stayed green
    with `ScriptedRunner.interrupt` gutted to `return None`. The count on the
    fourth observation channel is the thing that moves only if the member
    actually did something — the same reason `cleared` exists (T13-2).
    """
    handle, _ = started(impl)
    before_writes = impl.writes()
    before_interrupts = impl.interrupts()
    impl.runner.interrupt(handle)
    assert impl.interrupts() == before_interrupts + 1, "the interrupt never reached the pane"
    # …and only then the absence, plus the pane still being there: an interrupt
    # is not a terminate.
    assert impl.runner.probe(handle).alive is True
    assert impl.writes() == before_writes, "interrupt delivered a payload to the pane"


def row_pane_is_total(impl: Implementation) -> None:
    """`pane()` answers with one of the six kinds, twice running, for a live pane."""
    handle, _ = started(impl)
    for _ in range(2):
        state = impl.runner.pane(handle)
        assert isinstance(state, PaneState)
        assert state.kind in set(PaneKind)
        assert isinstance(state.fields, PaneFields)
        assert state.fields.width > 0 and state.fields.height > 0
        # Principle 5 on the screen: a draft and a placeholder are separate
        # values, so neither can be mistaken for the other.
        assert isinstance(state.input_text, str)
        assert state.ghost_text is None or isinstance(state.ghost_text, str)


def row_unknown_target_is_refused(impl: Implementation) -> None:
    """One refusal, never a driver exception — and an unknown pid is a *value*."""
    started(impl)
    stranger = RunnerHandle(runner="x", socket="x", session_name="shepherd_" + "Z" * 26)
    for member in (
        lambda: impl.runner.pane(stranger),
        lambda: impl.runner.snapshot(stranger, 10),
        lambda: impl.runner.write(stranger, b"x"),
        lambda: impl.runner.terminate(stranger),
    ):
        with pytest.raises(RunnerRefusal):
            member()
    # `probe` is the one member that answers rather than refuses: "gone" is a
    # fact about the pane, and a caller polling a session it just terminated is
    # the normal path (E-M3-17), not an error.
    gone = impl.runner.probe(stranger)
    assert gone.alive is False
    assert gone.observed_at.strip() != ""


def row_owned_panes_are_the_cap_population(impl: Implementation) -> None:
    """N11: the cap counts panes, so every entry is a pane with a readable name."""
    handle_a, handle_b = started(impl)
    refs = impl.runner.list_owned_panes()
    names = {ref.session_name for ref in refs}
    assert {handle_a.session_name, handle_b.session_name} <= names
    assert len(refs) == len(names), "the population has a duplicate"
    for ref in refs:
        assert isinstance(ref, PaneRef)
        assert OWNED_NAME_RE.fullmatch(ref.session_name), ref.session_name
        # The id travels beside the name, so nobody re-derives it by slicing.
        assert session_name(ref.session_id) == ref.session_name
        assert ref.pane_pid is None or isinstance(ref.pane_pid, int)
        assert isinstance(ref.dead, bool)


def row_terminate_ends_one_session(impl: Implementation) -> None:
    """K6/K16: one session, never the server — the 2026-09-12 incident, as a row."""
    handle_a, handle_b = started(impl)
    before = {ref.session_name for ref in impl.runner.list_owned_panes()}
    assert {handle_a.session_name, handle_b.session_name} <= before

    impl.runner.terminate(handle_a)

    after = {ref.session_name for ref in impl.runner.list_owned_panes()}
    assert handle_a.session_name not in after
    assert handle_b.session_name in after, "terminate took the other session with it"
    assert impl.runner.probe(handle_a).alive is False
    # …and the surviving session is still answerable, which is what "the server
    # is still there" means from the seam's side.
    assert impl.runner.pane(handle_b).kind in set(PaneKind)


def row_snapshot_is_undecoded_bytes(impl: Implementation) -> None:
    """Bytes, never text, and the escapes survive the driver.

    The pane is **made** to carry an escape rather than assumed to: the first run
    of this row against a real server found a blank `cat` pane with no ANSI on it
    at all, which would have made an "escapes survive" clause pass by accident
    everywhere the fixture happened to be colourful (T9-1).

    What `lines` means is *not* asserted here: the Protocol says "the last
    `lines` rendered rows" and `LocalRunner` sends `capture-pane -S -<lines>`,
    which is `lines` of **scrollback** plus the visible screen — 45 rows came
    back for `lines=40` on a real pane. The seam has not decided which it is, so
    this suite does not pretend it has (T9-1 in the blockers file).
    """
    handle, _ = started(impl)
    out = impl.runner.snapshot(handle, 40)
    assert isinstance(out, bytes)
    assert not isinstance(out, str)

    # The carriage return matters: without it the line discipline echoes the ESC
    # as a literal `^[` and the program never writes the real byte out, so the
    # pane would carry no escape and the clause would be vacuous on a real pty.
    impl.runner.write(handle, b"\x1b[31mshepherd-contract\x1b[0m\r")
    assert until(lambda: b"\x1b[" in impl.runner.snapshot(handle, 45)), (
        "the escape sequences did not survive the driver"
    )


def row_attach_closes_idempotently(impl: Implementation) -> None:
    """Two members, and closing a closed stream is not an error."""
    handle, _ = started(impl)
    stream = impl.runner.attach(handle)
    assert callable(stream.chunks) and callable(stream.close)
    stream.close()
    stream.close()
    # A closed stream terminates rather than blocking: this line hangs forever if
    # `close()` did not actually stop the reader.
    assert isinstance(list(stream.chunks()), list)


def row_a_fixture_starts_no_process(impl: Implementation) -> None:
    """The argv shape — and the fixture's emptiness is asserted, not skipped past.

    A double that had quietly grown toward a real runner would start showing
    argvs here, which is §14.2's `Out-of-Scope Drift` made checkable. For a real
    driver the same row asserts the opposite *and* runs every argv it built back
    through the guard (K6): `-L` present, never the user's socket, exact targets.
    """
    handle, _ = started(impl)
    impl.runner.write(handle, b"arrived")
    assert impl.writes()[-1] == b"arrived", "the row asserts absence before arrival"

    argvs = impl.argvs()
    if impl.answers_from_a_fixture:
        assert argvs == (), "a Scripted* answers from a fixture; it starts nothing"
        return
    assert argvs != (), "a real driver that issued no argv did nothing at all"
    for argv in argvs:
        assert FORBIDDEN_SOCKET not in argv
        check_tmux_argv(list(argv), permitted=PERMITTED, commands=COMMANDS)


def row_clear_input_presses_a_key_and_writes_nothing(impl: Implementation) -> None:
    """T13-2: the eleventh member **presses the captured key**, never a payload.

    Arrival before absence, and the arrival is not "it returned": `cleared()`
    counts a real `send-keys … C-u` for a driver and a recorded call for a
    fixture, so a `clear_input` that did nothing at all fails the first
    assertion rather than passing the second. **Goes red** if the clear is
    implemented through `write` (`send-keys -H 15` is not the captured form),
    if a fixture stops recording it, or if it grows a trailing `Enter`.
    """
    handle, _ = started(impl)
    impl.runner.write(handle, b"draft")
    before_writes = impl.writes()
    assert before_writes[-1] == b"draft", "the row asserts absence before arrival"
    before_clears = impl.cleared()

    impl.runner.clear_input(handle)

    assert impl.cleared() == before_clears + 1, "the clear never reached the pane at all"
    assert impl.writes() == before_writes, "the clear delivered a payload to the pane"
    # Twice is twice: a driver that remembered "already cleared" would be
    # deciding policy the caller owns (the re-read is what decides, DP10).
    impl.runner.clear_input(handle)
    assert impl.cleared() == before_clears + 2


def row_attached_clients_is_the_count_the_driver_saw(impl: Implementation) -> None:
    """BLOCKER-T1-3: how many terminal clients are attached to this pane, now.

    P3 captured the defect this answers — a human typing at `tmux attach` while
    Shepherd wrote, whose keystrokes ended up **inside the prompt Shepherd
    submitted**. The member is a *count*, not a flag: two clients and one client
    are different facts about the same pane, and the fixtures script **two** so a
    driver answering `1`, `True` or `0` cannot pass.

    It is a read: `writes` and `cleared` are both unchanged across it.
    """
    handle, _ = started(impl)
    before_writes, before_clears = impl.writes(), impl.cleared()

    count = impl.runner.attached_clients(handle)

    assert isinstance(count, int) and not isinstance(count, bool)
    assert count == impl.clients
    assert count >= 0
    assert impl.writes() == before_writes, "observing the clients wrote to the pane"
    assert impl.cleared() == before_clears, "observing the clients cleared the input line"


def row_snapshot_scrollback_is_a_depth_not_a_row_count(impl: Implementation) -> None:
    """T9-1, decided: the argument is tmux's `-S` **scrollback depth**.

    The result is that much scrollback **plus the whole visible pane**, so its row
    count is not derivable from the argument and no caller may do arithmetic on
    it — measured live at `snapshot(handle, 40)` returning 45 rows on a 45-row
    pane, and pinned by acceptance clause 10's `capture-pane -e -p -S -2000`.

    **Goes red** on either implementation reverting to a flat row count: a depth
    of **0** is "no scrollback, just the screen" and still returns the screen,
    while `rows[-0:]`/`rows[-lines:]` returns nothing or exactly the argument.
    """
    handle, _ = started(impl)
    shallow = impl.runner.snapshot(handle, 0)
    assert shallow != b"", "a depth of 0 returned nothing, so it was read as a row count"
    deep = impl.runner.snapshot(handle, 5)
    assert len(deep.splitlines()) >= len(shallow.splitlines())
    assert deep.endswith(shallow), "scrollback is added before the visible pane, never instead"

    if impl.answers_from_a_fixture:
        return
    # For a real driver the argument's meaning is visible in the argv it built:
    # it is handed to tmux as `-S -<depth>` and nothing trims the answer after.
    captures = [argv for argv in impl.argvs() if "capture-pane" in argv]
    depths = [argv[argv.index("-S") + 1] for argv in captures if "-S" in argv]
    assert depths[-2:] == ["-0", "-5"], depths


ROWS: tuple[Callable[[Implementation], None], ...] = (
    row_handle_round_trip,
    row_write_is_byte_exact,
    row_interrupt_is_not_a_write,
    row_pane_is_total,
    row_unknown_target_is_refused,
    row_owned_panes_are_the_cap_population,
    row_terminate_ends_one_session,
    row_snapshot_is_undecoded_bytes,
    row_attach_closes_idempotently,
    row_a_fixture_starts_no_process,
    row_clear_input_presses_a_key_and_writes_nothing,
    row_attached_clients_is_the_count_the_driver_saw,
    row_snapshot_scrollback_is_a_depth_not_a_row_count,
)
ROW_IDS: tuple[str, ...] = tuple(row.__name__.removeprefix("row_") for row in ROWS)

#: The loop's own size, stated. T6 used `DEGRADED_CASES = 10778` and T8 13585 for
#: the same reason: a generator change otherwise shrinks the loop to zero and
#: nothing goes red. `test_the_contract_loop_runs_the_case_count_it_states`
#: collects this module and asserts pytest agrees.
CONTRACT_ROWS = 13
CONTRACT_CASES = CONTRACT_ROWS * 2
#: The rows that need a server, plus the one live-only round-trip.
LIVE_CASES = CONTRACT_ROWS + 1


@pytest.mark.parametrize("row", ROWS, ids=ROW_IDS)
def test_contract_row(implementation: Implementation, row: Callable[[Implementation], None]) -> None:
    """Every row, against every implementation. One seam, one meaning."""
    row(implementation)


def test_the_contract_loop_runs_the_case_count_it_states() -> None:
    """The stated counts, read back out of pytest's own collection."""
    assert len(ROWS) == CONTRACT_ROWS
    assert len(set(ROW_IDS)) == CONTRACT_ROWS
    assert len(BUILDERS) == len(BUILDER_IDS) == 2
    assert CONTRACT_CASES == len(ROWS) * len(BUILDERS)

    collected = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__)),
            "--collect-only",
            # `addopts` already carries `-q`; without `-v` the collection prints
            # a count instead of the ids, and a count is what this test refuses
            # to take on trust.
            "-v",
            "-p",
            "no:cacheprovider",
            "-m",
            "live or not live",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        timeout=180,
    )
    assert collected.returncode == 0, collected.stdout.decode("utf-8", "replace")
    ids = collected.stdout.decode("utf-8", "replace").splitlines()
    assert sum("test_contract_row[" in line for line in ids) == CONTRACT_CASES
    assert sum("test_contract_row_against_a_real_server[" in line for line in ids) == CONTRACT_ROWS


# ----- §14.2's two rules about the double itself -------------------------------


def test_every_implementation_answers_every_protocol_member() -> None:
    """Ten members, read off `Runner` itself — never a hand-typed list.

    A hand-typed list stops covering a member the day the seam grows, which is
    §14.2's whole point and is how the tenth member (`list_owned_panes`) stays
    testable above the unit seam. **Goes red** when `Runner` gains a member and a
    double does not.
    """
    declared = {name for name in vars(Runner) if not name.startswith("_")}
    # Twelve since the two decided seam edits: `clear_input` (T13-2) and
    # `attached_clients` (BLOCKER-T1-3's caller-side precondition).
    assert len(declared) == 12, sorted(declared)

    for build in BUILDERS:
        impl = build()
        for name in sorted(declared):
            member = getattr(type(impl.runner), name, None)
            assert inspect.isfunction(member), f"{impl.name} does not answer {name}()"
            assert inspect.signature(member) == inspect.signature(
                getattr(Runner, name)
            ), f"{impl.name}.{name}() does not match the Protocol"


def test_scripted_runner_is_not_a_base_class() -> None:
    """§14.2: a `Scripted*` is a concrete peer — nothing in `src/` inherits from it."""
    assert ScriptedRunner.__subclasses__() == []

    src_root = Path(inspect.getfile(ScriptedRunner)).parents[1]
    inheritors: list[str] = []
    for module in sorted(src_root.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
                    if name == ScriptedRunner.__name__:
                        inheritors.append(f"{module.name}:{node.name}")
    assert inheritors == []


def test_every_write_is_recorded_byte_exact() -> None:
    """The double records what it was handed, not what it could make sense of.

    **Goes red** if `ScriptedRunner.write` normalises — decodes, strips, appends a
    newline, or copies into a different bytes object — because a driver with a
    real byte-mangling bug would then pass the suite this exists to be.
    """
    payloads: tuple[bytes, ...] = (
        b"",
        b"-",  # C4: a payload starting with a dash
        b"\x00",
        b"\r",
        b"\n",
        b"\r\n",
        b"\xff\xfe",  # not UTF-8 at all
        "✳ shp".encode("utf-8"),
        BYTE_PAYLOAD,
    )
    assert len(payloads) == 9

    impl = build_scripted()
    runner = impl.runner
    assert isinstance(runner, ScriptedRunner)
    handle = runner.start(spec_for(SESSION_A))
    for payload in payloads:
        runner.write(handle, payload)

    assert len(runner.writes) == len(payloads)
    assert tuple(runner.writes) == payloads
    for recorded, payload in zip(runner.writes, payloads):
        assert recorded is payload, "the double copied, so it could also have edited"


def test_the_scripted_runner_needs_none_of_local_runners_injected_fields() -> None:
    """T8-1, confirmed against the code rather than taken on faith.

    `LocalRunner` takes three injected fields beyond the plan's `Produces`
    because the argvs cannot be built without them. A fixture builds no argv, so
    it needs none — and this asserts the difference in both directions, so it
    cannot pass by the fields having vanished from `LocalRunner` too.
    """
    injected = {"spawn_argv", "sink_dir", "record_anomaly"}
    local_fields = {f.name for f in dataclasses.fields(LocalRunner)}
    scripted_fields = {f.name for f in dataclasses.fields(ScriptedRunner)}
    assert injected <= local_fields
    assert injected & scripted_fields == set()

    required = {
        f.name
        for f in dataclasses.fields(ScriptedRunner)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    }
    assert required == {"panes", "proc", "screen"}


# ----- the live lane: real-server rows, skipped rather than faked ---------------


def server_skip_reason() -> str | None:
    """Why the real-server rows cannot run here — visible, and never a fake.

    `test_hostplatform_contract.py` skips `MacHost`'s real-host rows on Linux
    rather than answering them from a fixture pretending to be a Mac. Same rule:
    a row that needs a server either gets one or says, in the skip reason, which
    socket it wanted.
    """
    if os.environ.get(NO_SERVER_ENV):
        return (
            f"no server on {LIVE_SOCKET} (forced by {NO_SERVER_ENV}): "
            "real-server rows are skipped, never faked"
        )
    if shutil.which(VERSION_ARGV[0]) is None:
        return (
            f"no multiplexer binary on this host, so no server on {LIVE_SOCKET}: "
            "real-server rows are skipped, never faked"
        )
    return None


@pytest.fixture(scope="module")
def live_server() -> Iterator[Callable[[list[str]], CommandResult]]:
    """One real server on the throwaway socket, and a teardown bounded to it.

    CLAUDE.md rules 1-3: `-L` on **every** invocation, teardown included, and the
    socket can never be `shepherd` — `permitted_sockets` refuses that name at
    construction and `check_tmux_argv` refuses it again at the exec site.
    """
    reason = server_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    # T8-3 gave `make_run_argv` a **required** `commands` allow-list, and this
    # call site was missed because it is `live`-marked: the default run never
    # reaches it, so the `TypeError` waited here for `pytest -m live` instead of
    # failing the moment the signature moved. `COMMANDS` is `cat` alone — this
    # fixture starts a bare server and composes no engine.
    run_argv = make_run_argv(permitted_sockets(LIVE_SOCKET), COMMANDS)
    try:
        yield run_argv
    finally:
        run_argv([VERSION_ARGV[0], "-L", LIVE_SOCKET, "kill-server"])


@pytest.fixture
def live_implementation(
    live_server: Callable[[list[str]], CommandResult], tmp_path: Path
) -> Iterator[Implementation]:
    """A fresh `LocalRunner` on the live socket; its panes go away with it."""
    calls: list[list[str]] = []

    def recording(argv: list[str]) -> CommandResult:
        calls.append(list(argv))
        return live_server(argv)

    runner = LocalRunner(
        socket=LIVE_SOCKET,
        run_argv=recording,
        launch=DetachedLaunch(prefix=(), mechanism="none", detail="", verified=True),
        now=lambda: NOW,
        # `SpawnArgv` (T10-R2): the engine is told how many bytes of ours precede
        # its words, because tmux's ceiling is on the whole client-to-server
        # message. A pane running `cat` needs none of that and says so.
        spawn_argv=lambda spec, *, frame_bytes: ["cat"],
        record_anomaly=collected(None),
        sink_dir=tmp_path,
    )
    runner.ensure_server()
    impl = Implementation(
        name="LocalRunner@live",
        runner=runner,
        writes=lambda: hex_writes(calls),
        argvs=lambda: tuple(tuple(argv) for argv in calls),
        cleared=lambda: key_presses(calls, CLEAR_KEY),
        interrupts=lambda: key_presses(calls, INTERRUPT_KEY),
        # A detached server has no client attached, and that **0** is the real
        # answer from the real binary rather than a fixture's: the live lane is
        # what would catch `list-clients` not meaning what this suite says.
        clients=0,
        answers_from_a_fixture=False,
    )
    try:
        yield impl
    finally:
        for ref in runner.list_owned_panes():
            runner.terminate(RunnerHandle(runner="local", socket=LIVE_SOCKET, session_name=ref.session_name))


@pytest.mark.live
@pytest.mark.parametrize("row", ROWS, ids=ROW_IDS)
def test_contract_row_against_a_real_server(
    live_implementation: Implementation, row: Callable[[Implementation], None]
) -> None:
    """The **same rows**, against a real server. This is what keeps the fixtures honest."""
    row(live_implementation)


@pytest.mark.live
def test_a_payload_written_to_a_real_pane_comes_back_byte_exact(
    live_implementation: Implementation,
) -> None:
    """`send-keys -H` into a real `cat`, read back off the real screen."""
    handle = live_implementation.runner.start(spec_for(SESSION_A))
    live_implementation.runner.write(handle, b"shepherd-contract\r")
    deadline = time.monotonic() + 5.0
    seen = b""
    while time.monotonic() < deadline:
        seen = live_implementation.runner.snapshot(handle, 45)
        if b"shepherd-contract" in seen:
            break
        time.sleep(0.1)
    assert b"shepherd-contract" in seen, seen[-400:]


def test_the_server_rows_skip_with_a_visible_reason() -> None:
    """The skip **count**, asserted — a skip that became normal tests nothing.

    Runs this module's live lane in a subprocess with no server available, and
    asserts every one of the real-server rows skipped, with a reason naming the
    socket it wanted. Deterministic: it forces the no-server branch rather than
    depending on what is running on this host.
    """
    environment = dict(os.environ, **{NO_SERVER_ENV: "1"})
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(Path(__file__)),
            "-m",
            "live",
            "-rs",
            "-p",
            "no:cacheprovider",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        env=environment,
        timeout=180,
    )
    output = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, output
    assert f"{LIVE_CASES} skipped" in output, output
    assert LIVE_SOCKET in output, output
    assert "skipped, never faked" in output, output
    assert " failed" not in output, output
