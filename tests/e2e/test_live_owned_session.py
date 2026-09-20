"""T24's live lane: one real owned session on a real tmux socket, end to end.

`.venv/bin/pytest tests/e2e -m live -q`. Excluded from the default run by
`addopts = "-q -m 'not live'"`.

Five of M3's claims cannot be reached from `tmp_path`, and each is reached here:

1. a **real** workspace-trust dialog — it only appears in a directory the engine
   has never trusted, which is what a `tmp_path` workdir is;
2. a **real** exit code — it comes from a pane that really died, preserved by
   `remain-on-exit on` (E-M3-16), which is the half of G-M2-2 M2 left open;
3. a spawn that registers **exactly one row** with Shepherd's own hook block
   really installed — with the shipped `{}` settings file the second writer
   could never run and the assertion could not fail;
4. a pane that survives a **real** `controld` restart (D14, DP5);
5. the **bytes a real `capture-pane -e -p -S -2000` returns on this host**
   (P-M3-17). P-M3-10's deterministic test frames a checked-in file and compares
   it to the same file, which proves the framer does not mutate and nothing at
   all about what the capture returns here. tmux is 3.4 both in the captures and
   on this host; the **path** is what was unproven.

**Every test asserts arrival before it asserts a property.** The precedent is in
the plan: revision 1's `test_a_spawn_registers_exactly_one_row` asserted
`count == 1` in a world spawned with `--settings {}`, where the hook lane — the
second writer — could never run. It was a vacuous pass and the acceptance clause
it served was false. So each test below first shows that the real thing happened
(the dialog appeared, the pane died, a hook event landed, the capture returned
bytes) and only then asserts the property.

**The socket.** `shepherd-m3-live`, a throwaway matching `THROWAWAY_SOCKET_RE`.
`-L` is on every invocation because `tmux_argv` puts it at argv[1:3] and the
exec site refuses an argv without it — a command run inside tmux inherits `$TMUX`
and otherwise resolves to that session's own socket, which is §18's incident of
2026-09-12. The user's `aivisor`, `main` and `spike` are on `shepherd`; nothing
here names it, and `check_tmux_argv` would refuse the argv if it did.

**Isolation** is this lane's (F10/A16): the user's **real** `CLAUDE_CONFIG_DIR`,
because an isolated one has no credentials (`Not logged in`, rc=1); a throwaway
working directory; an explicit throwaway `--settings`; Shepherd's own XDG dirs
relocated. The accepted residue is the engine's own bookkeeping — a trust entry
in `~/.claude.json` and a transcript under `~/.claude/projects/-tmp-…`. Nothing
is deleted (K3).

**No timing assertion appears here.** Every wait is a ceiling on a condition and
fails naming the condition that never arrived. A live test that fails is
investigated, never retried into green.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from e2e.conftest import (
    LIVE_MODEL,
    LIVE_TMUX_SOCKET,
    NO_SERVER,
    TMUX_CALLS,
    Throwaway,
    lane_run_argv,
    live_socket_has_no_server,
    live_socket_listing,
    teardown_live_socket,
)

from shepherd.core.anomalies import Anomaly
from shepherd.core.runner import PaneKind, ProcState, RunnerHandle, SessionSpec
from shepherd.core.states import Origin, SessionState
from shepherd.core.stream import StreamEvent
from shepherd.daemons import controld
from shepherd.daemons.sessiond import INGEST_SOCKET_NAME
from shepherd.engines.claude_code.hooks_config import MANAGED_MARKER, inspect_hooks
from shepherd.host.detect import detect_host
from shepherd.orchestration.spawn import SpawnOutcome, SpawnRefused, spawn_owned_session
from shepherd.runner.local import LocalRunner
from shepherd.store.db import Store, open_store
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from shepherd.toolsurface.tools_terminal import SNAPSHOT_SCROLLBACK
from shepherd.web import ws

pytestmark = pytest.mark.live

#: A ceiling on **waiting for a condition**, never an assertion about how long
#: anything took. When it is reached the failure names the condition.
DIALOG_CEILING_S = 90.0
EXIT_CEILING_S = 60.0
HOOK_CEILING_S = 180.0
POLL_S = 0.5

#: The trust dialog's default selection is `No, exit` (`01-trust-dialog.ansi`
#: has `❯` on it), so a bare Enter refuses the folder and the engine leaves.
#: That is how this module gets a **real** exit code out of a pane that really
#: died, without inventing a signal or a kill (D43, N14).
ENTER = b"\r"

#: Bytes, not key names: the seam's write channel is opaque and `send-keys -H`
#: delivers them byte-exact. `\x1b[B` is Down — the key the 2026-09-14 probe
#: pressed before Enter to accept the trust dialog.
DOWN = b"\x1b[B"

#: The trust dialog's second option, verbatim from the screen this host renders,
#: and the `❯` that marks the selected row.
TRUST_YES = "Yes, I trust this folder"
SELECTED = "❯"

#: `-e K=V` pairs the lane needs: none. Named so the spawn's frame arithmetic is
#: visibly the shipped one and not something this module adjusted.
NO_ENV: dict[str, str] = {}


# ----- the lane's runner, built the way the composition root builds one -------


@dataclass(frozen=True)
class Lane:
    """One live spawn and everything the checks read from it."""

    store: Store
    runner: LocalRunner
    throwaway: Throwaway
    outcome: SpawnOutcome
    events: tuple[StreamEvent, ...]
    argv_from: int

    @property
    def handle(self) -> RunnerHandle:
        row = self.store.get_owned_session(self.outcome.session_id)
        assert row is not None and row.runner_handle is not None, (
            f"the spawn left no runner handle on {self.outcome.session_id}"
        )
        return row.runner_handle

    @property
    def spawn_event(self) -> StreamEvent:
        published = [event for event in self.events if event.session_id == self.outcome.session_id]
        assert published, "the spawn published nothing"
        return published[-1]

    def issued(self) -> tuple[tuple[str, ...], ...]:
        """Every tmux argv issued since this lane's spawn began."""
        return tuple(TMUX_CALLS[self.argv_from :])


