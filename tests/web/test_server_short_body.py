"""BC-32: a POST whose body never arrives is answered, not held forever.

Seam: HTTP, against the real server on an ephemeral loopback port. A client
that claims `Content-Length: 100` and sends 10 bytes used to park the handler
thread in `rfile.read(100)` with no deadline — no answer, ever, and one thread
gone per such request. The read now has a whole-body deadline of
`BODY_READ_TIMEOUT_S`; a body that has not fully arrived by then is a 400 and
the connection is closed. The deadline is not a per-`recv` idle window: a client
that trickles one byte at a time, each well inside the window, is still cut off
once the window has passed (REM-FIX 1). A body sent slowly but completely
inside the window is still accepted (E15).
"""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
from web.conftest import Client

from shepherd.web import server as web_server

PATH = "/api/projects"

#: The test's own deadline: the server's window plus a second of slack.
ANSWER_WITHIN_S = 3.0


def _head(client: Client, length: int, *, close: bool = True) -> bytes:
    # `close`: so the server closes after answering — a client that hung up with
    # the response body unread would reset the socket under the next readline.
    # The keep-alive variant turns it off to prove the server closes anyway.
    connection = "Connection: close\r\n" if close else ""
    return (
        f"POST {PATH} HTTP/1.1\r\n"
        f"Host: {client.host}:{client.port}\r\n"
        f"Origin: {client.origin}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {length}\r\n"
        f"{connection}"
        "\r\n"
    ).encode("ascii")


def _status_line(connection: socket.socket) -> bytes:
    """The first response line, or `b""` if the deadline passed first."""
    received = b""
    try:
        while b"\r\n" not in received:
            chunk = connection.recv(4096)
            if chunk == b"":
                break
            received += chunk
    except TimeoutError:
        return b""
    return received.split(b"\r\n", 1)[0]


def test_the_window_is_the_declared_constant() -> None:
    assert web_server.BODY_READ_TIMEOUT_S == 2.0
    assert web_server.BODY_READ_TIMEOUT_S < ANSWER_WITHIN_S


def test_a_short_body_is_a_400_within_the_timeout(client: Client) -> None:
    with socket.create_connection((client.host, client.port), timeout=ANSWER_WITHIN_S) as conn:
        conn.sendall(_head(client, 100) + b'{"name":"p')
        started = time.monotonic()
        status = _status_line(conn)
        elapsed = time.monotonic() - started
    assert status.startswith(b"HTTP/1.1 400"), status
    assert elapsed < ANSWER_WITHIN_S


def test_a_slow_but_complete_body_is_accepted(client: Client) -> None:
    """E15: the deadline bounds a stall, not a client that is merely slow."""
    body = json.dumps({"name": "slow-but-complete"}).encode("utf-8")
    with socket.create_connection((client.host, client.port), timeout=ANSWER_WITHIN_S) as conn:
        conn.sendall(_head(client, len(body)) + body[:4])
        time.sleep(0.3)
        conn.sendall(body[4:])
        status = _status_line(conn)
    assert status.startswith(b"HTTP/1.1 200"), status


#: The trickle's gap between bytes: well inside the window, so a per-`recv`
#: idle timeout would never fire on it.
TRICKLE_GAP_S = 0.25


def _trickle(connection: socket.socket, stop: threading.Event) -> None:
    """One body byte every `TRICKLE_GAP_S` until told to stop or refused."""
    while not stop.wait(TRICKLE_GAP_S):
        try:
            connection.sendall(b" ")
        except OSError:
            return


def test_a_trickled_body_is_a_400_once_the_window_has_passed(client: Client) -> None:
    """The deadline is for the whole body, not for each `recv` (REM-FIX 1).

    100 bytes at 4 B/s would take 25 s; every gap is far inside the window.
    """
    stop = threading.Event()
    with socket.create_connection((client.host, client.port), timeout=ANSWER_WITHIN_S) as conn:
        conn.sendall(_head(client, 100) + b'{"name":"p')
        started = time.monotonic()
        sender = threading.Thread(target=_trickle, args=(conn, stop), daemon=True)
        sender.start()
        try:
            status = _status_line(conn)
            elapsed = time.monotonic() - started
        finally:
            stop.set()
            sender.join()
    assert status.startswith(b"HTTP/1.1 400"), status
    assert web_server.BODY_READ_TIMEOUT_S <= elapsed < ANSWER_WITHIN_S


def test_a_short_body_on_a_keep_alive_connection_is_a_400_then_closed(
    client: Client, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `Connection: close`: the server must close on its own after the 400,
    or the stranded body bytes would be parsed as the next request."""
    with socket.create_connection((client.host, client.port), timeout=ANSWER_WITHIN_S) as conn:
        conn.sendall(_head(client, 100, close=False) + b'{"name":"p')
        received = b""
        while True:
            chunk = conn.recv(4096)
            if chunk == b"":
                break
            received += chunk
    assert received.startswith(b"HTTP/1.1 400"), received
    head, _, _ = received.partition(b"\r\n\r\n")
    assert b"\r\nConnection: close" in head, head
    assert json.loads(received.split(b"\r\n\r\n", 1)[1])["ok"] is False
    assert capsys.readouterr().err == ""
