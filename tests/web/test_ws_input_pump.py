"""P12 / D76 (ruling 18, SD-05): the read loop `web/server.py` runs on a terminal.

Seam: `shepherd.web.ws.pump_input(read, deliver) -> int` — a pure loop over two
callables, driven here by byte buffers. No socket, no thread, no server: the
server-side wiring has its own seam in `test_terminal_input_server.py`.

**The frames below are built by hand, not by `ws.build_frame`.** That is the
server's *unmasked* writer; a client frame is masked, and a test that produced
its input with the module under test would prove only that the module agrees
with itself. The one RFC-quoted frame (§5.7's masked "Hello") is an independent
source; the others are masked with a fixed, non-zero key by `client_frame`
below, whose arithmetic is RFC §5.3's and nothing of ours.
"""

from __future__ import annotations

from collections.abc import Callable

from shepherd.web import ws

#: RFC 6455 §5.7: "A single-frame masked text message" containing "Hello".
RFC_TEXT_MASKED = bytes.fromhex("818537fa213d7f9f4d5158")

#: A key with every byte non-zero, so an unapplied mask cannot pass.
KEY = bytes.fromhex("a1b2c3d4")

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING = 0x0, 0x1, 0x2, 0x8, 0x9


def client_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    """One masked client frame (RFC §5.2, §5.3), for payloads under 64 KiB."""
    head = bytes([(0x80 if fin else 0x00) | opcode])
    length = len(payload)
    if length < 126:
        head += bytes([0x80 | length])
    else:
        head += bytes([0x80 | 126]) + length.to_bytes(2, "big")
    masked = bytes(byte ^ KEY[index % 4] for index, byte in enumerate(payload))
    return head + KEY + masked


def reader(*pieces: bytes) -> Callable[[int], bytes]:
    """`read1` over a script: each call returns the next piece, then `b""`.

    The size argument is honoured as an upper bound, the way `read1` does, so
    a pump that asked for too little would see its pieces split, not merged.
    """
    queue = [piece for piece in pieces]

    def read(size: int) -> bytes:
        assert size > 0, "a read of nothing is a spin, not a read"
        if not queue:
            return b""
        head = queue[0]
        if len(head) <= size:
            return queue.pop(0)
        queue[0] = head[size:]
        return head[:size]

    return read


def pump(*pieces: bytes) -> tuple[int, list[bytes]]:
    delivered: list[bytes] = []
    code = ws.pump_input(reader(*pieces), delivered.append)
    return code, delivered


def test_text_and_binary_frames_are_delivered_verbatim() -> None:
    """Text is delivered as its UTF-8 bytes, binary as-is — including `\\xff`,
    which no decode/encode round trip survives, and a raw ESC and CR."""
    code, delivered = pump(
        client_frame(OP_TEXT, "héllo\r".encode("utf-8")),
        client_frame(OP_BINARY, b"\x1b[A\xff\r"),
        client_frame(OP_CLOSE, (1000).to_bytes(2, "big")),
    )
    assert delivered == ["héllo\r".encode("utf-8"), b"\x1b[A\xff\r"]
    assert code == 1000


def test_a_masked_frame_is_unmasked() -> None:
    """RFC §5.7's own worked example: the masked bytes decode to `Hello`."""
    code, delivered = pump(RFC_TEXT_MASKED)
    assert delivered == [b"Hello"]
    assert code == ws.CLOSE_NORMAL


def test_a_frame_split_across_reads_is_reassembled() -> None:
    """A header cut in two and a payload cut in two are still one keystroke."""
    whole = client_frame(OP_TEXT, b"ls -la\r")
    code, delivered = pump(whole[:1], whole[1:4], whole[4:9], whole[9:])
    assert delivered == [b"ls -la\r"]
    # …and two frames in one read are two deliveries, in order.
    code, delivered = pump(client_frame(OP_TEXT, b"a") + client_frame(OP_TEXT, b"b"))
    assert delivered == [b"a", b"b"]


def test_a_close_frame_ends_the_pump() -> None:
    """Nothing after a close frame is read or delivered (RFC §5.5.1)."""
    code, delivered = pump(
        client_frame(OP_TEXT, b"before"),
        client_frame(OP_CLOSE, (1001).to_bytes(2, "big")),
        client_frame(OP_TEXT, b"after"),
    )
    assert delivered == [b"before"]
    assert code == ws.CLOSE_NORMAL


def test_an_empty_read_ends_the_pump() -> None:
    """EOF mid-frame ends the loop; a half frame is never delivered."""
    whole = client_frame(OP_TEXT, b"half")
    code, delivered = pump(client_frame(OP_TEXT, b"x"), whole[:5])
    assert delivered == [b"x"]
    assert code == ws.CLOSE_NORMAL


def test_an_oversize_frame_ends_the_pump_with_1009() -> None:
    """Refused from the header alone: the payload is never read."""
    over = ws.MAX_FRAME_BYTES + 1
    header = bytes([0x80 | OP_BINARY, 0x80 | 127]) + over.to_bytes(8, "big") + KEY
    reads: list[int] = []
    pieces = [header, b"\x00" * 16]

    def read(size: int) -> bytes:
        reads.append(size)
        return pieces.pop(0) if pieces else b""

    delivered: list[bytes] = []
    code = ws.pump_input(read, delivered.append)
    assert code == 1009
    assert delivered == []
    assert len(reads) == 1, "the pump read past a header that already refused"


def test_a_ping_is_not_delivered() -> None:
    """Control frames are not keystrokes; an unmasked frame fails with 1002."""
    code, delivered = pump(
        client_frame(OP_PING, b"hi"),
        client_frame(OP_TEXT, b"k"),
    )
    assert delivered == [b"k"]
    assert code == ws.CLOSE_NORMAL
    unmasked = bytes([0x80 | OP_TEXT, 0x01]) + b"k"
    code, delivered = pump(unmasked)
    assert (code, delivered) == (ws.CLOSE_PROTOCOL_ERROR, [])


def test_a_continuation_carries_the_rest_of_a_fragmented_message() -> None:
    """RFC §5.4: `Hel` + `lo` is delivered as the bytes of both, in order."""
    code, delivered = pump(
        client_frame(OP_TEXT, b"Hel", fin=False),
        client_frame(OP_CONT, b"lo"),
    )
    assert b"".join(delivered) == b"Hello"
