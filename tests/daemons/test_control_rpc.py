"""D68 / ADR-QR-1: `controld`'s RPC listener, over a real Unix socket.

Seam: `serve_control_rpc(plan, shutdown, bound)` on one side and
`call_remote(path, name, args, ctx)` on the other — the two halves a `shepherd`
process and a running daemon actually have. The socket is real and lives under
the suite's short `tmp_path`; the registry is the real one, filled by each test.

PP5 is proved here (0600 in a 0700 dir) and PP15 (the socket name fits the
control socket's budget). Trust note (D68): the socket is owner-only, so **the
same uid is the same trust** as the loopback page — nothing here claims more.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from chokepoint_fixture import install_test_chokepoint

from shepherd.daemons.control_rpc import serve_control_rpc
from shepherd.daemons.sessiond import CONTROL_SOCKET_NAME
from shepherd.engines.claude_code.ingest_socket import bind_listener, release_claim
from shepherd.host.base import SocketPlan
from shepherd.host.linux import LINUX_SOCKET_PATH_BUDGET, SOCKET_DIR_MODE, SOCKET_MODE
from shepherd.toolsurface.registry import install_chokepoint, register, reset_registry
from shepherd.toolsurface.rpc import RPC_SOCKET_NAME, call_remote, encode_request
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    AuthzOutcome,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolDef,
    ToolResult,
)

CEILING_S = 5.0
CORRELATION_ID = "fedcba9876543210fedcba9876543210"

#: The client's own context. Its audience is **not** sent: the server forces
#: HUMAN, so a client that says MASTER is still a human on the other side.
CLIENT_CTX = CallerContext(audience=Audience.MASTER, caller_id="whoever", correlation_id=CORRELATION_ID)


@pytest.fixture(autouse=True)
def clean_registry() -> Iterator[None]:
    reset_registry()
    yield
    reset_registry()


def rpc_plan(tmp_path: Path) -> SocketPlan:
    return SocketPlan(
        path=tmp_path / "shepherd" / f"{RPC_SOCKET_NAME}.sock",
        dir_mode=SOCKET_DIR_MODE,
        sock_mode=SOCKET_MODE,
        socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
    )


def whoami(args: ToolArgs, ctx: CallerContext) -> object:
    return {"audience": ctx.audience.value, "caller_id": ctx.caller_id, "args": dict(args)}


def register_whoami(blast_class: BlastClass = BlastClass.LOCAL_READ) -> None:
    register(
        ToolDef(
            name="whoami",
            description="says who called it",
            input_schema={"type": "object", "properties": {"n": {"type": "integer"}}},
            blast_class=blast_class,
            handler=whoami,
            audiences=frozenset({Audience.HUMAN}),
        )
    )


@contextmanager
def serving(plan: SocketPlan) -> Iterator[threading.Thread]:
    shutdown, bound = threading.Event(), threading.Event()
    thread = threading.Thread(
        target=serve_control_rpc,
        kwargs={"plan": plan, "shutdown": shutdown, "bound": bound},
        name="rpc",
        daemon=True,
    )
    thread.start()
    try:
        assert bound.wait(CEILING_S), "the RPC listener never bound"
        yield thread
    finally:
        shutdown.set()
        thread.join(CEILING_S)
        assert not thread.is_alive(), "the RPC listener did not exit on shutdown"


def test_a_call_round_trips_through_the_socket(tmp_path: Path) -> None:
    register_whoami()
    plan = rpc_plan(tmp_path)
    with serving(plan):
        result = call_remote(plan.path, "whoami", {"n": 1}, CLIENT_CTX)

    assert result == ToolResult(
        ok=True, data={"audience": "human", "caller_id": "cli", "args": {"n": 1}}, error=None
    )
    # F15: the listener's `finally` unlinked what it bound.
    assert not plan.path.exists()


def test_the_socket_is_0600_in_a_0700_dir(tmp_path: Path) -> None:
    """PP5. Read off the file the listener bound, not off the plan."""
    plan = rpc_plan(tmp_path)
    with serving(plan):
        socket_mode = stat.S_IMODE(os.stat(plan.path).st_mode)
        dir_mode = stat.S_IMODE(os.stat(plan.path.parent).st_mode)
        assert stat.S_ISSOCK(os.stat(plan.path).st_mode)

    assert (socket_mode, dir_mode) == (0o600, 0o700), (oct(socket_mode), oct(dir_mode))


def test_no_daemon_is_none_not_an_error(tmp_path: Path) -> None:
    """No socket file, and a stale file nobody listens on: both are "no daemon",
    so the caller falls back to its own `invoke` rather than failing."""
    plan = rpc_plan(tmp_path)
    assert call_remote(plan.path, "whoami", {}, CLIENT_CTX) is None

    plan.path.parent.mkdir(parents=True)
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(plan.path))
    stale.close()  # the file stays; nothing accepts on it
    assert plan.path.exists()
    assert call_remote(plan.path, "whoami", {}, CLIENT_CTX) is None


def test_a_peer_that_hangs_up_early_harms_nothing(tmp_path: Path) -> None:
    """E-QR-2: a probe, a half request, a garbage request — then a real call
    still answers. The peer loses its connection, never the daemon."""
    register_whoami()
    plan = rpc_plan(tmp_path)
    with serving(plan) as thread:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.connect(str(plan.path))  # connect and close, unread
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as half:
            half.connect(str(plan.path))
            half.sendall(encode_request("whoami", {}, CORRELATION_ID)[:10])
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as reset:
            reset.connect(str(plan.path))
            reset.sendall(encode_request("whoami", {}, CORRELATION_ID))
            reset.shutdown(socket.SHUT_WR)
            # closes without reading the reply

        result = call_remote(plan.path, "whoami", {}, CLIENT_CTX)
        assert thread.is_alive()

    assert result is not None and result.ok is True, result


def test_a_reply_the_client_cannot_read_is_a_failed_result(tmp_path: Path) -> None:
    """Any failure after the connect is FAILED and names its class — never a
    `None` that would silently fall back to a local answer."""
    plan = rpc_plan(tmp_path)
    plan.path.parent.mkdir(parents=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(plan.path))
    listener.listen(1)

    def garbage() -> None:
        conn, _ = listener.accept()
        with conn:
            # Read to the client's EOF first: a single recv can close before the request is
            # all in, and the client then fails on send, not on the reply (flaked 2 in 20).
            while conn.recv(65_536):
                pass
            conn.sendall(b"this is no reply")

    server = threading.Thread(target=garbage, daemon=True)
    server.start()
    try:
        result = call_remote(plan.path, "whoami", {}, CLIENT_CTX, timeout_s=CEILING_S)
    finally:
        server.join(CEILING_S)
        listener.close()

    assert result is not None
    assert result.ok is False and result.failure is Failure.FAILED
    assert result.error is not None and result.error.startswith("the daemon did not answer: "), result


def test_a_human_rpc_call_is_audited_like_the_web_ui(tmp_path: Path) -> None:
    """One call, one audit row, as HUMAN `cli` — `invoke` audits it exactly as
    it audits the web UI's calls, because it is the same `invoke`."""
    records = install_test_chokepoint()
    register_whoami(BlastClass.LOCAL_WRITE)
    plan = rpc_plan(tmp_path)
    with serving(plan):
        result = call_remote(plan.path, "whoami", {}, CLIENT_CTX)

    assert result is not None and result.ok is True, result
    assert [(r.tool, r.actor_kind, r.actor_id, r.correlation_id) for r in records] == [
        ("whoami", ActorKind.HUMAN, "cli", CORRELATION_ID)
    ]


