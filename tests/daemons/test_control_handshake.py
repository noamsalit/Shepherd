"""T10b: the handshake §7 migration rule 3 requires, over a real socket.

`sessiond` never migrates. It waits for `controld` — the only process that
owns the database (D37) — to report the schema version over the UDS, and it
relays nothing until that version is the one it expects. Two processes racing
one migration is the bug you cannot debug at 2am.
"""

from __future__ import annotations

import os
import socket
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from shepherd.core.frames import Frame
from shepherd.daemons.control_ingest import serve_control_ingest
from shepherd.engines.claude_code.relay import RELAY_BUFFER_MAX, Relay
from shepherd.engines.claude_code.relay_wire import Hello, encode_hello
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

CEILING_S = 3.0
QUIET_S = 0.3
FAST_BACKOFF = (0.01, 0.05)

FRAME_40KB = Frame(
    payload=b'{"pad":"' + b"x" * 40_000 + b'"}\n',
    received_at="2026-09-16T00:00:00+00:00",
    peer_pid=4048291,
)


def control_plan(tmp_path: Path) -> SocketPlan:
    return SocketPlan(
        path=tmp_path / "shepherd" / "controld.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


def await_true(predicate: object, message: str, ceiling_s: float = CEILING_S) -> None:
    assert callable(predicate)
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(message)


class Received:
    def __init__(self) -> None:
        self.frames: list[Frame] = []
        self.lock = threading.Lock()

    def on_frame(self, frame: Frame) -> None:
        with self.lock:
            self.frames.append(frame)

    def count(self) -> int:
        with self.lock:
            return len(self.frames)


@contextmanager
def controld(plan: SocketPlan, received: Received, schema_version: int) -> Iterator[None]:
    """The real `controld` half: `serve_control_ingest` on a thread."""
    stop = threading.Event()
    thread = threading.Thread(
        target=serve_control_ingest,
        args=(plan, schema_version, received.on_frame, stop),
        daemon=True,
    )
    thread.start()
    await_true(plan.path.exists, "controld never bound its socket")
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=CEILING_S)
        assert not thread.is_alive()


@contextmanager
def silent_listener(plan: SocketPlan, hello: bytes | None) -> Iterator[None]:
    """A `controld` that accepts and then either says nothing or lies.

    Not a mock of the relay's collaborators: it is the real socket, speaking a
    wrong dialect. That is the only way to observe "waits for hello".
    """
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(plan.path.parent, plan.dir_mode)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(plan.path))
    listener.listen(8)
    listener.settimeout(0.05)
    stop = threading.Event()
    seen: list[bytes] = []

    def run() -> None:
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except (TimeoutError, socket.timeout):
                continue
            with conn:
                if hello is not None:
                    conn.sendall(hello)
                conn.settimeout(0.05)
                while not stop.is_set():
                    try:
                        chunk = conn.recv(65536)
                    except (TimeoutError, socket.timeout):
                        continue
                    except OSError:
                        break
                    if not chunk:
                        break
                    seen.append(chunk)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=CEILING_S)
        listener.close()
        plan.path.unlink(missing_ok=True)
        assert seen == [], f"the relay sent bytes before a valid hello: {seen!r}"


def test_controld_socket_is_0600_in_0700_dir(tmp_path: Path) -> None:
    """E20/E21: `controld` creates and owns its own socket, under the same rules."""
    plan = control_plan(tmp_path)
    received = Received()
    previous = os.umask(0o022)
    try:
        with controld(plan, received, EXPECTED_SCHEMA_VERSION):
            assert stat.S_IMODE(plan.path.stat().st_mode) == 0o600
            assert stat.S_IMODE(plan.path.parent.stat().st_mode) == 0o700
    finally:
        os.umask(previous)


def test_relay_frame_roundtrip_40kb(tmp_path: Path) -> None:
    """A 40 KB payload survives the hop byte-complete, over a real socket."""
    plan = control_plan(tmp_path)
    received = Received()
    with controld(plan, received, EXPECTED_SCHEMA_VERSION):
        relay = Relay(plan.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
        relay.send(FRAME_40KB)
        await_true(lambda: received.count() == 1, "the 40 KB frame never arrived")
        stats = relay.close(1.0)
    assert received.frames[0] == FRAME_40KB
    assert stats.delivered == 1
    assert stats.buffered == 0


def test_relay_waits_for_hello_before_sending(tmp_path: Path) -> None:
    """§7 rule 3: no hello, no frames — they are held, not sent and not lost."""
    plan = control_plan(tmp_path)
    with silent_listener(plan, hello=None):
        relay = Relay(plan.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
        relay.send(FRAME_40KB)
        time.sleep(QUIET_S)
        stats = relay.stats()
        assert stats.buffered == 1, "the frame was not held while the hello was missing"
        assert stats.delivered == 0
        assert not stats.connected
        relay.close(0.1)


def test_relay_refuses_on_schema_version_mismatch(tmp_path: Path) -> None:
    """§7 rule 3: a version that is not ours means buffer and count — never
    relay, never migrate. `sessiond` is not the process that owns the schema."""
    plan = control_plan(tmp_path)
    wrong = encode_hello(Hello(schema_version=EXPECTED_SCHEMA_VERSION + 1, pid=os.getpid()))
    with silent_listener(plan, hello=wrong):
        relay = Relay(plan.path, RELAY_BUFFER_MAX, EXPECTED_SCHEMA_VERSION, backoff=FAST_BACKOFF)
        relay.send(FRAME_40KB)
        await_true(
            lambda: relay.stats().schema_mismatch > 0,
            "the version mismatch was never counted",
        )
        stats = relay.stats()
        assert stats.buffered == 1
        assert stats.delivered == 0
        assert not stats.connected
        assert stats.last_error is not None and str(EXPECTED_SCHEMA_VERSION + 1) in stats.last_error
        relay.close(0.1)
