"""P12 / D76 (ruling 18, SD-05): a typed frame on the terminal socket reaches the pane.

Seam: the HTTP/WebSocket wire — a raw socket to a real `FleetServer` on
loopback port 0 (the `client` fixture), wired through `invoke()` to the
scripted runner. Nothing here reaches into a handler; what is observed is the
runner's own record of what it was handed (`ScriptedRunner.writes`) and the
audit sink the composition root would install.

ADR-QR-4's shape is what is under test: the **open** is the audited
`invoke("terminal_stream")`, and the keystrokes go through the handle it
returned — so they are not tool calls and write no audit row (D40, PP11).

Every wait is bounded (`BOUND_S`) and asserted, so a reader thread that never
ends is a red test rather than a hung suite.
"""

from __future__ import annotations

import os
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from chokepoint_fixture import install_test_chokepoint
from web.conftest import Client
from runner.test_local_write_chunks import RecordingTmux
from web.terminal_input_fixture import HoldingRunner
from web.test_routes_m3 import owned

from shepherd.store.db import Store
from shepherd.testkit.scripted_runner import ScriptedRunner

BOUND_S = 5.0

#: The name `web/server.py` gives the one reader thread per connection. Spelled
#: here rather than imported, so the test does not agree with the code by
#: construction.
READER_THREAD = "shepherd-terminal-input"

OP_TEXT, OP_BINARY, OP_CLOSE = 0x1, 0x2, 0x8

#: RFC 6455 §7.4.1's 1011, and the two reasons the reader can end on it. Spelled
#: here rather than imported, for the same reason as `READER_THREAD`.
CLOSE_KEY_REFUSED = 1011
KEY_REFUSED_REASON = b"a key was refused"
READER_FAILED_REASON = b"the input reader failed"


@pytest.fixture()
def scripted_runner() -> HoldingRunner:
    """The conftest's runner, with a stream that stays open while a human types.

    Overrides the conftest fixture for this module, so the autouse `tools`
    fixture registers the terminal tools against this runner.
    """
    from shepherd.core.runner import PaneState, ProcState
    from shepherd.runner.pane import parse_pane_fields, read_pane

    from web.conftest import LIVE_FIELDS, NOW
    from web.test_ws import capture_bytes

    capture = capture_bytes("03-after-stop.ansi")
    pane: PaneState = read_pane(capture, parse_pane_fields(LIVE_FIELDS), [])
    inner = ScriptedRunner(
        panes=(pane,),
        proc=ProcState(alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW),
        screen=capture,
        owned_panes=(),
    )
    return HoldingRunner(inner)


def client_frame(opcode: int, payload: bytes) -> bytes:
    """One masked client frame (RFC §5.3), built here and not by `ws`."""
    key = os.urandom(4)
    assert len(payload) < 1 << 16
    if len(payload) < 126:
        length = bytes([0x80 | len(payload)])
    else:
        length = bytes([0x80 | 126]) + len(payload).to_bytes(2, "big")
    masked = bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))
    return bytes([0x80 | opcode]) + length + key + masked


def readers() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name.startswith(READER_THREAD)]


def within(predicate: Callable[[], bool], bound_s: float = BOUND_S) -> bool:
    deadline = time.monotonic() + bound_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class Tap:
    """One upgraded socket: the status, then everything the server sent."""

    def __init__(self, sock: socket.socket, status: int, received: bytes) -> None:
        self.sock = sock
        self.status = status
        self.received = received

    def send(self, frame: bytes) -> None:
        self.sock.sendall(frame)

    def read_to_close(self) -> int | None:
        """Read until the server's close frame; its status code, or `None`."""
        self.sock.settimeout(BOUND_S)
        while True:
            code = close_code_in(self.received)
            if code is not None:
                return code
            try:
                chunk = self.sock.recv(65536)
            except OSError:
                return None
            if not chunk:
                return None
            self.received += chunk


