"""A raw WebSocket client — enough to read the pane, and nothing more.

Raw sockets rather than `http.client`: a 101 hands the connection over and
`http.client` will not read past its own response.

**Server frames are decoded by hand, and that is deliberate.** `ws.parse_frame`
in the product is the *client*-frame reader and rejects an unmasked frame by
design (RFC §5.1), so it cannot read a server frame at all — and a harness that
round-tripped the product's own writer through the product's own reader would
prove self-consistency and nothing else.

**The stream does not end on a live pane.** `server.py::_terminal` writes the
snapshot, then every chunk `runner.attach()` yields, and only then a close frame.
Against a real tmux pane that is a stream with no end, so `read_frames` stops at
a **frame count** the caller names and closes from this side. A helper that read
"to the close frame" would hang forever on exactly the ground round 5 exists to
drive.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from .runroot import HarnessBlocked

#: RFC 6455 §1.3's worked example key. The value is irrelevant to the server's
#: answer beyond its length; using the spec's own keeps it checkable by hand.
CLIENT_KEY = "dGhlIHNhbXBsZSBub25jZQ=="

OP_BINARY, OP_CLOSE = 0x2, 0x8


@dataclass(frozen=True)
class Upgrade:
    status: int
    headers: dict[str, str]
    frames: list[tuple[int, bytes]]

    def binary(self) -> list[bytes]:
        return [payload for opcode, payload in self.frames if opcode == OP_BINARY]

    def close_code(self) -> int | None:
        for opcode, payload in self.frames:
            if opcode == OP_CLOSE and len(payload) >= 2:
                return int.from_bytes(payload[:2], "big")
        return None


def _decode(buffer: bytes) -> list[tuple[int, bytes]]:
    frames: list[tuple[int, bytes]] = []
    while len(buffer) >= 2:
        opcode = buffer[0] & 0x0F
        length = buffer[1] & 0x7F
        offset = 2
        if length == 126:
            length = int.from_bytes(buffer[2:4], "big")
            offset = 4
        elif length == 127:
            length = int.from_bytes(buffer[2:10], "big")
            offset = 10
        if len(buffer) < offset + length:
            break
        frames.append((opcode, buffer[offset : offset + length]))
        buffer = buffer[offset + length :]
    return frames


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

    A non-101 answer returns with its status and no frames — which is the
    assertion S14's negative control and S16 both need: the refusal happens
    **before** a byte of the connection is handed over.
    """
    authority = host or f"127.0.0.1:{port}"
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {CLIENT_KEY}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: {origin or f'http://127.0.0.1:{port}'}\r\n"
        "\r\n"
    ).encode("ascii")

    with socket.create_connection(("127.0.0.1", port), timeout=read_timeout) as sock:
        sock.sendall(request)
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        if not head:
            raise HarnessBlocked("the server answered nothing at all to the upgrade")
        status_line, *header_lines = head.decode("latin-1").split("\r\n")
        status = int(status_line.split(" ")[1])
        headers = {}
        for line in header_lines:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if status != 101:
            return Upgrade(status=status, headers=headers, frames=[])

        buffer = rest
        while len(_decode(buffer)) < want_frames:
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                break
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
        return Upgrade(status=status, headers=headers, frames=_decode(buffer))