def live_runner(throwaway: Throwaway, tmp_path: Path) -> LocalRunner:
    """A `LocalRunner` over real tmux on the throwaway socket.

    Shaped exactly like `toolsurface/compose.py::build_runner` — the same exec
    site, the same `permitted_commands`, the same detached launch — with one
    difference this lane owns: the spawn words come from `Throwaway.tui_argv`,
    which is the shipped `spawn_argv` with `--settings <throwaway>` appended and
    its size counted into the frame tmux measures.
    """
    anomalies: list[Anomaly] = []

    def words(spec: SessionSpec, *, frame_bytes: int) -> list[str]:
        return throwaway.tui_argv(spec.brief, spec=spec, frame_bytes=frame_bytes)

    return LocalRunner(
        socket=LIVE_TMUX_SOCKET,
        run_argv=lane_run_argv(LIVE_TMUX_SOCKET),
        launch=detect_host().detached_launch(),
        now=utc_stamp,
        spawn_argv=words,
        record_anomaly=anomalies.append,
        sink_dir=tmp_path / "sink",
    )


def utc_stamp() -> str:
    """The one clock this module reads, and it spells no assertion."""
    from shepherd.core.clock import utc_now

    return utc_now()


def await_value[T](probe: Callable[[], T | None], message: str, ceiling_s: float) -> T:
    """Poll until the probe answers, or fail naming what never arrived."""
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        found = probe()
        if found is not None:
            return found
        time.sleep(POLL_S)
    raise AssertionError(f"{message} (waited {ceiling_s}s)")


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


