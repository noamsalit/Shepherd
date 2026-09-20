"""T18's live proof: real processes, real sockets, this host's real sessions.

`pytest tests/e2e -m live -q`. Excluded from the default run; the CI-equivalent
is `pytest -m "not live"`.

Three M1 claims cannot be proven by fixtures, and this is where each is proven:

1. **hookless discovery works on a machine with no hooks installed** — the whole
   reason T7b exists (Decision pressure 5). The scan is pointed at the user's
   real config dir, read-only, and the rows land in a throwaway database;
2. **`sessiond` → `controld` survives a `controld` restart with the buffer
   draining in order** — D37's whole claim, and the reason the two-process split
   exists, here with two real processes and a real UDS rather than two threads;
3. **an authenticated `claude` run is reachable at all under this lane's
   isolation posture** — which is the fact F10 corrected the plan for: an
   isolated `CLAUDE_CONFIG_DIR` has no credentials, so isolation is by working
   directory and `--settings`, and if that were wrong every other assertion here
   would be measuring a dead engine.

**No assertion counts sessions.** The real config dir means the user's own work
is visible; a count would fail whenever they are working (F10).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from e2e.conftest import (
    LIVE_MODEL,
    LIVE_TMUX_SOCKET,
    SHEPHERD_HOME_DIRNAME,
    TMUX_CALLS,
    Throwaway,
    live_socket_listing,
    real_config_dir,
    settings_digest,
)

from shepherd.core.frames import Frame
from shepherd.core.runner import RunnerRefusal
from shepherd.daemons import controld
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME, INGEST_SOCKET_NAME
from shepherd.engines.claude_code.registry import claude_config_dir, scan_registry
from shepherd.engines.claude_code.spawn import BINARY_NAME
from shepherd.host.base import HostPlatform
from shepherd.runner.tmux_cmd import (
    FORBIDDEN_SOCKET,
    THROWAWAY_SOCKET_RE,
    check_tmux_argv,
    permitted_commands,
    permitted_sockets,
)
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION
from shepherd.toolsurface.compose import SINK_PROGRAM

pytestmark = pytest.mark.live

CEILING_S = 20.0
REPO_ROOT = Path(__file__).resolve().parents[2]

def await_true(predicate: object, message: str, ceiling_s: float = CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def get(port: int, path: str) -> tuple[int, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=CEILING_S)
    try:
        connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    finally:
        connection.close()


def dispatch(path: Path, payload: bytes) -> None:
    """What the installed hook command does: connect, write, shut the write side."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)


# ----- posture ---------------------------------------------------------------


def test_the_lane_uses_the_real_config_dir_and_isolates_by_working_dir(
    throwaway: Throwaway,
) -> None:
    """F10, asserted rather than assumed: the posture this lane actually has."""
    assert os.environ.get("CLAUDE_CONFIG_DIR") in (None, str(real_config_dir()))
    assert claude_config_dir() == real_config_dir()

    argv = throwaway.argv("noop")
    assert "--settings" in argv
    assert argv[argv.index("--settings") + 1] == str(throwaway.settings)
    assert throwaway.settings != real_config_dir() / "settings.json"
    assert not throwaway.workdir.is_relative_to(Path.home() / ".claude")
    assert LIVE_MODEL == "claude-haiku-4-5"

    # The per-test guard is armed: this is the value it compares against.
    assert settings_digest() != ""


