"""T10: the process that must not restart, doing the least possible.

Real sockets under `tmp_path`, never `$XDG_RUNTIME_DIR` — the user's live
sessions own that directory. Every mode, every errno and the 40 KB frame here
has a capture behind it in data-schemas §"Unix domain socket at mode 0600 +
`SO_PEERCRED`" (E20, E21).
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from shepherd.core.clock import parse_stamp
from shepherd.core.frames import Frame
from shepherd.daemons.control_ingest import serve_control_ingest
from shepherd.engines.claude_code.ingest_socket import (
    SHUTDOWN_DRAIN_S,
    serve_ingest,
)
from shepherd.engines.claude_code.relay import RELAY_BUFFER_MAX, Relay
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

#: A real corpus payload (data-schemas §"Common input fields", first example).
CORPUS_PAYLOAD = (
    b'{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","cwd":'
    b'"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"PreToolUse","tool_name":"Bash"}\n'
)

#: Result 2 of `docs/probes/2026-09-16-hookd-latency.md`: 40 KB arrives complete.
FRAME_40KB = b'{"pad":"' + b"x" * 40_000 + b'"}\n'

STARTUP_CEILING_S = 2.0


def plan_for(tmp_path: Path) -> SocketPlan:
    """A `SocketPlan` with the real Linux modes and budget, pointed at `tmp_path`."""
    return SocketPlan(
        path=tmp_path / "shepherd" / "sessiond.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


class Collector:
    """Frames the listener handed us, in arrival order."""

    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.lock = threading.Lock()
        self.shutdown_calls = 0

    def on_frame(self, frame: Frame) -> None:
        with self.lock:
            self.frames.append(frame)

    def on_shutdown(self) -> None:
        self.shutdown_calls += 1

    def count(self) -> int:
        with self.lock:
            return len(self.frames)


@contextmanager
def listening(plan: SocketPlan, collector: Collector) -> Iterator[threading.Event]:
    """`serve_ingest` on a background thread, torn down the way `sessiond` does."""
    stop = threading.Event()
    thread = threading.Thread(
        target=serve_ingest,
        args=(plan, collector.on_frame, collector.on_shutdown, stop),
        daemon=True,
    )
    thread.start()
    await_true(plan.path.exists, "the socket was never bound")
    try:
        yield stop
    finally:
        stop.set()
        thread.join(timeout=SHUTDOWN_DRAIN_S + STARTUP_CEILING_S)
        assert not thread.is_alive(), "serve_ingest did not return after shutdown"


def await_true(predicate: object, message: str, ceiling_s: float = STARTUP_CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(message)


def dispatch(path: Path, payload: bytes) -> None:
    """What the hook's dispatcher does: connect, write, shut the write side."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)