def spawn(store: Store, runner: LocalRunner, throwaway: Throwaway) -> Lane:
    """One spawn through the shipped sequence, into a never-trusted directory."""
    workspace = store.upsert_workspace("shepherd-m3-live", str(throwaway.workdir))
    events: list[StreamEvent] = []
    argv_from = len(TMUX_CALLS)
    outcome = spawn_owned_session(
        store=store,
        runner=runner,
        now=utc_stamp,
        sleep=time.sleep,
        publish=events.append,
        ensure_server=runner.ensure_server,
        engine_config_home=None,
        workspace_id=workspace.id,
        cwd=str(throwaway.workdir),
        brief=None,
        title=None,
        model=LIVE_MODEL,
        effort=None,
        parent_session_id=None,
        origin=Origin.ORCHESTRATOR,
    )
    # Arrival, before anything reads a property: the spawn is an outcome and not
    # a refusal. A refused spawn starts no pane, and every assertion below it
    # would then be about a session that does not exist.
    assert not isinstance(outcome, SpawnRefused), outcome
    assert isinstance(outcome, SpawnOutcome)
    return Lane(
        store=store,
        runner=runner,
        throwaway=throwaway,
        outcome=outcome,
        events=tuple(events),
        argv_from=argv_from,
    )


@pytest.fixture()
def lane(store: Store, throwaway: Throwaway, tmp_path: Path, tmux_live: str) -> Iterator[Lane]:
    """One spawned pane, torn down by `kill-session` whatever the test did."""
    assert tmux_live == LIVE_TMUX_SOCKET
    runner = live_runner(throwaway, tmp_path)
    started = spawn(store, runner, throwaway)
    try:
        yield started
    finally:
        try:
            runner.terminate(started.handle)
        except Exception:  # noqa: BLE001 — a pane tmux already forgot is not a failure
            pass


def press_enter_until_dead(runner: LocalRunner, handle: RunnerHandle) -> ProcState | None:
    """One press, then a **re-read** — T20's shipped idiom, for the other option.

    A key pressed at the first frame that classifies as the trust dialog is
    dropped by the TUI; T20 handles that for `Down` by re-reading until the pane
    itself shows `Yes` selected. `No, exit` is already the selected row, so the
    only confirmation available is the pane dying, and that is what is re-read.
    The 2026-09-14 probe avoided the problem by sleeping 15 s on the dialog
    first; a re-read is the same wait without an assertion about a duration.
    """
    state = runner.probe(handle)
    if state.alive is False:
        return state
    runner.write(handle, ENTER)
    return None


def verbs(issued: tuple[tuple[str, ...], ...]) -> list[str]:
    """The tmux verb of each issued argv: argv[3], after the binary and `-L s`."""
    return [argv[3] for argv in issued if len(argv) > 3]


# ----- 1. the trust dialog is real, and no key was sent at it -----------------


def test_an_untrusted_directory_stops_on_the_trust_dialog_and_no_key_is_sent(
    lane: Lane,
) -> None:
    """C15, E-M3-1, C-M3-5. The fixture's workdir is a fresh `tmp_path`, so the
    engine has never trusted it and the dialog is the real one.

    **Arrival first.** `state == needs_you` and the published `pane_kind` say the
    dialog really appeared; only then is the absence asserted. The absence on its
    own would pass just as well against a pane that never started.
    """
    assert lane.outcome.state is SessionState.NEEDS_YOU, lane.outcome
    assert str(lane.throwaway.workdir) in lane.outcome.detail

    published = lane.spawn_event.payload
    assert published["pane_kind"] == PaneKind.TRUST_DIALOG.value, published
    assert published["state"] == SessionState.NEEDS_YOU.value
    # The engine's own `~/.claude.json` agrees the directory was untrusted, so
    # the dialog is not a screen this lane happened to catch mid-startup.
    assert published["trusted"] is not True, published

    # …and the row says the same thing, which is what a page would render.
    row = lane.store.get_owned_session(lane.outcome.session_id)
    assert row is not None and row.state is SessionState.NEEDS_YOU

    # Now the absence: not one key was typed at a pane waiting on a human.
    # Observed over the argvs the lane really issued, not over this file's text.
    issued = lane.issued()
    assert issued, "no tmux argv was issued at all: this check would be vacuous"
    assert "send-keys" not in verbs(issued), issued