def test_every_tmux_call_in_the_live_lane_names_a_throwaway_socket() -> None:
    """T24's **narrower live second check** — the call-observing half of K6.

    `tests/boundaries/test_tmux_blast_radius.py` scans the tree's source and runs
    on the default sweep; this one watches the argvs the live lane actually
    **issues**, through the lane's own `make_run_argv`. The two catch different
    things, which is why both exist: a source scan cannot see
    `f"tm{'ux'}"`, and a call ledger cannot see an argv in a file nobody ran.

    Three assertions, in this order:

    1. **arrival** — a real tmux argv is issued here, so the ledger is non-empty.
       A scan of nothing finds nothing, and the emptiest ledger passes every rule
       below it. `list-sessions` against a socket with no server starts no server
       and contacts nothing;
    2. every argv recorded this session — by every module in this lane, not only
       this one — carries `-L` at argv[1:3] with a `^shepherd-m3-` socket;
    3. the exec site **refuses** the user's own socket, so the rule bites. That
       one is checked through `check_tmux_argv` directly rather than through the
       exec site: an argv naming `shepherd` must never reach a process, not even
       to be refused by it.
    """
    result = live_socket_listing()
    assert TMUX_CALLS, "no tmux argv was issued at all: this check would be vacuous"
    assert result.rc in (0, 1), result

    throwaway_socket = re.compile(THROWAWAY_SOCKET_RE)
    for argv in TMUX_CALLS:
        assert len(argv) > 2, argv
        assert argv[1] == "-L", f"a tmux argv with no explicit socket: {argv}"
        assert argv[2] != FORBIDDEN_SOCKET, f"the lane named the user's own socket: {argv}"
        assert throwaway_socket.fullmatch(argv[2]), (
            f"{argv[2]!r} is not a throwaway socket ({THROWAWAY_SOCKET_RE}): {argv}"
        )
    assert {argv[2] for argv in TMUX_CALLS} == {LIVE_TMUX_SOCKET}, {
        argv[2] for argv in TMUX_CALLS
    }

    # …and the rule bites. Built from the recorded argv rather than typed, so
    # this is the lane's own shape with one word changed.
    forbidden = [*TMUX_CALLS[0]]
    forbidden[2] = FORBIDDEN_SOCKET
    with pytest.raises(RunnerRefusal) as refused:
        check_tmux_argv(
            forbidden,
            permitted=permitted_sockets(LIVE_TMUX_SOCKET),
            commands=permitted_commands(SINK_PROGRAM, BINARY_NAME),
        )
    assert FORBIDDEN_SOCKET in refused.value.reason


# `test_no_tmux_is_invoked_at_all` used to live here, scanning this package's own
# literals. Its rule — CLAUDE.md rules 1-4 and §18's incident — is now
# `tests/boundaries/test_tmux_blast_radius.py`, which walks `src/`, `tests/` and
# `docs/probes/` recursively and checks the argv rather than the spelling, and
# which runs on the default sweep instead of only under `-m live`. The rule was
# replaced, not dropped: a lane-local scan could only ever see one directory, and
# the two one-liners that defeat a literal scan now ship as fixtures beside it.


# ----- 1. hookless discovery against this host -------------------------------


def test_hookless_discovery_sees_this_hosts_real_sessions(
    shepherd_host: HostPlatform,
) -> None:
    """Decision pressure 5's acceptance test, on the machine it exists for.

    No hook is installed anywhere. `controld` scans the user's real registry
    read-only and the rows land in a throwaway database. The page is then
    non-empty — which is the milestone's whole point.

    The *real registry* and the *throwaway database* are the two halves, and
    they used to be resolved from one place: `detect_host()` reads the process
    environment, which on macOS has to keep the engine's real `HOME` — so this
    docstring's "throwaway database" was false there and the rows landed in the
    operator's own `shepherd.db`. The registry now comes from the environment
    (real, as intended) and the database from the injected host (throwaway, as
    stated).
    """
    live, _ = scan_registry(claude_config_dir())
    if not live:
        pytest.skip("no live Claude Code sessions on this host right now")

    before = {path: path.stat().st_mtime_ns for path in claude_config_dir().glob("sessions/*")}

    started = controld.start(host=shepherd_host, port=0, engine_config_dir=None)
    try:
        await_true(
            lambda: json.loads(get(started.port, "/api/fleet/tree")[1])["data"]["session_count"]
            > 0,
            "the registry scan registered nothing from the real config dir",
        )
        data = json.loads(get(started.port, "/api/fleet/tree")[1])["data"]
        rows = [row for workspace in data["workspaces"] for row in workspace["sessions"]]
        known = {entry.cwd for entry in live}
        # Scoped to sessions the registry actually reported, never to a count.
        assert [row for row in rows if row["cwd"] in known]
        assert all(row["state"] in {"needs_you", "running", "starting", "stopped"} for row in rows)
        # Titles come from the registry's `name` on the hookless path (D29).
        assert any(row["title"] for row in rows)

        status, body = get(started.port, "/")
        assert status == 200 and "<title>Shepherd — fleet</title>" in body
    finally:
        controld.stop(started)

    after = {path: path.stat().st_mtime_ns for path in claude_config_dir().glob("sessions/*")}
    assert after == before, "the scan modified the user's registry — it must be read-only"


