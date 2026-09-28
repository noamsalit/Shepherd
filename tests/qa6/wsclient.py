"""A raw WebSocket client — enough to read the pane terminal, and nothing more.

Copied from `tests/qa5/wsclient.py` (re-proved by
`fixtures/mutations/wsclient.json`, env-plan §4 step 1a), with the addition the
audit asked for: `read_to_close`, for a finite stream (T4's dying pane closes
the stream normally). `upgrade(..., origin=None)` now really sends **no**
`Origin` header (A5/T2's "WS no Origin → 403"); qa5 always sent one.

Server frames are decoded by hand on purpose: the product's `ws.parse_frame`
is the *client*-frame reader and rejects an unmasked frame by design, so a
harness that round-tripped the product's writer through its reader would prove
self-consistency and nothing else.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass

from .verdict import Blocked

#: RFC 6455 §1.3's worked-example key.
CLIENT_KEY = "dGhlIHNhbXBsZSBub25jZQ=="
OP_TEXT, OP_BINARY, OP_CLOSE = 0x1, 0x2, 0x8
NO_ORIGIN = "\x00no-origin"


@dataclass(frozen=True)
class Upgrade:
    status: int
    headers: dict[str, str]
    frames: list[tuple[int, bytes]]
    closed_by_server: bool = False

    def binary(self) -> list[bytes]:
        return [payload for opcode, payload in self.frames if opcode == OP_BINARY]

    def close_code(self) -> int | None:
        for opcode, payload in self.frames:
            if opcode == OP_CLOSE and len(payload) >= 2:
                return int.from_bytes(payload[:2], "big")
        return None


def decode(buffer: bytes) -> list[tuple[int, bytes]]:
    """Unmasked server frames → (opcode, payload). Stops at an incomplete frame."""
    frames: list[tuple[int, bytes]] = []
    while len(buffer) >= 2:
        opcode = buffer[0] & 0x0F
        length = buffer[1] & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                break
            length = int.from_bytes(buffer[2:4], "big")
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                break
            length = int.from_bytes(buffer[2:10], "big")
            offset = 10
        if len(buffer) < offset + length:
            break
        frames.append((opcode, buffer[offset : offset + length]))
        buffer = buffer[offset + length :]
    return frames


def mask_frame(opcode: int, payload: bytes) -> bytes:
    """A client frame (masked, FIN set), for T3's keystrokes."""
    key = os.urandom(4)
    head = bytes([0x80 | opcode])
    length = len(payload)
    if length < 126:
        head += bytes([0x80 | length])
    elif length < 65536:
        head += bytes([0x80 | 126]) + length.to_bytes(2, "big")
    else:
        head += bytes([0x80 | 127]) + length.to_bytes(8, "big")
    masked = bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))
    return head + key + masked


def _request(port: int, path: str, origin: str | None, host: str | None) -> bytes:
    authority = host or f"127.0.0.1:{port}"
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {authority}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {CLIENT_KEY}",
        "Sec-WebSocket-Version: 13",
    ]
    if origin != NO_ORIGIN:
        lines.append(f"Origin: {origin or f'http://127.0.0.1:{port}'}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def _handshake(sock: socket.socket) -> tuple[int, dict[str, str], bytes]:
    raw = b""
    while b"\r\n\r\n" not in raw:
        chunk = sock.recv(65536)
        if not chunk:
            break
        raw += chunk
    head, _, rest = raw.partition(b"\r\n\r\n")
    if not head:
        raise Blocked("the server answered nothing at all to the upgrade")
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    status = int(status_line.split(" ")[1])
    headers: dict[str, str] = {}
    for line in header_lines:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers, rest


def upgrade(
    port: int,
    path: str,
    *,
    origin: str | None = None,
    host: str | None = None,
    want_frames: int = 1,
    read_timeout: float = 10.0,
) -> Upgrade:
    """One upgrade attempt, then `want_frames` frames, then hang up.

    `origin=None` sends the same-origin header; `origin=NO_ORIGIN` sends none.
    A non-101 answer returns with its status and no frames.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=read_timeout) as sock:
        sock.sendall(_request(port, path, origin, host))
        status, headers, rest = _handshake(sock)
        if status != 101:
            return Upgrade(status=status, headers=headers, frames=[])
        buffer = rest
        while len(decode(buffer)) < want_frames:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
        return Upgrade(status=status, headers=headers, frames=decode(buffer))


def read_to_close(port: int, path: str, *, bound_s: float, origin: str | None = None) -> Upgrade:
    """Upgrade, then read until the server's close frame or EOF, within `bound_s`."""
    deadline = time.monotonic() + bound_s
    with socket.create_connection(("127.0.0.1", port), timeout=bound_s) as sock:
        sock.sendall(_request(port, path, origin, None))
        status, headers, rest = _handshake(sock)
        if status != 101:
            return Upgrade(status=status, headers=headers, frames=[])
        buffer = rest
        closed = False
        while time.monotonic() < deadline:
            if any(opcode == OP_CLOSE for opcode, _ in decode(buffer)):
                closed = True
                break
            sock.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                break
            except OSError:
                break
            if not chunk:
                closed = True
                break
            buffer += chunk
        return Upgrade(status=status, headers=headers, frames=decode(buffer), closed_by_server=closed)