# ----- 2. a real stop carries a real exit code --------------------------------


def test_a_real_stop_carries_an_exit_code(lane: Lane) -> None:
    """E-M3-16 — **G-M2-2 closed for owned sessions**.

    The engine really dies: a bare Enter at the trust dialog selects `No, exit`,
    which is C15's own captured behaviour. `remain-on-exit on` was set by
    `LocalRunner.start` before anything could exit, so tmux still holds the
    pane's status when it is read.

    Arrival is the dialog **and** the send-keys: a pane that never started is
    also `alive=False` with no exit code, and asserting the absence of life
    without first showing life would not tell the two apart.
    """
    before = lane.runner.probe(lane.handle)
    assert before.alive is True, f"the pane was already gone before anything was typed: {before}"
    assert before.pid is not None

    kind = await_value(
        lambda: lane.runner.pane(lane.handle).kind
        if lane.runner.pane(lane.handle).kind is PaneKind.TRUST_DIALOG
        else None,
        "the trust dialog never appeared, so a bare Enter would not refuse anything",
        DIALOG_CEILING_S,
    )
    assert kind is PaneKind.TRUST_DIALOG

    mark = len(TMUX_CALLS)
    dead = await_value(
        lambda: press_enter_until_dead(lane.runner, lane.handle),
        "the pane never died after the trust dialog was refused",
        EXIT_CEILING_S,
    )
    assert "send-keys" in verbs(tuple(TMUX_CALLS[mark:])), TMUX_CALLS[mark:]
    assert dead.alive is False

    # **The status is not readable at the instant the pane goes dead.** tmux
    # marks the pane dead on EOF from the pty and fills `#{pane_dead_status}`
    # when it reaps the child, and this lane measured a live-lane read 0.3 s
    # after the keypress returning `pane_dead=1` with an empty status while the
    # process was still running. The 2026-09-14 probe read the same pane 4 s
    # later and captured `probe_b|…|1|1||`
    # (`run-20260914T154946Z/01b-list-sessions-after-refuse.txt`). So the wait is
    # for the **status**, not for the death — a ceiling on a condition, not an
    # assertion about elapsed time.
    settled = await_value(
        lambda: found
        if (found := lane.runner.probe(lane.handle)).exit_code is not None
        else None,
        "the pane died and tmux never reported an exit status for it — "
        "remain-on-exit kept the row but E-M3-16's exit_code is not there",
        EXIT_CEILING_S,
    )
    # The real number. C15 says a refused trust dialog exits 1, and the
    # 2026-09-14 capture agrees: `probe_b|4041912|1|1||`.
    assert settled.exit_code == 1, f"observed exit code {settled.exit_code}"
    # `#{pane_dead_signal}` was empty even after SIGTERM on this host
    # (`14-list-sessions-after-sigterm.txt`: `probe_sig|…|1|143||`), so the
    # signal stays an unknown rather than something inferred from the status.
    assert settled.exit_signal is None


# ----- 3. the pane survives a real `controld` restart -------------------------


def test_the_pane_survives_a_controld_restart(lane: Lane, shepherd_home: Path) -> None:
    """D14 / DP5, with a real process boundary rather than two threads.

    The tmux server is started outside the caller's supervision through the
    host's `DetachedLaunch` prefix; a server first started *inside* a unit dies
    with the unit and takes every owned pane with it, which is the opposite of
    the guarantee tmux was chosen for.
    """
    assert lane.runner.probe(lane.handle).alive is True, "there is no pane to survive anything"
    names_before = [ref.session_name for ref in lane.runner.list_owned_panes()]
    assert lane.handle.session_name in names_before, names_before

    host = detect_host()
    (shepherd_home / "engine" / "sessions").mkdir(parents=True, exist_ok=True)
    started = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
    # Arrival: `controld` really came up, so what follows is really a restart.
    assert started.port > 0
    assert started.control_socket_path.exists()
    controld.stop(started)
    assert not started.control_socket_path.exists(), "controld left its socket behind (F15)"

    # …and the pane is still there with the daemon gone.
    assert lane.runner.probe(lane.handle).alive is True, (
        "the pane died when controld stopped: the server is inside the daemon's cgroup"
    )

    restarted = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
    try:
        assert restarted.control_socket_path.exists()
        after = lane.runner.probe(lane.handle)
        assert after.alive is True, "the pane did not survive the controld restart"
        assert after.pid == lane.runner.probe(lane.handle).pid
        assert [ref.session_name for ref in lane.runner.list_owned_panes()] == names_before
    finally:
        controld.stop(restarted)