def close_code_in(buffer: bytes) -> int | None:
    """The status of the first unmasked server close frame in `buffer`."""
    while len(buffer) >= 2:
        opcode, length, offset = buffer[0] & 0x0F, buffer[1] & 0x7F, 2
        if length == 126:
            length, offset = int.from_bytes(buffer[2:4], "big"), 4
        elif length == 127:
            length, offset = int.from_bytes(buffer[2:10], "big"), 10
        if len(buffer) < offset + length:
            return None
        if opcode == OP_CLOSE:
            return int.from_bytes(buffer[offset : offset + 2], "big")
        buffer = buffer[offset + length :]
    return None


@contextmanager
def upgraded(client: Client, session_id: str, origin: str | None = None) -> Iterator[Tap]:
    request = (
        f"GET /api/sessions/{session_id}/terminal HTTP/1.1\r\n"
        f"Host: {client.host}:{client.port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
        f"Origin: {origin or client.origin}\r\n\r\n"
    ).encode("ascii")
    with socket.create_connection((client.host, client.port), timeout=BOUND_S) as sock:
        sock.sendall(request)
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        yield Tap(sock, int(head.split(b" ")[1]), rest)


def test_a_typed_frame_reaches_runner_write(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """Text and binary frames arrive at `Runner.write`, verbatim and in order."""
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_TEXT, b"QA6-INJECT\r"))
        tap.send(client_frame(OP_BINARY, b"\x1b[A\xff"))
        assert within(lambda: len(scripted_runner.writes) >= 2), scripted_runner.writes
        assert scripted_runner.writes == [b"QA6-INJECT\r", b"\x1b[A\xff"]
        tap.send(client_frame(OP_CLOSE, (1000).to_bytes(2, "big")))
        assert tap.read_to_close() == 1000
    assert within(lambda: readers() == []), readers()


def test_typing_writes_no_audit_row_but_the_open_does(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """D40 / PP11: one `terminal_stream` record for the open, none per key."""
    records = install_test_chokepoint()
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        for key in (b"a", b"b", b"c", b"\r"):
            tap.send(client_frame(OP_TEXT, key))
        assert within(lambda: len(scripted_runner.writes) == 4), scripted_runner.writes
        tap.send(client_frame(OP_CLOSE, (1000).to_bytes(2, "big")))
        assert tap.read_to_close() == 1000
    # Arrival: the sink really is the one `invoke()` writes to.
    assert [record.tool for record in records] == ["terminal_stream"], records
    assert records[0].args == {"session_id": session_id}


def test_a_closed_pane_ends_the_reader_thread(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """The pane ends while the client sends nothing: the server closes with 1000
    and the reader, blocked on a socket nobody writes to, still ends."""
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_TEXT, b"x"))
        assert within(lambda: scripted_runner.writes == [b"x"]), scripted_runner.writes
        # Arrival: there is a reader to end.
        assert len(readers()) == 1, readers()
        scripted_runner.streams[0].close()
        assert tap.read_to_close() == 1000
        # The client still holds its socket open and has sent no close.
        assert within(lambda: readers() == []), readers()


def test_a_bad_origin_gets_no_reader(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """§13 stays first: a refused upgrade opens no stream and starts no reader,
    and a frame sent after the refusal reaches no pane."""
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id, origin="http://evil.example") as tap:
        assert tap.status == 403
        try:
            tap.send(client_frame(OP_TEXT, b"rm -rf /\r"))
        except OSError:
            pass
        time.sleep(0.2)
        assert readers() == []
    assert scripted_runner.streams == []
    assert scripted_runner.writes == []