# ----- 2. the two-process hop, and the restart -------------------------------


def start_sessiond(shepherd_home: Path) -> subprocess.Popen[bytes]:
    """The real second process, with Shepherd's dirs pointed at a throwaway."""
    environment = dict(os.environ)
    for name in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        environment[name] = str(shepherd_home / name.lower())
    environment["XDG_RUNTIME_DIR"] = str(shepherd_home / "run")
    # `MacHost` reads `TMPDIR` rather than `XDG_RUNTIME_DIR`; without this the
    # child bound its ingest socket in the operator's real `$TMPDIR/Shepherd/`
    # while the parent looked for it under the throwaway.
    environment["TMPDIR"] = str(shepherd_home / "run")
    # …and `HOME`, so this child's `detect_host()` resolves the same directories
    # the parent injects as `shepherd_host`. Safe to redirect **here** and not in
    # the process environment: `sessiond` starts no engine, so nothing in this
    # subprocess needs the account record that a throwaway `HOME` would hide.
    environment["HOME"] = str(shepherd_home / SHEPHERD_HOME_DIRNAME)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
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


def test_sessiond_relays_and_the_buffer_drains_in_order_across_a_restart(
    shepherd_home: Path, shepherd_host: HostPlatform
) -> None:
    """D37/T10b with two real processes: `controld` restarts, nothing is lost,
    and the frames land in the order they were dispatched."""
    host = shepherd_host
    ingest_path = host.control_socket(INGEST_SOCKET_NAME).path
    control_path = host.control_socket(CONTROL_SOCKET_NAME).path

    started = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
    (shepherd_home / "engine" / "sessions").mkdir(parents=True, exist_ok=True)
    daemon = start_sessiond(shepherd_home)
    try:
        await_true(ingest_path.exists, "sessiond never bound its socket")

        dispatch(ingest_path, frame_payload("live-a"))
        await_true(lambda: session_count(started.port) == 1, "the first hop never landed")

        # `controld` goes away. `sessiond` keeps accepting and buffering (D37).
        controld.stop(started)
        assert not control_path.exists(), "controld left its socket behind (F15)"
        for name in ("live-b", "live-c", "live-d"):
            dispatch(ingest_path, frame_payload(name))

        restarted = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
        try:
            await_true(
                lambda: session_count(restarted.port) == 4,
                "the buffer did not drain after controld restarted",
            )
            rows = json.loads(get(restarted.port, "/api/sessions")[1])["data"]["sessions"]
        finally:
            controld.stop(restarted)
    finally:
        daemon.terminate()
        daemon.wait(timeout=CEILING_S)

    stamps = [row["last_event_at"] for row in rows]
    assert stamps == sorted(stamps), f"frames were applied out of order: {stamps}"
    assert not ingest_path.exists(), "sessiond left its socket behind (F15)"
    assert daemon.returncode == 0


def frame_payload(engine_session_id: str) -> bytes:
    return json.dumps(
        {
            "session_id": engine_session_id,
            "cwd": str(REPO_ROOT),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "prove the hop",
        }
    ).encode("utf-8") + b"\n"


def session_count(port: int) -> int:
    body = get(port, "/api/sessions")[1]
    sessions = json.loads(body)["data"]["sessions"]
    assert isinstance(sessions, list)
    return len(sessions)


# ----- 3. a real authenticated engine run ------------------------------------


