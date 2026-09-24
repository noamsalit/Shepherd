"""qa6 BC-16: a live socket is never stolen, and probing it harms nothing.

Seam: `claim_socket` / `bind_listener` (unit) and the two real listener loops,
`serve_control_ingest` and `serve_ingest` (integration, in-process). Every
socket lives under the per-test `tmp_path`, which `tests/conftest.py` keeps
inside the macOS 103-byte `AF_UNIX` budget; nothing here connects to a path
outside it.

The probe's shape is the one `claim_socket` itself uses: connect, then close
without reading a byte. A live owner must survive any number of those — the
refusal path must not become the theft it refuses (PP-G).
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from shepherd.core.frames import Frame
from shepherd.daemons.control_ingest import serve_control_ingest
from shepherd.engines.claude_code import ingest_socket
from shepherd.engines.claude_code.ingest_socket import bind_listener, serve_ingest
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE
from shepherd.store.migrate import EXPECTED_SCHEMA_VERSION

CEILING_S = 5.0
PROBES = 5
FRAME = b'{"hook_event_name":"PreToolUse","session_id":"s-1"}\n'


def plan_for(tmp_path: Path, name: str = "controld") -> SocketPlan:
    return SocketPlan(
        path=tmp_path / "shepherd" / f"{name}.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


def probe(path: Path) -> None:
    """Connect and close without reading — exactly what a liveness probe does."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(path))


def hello_from(path: Path) -> bytes | None:
    """The owner's greeting line, or `None` when nobody greets us."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(CEILING_S)
            client.connect(str(path))
            received = b""
            while b"\n" not in received:
                chunk = client.recv(4096)
                if not chunk:
                    return None
                received += chunk
            return received
    except OSError:
        return None


def send_frame(path: Path, payload: bytes) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(CEILING_S)
        client.connect(str(path))
        client.sendall(payload)
        client.shutdown(socket.SHUT_WR)


def await_true(predicate: Callable[[], bool], message: str) -> None:
    deadline = time.monotonic() + CEILING_S
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(message)


def claim_refusal(plan: SocketPlan) -> BaseException | None:
    """What `claim_socket` raised, or `None` when it handed the plan back."""
    try:
        ingest_socket.claim_socket(plan)
    except Exception as raised:  # noqa: BLE001 - the type is asserted by the caller
        return raised
    return None


def test_probing_a_live_control_ingest_leaves_the_owner_serving(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    shutdown, bound = threading.Event(), threading.Event()
    frames: list[Frame] = []
    owner = threading.Thread(
        target=serve_control_ingest,
        kwargs={"plan": plan, "schema_version": EXPECTED_SCHEMA_VERSION,
                "on_frame": frames.append, "shutdown": shutdown, "bound": bound},
        daemon=True,
    )
    owner.start()
    try:
        assert bound.wait(CEILING_S), "the owner never bound"
        inode = os.stat(plan.path).st_ino

        for _ in range(PROBES):
            probe(plan.path)

        greeting = hello_from(plan.path)
        assert greeting is not None, "the owner stopped greeting after a connect-and-close probe"
        assert b'"schema_version"' in greeting
        assert owner.is_alive(), "the owner's accept loop ended after a probe"
        assert plan.path.exists() and os.stat(plan.path).st_ino == inode

        refusal = claim_refusal(plan)
        assert isinstance(refusal, ingest_socket.SocketInUse), refusal
        assert str(plan.path) in str(refusal)
        assert hello_from(plan.path) is not None, "claim_socket's own probe harmed the owner"
        assert owner.is_alive() and os.stat(plan.path).st_ino == inode
    finally:
        shutdown.set()
        owner.join(CEILING_S)
    assert not owner.is_alive()


def test_probing_a_live_ingest_listener_leaves_it_serving(tmp_path: Path) -> None:
    plan = plan_for(tmp_path, "sessiond")
    shutdown = threading.Event()
    frames: list[Frame] = []
    owner = threading.Thread(
        target=serve_ingest,
        kwargs={"plan": plan, "on_frame": frames.append, "on_shutdown": lambda: None,
                "shutdown": shutdown},
        daemon=True,
    )
    owner.start()
    try:
        await_true(plan.path.exists, "the ingest listener never bound")
        inode = os.stat(plan.path).st_ino

        for _ in range(PROBES):
            probe(plan.path)
        refusal = claim_refusal(plan)
        assert isinstance(refusal, ingest_socket.SocketInUse), refusal

        send_frame(plan.path, FRAME)
        await_true(lambda: len(frames) == 1, "a frame sent after the probe was not delivered")
        assert frames[0].payload == FRAME
        assert owner.is_alive() and os.stat(plan.path).st_ino == inode
    finally:
        shutdown.set()
        owner.join(CEILING_S)
    assert not owner.is_alive()


def test_a_second_bind_does_not_steal_a_live_socket(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    first = bind_listener(plan)
    try:
        inode = os.stat(plan.path).st_ino
        second: socket.socket | None = None
        raised: BaseException | None = None
        try:
            second = bind_listener(plan)
        except Exception as error:  # noqa: BLE001 - the type is asserted below
            raised = error
        if second is not None:
            second.close()

        assert os.stat(plan.path).st_ino == inode, "the second bind unlinked and rebound the path"
        assert isinstance(raised, ingest_socket.SocketInUse), raised

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(plan.path))
            first.settimeout(CEILING_S)
            accepted, _ = first.accept()
            accepted.close()
    finally:
        first.close()


def test_a_stale_socket_file_is_reclaimed(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    plan.path.parent.mkdir(parents=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(plan.path))
    stale.close()  # the file stays behind, and nobody listens on it
    assert plan.path.exists()

    assert ingest_socket.claim_socket(plan) is plan

    reclaimed = bind_listener(plan)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(plan.path))
    finally:
        reclaimed.close()


def test_an_absent_socket_is_claimed(tmp_path: Path) -> None:
    plan = plan_for(tmp_path)
    assert not plan.path.exists()
    assert ingest_socket.claim_socket(plan) is plan


def test_socket_in_use_is_not_an_oserror() -> None:
    """`controld.main` reads any `OSError` as a held port; this refusal is not one."""
    assert not issubclass(ingest_socket.SocketInUse, OSError)
