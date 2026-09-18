"""RFC 6455, hand-rolled and owned (D51) — ~250 lines instead of a dependency.

D51 chose the stdlib and no build step, and this host has no WebSocket library
and no pip (`websockets`, `wsproto`, `aiohttp`, `tornado` and `simple_websocket`
are all recorded absent in
`docs/probes/2026-09-14-schemas/gap-fill/websocket-…/imports.json`). So the
framing is ours. It is ~250 lines of arithmetic against a fixed target, and the
tests check it against the RFC's own worked examples and a captured exchange —
never against this module's own output, which would only prove self-consistency.

**This module is a framer, not a session.** It resolves nothing, opens nothing,
and imports nothing from `shepherd` at all — the handler above it is handed a
stream and resolves its capability through `toolsurface` (DP4, D35). That also
keeps D25 intact by construction: there is no path from here to a log.

**Half of this module has no caller in this build, and that is deliberate.**
`handshake_response`, `build_frame` and `close_frame` are reached;
`parse_frame`, `Frame`, `WebSocketClosed` and `close_code` — the *reader* — are
not, anywhere in `src/`. `web/server.py::_terminal` writes the 101, the
snapshot frame, the live chunks and a close frame, and **never reads** a byte
back from the upgraded socket: there is no browser→pane keystroke path in M3 by
decision, because it would need a route outside T18's closed set
(**BLOCKER-T19-c**). The reader is kept because it is correct and a future read
loop will use it, and the absence is asserted rather than assumed, by
`tests/boundaries/test_ws_read_path.py` — which goes red the day a caller
appears, so the read loop brings its own tests instead of inheriting the
parser's. An earlier revision of this docstring said an unmasked frame "fails
the connection with 1002"; that is true of `parse_frame` and false of this
server, which never looks.

Three rules are enforced in code rather than documented, because each is a place
where a hand-rolled framer is commonly wrong in the permissive direction. The
first two are the reader's, so they bind whoever calls it and bind nothing in
this build today:

* **A client frame must be masked** (RFC §5.1). A server that accepts an
  unmasked frame is a bug, so `parse_frame` fails the connection with 1002 —
  and nothing here hands it a client frame, so no connection of this server's
  has ever failed that way.
* **A payload over `MAX_FRAME_BYTES` fails with 1009 from the header alone** —
  before a byte of it is read, which is the only point at which refusing costs
  nothing. `parse_frame`'s rule again, and unreached for the same reason.
* **A server frame is never masked** (RFC §5.1 again, the other direction).
  `build_frame` has no mask key and no parameter that would add one. This one
  is on the write path, which the product does use on every terminal stream.

§13 is upstream of all of this: the handshake is origin-checked against the
address the server actually bound, and an absent `Origin` is refused here even
though `server.py` tolerates one on a plain page read. A browser always sends
`Origin` on a WebSocket upgrade, so the tolerance buys nothing and costs the
check.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

#: RFC 6455 §1.3. The constant is the whole of the handshake's security value —
#: a wrong GUID produces a plausible-looking digest that no browser accepts.
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

#: The largest payload this server will read from a client. The inbound traffic
#: is keystrokes and resizes, so the cap is generous by three orders of
#: magnitude and still bounds the allocation a single frame header can demand.
MAX_FRAME_BYTES = 1 << 20

WS_VERSION = "13"

#: RFC §5.2's opcodes. The reserved ranges (0x3–0x7, 0xB–0xF) are not here, and
#: a frame carrying one fails the connection rather than being ignored.
OP_CONT = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

_DATA_OPCODES = frozenset({OP_CONT, OP_TEXT, OP_BINARY})
_CONTROL_OPCODES = frozenset({OP_CLOSE, OP_PING, OP_PONG})

#: RFC §5.5: a control frame's payload may not exceed 125 bytes, and it may not
#: be fragmented.
MAX_CONTROL_BYTES = 125

#: RFC §7.4.1's codes, for the three cases this module can reach on its own.
CLOSE_NORMAL = 1000
CLOSE_PROTOCOL_ERROR = 1002
CLOSE_TOO_BIG = 1009

_FIN = 0x80
_RSV = 0x70
_MASK = 0x80
_LENGTH_16 = 126
_LENGTH_64 = 127


class WebSocketClosed(Exception):
    """Fail the connection, with the RFC's status code for why.

    Raised rather than returned because every caller's correct response is the
    same one — send a close frame carrying `code` and stop reading. A parser
    that returned an error value would let a caller keep reading a stream whose
    framing is already known to be untrustworthy.
    """

    def __init__(self, code: int, reason: str = "") -> None:
        super().__init__(reason or str(code))
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class Frame:
    """One RFC §5.2 frame, already unmasked. `fin` is the fragmentation bit."""

    opcode: int
    payload: bytes
    fin: bool


# ----- the handshake (RFC §4, §13) --------------------------------------------


def accept_key(client_key: str) -> str:
    """RFC §4.2.2 step 5.4: base64(sha1(key + GUID)).

    The client's key is echoed through a fixed transform, so the answer for a
    given key is fixed too: `dGhlIHNhbXBsZSBub25jZQ==` must always produce
    `s3pPLMBiTxaQ9kYGzzhZRbK+xOo=`. That is what the test asserts — a round trip
    through our own digest would agree with any GUID at all.
    """
    digest = hashlib.sha1((client_key + WS_MAGIC).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _lowered(headers: Mapping[str, str]) -> dict[str, str]:
    """HTTP header names are case-insensitive; this module's lookups are not."""
    return {name.lower(): value for name, value in headers.items()}