def test_an_attached_session_gets_no_reader(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """Only an owned session with a live pane accepts input: an attached row has
    no pane of ours, so the upgrade is refused and nothing is written."""
    from web.conftest import seed

    attached = seed(store).id
    with upgraded(client, attached) as tap:
        assert tap.status == 404
    assert readers() == []
    assert scripted_runner.streams == []
    assert scripted_runner.writes == []


def test_a_key_for_a_pane_that_is_gone_ends_the_stream(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """A write the runner refuses ends the stream, and the page is told **why**
    with a close frame, rather than keys vanishing into a dead pane.

    REM-FIX 1 #2: 1011 and its reason, not 1000 — a pane that refused a key is
    not the same fact as a pane that ended, and the page says them apart.
    """
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        scripted_runner._inner.live.clear()
        tap.send(client_frame(OP_TEXT, b"lost"))
        assert tap.read_to_close() == CLOSE_KEY_REFUSED
        assert KEY_REFUSED_REASON in tap.received
        assert scripted_runner.writes == []
    assert within(lambda: readers() == []), readers()


# ----- REM-FIX 1: a paste, a refusal, a failing reader, a reader that outlives the join


def test_a_six_kilobyte_frame_does_not_close_the_stream(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """#1: a paste over the ~5.4 KB tmux takes in one command still reaches the
    pane whole, through the real `LocalRunner.write` against tmux's ceiling."""
    scripted_runner.tmux = RecordingTmux()
    session_id = owned(store, scripted_runner._inner)
    paste = bytes(index % 256 for index in range(6 * 1024))
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_BINARY, paste))
        tap.send(client_frame(OP_TEXT, b"after"))
        assert within(lambda: len(scripted_runner.writes) == 2), scripted_runner.writes
        assert scripted_runner.writes == [paste, b"after"]
        assert b"".join(scripted_runner.tmux.payloads()) == paste + b"after"
        tap.send(client_frame(OP_CLOSE, (1000).to_bytes(2, "big")))
        assert tap.read_to_close() == 1000
    assert within(lambda: readers() == []), readers()


def test_after_a_refused_key_no_later_key_is_written(
    client: Client, store: Store, scripted_runner: HoldingRunner
) -> None:
    """#2 / hunter M4: the pump stops at the refusal. A key already buffered
    behind the refused one is not written, even though the pane would take it."""
    from shepherd.core.runner import RunnerRefusal

    scripted_runner.fault = RunnerRefusal("tmux timed out after 10.0s")
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_TEXT, b"refused") + client_frame(OP_TEXT, b"behind"))
        assert tap.read_to_close() == CLOSE_KEY_REFUSED
    assert within(lambda: readers() == []), readers()
    assert scripted_runner.writes == []


def test_a_reader_that_fails_closes_with_1011(
    client: Client, store: Store, scripted_runner: HoldingRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3 / hunter M1+M2: an `OSError` from the write is not "the socket shut".
    The reader dies visibly, and the connection still ends, non-normally."""
    died: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: died.append(args.exc_value))
    scripted_runner.fault = OSError("the write failed")
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_TEXT, b"x"))
        assert tap.read_to_close() == CLOSE_KEY_REFUSED
        assert READER_FAILED_REASON in tap.received
    assert within(lambda: readers() == []), readers()
    assert [type(error) for error in died] == [OSError], died


def test_a_reader_outliving_the_join_writes_nothing_after_close(
    client: Client, store: Store, scripted_runner: HoldingRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3 / hunter M3: the pane ends while a key write is still in flight and the
    join gives up. When the write returns, the key buffered behind it is not
    written (the connection has closed), and the reader ends quietly rather
    than dying on the handler's already-closed `rfile`."""
    from shepherd.web import server

    died: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: died.append(args.exc_value))
    monkeypatch.setattr(server, "INPUT_JOIN_S", 0.2)
    scripted_runner.gate.clear()
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        tap.send(client_frame(OP_TEXT, b"first") + client_frame(OP_TEXT, b"second"))
        assert scripted_runner.in_flight.wait(BOUND_S)
        scripted_runner.streams[0].close()
        assert tap.read_to_close() == 1000
        # The handler has returned (join bounded at 0.2 s) and closed its files.
        time.sleep(0.5)
        scripted_runner.gate.set()
        assert within(lambda: readers() == []), readers()
    assert scripted_runner.writes == [b"first"]
    assert died == []


def test_the_input_join_outlasts_one_tmux_call() -> None:
    """#3: the writer's bounded join waits out one in-flight key write, which is
    one tmux call bounded by the runner's own timeout. `web/` does not import
    `runner/`, so the relation between the two numbers is pinned here."""
    from shepherd.runner.local import TMUX_CALL_TIMEOUT_S
    from shepherd.web.server import INPUT_JOIN_S

    assert INPUT_JOIN_S > TMUX_CALL_TIMEOUT_S