def test_the_rpc_socket_name_fits_the_control_sockets_budget() -> None:
    """PP15: wherever `controld.sock` fits, `rpc.sock` fits, so the second
    socket can never be the one that makes a working host refuse to start."""
    assert RPC_SOCKET_NAME == "rpc"
    assert len(RPC_SOCKET_NAME) <= len(CONTROL_SOCKET_NAME)


def test_two_listeners_binding_at_once_leave_the_process_umask_alone(tmp_path: Path) -> None:
    """D68's second listener binds on its own thread beside the ingest one, and
    `umask` is process-global: two unserialised save/set/restore pairs can
    interleave and leave the process at the socket's `0o177`, after which every
    directory it makes is `0600` and cannot be entered. Many binds at once,
    then the umask is the one the process started with."""
    workers, rounds = 16, 20
    start = threading.Barrier(workers)
    errors: list[BaseException] = []

    def bind_many(worker: int) -> None:
        try:
            start.wait(CEILING_S)
            for turn in range(rounds):
                plan = SocketPlan(
                    path=tmp_path / f"w{worker}" / f"{turn}.sock",
                    dir_mode=SOCKET_DIR_MODE,
                    sock_mode=SOCKET_MODE,
                    socket_path_budget=LINUX_SOCKET_PATH_BUDGET,
                )
                bind_listener(plan).close()
                release_claim(plan.path)
        except BaseException as error:  # collected, asserted below
            errors.append(error)

    previous = os.umask(0o022)
    try:
        threads = [threading.Thread(target=bind_many, args=(n,)) for n in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(CEILING_S * 4)
        after = os.umask(0o022)
    finally:
        os.umask(previous)

    assert errors == []
    assert after == 0o022, oct(after)


# --- REM-FIX 1: the listener outlives any one request -------------------------


def send_raw(path: Path, raw: bytes) -> bytes:
    """One raw request, one reply read to EOF — what a hostile peer can send."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(CEILING_S)
        conn.connect(str(path))
        conn.sendall(raw)
        conn.shutdown(socket.SHUT_WR)
        chunks = []
        while chunk := conn.recv(65_536):
            chunks.append(chunk)
    return b"".join(chunks)


def test_a_request_nested_past_the_recursion_limit_leaves_the_listener_serving(
    tmp_path: Path,
) -> None:
    """`json.loads` raises `RecursionError` on `[` × 200000; it used to escape
    `answer_request`, kill the thread and unlink `rpc.sock`."""
    register_whoami()
    plan = rpc_plan(tmp_path)
    with serving(plan) as thread:
        refused = json.loads(send_raw(plan.path, b"[" * 200_000))
        after = call_remote(plan.path, "whoami", {}, CLIENT_CTX)
        assert thread.is_alive()

    assert refused["ok"] is False and refused["failure"] == "refused", refused
    assert after is not None and after.ok is True, after


def test_an_authorizer_that_raises_is_answered_failed_and_the_listener_keeps_serving(
    tmp_path: Path,
) -> None:
    """H-1: an exception out of `invoke`'s own path (a corrupt `app_state` row
    the gate reads, a `sqlite3.Error` from the audit write) is a FAILED reply
    carrying the correlation id — and the next call on the same listener answers."""

    def authorizer(tool: ToolDef, args: ToolArgs, ctx: CallerContext) -> AuthzOutcome:
        if tool.name == "boom":
            raise RuntimeError("secret detail from the traceback")
        return AuthzOutcome(allowed=True, approved_by=None, approval_id=None, reason=None)

    register_whoami()
    register(
        ToolDef(
            name="boom",
            description="its gate raises",
            input_schema={"type": "object", "properties": {}},
            blast_class=BlastClass.LOCAL_READ,
            handler=whoami,
            audiences=frozenset({Audience.HUMAN}),
        )
    )
    install_chokepoint(authorizer, lambda record: None)
    plan = rpc_plan(tmp_path)
    with serving(plan) as thread:
        failed = call_remote(plan.path, "boom", {}, CLIENT_CTX)
        after = call_remote(plan.path, "whoami", {}, CLIENT_CTX)
        assert thread.is_alive()

    assert failed is not None and failed.failure is Failure.FAILED, failed
    assert failed.error is not None and failed.error.endswith(f"(correlation_id={CORRELATION_ID})")
    assert "secret" not in failed.error
    assert after is not None and after.ok is True, after


def test_a_failure_after_sending_keeps_its_detail_not_only_its_class(tmp_path: Path) -> None:
    """M-4: `ReplyMalformed("not a version-1 reply")` says more than `ReplyMalformed`."""
    plan = rpc_plan(tmp_path)
    plan.path.parent.mkdir(parents=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(plan.path))
    listener.listen(1)

    def garbage() -> None:
        conn, _ = listener.accept()
        with conn:
            # Read to the client's EOF first: a single recv can close before the request is
            # all in, and the client then fails on send, not on the reply (flaked 2 in 20).
            while conn.recv(65_536):
                pass
            conn.sendall(b"this is no reply")

    server = threading.Thread(target=garbage, daemon=True)
    server.start()
    try:
        result = call_remote(plan.path, "whoami", {}, CLIENT_CTX, timeout_s=CEILING_S)
    finally:
        server.join(CEILING_S)
        listener.close()

    assert result is not None and result.error is not None
    assert result.error == "the daemon did not answer: ReplyMalformed: not a version-1 reply", result


def test_a_connect_that_fails_is_worded_not_sent(tmp_path: Path) -> None:
    """M-4: a failure before any byte left is "not sent" — nothing ran, so the
    caller is not told the call may be half done."""
    plan = rpc_plan(tmp_path)
    plan.path.parent.mkdir(parents=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(plan.path))
    listener.listen(1)
    plan.path.parent.chmod(0o000)  # the socket is there; this uid may not reach it
    try:
        result = call_remote(plan.path, "whoami", {}, CLIENT_CTX, timeout_s=CEILING_S)
    finally:
        plan.path.parent.chmod(0o700)
        listener.close()

    assert result is not None and result.failure is Failure.FAILED, result
    assert result.error is not None
    assert result.error.startswith("the daemon did not answer: not sent — PermissionError: "), result


def test_a_request_that_cannot_be_encoded_is_not_sent(tmp_path: Path) -> None:
    deep: object = []
    for _ in range(200_000):
        deep = [deep]
    plan = rpc_plan(tmp_path)
    register_whoami()
    with serving(plan):
        result = call_remote(plan.path, "whoami", {"n": deep}, CLIENT_CTX)
        after = call_remote(plan.path, "whoami", {}, CLIENT_CTX)

    assert result is not None and result.failure is Failure.FAILED, result
    assert result.error is not None
    assert result.error.startswith("the daemon did not answer: not sent — RecursionError: "), result
    assert after is not None and after.ok is True