def handshake_response(
    headers: Mapping[str, str], allowed_origins: frozenset[str]
) -> bytes | None:
    """The 101 response for a valid same-origin upgrade, or `None` to refuse.

    `None` rather than an exception: a refusal is an ordinary HTTP answer the
    caller already knows how to send (§13's generic 403), not a condition.
    """
    offered = _lowered(headers)
    if offered.get("upgrade", "").lower() != "websocket":
        return None
    connection = offered.get("connection", "")
    if "upgrade" not in {part.strip().lower() for part in connection.split(",")}:
        return None
    if offered.get("sec-websocket-version", "") != WS_VERSION:
        return None
    client_key = offered.get("sec-websocket-key", "")
    if not client_key:
        return None
    # §13: an absent `Origin` is a refusal here. A browser always sends one on
    # an upgrade, so tolerating its absence would only admit non-browser callers.
    origin = offered.get("origin")
    if origin is None or origin not in allowed_origins:
        return None
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key(client_key)}\r\n"
        "\r\n"
    ).encode("ascii")


# ----- framing (RFC §5.2) -----------------------------------------------------


def _payload_length(buffer: bytes) -> tuple[int, int] | None:
    """The declared length and the offset just past it, or `None` for "short".

    **The two short-header guards below are behaviour-neutral, and the mutation
    run says so:** deleting either leaves every test green, because a truncated
    extended length can only *shrink* (the field is big-endian, so the dropped
    bytes are the low ones) and `parse_frame` then finds `offset + 4 + length`
    past the end of the buffer and answers "not yet" anyway. They are kept
    because the alternative is a function that reads a length out of bytes that
    have not arrived and is correct only by an argument made somewhere else.
    That is recorded here rather than claimed as covered.
    """
    marker = buffer[1] & 0x7F
    if marker < _LENGTH_16:
        return marker, 2
    if marker == _LENGTH_16:
        if len(buffer) < 4:
            return None
        return int.from_bytes(buffer[2:4], "big"), 4
    if len(buffer) < 10:
        return None
    return int.from_bytes(buffer[2:10], "big"), 10


def parse_frame(buffer: bytes) -> tuple[Frame | None, int]:
    """The first frame in `buffer`, and how many bytes it consumed.

    `(None, 0)` means "not yet" — the caller reads more and asks again. It never
    means "bad", which is always an exception: a parser that answered "need more
    bytes" to a malformed frame would spin forever on one.
    """
    if len(buffer) < 2:
        return None, 0
    first, second = buffer[0], buffer[1]
    if first & _RSV:
        raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, "reserved bit set")
    opcode = first & 0x0F
    if opcode not in _DATA_OPCODES and opcode not in _CONTROL_OPCODES:
        raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, f"reserved opcode {opcode:#x}")
    fin = bool(first & _FIN)
    if not second & _MASK:
        # RFC §5.1: "The server MUST close the connection upon receiving a
        # frame that is not masked."
        raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, "client frame is not masked")
    measured = _payload_length(buffer)
    if measured is None:
        return None, 0
    length, offset = measured
    if length > MAX_FRAME_BYTES:
        # Refused from the header, before the payload is read or allocated.
        raise WebSocketClosed(CLOSE_TOO_BIG, f"{length} bytes exceeds the cap")
    if opcode in _CONTROL_OPCODES:
        if not fin:
            raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, "fragmented control frame")
        if length > MAX_CONTROL_BYTES:
            raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, "control frame too long")
        if opcode == OP_CLOSE and length == 1:
            raise WebSocketClosed(CLOSE_PROTOCOL_ERROR, "close payload of one byte")
    total = offset + 4 + length
    if len(buffer) < total:
        return None, 0
    key = buffer[offset : offset + 4]
    masked = buffer[offset + 4 : total]
    payload = bytes(byte ^ key[index % 4] for index, byte in enumerate(masked))
    return Frame(opcode=opcode, payload=payload, fin=fin), total


def build_frame(payload: bytes, *, opcode: int) -> bytes:
    """One unfragmented server frame. There is no mask key and no way to add one.

    RFC §5.1: "A server MUST NOT mask any frames that it sends to the client."
    Masking exists to stop a hostile script from steering an intermediary's
    cache, which is a client-side problem; a masking server is simply wrong, and
    the absence of the parameter is how that is guaranteed rather than intended.
    """
    length = len(payload)
    if length < _LENGTH_16:
        header = bytes([_FIN | opcode, length])
    elif length < 1 << 16:
        header = bytes([_FIN | opcode, _LENGTH_16]) + length.to_bytes(2, "big")
    else:
        header = bytes([_FIN | opcode, _LENGTH_64]) + length.to_bytes(8, "big")
    return header + payload


def close_frame(code: int, reason: str = "") -> bytes:
    """RFC §5.5.1: a close payload is a 16-bit code, then an optional reason."""
    return build_frame(code.to_bytes(2, "big") + reason.encode("utf-8"), opcode=OP_CLOSE)


def close_code(frame: Frame) -> int | None:
    """The status code a close frame carried, or `None` if it carried none.

    An empty close payload is legal (RFC §5.5.1) and means "no status", which is
    a different fact from 1000 — so it is `None` rather than a stand-in value.
    """
    if len(frame.payload) < 2:
        return None
    return int.from_bytes(frame.payload[:2], "big")