def test_a_real_claude_run_is_authenticated_under_this_isolation(
    throwaway: Throwaway,
) -> None:
    """A16/E36: the posture F10 corrected the plan to. If this fails, the lane's
    isolation and its authentication are in conflict again and every other live
    assertion here is measuring a dead engine."""
    completed = throwaway.run("Reply with exactly: SHEPHERD_LIVE_OK")

    assert completed.returncode == 0, completed.stderr
    assert "SHEPHERD_LIVE_OK" in completed.stdout
    assert "Not logged in" not in completed.stdout + completed.stderr


def test_an_unhooked_p_run_is_not_registered_as_an_attached_session(
    throwaway: Throwaway, shepherd_host: HostPlatform
) -> None:
    """E35/RD9/C8 **through the discovery lane**: `entrypoint` is the
    discriminator there, and a `-p` run is not an attached interactive session.

    **The name says `unhooked` because that is the whole of what this checks.**
    It was `test_a_p_run_is_not_registered_as_an_attached_session` until T19
    proved live that a `-p` run *with the hook installed* does register, through
    the hook lane, and does reach the fleet tree — see **BLOCKER T19-1**. The two
    results do not contradict each other: this run installs no hook, so the only
    lane that can see it is discovery, which reads the registry and has
    `entrypoint`. The hook lane never does — `entrypoint` is absent from all 429
    captured hook payloads.

    The old name asserted a general property this test cannot reach, which is
    the one defect class this repo treats as non-negotiable.

    Asserted by `sessionId`, never by a count: the user's own sessions are in the
    same registry.
    """
    completed = throwaway.run("Reply with exactly: SHEPHERD_P_RUN")
    assert completed.returncode == 0, completed.stderr

    started = controld.start(host=shepherd_host, port=0, engine_config_dir=None)
    try:
        await_true(
            lambda: json.loads(get(started.port, "/api/fleet/tree")[1])["data"] is not None,
            "the tree never answered",
        )
        data = json.loads(get(started.port, "/api/fleet/tree")[1])["data"]
        rows = [row for workspace in data["workspaces"] for row in workspace["sessions"]]
    finally:
        controld.stop(started)

    assert not [row for row in rows if row["cwd"] == str(throwaway.workdir)], (
        "a -p run in a throwaway directory reached the fleet page"
    )


# ----- 4. the stream, live ----------------------------------------------------


def test_an_update_reaches_a_subscriber_over_sse_with_no_polling(
    shepherd_home: Path, shepherd_host: HostPlatform
) -> None:
    """§12: one connection, opened once, and the update is pushed onto it."""
    host = shepherd_host
    (shepherd_home / "engine" / "sessions").mkdir(parents=True, exist_ok=True)
    started = controld.start(host=host, port=0, engine_config_dir=shepherd_home / "engine")
    frames: list[str] = []
    connection = http.client.HTTPConnection("127.0.0.1", started.port, timeout=CEILING_S)
    try:
        connection.request(
            "GET", "/api/events", headers={"Host": f"127.0.0.1:{started.port}"}
        )
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/event-stream"

        reader = threading.Thread(target=_collect, args=(response, frames), daemon=True)
        reader.start()

        dispatch_through_control(started.control_socket_path, frame_payload("live-sse"))
        await_true(lambda: frames != [], "no SSE frame was pushed")
    finally:
        connection.close()
        controld.stop(started)

    assert any("event:" in frame or "data:" in frame for frame in frames)


def _collect(response: http.client.HTTPResponse, frames: list[str]) -> None:
    try:
        while True:
            raw = response.fp.readline() if response.fp else b""
            if raw == b"":
                return
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("data:"):
                frames.append(line)
    except OSError:
        return


def dispatch_through_control(control_path: Path, payload: bytes) -> None:
    """Speak the `sessiond` → `controld` wire directly: hello, then one frame."""
    from shepherd.engines.claude_code.relay import Relay

    relay = Relay(control_path, 100, EXPECTED_SCHEMA_VERSION)
    try:
        relay.send(Frame(payload=payload, received_at="2026-09-17T00:00:00Z", peer_pid=None))
        await_true(lambda: relay.stats().delivered == 1, "the frame was never delivered")
    finally:
        relay.close(5.0)
