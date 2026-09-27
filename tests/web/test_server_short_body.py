"""BC-32: a POST whose body never arrives is answered, not held forever.

Seam: HTTP, against the real server on an ephemeral loopback port. A client
that claims `Content-Length: 100` and sends 10 bytes used to park the handler
thread in `rfile.read(100)` with no deadline — no answer, ever, and one thread
gone per such request. The read now has `BODY_READ_TIMEOUT_S`; a body that has
not arrived by then is a 400 and the connection is closed. A body sent slowly
but completely inside the window is still accepted (E15).
"""

from __future__ import annotations

import json
import socket
import time

from web.conftest import Client

from shepherd.web import server as web_server

PATH = "/api/projects"

#: The test's own deadline: the server's window plus a second of slack.
ANSWER_WITHIN_S = 3.0


def _head(client: Client, length: int) -> bytes:
    return (
        f"POST {PATH} HTTP/1.1\r\n"
        f"Host: {client.host}:{client.port}\r\n"
        f"Origin: {client.origin}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {length}\r\n"
        # So the server closes after answering: a client that hung up with the
        # response body unread would reset the socket under the next readline.
        "Connection: close\r\n"
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
