"""T18: the composition root, end to end, in one process.

Seam: the two real sockets and the loopback HTTP port — the surfaces a hook, a
browser and an operator actually have. Nothing here reaches inside a handler,
and nothing is faked: `controld` opens a real SQLite store under a throwaway
`XDG_DATA_HOME`, binds its real control socket, serves the real static page, and
`sessiond`'s real `Relay` carries real frames across.

The registry scan is pointed at a **throwaway** engine config dir so these tests
are deterministic. The live lane (`tests/e2e/`) is where it is pointed at this
host's real one.

What each test is the acceptance evidence for:

* ADR-7 — the registry is frozen before the server binds;
* §12 — an update reaches a subscriber over SSE with no polling anywhere;
* D37 — `controld` is the only writer, and a restart drains `sessiond`'s buffer
  **in order**, which is the entire reason the two-process split exists;
* F15/ADR-7 — shutdown unlinks both sockets, closes the store and joins the
  writer thread, and a restart binds without `EADDRINUSE`.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.core.frames import Frame
from shepherd.daemons import controld, plane
from shepherd.daemons import shutdown
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME, INGEST_SOCKET_NAME
from shepherd.engines.claude_code.relay import Relay
from shepherd.host.base import (
    HookDispatchPlan,
    HostDirs,
    LoginPersistence,
    SocketPathTooLong,
    SocketPlan,
    Supervision,
)
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface import compose
from shepherd.host.detect import detect_host
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from shepherd.toolsurface.registry import RegistryFrozen, register, registered_tools
from shepherd.toolsurface.types import Audience, BlastClass, ToolDef

from shepherd.core.runner import ProcState

ENGINE_SESSION_ID = "5d1202ea-3765-459d-8299-8630c710c50d"
CEILING_S = 10.0

#: One scripted process reading, for the fixtures below.
SCRIPTED_PROC = ProcState(
    alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at="2026-09-17T10:00:00Z"
)


def imported_names(path: Path) -> set[str]:
    """Every name bound by an import in `path`, by AST — never by importing it.

    The same reader `tests/daemons/test_controld_composition.py` uses, repeated
    rather than shared: these two files assert different properties of the same
    text, and a helper imported across them would make one file's edit silently
    change the other's meaning.
    """
    import ast

    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom | ast.Import):
            found.update(alias.asname or alias.name for alias in node.names)
    return found


def payload_for(cwd: str, engine_session_id: str = ENGINE_SESSION_ID) -> bytes:
    """The captured `UserPromptSubmit` shape — one real event, one real state."""
    return (
        json.dumps(
            {
                "session_id": engine_session_id,
                "cwd": cwd,
                "hook_event_name": "UserPromptSubmit",
                "prompt": "build the composition root",
            }
        ).encode("utf-8")
        + b"\n"
    )


@dataclass(frozen=True)
class World:
    """A throwaway host: XDG dirs, an engine config dir with no sessions in it."""

    data_dir: Path
    runtime_dir: Path
    engine_config_dir: Path
    cwd: Path


#: Every environment variable any `HostPlatform` driver reads to place its
#: directories. All of them are redirected, not just the ones the platform this
#: was written on happens to read: `LinuxHost` takes `XDG_*`, `MacHost` takes
#: `HOME` and `TMPDIR`, and a fixture that sets only one family silently hands
#: the *other* platform the developer's real home. That is not hypothetical —
#: it is what this fixture did, and `~/Library/Application Support/Shepherd`
#: had a real `shepherd.db` in it to prove the point.
HOST_DIR_ENV: tuple[str, ...] = (
    "XDG_DATA_HOME",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
    "HOME",
    "TMPDIR",
)


@pytest.fixture()
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """A throwaway host — for **whichever** driver `detect_host()` returns.

    `data_dir` and `runtime_dir` are read back from the seam rather than spelled
    here, because the two drivers place them differently
    (`.local/share/shepherd` vs `Library/Application Support/Shepherd`) and a
    test that spells one platform's layout is asserting about the wrong machine
    on the other.
    """
    targets = {
        "XDG_DATA_HOME": tmp_path / "xdg_data_home",
        "XDG_CONFIG_HOME": tmp_path / "xdg_config_home",
        "XDG_STATE_HOME": tmp_path / "xdg_state_home",
        "XDG_CACHE_HOME": tmp_path / "xdg_cache_home",
        "XDG_RUNTIME_DIR": tmp_path / "run",
        "HOME": tmp_path / "home",
        "TMPDIR": tmp_path / "run",
    }
    # The list and the redirect cannot drift apart: adding a variable to
    # HOST_DIR_ENV without redirecting it fails here rather than in whichever
    # test first reads the developer's real home.
    assert tuple(targets) == HOST_DIR_ENV
    for name, target in targets.items():
        monkeypatch.setenv(name, str(target))

    engine_config_dir = tmp_path / "engine-config"
    (engine_config_dir / "sessions").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()

    dirs = detect_host().dirs()
    # Arrival, not trust: the driver really did follow the redirect. Without
    # this the fixture is happy to hand back the real user's directories.
    for directory in (dirs.data_dir, dirs.runtime_dir):
        assert tmp_path in directory.parents, f"{directory} escaped the throwaway host"

    return World(
        data_dir=dirs.data_dir,
        runtime_dir=dirs.runtime_dir,
        engine_config_dir=engine_config_dir,
        cwd=work,
    )


@contextmanager
def running(world: World) -> Iterator[controld.Controld]:
    started = controld.start(
        host=detect_host(),
        port=0,
        engine_config_dir=world.engine_config_dir,
    )
    try:
        yield started
    finally:
        controld.stop(started)


def await_true(predicate: object, message: str, ceiling_s: float = CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def get(started: controld.Controld, path: str) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", started.port, timeout=CEILING_S)
    try:
        connection.request("GET", path, headers={"Host": f"127.0.0.1:{started.port}"})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def applied_rows(started: controld.Controld) -> list[dict[str, object]]:
    """Every session row `controld` has finished applying, in **application order**.

    Two facts this test depends on, neither of them obvious from `/api/sessions`:

    * **A row is registered and folded in two separate commits.**
      `HookLane.apply` calls `register_session` (one writer transaction) and
      then, after reading a snapshot and folding, `apply_fold_delta` (a second
      one). Between them the row is already on `/api/sessions` with
      `last_event_at` still `NULL` — a frame that has arrived and has not
      landed. Waiting on the row *count* therefore does not mean the frames
      were applied, and reading `last_event_at` in that window yields `None`.
      That is the whole of this test's one observed red: `TypeError: '<' not
      supported between instances of 'NoneType' and 'str'`, reproduced 5/5 by
      widening the window with a sleep inside `Store.snapshot`.
    * **`id` is the application order and `started_at` is not.** `id` is a ulid
      minted from the wall clock inside `register_session`, so it increases in
      the order `controld` registered the rows; `started_at` is the frame's own
      `received_at`, which is whatever the sender put there. `list_sessions`
      returns `ORDER BY started_at, id`, so asserting that *its* output is
      ascending in `started_at` (or in `last_event_at`, which the fold copies
      from `received_at`) asserts nothing at all.
    """
    rows = json.loads(get(started, "/api/sessions")[1])["data"]["sessions"]
    landed = [row for row in rows if row["last_event_at"] is not None]
    return sorted(landed, key=lambda row: str(row["session_id"]))


class Subscriber:
    """One SSE connection, read on a thread. Nothing here polls: the socket is
    opened once and the frames arrive when the server pushes them."""

    def __init__(self, port: int) -> None:
        self.frames: list[dict[str, str]] = []
        self._connection = http.client.HTTPConnection("127.0.0.1", port, timeout=CEILING_S)
        self._connection.request(
            "GET", "/api/events", headers={"Host": f"127.0.0.1:{port}"}
        )
        self._response = self._connection.getresponse()
        assert self._response.status == 200
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        try:
            self._read_frames()
        except OSError:
            # The test closed the connection: a read that fails is how a closed
            # tab looks from in here, not a failure to report.
            return

    def _read_frames(self) -> None:
        current: dict[str, str] = {}
        while True:
            raw = self._response.fp.readline() if self._response.fp else b""
            if raw == b"":
                return
            line = raw.decode("utf-8").rstrip("\n")
            if line == "":
                if current:
                    self.frames.append(current)
                    current = {}
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            current[field] = value.lstrip(" ")

    def close(self) -> None:
        self._connection.close()


def relay_to(started: controld.Controld, frames: list[bytes]) -> None:
    """What `sessiond` does: a real `Relay` over the real control socket."""
    relay = Relay(started.control_socket_path, 100, EXPECTED_SCHEMA_VERSION)
    try:
        for index, raw in enumerate(frames):
            relay.send(Frame(payload=raw, received_at=f"2026-09-16T10:00:{index:02d}Z", peer_pid=None))
    finally:
        relay.close(5.0)


def test_the_registry_is_frozen_before_the_server_binds(world: World) -> None:
    """ADR-7: written by one thread at startup, read-only thereafter."""
    with running(world) as started:
        assert started.port != 0
        assert {"fleet_summary", "fleet_tree", "schema_status", "engine_version"} <= set(
            registered_tools()
        )
        with pytest.raises(RegistryFrozen):
            register(
                ToolDef(
                    name="too_late",
                    description="registered after the bind",
                    input_schema={"type": "object", "properties": {}},
                    blast_class=BlastClass.LOCAL_READ,
                    handler=lambda args, ctx: None,
                    audiences=frozenset({Audience.HUMAN}),
                )
            )


def test_the_page_and_its_tools_are_served_on_loopback(world: World) -> None:
    """§13: loopback only, and the fleet page is served from the package."""
    with running(world) as started:
        status, body = get(started, "/")
        assert status == 200
        assert "no sessions discovered yet" in body

        status, body = get(started, "/api/fleet/tree")
        assert status == 200
        data = json.loads(body)["data"]
        assert data["workspaces"] == []
        assert data["session_count"] == 0
        assert isinstance(data["now"], str) and data["now"] != ""


def test_a_relayed_frame_becomes_a_row_and_an_sse_update(world: World) -> None:
    """The whole path in one assertion: hook payload → sessiond → controld →
    store → stream → subscriber, with no polling anywhere in it (§12)."""
    with running(world) as started:
        subscriber = Subscriber(started.port)
        try:
            relay_to(started, [payload_for(str(world.cwd))])
            await_true(lambda: subscriber.frames != [], "no SSE frame arrived")
        finally:
            subscriber.close()

        status, body = get(started, "/api/fleet/tree")
        assert status == 200
        data = json.loads(body)["data"]
        assert data["session_count"] == 1
        sessions = data["workspaces"][0]["sessions"]
        assert sessions[0]["cwd"] == str(world.cwd)

    assert subscriber.frames[0]["id"].isdigit()
    envelope = json.loads(subscriber.frames[0]["data"])
    # §12's envelope keys, as `web/sse.py` writes them.
    assert envelope["type"] != ""
    assert envelope["seq"] == int(subscriber.frames[0]["id"])


def test_the_buffer_drains_in_order_across_a_controld_restart(world: World) -> None:
    """D37/T10b: the reason the two-process split exists. `sessiond` buffers
    while `controld` is down, and the frames arrive afterwards **in order**."""
    with running(world) as started:
        relay_to(started, [payload_for(str(world.cwd), f"sess-{index}") for index in (0, 1)])
        await_true(
            lambda: len(applied_rows(started)) == 2,
            "the first two frames never landed",
        )
        control_path = started.control_socket_path

    assert not control_path.exists(), "the control socket was not unlinked (F15)"

    # `controld` is down. A relay started now buffers rather than losing frames.
    relay = Relay(control_path, 100, EXPECTED_SCHEMA_VERSION)
    try:
        for index in (2, 3, 4):
            relay.send(
                Frame(
                    payload=payload_for(str(world.cwd), f"sess-{index}"),
                    received_at=f"2026-09-16T10:01:{index:02d}Z",
                    peer_pid=None,
                )
            )
        await_true(lambda: relay.stats().buffered > 0, "nothing was buffered while down")

        with running(world) as restarted:
            await_true(
                lambda: relay.stats().delivered >= 3, "the buffer never drained after restart"
            )
            await_true(
                lambda: len(applied_rows(restarted)) == 5,
                "not every buffered frame reached the store",
            )
            rows = applied_rows(restarted)
    finally:
        relay.close(5.0)

    # The claim is **in order**, so the assertion reads the frames off in the
    # order `controld` applied them (`id`) and names which frame each one was
    # (`started_at`, the `received_at` this test sent). Draining the relay
    # newest-first (`popleft` -> `pop` in `relay._drain_once`) turns this red;
    # it left the previous `stamps == sorted(stamps)` green, which is how that
    # assertion was found to be satisfied by construction.
    applied = [row["started_at"] for row in rows]
    assert applied == [
        "2026-09-16T10:00:00Z",
        "2026-09-16T10:00:01Z",
        "2026-09-16T10:01:02Z",
        "2026-09-16T10:01:03Z",
        "2026-09-16T10:01:04Z",
    ], f"frames were applied out of order: {applied}"
    assert relay.stats().overflowed == 0
    assert relay.stats().schema_mismatch == 0


def test_shutdown_unlinks_both_sockets_and_closes_the_store(world: World) -> None:
    """F15 + ADR-7: nothing is left behind, and the next start binds cleanly."""
    with running(world) as started:
        assert started.control_socket_path.exists()
        assert started.store.writer_is_alive() is True

    assert not started.control_socket_path.exists()
    assert started.store.writer_is_alive() is False

    # …and a second start binds the same path with no EADDRINUSE.
    with running(world) as again:
        assert again.control_socket_path.exists()
        assert again.control_socket_path.name == f"{CONTROL_SOCKET_NAME}.sock"


def test_nothing_binds_anything_but_loopback(world: World) -> None:
    """§13: there is no knob, so the refusal is a call that fails."""
    with running(world) as started:
        assert started.server.server_address[0] == "127.0.0.1"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1.0)
            assert probe.connect_ex(("127.0.0.1", started.port)) == 0


def test_a_refused_start_leaves_no_database_behind(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The socket plan is validated **before** the store is opened.

    `SocketPathTooLong` is the refusal `controld` already models honestly. It
    was raised after `open_store` had already migrated a `shepherd.db` into
    place and left its writer thread running, so a start that refused still
    changed the disk and leaked a thread — the opposite of a refusal.
    """
    long_runtime = tmp_path / ("r" * 90) / ("u" * 90)
    # Both spellings of "where the runtime directory is", so the path is over
    # budget for whichever driver this platform uses (HOST_DIR_ENV).
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(long_runtime))
    monkeypatch.setenv("TMPDIR", str(long_runtime))

    with pytest.raises(SocketPathTooLong):
        controld.start(host=detect_host(), port=0, engine_config_dir=world.engine_config_dir)

    assert not (world.data_dir / controld.DB_NAME).exists()

    # …and `main` turns it into the exit code and the one honest line.
    monkeypatch.setattr(controld, "install_shutdown_handlers", lambda shutdown: None)
    assert controld.main(["--port", "0", "--engine-config-dir", str(world.engine_config_dir)]) == (
        controld.EXIT_REFUSED
    )
    assert "refuses to start" in capsys.readouterr().out


def test_an_occupied_port_is_refused_honestly_not_as_a_traceback(
    world: World, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A port someone else holds is a refusal, like the socket path is.

    `SocketPathTooLong` set the standard: say what is wrong and exit `2`. A raw
    `OSError` traceback out of `main` is the same event reported worse.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
        occupier.bind(("127.0.0.1", 0))
        occupier.listen(1)
        port = int(occupier.getsockname()[1])

        monkeypatch.setattr(controld, "install_shutdown_handlers", lambda shutdown: None)
        code = controld.main(
            ["--port", str(port), "--engine-config-dir", str(world.engine_config_dir)]
        )

    assert code == controld.EXIT_REFUSED
    printed = capsys.readouterr().out
    assert "refuses to start" in printed
    assert str(port) in printed


def test_the_daemon_restarts_on_the_same_port_after_a_page_connected(world: World) -> None:
    """D37's other half, end to end: restart the control plane, keep the port.

    The fleet page holds an SSE connection, so a socket in `TIME_WAIT` on the
    daemon's port is the ordinary end state of a watched run. The rest of this
    module binds `port=0`, which is exactly why this was never seen.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()

    first = controld.start(
        host=detect_host(), port=port, engine_config_dir=world.engine_config_dir
    )
    assert first.port == port
    subscriber = Subscriber(port)
    assert get(first, "/")[0] == 200
    subscriber.close()
    controld.stop(first)

    again = controld.start(
        host=detect_host(), port=port, engine_config_dir=world.engine_config_dir
    )
    try:
        assert again.port == port
        assert get(again, "/")[0] == 200
    finally:
        controld.stop(again)


# ----- the stop path's construction (T18-3, r3 BLOCKING 2) ------------------
# Seam: the same two — the real ingest socket and the real loopback port. The
# stop path is proved the way every other lane here is, by driving a captured
# frame in from outside and reading what the process left on disk. A test that
# asserted `StopLog` had been *constructed* would pass against a log nothing
# ever writes to, which is the exact defect BLOCKER T18-3a was about.

#: The `Stop` capture's shape, §Stop in `docs/specs/data-schemas.md`
#: (`S10_effort_sonnet/events.jsonl`). `transcript_path` is the one substituted
#: value: the announced path is consulted first and must be absent here, so
#: what the test proves is the fallback through the wired `projects_root`.
STOP_TRANSCRIPT_SESSION_ID = "7c27bb7f-5390-48b0-8b2e-cf4004113d09"
A_REAL_TRANSCRIPT = (
    Path(__file__).resolve().parents[2]
    / "docs/probes/2026-09-14-schemas/transcripts/copies"
    / "-tmp-shp-schemas-tx-blIf90-work"
    / f"{STOP_TRANSCRIPT_SESSION_ID}.jsonl"
)


def stop_payload_for(cwd: str, engine_session_id: str, transcript_path: Path) -> bytes:
    return (
        json.dumps(
            {
                "session_id": engine_session_id,
                "transcript_path": str(transcript_path),
                "cwd": cwd,
                "prompt_id": "a95c9922-3b49-44f2-8906-ef313239b6c1",
                "permission_mode": "default",
                "hook_event_name": "Stop",
                "stop_hook_active": False,
                "last_assistant_message": "DONE",
                "background_tasks": [],
                "session_crons": [],
            }
        ).encode("utf-8")
        + b"\n"
    )


def plant_transcript(world: World) -> None:
    """The engine's own transcript root, under the throwaway engine config dir —
    the directory `controld` must resolve for `handle_stop` to read anything."""
    directory = world.engine_config_dir / "projects" / "-a-lossy-slug"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{STOP_TRANSCRIPT_SESSION_ID}.jsonl").write_bytes(
        A_REAL_TRANSCRIPT.read_bytes()
    )


def drive_a_real_stop(started: controld.Controld, world: World) -> None:
    """One session, then one turn ending, both over the real ingest socket."""
    relay_to(
        started,
        [
            payload_for(str(world.cwd), STOP_TRANSCRIPT_SESSION_ID),
            stop_payload_for(
                str(world.cwd), STOP_TRANSCRIPT_SESSION_ID, world.cwd / "no-such-transcript.jsonl"
            ),
        ],
    )


def classified_row(started: controld.Controld) -> dict[str, object] | None:
    """The one session's row, or `None` while the frames are still in flight."""
    rows = json.loads(get(started, "/api/sessions")[1])["data"]["sessions"]
    if not rows or rows[0]["stop_reason"] is None:
        return None
    row: dict[str, object] = rows[0]
    return row


def stop_records(world: World) -> list[dict[str, object]]:
    directory = world.data_dir / "logs" / "stops"
    if not directory.is_dir():
        return []
    return [
        json.loads(line)
        for path in sorted(directory.rglob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_controld_constructs_the_stop_log_and_hands_it_to_the_hook_lane(world: World) -> None:
    """r3 BLOCKING 2: T11's seam finally has a caller in a running process.

    The evidence is the eight columns `handle_stop` writes — reachable only if
    the lane was handed both collaborators, because `_classify` returns early
    when either is `None`.
    """
    plant_transcript(world)
    with running(world) as started:
        drive_a_real_stop(started, world)
        await_true(
            lambda: classified_row(started) is not None,
            "no verdict was ever written: the hook lane got no stop log",
        )
        row = classified_row(started)

    assert row is not None
    assert row["stop_reason"] not in (None, "")
    assert row["bucket"] not in (None, "")


def test_a_real_stop_lands_a_record_under_logs_stops(world: World) -> None:
    """Acceptance clause 12, through `controld`'s own construction."""
    plant_transcript(world)
    with running(world) as started:
        drive_a_real_stop(started, world)
        await_true(lambda: stop_records(world) != [], "nothing was written under logs/stops/")

    records = stop_records(world)
    assert len(records) == 1
    assert records[0]["record_version"] == 1
    # …and the record is the *evidence plus the verdict* D25 requires of it: the
    # evidence alone could not tell `replay` what a rule change changed.
    assert records[0]["evidence"]["engine_session_id"] == STOP_TRANSCRIPT_SESSION_ID
    assert records[0]["evidence"]["tail"]["ending"] != ""
    assert records[0]["verdict"]["stop_reason"] not in (None, "")
    assert records[0]["verdict"]["bucket"] not in (None, "")


def test_log_directories_are_resolved_from_host_dirs_only(
    world: World, tmp_path: Path
) -> None:
    """ADR-2: `logs/` receives its paths, and the root reads no environment.

    Two halves, because either alone is weak: the record lands under *this*
    host's `data_dir` and nowhere else, and the composition root's source
    names no other source of a path.
    """
    plant_transcript(world)
    with running(world) as started:
        drive_a_real_stop(started, world)
        await_true(lambda: stop_records(world) != [], "nothing was written under logs/stops/")

    assert (world.data_dir / "logs" / "stops").is_dir()
    strays = [
        path
        for path in tmp_path.rglob("stops")
        if path.is_dir() and path != world.data_dir / "logs" / "stops"
    ]
    assert strays == []

    source = Path(controld.__file__).read_text(encoding="utf-8")
    for forbidden in ("os.environ", "getenv", "Path.home()", "Path.cwd()", "os.getcwd"):
        assert forbidden not in source, f"the composition root resolves a path via {forbidden}"
    assert "host.dirs()" in source


# ----- T23: M3's wiring, and the three threads it does NOT become -------------


def scripted_host(tmp_path: Path) -> ScriptedHost:
    """A host whose every answer is a fixture, rooted under `tmp_path`."""
    runtime_dir = tmp_path / "run"
    return ScriptedHost(
        host_dirs=HostDirs(
            data_dir=tmp_path / "data",
            config_dir=tmp_path / "config",
            runtime_dir=runtime_dir,
        ),
        socket_plan=SocketPlan(
            path=runtime_dir / "sessiond.sock",
            dir_mode=0o700,
            sock_mode=0o600,
            socket_path_budget=107,
        ),
        dispatch=HookDispatchPlan(
            command=f"scripted-send {runtime_dir / 'sessiond.sock'}",
            requires=("scripted-send",),
            available=True,
            reason="scripted fixture",
        ),
        supervision_plan=Supervision(
            kind="foreground",
            detail="no supervisor on this host",
            manageable=False,
            start_limit_note="five restarts in ten seconds then the unit is refused",
        ),
        login=LoginPersistence(
            enabled=None,
            mechanism="none observed",
            detail="no persistence mechanism could be read on this host",
        ),
        observed_at="2026-09-17T10:00:00Z",
    )


def test_the_mailbox_sweep_runs_on_the_existing_loop(tmp_path: Path) -> None:
    """T14's `sweep_pending` rides the 2.0 s cadence `run_discovery_loop` owns.

    Goes red if a fourth thread appears to carry it: the sweep is asserted to run
    on **the loop's own thread**, which is this one, and `threads` in `start()`
    is asserted to stay three in `test_the_root_still_wires_exactly_three_threads`.

    Arrival before absence: the call count is asserted non-zero before the thread
    identity is read, so a sweep that never ran cannot pass the identity check.
    """
    from shepherd.signals.discovery_loop import run_discovery_loop
    from shepherd.store.db import open_store

    engine_config_dir = tmp_path / "engine-config"
    (engine_config_dir / "sessions").mkdir(parents=True)
    store = open_store(tmp_path / "data" / "shepherd.db")
    shutdown = threading.Event()
    ran_on: list[int] = []

    def sweep() -> object:
        ran_on.append(threading.get_ident())
        shutdown.set()  # one pass is all this test needs
        return None

    # A backstop, so a loop that never calls the sweep **fails** rather than
    # hanging: a check whose red is a timeout is a check nobody can read.
    backstop = threading.Timer(CEILING_S / 2, shutdown.set)
    backstop.start()
    try:
        run_discovery_loop(
            store=store,
            host=scripted_host(tmp_path),
            on_result=lambda result: None,
            shutdown=shutdown,
            engine_config_dir=engine_config_dir,
            sweep=sweep,
        )
    finally:
        backstop.cancel()
        store.close()

    assert len(ran_on) == 1, "the sweep never ran on the discovery loop's pass"
    assert ran_on == [threading.get_ident()]


def test_the_root_still_wires_exactly_three_threads(world: World) -> None:
    """Out-of-Scope Drift, as a check: M3 buys no fourth thread and no second
    socket. The ingest listener, the discovery loop and the HTTP server are the
    three the root has had since T18; the mailbox sweep rides the second."""
    with running(world) as started:
        names = tuple(thread.name for thread in started.threads)

        assert names == ("ingest", "scan", "http")
        assert all(thread.is_alive() for thread in started.threads)


def test_no_new_socket_is_bound(world: World) -> None:
    """DP4/§13: the terminal is served over the HTTP server's own upgrade, so
    `controld` still binds exactly **one** socket of its own — the control
    socket. (The ingest socket is `sessiond`'s; no file for it appears here
    because no `sessiond` runs in this test.)

    Goes red if a second listener appears — which is what a terminal daemon or a
    second control channel would look like from here.
    """
    with running(world) as started:
        bound = sorted(path.name for path in world.runtime_dir.iterdir())

        # Arrival: the directory really is the one `start()` bound into…
        assert started.control_socket_path.parent == world.runtime_dir
        assert started.control_socket_path.exists()
        # …and the one socket in it is that one, by name.
        assert bound == [started.control_socket_path.name]
        assert bound[0].startswith(CONTROL_SOCKET_NAME)
        assert INGEST_SOCKET_NAME not in bound


def test_the_composition_builds_the_runner_and_the_root_never_names_it() -> None:
    """The root keeps the order; `compose.py` keeps the composition (ADR-1).

    Goes red if a tool builds its own runner in the daemon — two `LocalRunner`s
    would be two sockets' worth of state — and red if the root learns a
    capability's name. The arrival half is the other file: `compose.py` is
    asserted to name both, so "the root does not" cannot pass on a tree where
    **nobody** builds a runner.
    """
    root = Path(controld.__file__)
    composed = Path(compose.__file__)
    root_names = imported_names(root)
    composed_names = imported_names(composed)

    assert {"LocalRunner", "make_run_argv"} <= composed_names
    assert [name for name in sorted(composed_names) if name.startswith("register_")] != []

    assert "LocalRunner" not in root_names
    assert "make_run_argv" not in root_names
    assert [name for name in sorted(root_names) if name.startswith("register")] == []
    assert "compose_tool_surface" in root_names


def test_the_reconcile_runs_before_the_registry_freezes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T12's startup reconcile runs inside the composition, before the freeze.

    An orphaned pane fills one of §11's total-cap slots whether or not anything
    knows of it, and the cap is asked on the first spawn — which cannot happen
    before the registry is frozen and the server binds. So the observation is
    taken at the freeze itself: the anomaly the reconcile counts is asserted to
    be **already in the store** at the moment `freeze_registry()` is called.

    Goes red if the reconcile is moved after the freeze, or dropped.
    """
    from shepherd.core.anomalies import AnomalyKind
    from shepherd.runner.base import PaneRef
    from shepherd.store.db import open_store
    from shepherd.testkit.scripted_runner import ScriptedRunner
    from shepherd.toolsurface import registry as registry_module

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "engine-config"))
    class ServerlessRunner(ScriptedRunner):
        """`ensure_server` is not one of the `Runner` seam's members — it is the
        driver's own, and the composition hands it to the spawn tool. The fixture
        answers it with a no-op so nothing here can start a tmux server."""

        def ensure_server(self) -> None:
            return None

    alien = PaneRef(session_name="shepherd_not-one-of-ours", session_id="x", pane_pid=1, dead=False)
    runner = ServerlessRunner(panes=(), proc=SCRIPTED_PROC, screen=b"", owned_panes=(alien,))
    monkeypatch.setattr(compose, "build_runner", lambda store, host: runner)

    store = open_store(tmp_path / "data" / "shepherd.db")
    seen_at_freeze: list[dict[str, int]] = []
    real_freeze = registry_module.freeze_registry

    def freeze_and_record() -> None:
        seen_at_freeze.append(store.list_anomaly_counts())
        real_freeze()

    monkeypatch.setattr(compose, "freeze_registry", freeze_and_record)
    host = scripted_host(tmp_path)
    try:
        wiring = compose.compose_tool_surface(
            store,
            host,
            tmp_path / "data" / "shepherd.db",
            host.control_socket("sessiond"),
            plane.build_master,
            plane.audit_sink(store, host),
        )
    finally:
        store.close()

    assert wiring.runner is runner
    assert len(seen_at_freeze) == 1, "freeze_registry() was never reached"
    assert seen_at_freeze[0].get(str(AnomalyKind.ORPHANED_PANE.value), 0) == 1


def test_the_root_hands_the_mailbox_sweep_to_the_loop_it_already_starts(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of `test_the_mailbox_sweep_runs_on_the_existing_loop`: the
    loop accepts a sweep, and **this** is the check that the root supplies one.

    Observed at the seam the root actually crosses — the keyword arguments it
    hands the scan thread — rather than in the source text, so a `scan_args`
    that spelled the key and never reached the loop would still be red.
    """
    from shepherd.core.mailbox import MailboxCounts

    handed: list[dict[str, object]] = []
    real_loop = controld.run_discovery_loop

    def capture(**kwargs: object) -> None:
        handed.append(dict(kwargs))
        real_loop(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(controld, "run_discovery_loop", capture)

    with running(world):
        await_true(lambda: handed != [], "the scan thread never started")
        sweep = handed[0].get("sweep")

        assert callable(sweep), handed[0].keys()
        # …and it is a live sweep over this daemon's own store, not a stub.
        assert isinstance(sweep(), MailboxCounts)


# ----- shutdown: a thread that will not exit is an unknown, not an exit --------


def a_thread(name: str, hold: threading.Event | None) -> threading.Thread:
    """A started thread that exits at once, or blocks on `hold` until it is set."""
    thread = threading.Thread(
        target=(lambda: None) if hold is None else (lambda: hold.wait(30.0)),
        name=name,
        daemon=True,
    )
    thread.start()
    return thread


def test_a_thread_that_will_not_exit_is_counted_and_named_not_treated_as_exited() -> None:
    """Principle 5 at F15: `join(timeout=…)` answers, and the answer is kept.

    `thread.join(timeout=…)` returns `None` whether or not the thread exited —
    the only way to tell is `is_alive()` afterwards, and discarding that is how
    a hung thread reads as a clean shutdown. The store is the thing at stake:
    `Store.close()` drains the queue and joins its writer with **no** timeout,
    so closing it under a thread that is still enqueueing writes converts an
    unknown into a hang with no message.
    """
    hold = threading.Event()
    closed: list[str] = []
    try:
        quick, stuck = a_thread("ingest", None), a_thread("scan", hold)
        quick.join(5.0)

        outcome = shutdown.shut_down(
            (quick, stuck), lambda: closed.append("store"), timeout_s=0.05
        )
    finally:
        hold.set()

    assert outcome.hung == ("scan",)
    assert outcome.joined == ("ingest",)
    # The store is left open **and the outcome says so**: an unknown never
    # licenses the irreversible step, and it never hides either.
    assert outcome.store_closed is False
    assert closed == []
    assert "scan" in str(outcome)
    assert "did not exit" in str(outcome)


def test_when_every_thread_exits_the_store_is_closed_and_the_count_is_displayed() -> None:
    """The ordinary path: three exits, the store closed, and a line to print."""
    closed: list[str] = []
    threads = tuple(a_thread(name, None) for name in ("ingest", "scan", "http"))

    outcome = shutdown.shut_down(threads, lambda: closed.append("store"), timeout_s=5.0)

    assert outcome.hung == ()
    assert outcome.joined == ("ingest", "scan", "http")
    assert outcome.store_closed is True
    assert closed == ["store"]
    assert str(outcome) == "3 threads exited · store closed"


def test_stop_returns_the_shutdown_outcome_rather_than_nothing(world: World) -> None:
    """The root's `stop()` hands the outcome back; it does not swallow it."""
    started = controld.start(
        host=detect_host(), port=0, engine_config_dir=world.engine_config_dir
    )
    outcome = controld.stop(started)

    assert outcome.hung == ()
    assert sorted(outcome.joined) == ["http", "ingest", "scan"]
    assert outcome.store_closed is True
    assert started.store.writer_is_alive() is False


def test_the_process_prints_what_shutdown_found(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Counted **and displayed** (principle 5): `main` puts the outcome on stdout.

    Driven through `main` rather than asserted against its source, because the
    claim is that a human running `shepherd-controld` sees it. `main` installs
    signal handlers, so it must run on the main thread and the shutdown is set
    from a helper — the reverse of the obvious arrangement, and the only one
    `signal.signal` allows.
    """
    started: list[controld.Controld] = []
    real_start = controld.start

    def spy(*args: object, **kwargs: object) -> controld.Controld:
        running = real_start(*args, **kwargs)  # type: ignore[arg-type]
        started.append(running)
        return running

    monkeypatch.setattr(controld, "start", spy)

    def request_shutdown() -> None:
        await_true(lambda: started != [], "controld never started")
        started[0].shutdown.set()

    stopper = threading.Thread(target=request_shutdown, name="stopper", daemon=True)
    stopper.start()
    code = controld.main(
        ["--port", "0", "--engine-config-dir", str(world.engine_config_dir)]
    )
    stopper.join(timeout=CEILING_S)

    assert code == 0
    printed = capsys.readouterr().out
    # Arrival before the claim: the run really did reach shutdown…
    assert started != []
    # …and the line a human reads names the count, not nothing.
    assert "3 threads exited · store closed" in printed, printed