# ----- 4. P-M3-17: the bytes a real `capture-pane` returns --------------------


def server_frame(frame: bytes) -> tuple[int, bytes]:
    """`(opcode, payload)` of an unmasked **server** frame, read independently.

    Not `ws.parse_frame`: that is the *client* half of RFC 6455 and raises on an
    unmasked frame by design ("a server MUST NOT mask any frames that it sends"),
    so it cannot read what the server wrote. The header is decoded here from
    §5.2 rather than from `build_frame`'s own arithmetic — an expected value
    re-derived by the code under test is a tautology.
    """
    first, second = frame[0], frame[1]
    assert first & 0x80, "the frame is not FIN"
    assert not second & 0x80, "a server frame must not be masked"
    length, offset = second & 0x7F, 2
    if length == 126:
        length, offset = int.from_bytes(frame[2:4], "big"), 4
    elif length == 127:
        length, offset = int.from_bytes(frame[2:10], "big"), 10
    assert len(frame) == offset + length, (len(frame), offset, length)
    return first & 0x0F, frame[offset:]


def test_the_live_snapshot_frame_is_the_bytes_capture_pane_returned(lane: Lane) -> None:
    """P-M3-17 — C-M3-9's real basis, on this host's own tmux 3.4.

    The capture goes out through the lane's `make_run_argv`, so the argv asserted
    below is the one a process really received; the bytes it returned are framed
    with the shipped `build_frame` and the frame's payload is compared to them.
    """
    mark = len(TMUX_CALLS)
    raw = await_value(
        lambda: lane.runner.snapshot(lane.handle, SNAPSHOT_SCROLLBACK) or None,
        "capture-pane returned no bytes at all, so there is nothing to frame",
        DIALOG_CEILING_S,
    )
    # Arrival: a real screen, with the real escape sequences `-e` preserves.
    assert raw, "the capture is empty"
    assert b"\x1b[" in raw, "the capture carries no ANSI at all, so `-e` did not hold"

    # The path is the claim. This is the argv a tmux process really received.
    captures = [
        argv for argv in TMUX_CALLS[mark:] if len(argv) > 3 and argv[3] == "capture-pane"
    ]
    assert captures, TMUX_CALLS[mark:]
    issued = captures[-1]
    assert issued[:3] == ("tmux", "-L", LIVE_TMUX_SOCKET), issued
    assert issued[3:8] == ("capture-pane", "-e", "-p", "-S", f"-{SNAPSHOT_SCROLLBACK}"), issued
    assert issued[8] == "-t" and issued[9] == f"={lane.handle.session_name}:", issued

    frame = ws.build_frame(raw, opcode=ws.OP_BINARY)
    opcode, payload = server_frame(frame)
    assert opcode == ws.OP_BINARY
    assert payload == raw, (len(payload), len(raw))
    assert len(frame) > len(raw), "a frame with no header is not a frame"


# ----- 5. a spawn registers exactly one row, with the real hook block ---------