def accepts_connections(path: Path) -> bool:
    """Is something listening *now*? A stale file exists but refuses (E20), and
    an inode number is reused across unlink-and-rebind, so this is the only
    honest readiness signal."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))
    except (ConnectionRefusedError, FileNotFoundError):
        return False
    return True


def test_socket_is_0600_in_0700_dir(tmp_path: Path) -> None:
    """E20: the mode is set by `umask` **before** `bind()` — there is no chmod
    window — and the containing directory is 0700 (§15 l.2219)."""
    plan = plan_for(tmp_path)
    collector = Collector()
    previous_umask = os.umask(0o022)  # the default that produced 0755 in the capture
    try:
        with listening(plan, collector):
            mode = stat.S_IMODE(plan.path.stat().st_mode)
            dir_mode = stat.S_IMODE(plan.path.parent.stat().st_mode)
            assert stat.S_ISSOCK(plan.path.stat().st_mode)
            assert mode == 0o600, f"socket is {mode:04o}, not 0600"
            assert dir_mode == 0o700, f"directory is {dir_mode:04o}, not 0700"
        assert os.umask(0o022) == 0o022, "the process umask was not restored"
    finally:
        os.umask(previous_umask)


def test_stale_socket_is_unlinked_before_bind(tmp_path: Path) -> None:
    """E20: a stale socket file gives `EADDRINUSE` on re-bind. Unlink first."""
    plan = plan_for(tmp_path)
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(plan.path))
    stale.close()  # the file survives the close: that is what "stale" means
    assert plan.path.exists()
    with pytest.raises(ConnectionRefusedError):
        dispatch(plan.path, CORPUS_PAYLOAD)  # E20: a stale path refuses clients

    collector = Collector()
    with listening(plan, collector):
        await_true(
            lambda: accepts_connections(plan.path),
            "the stale socket was never replaced by a listening one",
        )
        dispatch(plan.path, CORPUS_PAYLOAD)
        await_true(lambda: collector.count() == 1, "the rebound socket accepted nothing")


def test_frames_are_read_to_eof(tmp_path: Path) -> None:
    """The dispatcher writes and closes; the listener must read to EOF, not to
    the first short read. The payload is sent in two writes with a gap."""
    plan = plan_for(tmp_path)
    collector = Collector()
    with listening(plan, collector):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(plan.path))
            client.sendall(CORPUS_PAYLOAD[:20])
            time.sleep(0.05)
            client.sendall(CORPUS_PAYLOAD[20:])
            client.shutdown(socket.SHUT_WR)
        await_true(lambda: collector.count() == 1, "no frame arrived")
    assert collector.frames[0].payload == CORPUS_PAYLOAD
    # C8: the receiver stamps the frame, in the one format the liveness
    # backstop reads (`core.clock`). A spelling it cannot read is BLOCKING 1.
    assert parse_stamp(collector.frames[0].received_at) is not None


def test_40kb_frame_is_complete(tmp_path: Path) -> None:
    """Result 2: a 40 KB frame was verified delivered byte-complete."""
    plan = plan_for(tmp_path)
    collector = Collector()
    with listening(plan, collector):
        dispatch(plan.path, FRAME_40KB)
        await_true(lambda: collector.count() == 1, "no frame arrived")
    assert collector.frames[0].payload == FRAME_40KB
    assert len(collector.frames[0].payload) == len(FRAME_40KB)


def test_restart_after_clean_shutdown_binds_without_eaddrinuse(tmp_path: Path) -> None:
    """F15 + E20: the socket is gone after a clean exit, so the next start binds."""
    plan = plan_for(tmp_path)
    first = Collector()
    with listening(plan, first):
        dispatch(plan.path, CORPUS_PAYLOAD)
        await_true(lambda: first.count() == 1, "no frame arrived")
    assert not plan.path.exists(), "the socket outlived a clean shutdown"
    assert first.shutdown_calls == 1

    second = Collector()
    with listening(plan, second):
        dispatch(plan.path, CORPUS_PAYLOAD)
        await_true(lambda: second.count() == 1, "the restarted listener accepted nothing")
    assert not plan.path.exists()


def test_shutdown_drains_the_relay_within_the_window(tmp_path: Path) -> None:
    """F15: shutdown stops accepting, gives the relay a bounded drain window,
    and only then unlinks. Frames buffered while `controld` was down are the
    ones that prove the window is doing something."""
    ingest = plan_for(tmp_path)
    control = SocketPlan(
        path=tmp_path / "shepherd" / "controld.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )
    relay = Relay(control.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=(0.01, 0.05))
    received: list[Frame] = []
    lock = threading.Lock()

    def collect(frame: Frame) -> None:
        with lock:
            received.append(frame)

    def count() -> int:
        with lock:
            return len(received)

    stop = threading.Event()
    listener = threading.Thread(
        target=serve_ingest,
        args=(ingest, relay.send, lambda: relay.close(SHUTDOWN_DRAIN_S), stop),
        daemon=True,
    )
    listener.start()
    await_true(lambda: accepts_connections(ingest.path), "sessiond never bound")

    for index in range(5):
        dispatch(ingest.path, b'{"n":%d}\n' % index)
    await_true(lambda: relay.stats().buffered == 5, "the frames were not buffered")

    control_stop = threading.Event()
    controld = threading.Thread(
        target=serve_control_ingest,
        args=(control, EXPECTED_SCHEMA_VERSION, collect, control_stop),
        daemon=True,
    )
    controld.start()
    await_true(control.path.exists, "controld never bound")

    started = time.monotonic()
    stop.set()
    listener.join(timeout=SHUTDOWN_DRAIN_S + STARTUP_CEILING_S)
    elapsed = time.monotonic() - started
    control_stop.set()
    controld.join(timeout=STARTUP_CEILING_S)

    assert not listener.is_alive()
    assert elapsed <= SHUTDOWN_DRAIN_S + 0.5, f"shutdown took {elapsed:.2f}s"
    assert count() == 5, "the drain window delivered nothing"
    assert [frame.payload for frame in received] == [b'{"n":%d}\n' % i for i in range(5)]
    assert not ingest.path.exists(), "the socket outlived the drain"


def test_sigterm_unlinks_the_socket(tmp_path: Path) -> None:
    """F15/E20, in a real process with a real signal: `SIGTERM` exits 0 and
    leaves no socket behind, so the next start binds instead of `EADDRINUSE`.

    The runtime directory is `tmp_path` — never the real one: the user's live
    sessions own `$XDG_RUNTIME_DIR/shepherd/`.
    """
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = str(tmp_path)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    socket_path = tmp_path / "shepherd" / "sessiond.sock"

    process = subprocess.Popen(
        [
            os.environ.get("PYTHON", "python3"),
            "-m",
            "shepherd.daemons.sessiond",
            "--expected-schema-version",
            str(EXPECTED_SCHEMA_VERSION),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        await_true(lambda: accepts_connections(socket_path), "sessiond never bound", 10.0)
        dispatch(socket_path, CORPUS_PAYLOAD)
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=SHUTDOWN_DRAIN_S + 10.0)
    finally:
        if process.poll() is None:  # pragma: no cover - only on a hung daemon
            process.kill()
            process.wait(timeout=5)
    assert process.returncode == 0, f"exit {process.returncode}: {stdout}{stderr}"
    assert not socket_path.exists(), "SIGTERM left the socket behind"


@pytest.mark.skipif(
    os.getuid() != 0 or shutil.which("runuser") is None,
    reason="needs a second uid: the capture used `runuser -u nobody`",
)
def test_other_uid_cannot_connect(tmp_path: Path) -> None:
    """E21: uid `nobody` gets `EACCES` on a 0600 socket in a 0700 directory."""
    plan = plan_for(tmp_path)
    collector = Collector()
    os.chmod(tmp_path, 0o755)
    with listening(plan, collector):
        probe = (
            "import socket,sys\n"
            "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)\n"
            "try:\n"
            f"    s.connect({str(plan.path)!r})\n"
            "except PermissionError as e:\n"
            "    print('EACCES', e.errno); sys.exit(0)\n"
            "print('CONNECTED'); sys.exit(1)\n"
        )
        completed = subprocess.run(
            ["runuser", "-u", "nobody", "--", "python3", "-c", probe],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "EACCES 13" in completed.stdout
        assert collector.count() == 0
