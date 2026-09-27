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
    assert len(payload) < 126
    masked = bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))
    return bytes([0x80 | opcode, 0x80 | len(payload)]) + key + masked


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
    """A write the runner refuses means the pane is gone: the stream ends and the
    page is told with a close frame, rather than keys vanishing into a dead pane."""
    session_id = owned(store, scripted_runner._inner)
    with upgraded(client, session_id) as tap:
        assert tap.status == 101
        scripted_runner._inner.live.clear()
        tap.send(client_frame(OP_TEXT, b"lost"))
        assert tap.read_to_close() == 1000
        assert scripted_runner.writes == []
    assert within(lambda: readers() == []), readers()