def start_sessiond(home: Path) -> subprocess.Popen[bytes]:
    """The real relay process, with Shepherd's dirs pointed at a throwaway."""
    environment = dict(os.environ)
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        environment[name] = str(home / name.lower())
    environment["XDG_RUNTIME_DIR"] = str(home / "run")
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from shepherd.daemons.sessiond import main; raise SystemExit(main())",
            "--expected-schema-version",
            str(EXPECTED_SCHEMA_VERSION),
        ],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def press_down_until_yes(runner: LocalRunner, handle: RunnerHandle) -> str | None:
    """One press, then a **re-read**. Returns the selected row once it is `Yes`.

    C15/A11: a bare Enter here selects `No, exit` and the process is gone. The
    re-read is not politeness — pressed at the first frame that classifies as the
    dialog, `Down` is dropped and the `Enter` that follows exits (T20 observed
    that twice on this host).
    """
    for line in (runner.pane(handle).dialog_text or "").splitlines():
        if line.strip().startswith(SELECTED) and TRUST_YES in line:
            return line.strip()
    runner.write(handle, DOWN)
    return None


def test_a_spawn_registers_exactly_one_row(
    throwaway: Throwaway,
    tmp_path: Path,
    shepherd_home: Path,
    installed_settings: Path,
    tmux_live: str,
) -> None:
    """C-M3-7, P-M3-8 — and the reason `installed_settings` exists.

    The spawn writes one row itself; the hook lane is the **second writer**, and
    the claim is that it rebinds onto that row rather than creating another. With
    the shipped `--settings {}` fixture the engine emits no hook to Shepherd at
    all, so the second writer could never run and `count == 1` could not fail.
    Here Shepherd's own installed block is in the settings file the pane is
    started with, `sessiond` is a real process on the real ingest socket, and
    **a hook event is asserted to have actually landed** — `last_event_at` is
    stamped by the fold on every received frame and by nothing else on this path
    — before anything is asserted about how many rows there are.
    """
    host = detect_host()
    ingest = host.control_socket(INGEST_SOCKET_NAME)
    (shepherd_home / "engine" / "sessions").mkdir(parents=True, exist_ok=True)
    started = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
    daemon = start_sessiond(shepherd_home)
    runner = live_runner(throwaway, tmp_path)
    opened: RunnerHandle | None = None
    try:
        await_value(
            lambda: True if ingest.path.exists() else None,
            "sessiond never bound its ingest socket, so no hook could reach Shepherd",
            EXIT_CEILING_S,
        )
        # The spawn writes into **controld's own store**, which is also where the
        # hook lane writes. Two databases would make "exactly one row" a
        # statement about nothing.
        lane = spawn(started.store, runner, throwaway)
        handle = opened = lane.handle
        row = started.store.get_owned_session(lane.outcome.session_id)
        assert row is not None and row.engine_session_id is not None
        engine_session_id = row.engine_session_id
        assert lane.outcome.state is SessionState.NEEDS_YOU, lane.outcome

        # **`last_event_at` is not `None` here, and the reason matters.** The
        # spawn's own `_record` writes `FoldDelta(state=needs_you,
        # needs_you_reason=…, last_event_at=now())` on the trust-dialog
        # resolution, so the column is already stamped by *us*. Taking
        # `is not None` as "a hook arrived" would therefore be a false green —
        # it was measured as one on the first run of this test. The arrival
        # signal is the stamp **moving off this value**, which on a `starting`
        # row only the fold applying a received frame can do.
        spawn_stamp = row.last_event_at
        assert spawn_stamp is not None, row

        # The trust dialog, accepted the way T20 accepts it: press, re-read, Enter.
        await_value(
            lambda: True if runner.pane(handle).kind is PaneKind.TRUST_DIALOG else None,
            "the trust dialog never appeared",
            DIALOG_CEILING_S,
        )
        selection = await_value(
            lambda: press_down_until_yes(runner, handle),
            "the trust dialog never showed `Yes, I trust this folder` selected",
            DIALOG_CEILING_S,
        )
        assert TRUST_YES in selection, selection
        runner.write(handle, ENTER)

        await_value(
            lambda: True if runner.pane(handle).kind is PaneKind.PROMPT_READY else None,
            f"the engine never reached a prompt-ready pane; last screen was "
            f"{runner.pane(handle).kind}",
            HOOK_CEILING_S,
        )

        # **Arrival**: a hook frame really reached Shepherd for this session,
        # through the engine's own hook command, `sessiond`, the ingest socket
        # and `controld`'s hook lane. `fold.py` stamps `last_event_at =
        # received_at` on every frame it applies; nothing else writes that
        # column after the spawn has finished.
        stamped = await_value(
            lambda: (
                found.last_event_at
                if (found := started.store.get_owned_session(lane.outcome.session_id)) is not None
                and found.last_event_at is not None
                and found.last_event_at != spawn_stamp
                else None
            ),
            f"no hook event ever reached Shepherd for this spawn — last_event_at "
            f"is still the spawn's own {spawn_stamp!r}, so the second writer never "
            f"ran and the row count below would be vacuous",
            HOOK_CEILING_S,
        )
        assert stamped != spawn_stamp

        # …and only now the property: one row, not two.
        rows = [
            entry
            for entry in started.store.list_sessions()
            if entry.cwd == str(throwaway.workdir)
        ]
        assert len(rows) == 1, [(entry.id, entry.engine_session_id, entry.cwd) for entry in rows]
        assert rows[0].id == lane.outcome.session_id
        assert rows[0].engine_session_id == engine_session_id
        by_engine = started.store.get_session_by_engine_id(engine_session_id)
        assert by_engine is not None and by_engine.id == lane.outcome.session_id
    finally:
        if opened is not None:
            try:
                runner.terminate(opened)
            except Exception:  # noqa: BLE001 — a pane tmux already forgot is fine
                pass
        controld.stop(started)
        daemon.terminate()
        daemon.wait(timeout=EXIT_CEILING_S)


# ----- 6. the installed block is the installer's own output -------------------


def test_the_installed_block_is_the_installers_own_output(
    installed_settings: Path, throwaway: Throwaway
) -> None:
    """Goes red on a hand-written imitation, which would let the lane pass
    against a block Shepherd does not actually install.

    Read three ways: the marker the installer writes, the installer's own
    `inspect_hooks` reading of the file, and the foreign entry the fixture
    planted, which the installer must have left alone.
    """
    assert installed_settings == throwaway.settings
    document = json.loads(installed_settings.read_text(encoding="utf-8"))
    hooks = document["hooks"]

    managed = [
        group
        for entries in hooks.values()
        for group in entries
        if group.get(MANAGED_MARKER) is True
    ]
    assert managed, "nothing in the file is marked as Shepherd's"
    for group in managed:
        assert all(entry.get(MANAGED_MARKER) is True for entry in group["hooks"]), group

    inspected = inspect_hooks(installed_settings)
    assert inspected.installed is True
    assert inspected.managed_entries == len(managed)
    assert inspected.foreign_entries == 1, "the foreign PreToolUse entry was not left alone"
    assert inspected.pre_existing_breakage == ()

    # …and the real file is not this file, nor named anywhere inside it.
    assert str(Path.home() / ".claude") not in installed_settings.read_text(encoding="utf-8")


# ----- 7. the socket is empty when the lane is done ---------------------------


def test_the_live_socket_has_no_server_at_teardown(lane: Lane) -> None:
    """Goes red if a run leaks a session onto a shared machine.

    The `lane` fixture is requested so this test has something of its own to tear
    down: run under `-k`, it would otherwise assert an empty socket that was
    never populated, which is a check that cannot fail. Arrival is therefore the
    listing showing this lane's own session **before** the teardown.

    The sequence is `kill-session` per session, then **one** `kill-server` on
    `shepherd-m3-live`, then the assertion. `check_tmux_argv` permits that verb
    here because the socket matches `^shepherd-m3-` and for no other reason
    (K6, K6-a) — it can never be `shepherd`, and never `shepherd-runner`.
    """
    before = live_socket_listing()
    assert before.rc == 0, before.stderr
    names = before.stdout.decode("utf-8", "replace").split()
    assert lane.handle.session_name in names, names

    teardown_live_socket()

    after = live_socket_listing()
    assert after.rc != 0, after.stdout
    assert NO_SERVER in after.stderr.decode("utf-8", "replace"), after.stderr
    assert live_socket_has_no_server() is True
