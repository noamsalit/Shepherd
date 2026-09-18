"""T17: the hand-rolled RFC 6455 framer, checked against bytes it did not write.

Seam: `shepherd.web.ws`'s public interface — `accept_key`, `handshake_response`,
`parse_frame`, `build_frame`. Unit, as the plan's `Test Seams` line says.

**Every expected value here comes from outside this repository's code.** A frame
pushed through our own encoder and back through our own decoder proves the pair
agrees with itself and nothing else; this repo has already shipped a test helper
that reimplemented its subject, so the round trip is deliberately not the proof.
Two independent sources are used instead:

* **RFC 6455 §5.7** — the worked frame examples, with their hex reproduced
  verbatim in `RFC_*` constants below, plus §1.3's worked `Sec-WebSocket-Accept`.
* **`docs/probes/2026-09-14-schemas/gap-fill/websocket-…/handshake.json`** — a
  real handshake and a real masked client frame captured on this host (K1).

Where the RFC's example is unmasked but the byte sequence must reach the
*server's* parser, which may not accept an unmasked frame, the frame is given a
**zero mask key**: masking is `payload[i] ^ key[i % 4]`, so a zero key is the
identity and the RFC's payload bytes still appear verbatim in the hex. The
capture's frame (`b10402d1`) is what proves a non-trivial key is really applied.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from shepherd.web import ws

CAPTURE = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "gap-fill"
    / "websocket-20260914T171610Z"
    / "handshake.json"
)

WS_MODULE = (
    Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "ws.py"
)

# ----- the reader this build does not call (BLOCKER-T19-c) --------------------

#: `ws.py`'s read half. `parse_frame` is the entry point; the other three are
#: the vocabulary it answers in.
READ_HALF = frozenset({"parse_frame", "Frame", "WebSocketClosed", "close_code"})

#: The one place the sentence is written. Appended to the docstring of every
#: test below that exercises the reader, so it is on the test pytest prints and
#: on the test the next reader opens — not in a comment at the top of a file
#: nobody scrolls to.
PARSER_HAS_NO_CALLER = """
**This exercises a parser the product does not yet call.** `src/` contains no
caller of `ws.parse_frame`: `web/server.py::_terminal` writes the 101, the
snapshot, the live chunks and a close frame, and never reads a byte back. There
is no browser->pane keystroke path in M3 by decision (BLOCKER-T19-c), so the
contract asserted here — including "read more and ask again" — has **no
implementer in this build**. The test is correct, is kept, and is not weakened:
the framer is real and a future read loop will use it. The absence is enforced
at `tests/boundaries/test_ws_read_path.py`, which goes red the day a caller
appears, so that read loop has to bring its own tests rather than inherit these.
"""

#: Every test the decorator has been applied to. Asserted at the bottom of this
#: module against an independent AST derivation, so the mark cannot drift off a
#: test that still exercises the reader.
PARSER_TESTS: set[str] = set()


def parser_has_no_caller_in_src(test: Callable[[], None]) -> Callable[[], None]:
    """Say, once and in one place, what this test does and does not prove."""
    PARSER_TESTS.add(test.__name__)
    test.__doc__ = f"{test.__doc__ or ''}\n{PARSER_HAS_NO_CALLER}"
    return test


# ----- RFC 6455 §5.7, quoted ---------------------------------------------------

#: "A single-frame unmasked text message" containing "Hello".
RFC_TEXT_UNMASKED = bytes.fromhex("81054865 6c6c6f".replace(" ", ""))
#: "A single-frame masked text message" containing "Hello".
RFC_TEXT_MASKED = bytes.fromhex("818537fa 213d7f9f 4d5158".replace(" ", ""))
#: "A fragmented unmasked text message" — "Hel" then "lo".
RFC_FRAGMENT_1 = bytes.fromhex("010348656c")
RFC_FRAGMENT_2 = bytes.fromhex("80026c6f")
#: "Unmasked Ping request" / "masked Pong response", both carrying "Hello".
RFC_PING_UNMASKED = bytes.fromhex("89054865 6c6c6f".replace(" ", ""))
RFC_PONG_MASKED = bytes.fromhex("8a8537fa 213d7f9f 4d5158".replace(" ", ""))
#: "256 bytes binary message in a single unmasked frame" — the header only.
RFC_BINARY_256_HEADER = bytes.fromhex("827e0100")
#: "64KiB binary message in a single unmasked frame" — the header only.
RFC_BINARY_65536_HEADER = bytes.fromhex("827f00000000 00010000".replace(" ", ""))

#: RFC 6455 §1.3's worked example of the handshake digest.
RFC_CLIENT_KEY = "dGhlIHNhbXBsZSBub25jZQ=="
RFC_ACCEPT = "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def capture() -> dict[str, object]:
    loaded: object = json.loads(CAPTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def captured_request_headers() -> dict[str, str]:
    """The captured request line's headers, parsed from the probe's own bytes."""
    request = capture()["request"]
    assert isinstance(request, str)
    headers: dict[str, str] = {}
    for line in request.split("\r\n")[1:]:
        if line == "":
            break
        name, _, value = line.partition(":")
        headers[name] = value.strip()
    return headers


def masked(header_and_payload: bytes) -> bytes:
    """The RFC's unmasked example, re-presented with a zero mask key.

    The mask bit is set and four zero bytes are inserted; a zero key is the
    identity transform, so every payload byte below is still the RFC's own.
    """
    first, second = header_and_payload[0], header_and_payload[1]
    assert second < 126 and not second & 0x80
    return bytes([first, second | 0x80, 0, 0, 0, 0]) + header_and_payload[2:]


# ----- the handshake (§13, the capture) ---------------------------------------


def test_the_handshake_matches_rfc6455_and_checks_origin() -> None:
    """The digest has a fixed known answer; a round trip would prove nothing."""
    assert ws.accept_key(RFC_CLIENT_KEY) == RFC_ACCEPT

    captured = capture()
    headers = captured_request_headers()
    assert ws.accept_key(headers["Sec-WebSocket-Key"]) == captured["expected_accept"]

    origin = f"http://{headers['Host']}"
    response = ws.handshake_response(
        {**headers, "Origin": origin}, frozenset({origin})
    )
    assert response is not None
    text = response.decode("ascii")
    assert text.startswith("HTTP/1.1 101 Switching Protocols\r\n")
    assert f"Sec-WebSocket-Accept: {captured['expected_accept']}\r\n" in text
    assert "Upgrade: websocket\r\n" in text
    assert "Connection: Upgrade\r\n" in text
    assert text.endswith("\r\n\r\n")


def test_a_cross_origin_handshake_is_refused() -> None:
    """§13: one case per origin form a browser or an attacker can present."""
    headers = captured_request_headers()
    allowed = f"http://{headers['Host']}"
    host_port = headers["Host"].split(":")[1]
    refused = {
        "absent": None,
        "null": "null",
        "lan": f"http://192.168.1.5:{host_port}",
        "other-port": "http://127.0.0.1:9",
        "foreign": "http://evil.example",
    }
    for label, origin in refused.items():
        offered = dict(headers)
        if origin is not None:
            offered["Origin"] = origin
        assert ws.handshake_response(offered, frozenset({allowed})) is None, label
    # The check is not "refuse everything": the bound origin still completes.
    assert ws.handshake_response(
        {**headers, "Origin": allowed}, frozenset({allowed})
    ) is not None


def test_a_malformed_upgrade_is_refused() -> None:
    headers = captured_request_headers()
    allowed = f"http://{headers['Host']}"
    for broken in (
        {"Upgrade": "h2c"},
        {"Connection": "keep-alive"},
        {"Sec-WebSocket-Version": "8"},
        {"Sec-WebSocket-Key": ""},
    ):
        offered = {**headers, "Origin": allowed, **broken}
        assert ws.handshake_response(offered, frozenset({allowed})) is None, broken


# ----- masking (RFC §5.1: a server must fail an unmasked client frame) --------


@parser_has_no_caller_in_src
def test_an_unmasked_client_frame_is_rejected() -> None:
    """The RFC's own unmasked examples, handed to the server's parser."""
    for frame in (RFC_TEXT_UNMASKED, RFC_PING_UNMASKED, RFC_FRAGMENT_1):
        with pytest.raises(ws.WebSocketClosed) as raised:
            ws.parse_frame(frame)
        assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR


@parser_has_no_caller_in_src
def test_a_masked_client_frame_is_unmasked_the_way_the_capture_was() -> None:
    """`8183 b10402d1 aa5f43` → `\\x1b[A`, straight out of the probe."""
    captured = capture()
    hex_frame = captured["client_frame_hex"]
    assert isinstance(hex_frame, str)
    frame, consumed = ws.parse_frame(bytes.fromhex(hex_frame))
    assert frame is not None
    assert consumed == len(hex_frame) // 2
    assert frame.opcode == ws.OP_TEXT
    assert frame.fin is True
    side = captured["server_side"]
    assert isinstance(side, list)
    expected = side[0]["unmasked_payload"]
    assert isinstance(expected, str)
    assert frame.payload == expected.encode("utf-8")


@parser_has_no_caller_in_src
def test_the_rfc_masked_text_example_decodes_to_hello() -> None:
    frame, consumed = ws.parse_frame(RFC_TEXT_MASKED)
    assert frame is not None
    assert (frame.opcode, frame.fin, frame.payload) == (ws.OP_TEXT, True, b"Hello")
    assert consumed == len(RFC_TEXT_MASKED)


# ----- length classes ---------------------------------------------------------


@parser_has_no_caller_in_src
def test_frames_round_trip_for_every_length_class() -> None:
    """0, 1, 125, 126, 127, 65 535, 65 536 — the 7-bit/16-bit/64-bit boundaries.

    The *header* is asserted against literals taken from the RFC's layout, not
    against the encoder: an encoder that agreed with its own decoder about a
    wrong length class would pass a round trip and fail here.
    """
    expected_headers = {
        0: "8200",
        1: "8201",
        125: "827d",
        126: "827e007e",
        127: "827e007f",
        65535: "827effff",
        65536: "827f0000000000010000",
    }
    # RFC §5.7's own two multi-byte examples, as a cross-check on the table.
    assert bytes.fromhex(expected_headers[65536]) == RFC_BINARY_65536_HEADER
    assert RFC_BINARY_256_HEADER == bytes.fromhex("827e") + (256).to_bytes(2, "big")

    for length, header_hex in expected_headers.items():
        payload = bytes(range(256)) * (length // 256) + bytes(range(length % 256))
        built = ws.build_frame(payload, opcode=ws.OP_BINARY)
        header = bytes.fromhex(header_hex)
        assert built[: len(header)] == header, length
        assert built[len(header) :] == payload, length
        # And the server parses the same class when a client sends it masked.
        client = bytes([built[0], *_masked_length(length)]) + bytes(4) + payload
        frame, consumed = ws.parse_frame(client)
        assert frame is not None and frame.payload == payload, length
        assert consumed == len(client), length


def _masked_length(length: int) -> bytes:
    """The RFC's length encoding with the mask bit set, written out longhand."""
    if length < 126:
        return bytes([0x80 | length])
    if length < 65536:
        return bytes([0x80 | 126]) + length.to_bytes(2, "big")
    return bytes([0x80 | 127]) + length.to_bytes(8, "big")


@parser_has_no_caller_in_src
def test_a_partial_frame_asks_for_more_bytes_instead_of_guessing() -> None:
    """Cut at every byte, in all three length classes.

    The 16- and 64-bit classes are here because a header can be *itself*
    incomplete: two bytes have arrived, they promise a 16-bit length, and the
    length is not there yet. A guard that only counted the payload would read
    two bytes past the buffer and invent a length.
    """
    whole = {
        "7-bit": RFC_TEXT_MASKED,
        "16-bit": bytes([0x82, 0x80 | 126]) + (300).to_bytes(2, "big") + bytes(4 + 300),
        "64-bit": bytes([0x82, 0x80 | 127]) + (70000).to_bytes(8, "big") + bytes(4 + 70000),
    }
    for label, frame_bytes in whole.items():
        assert ws.parse_frame(frame_bytes)[0] is not None, label
        for cut in range(1, len(frame_bytes)):
            frame, consumed = ws.parse_frame(frame_bytes[:cut])
            assert frame is None and consumed == 0, (label, cut)


@parser_has_no_caller_in_src
def test_trailing_bytes_are_left_for_the_next_frame() -> None:
    buffer = RFC_TEXT_MASKED + b"\x99trailing"
    frame, consumed = ws.parse_frame(buffer)
    assert frame is not None
    assert consumed == len(RFC_TEXT_MASKED)
    assert buffer[consumed:] == b"\x99trailing"


# ----- the cap (§13: a client may not allocate without bound) -----------------


@parser_has_no_caller_in_src
def test_a_payload_over_the_cap_closes_with_1009() -> None:
    """Refused from the header alone — before a byte of the payload arrives."""
    oversized = bytes([0x82, 0x80 | 127]) + (ws.MAX_FRAME_BYTES + 1).to_bytes(8, "big")
    header_only = oversized + bytes(4)
    assert len(header_only) == 14
    with pytest.raises(ws.WebSocketClosed) as raised:
        ws.parse_frame(header_only)
    assert raised.value.code == ws.CLOSE_TOO_BIG

    at_the_cap = (
        bytes([0x82, 0x80 | 127])
        + ws.MAX_FRAME_BYTES.to_bytes(8, "big")
        + bytes(4)
    )
    frame, consumed = ws.parse_frame(at_the_cap)
    assert (frame, consumed) == (None, 0)  # incomplete, not refused


# ----- fragmentation ----------------------------------------------------------


@parser_has_no_caller_in_src
def test_fragmentation_follows_the_rfc_example() -> None:
    """RFC §5.7's "Hel"/"lo" pair: fin=0 opcode=1, then fin=1 opcode=0."""
    first, consumed_first = ws.parse_frame(masked(RFC_FRAGMENT_1))
    second, consumed_second = ws.parse_frame(masked(RFC_FRAGMENT_2))
    assert first is not None and second is not None
    assert (first.fin, first.opcode, first.payload) == (False, ws.OP_TEXT, b"Hel")
    assert (second.fin, second.opcode, second.payload) == (True, ws.OP_CONT, b"lo")
    assert consumed_first == 9 and consumed_second == 8


@parser_has_no_caller_in_src
def test_a_fragmented_control_frame_is_refused() -> None:
    """RFC §5.5: control frames may not be fragmented, and may not exceed 125."""
    unfinished_ping = masked(bytes([0x09, *RFC_PING_UNMASKED[1:]]))
    with pytest.raises(ws.WebSocketClosed) as raised:
        ws.parse_frame(unfinished_ping)
    assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR

    long_ping = bytes([0x89, 0x80 | 126]) + (126).to_bytes(2, "big") + bytes(4 + 126)
    with pytest.raises(ws.WebSocketClosed) as raised:
        ws.parse_frame(long_ping)
    assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR


@parser_has_no_caller_in_src
def test_a_reserved_bit_is_refused() -> None:
    """No extension is negotiated (D51 rules out permessage-deflate)."""
    for rsv in (0x40, 0x20, 0x10):
        frame = masked(bytes([RFC_TEXT_UNMASKED[0] | rsv, *RFC_TEXT_UNMASKED[1:]]))
        with pytest.raises(ws.WebSocketClosed) as raised:
            ws.parse_frame(frame)
        assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR


@parser_has_no_caller_in_src
def test_an_unknown_opcode_is_refused() -> None:
    for opcode in (0x3, 0x7, 0xB, 0xF):
        frame = masked(bytes([0x80 | opcode, *RFC_TEXT_UNMASKED[1:]]))
        with pytest.raises(ws.WebSocketClosed) as raised:
            ws.parse_frame(frame)
        assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR


# ----- ping, pong and close ---------------------------------------------------


def test_the_server_builds_the_rfc_ping_and_pong_bytes() -> None:
    """A server never masks (RFC §5.1), so the RFC's unmasked bytes are ours."""
    assert ws.build_frame(b"Hello", opcode=ws.OP_PING) == RFC_PING_UNMASKED
    assert ws.build_frame(b"Hello", opcode=ws.OP_TEXT) == RFC_TEXT_UNMASKED
    assert ws.build_frame(b"Hello", opcode=ws.OP_PONG) == bytes.fromhex(
        "8a054865 6c6c6f".replace(" ", "")
    )


@parser_has_no_caller_in_src
def test_a_masked_pong_is_read_as_the_rfc_says() -> None:
    frame, _ = ws.parse_frame(RFC_PONG_MASKED)
    assert frame is not None
    assert (frame.opcode, frame.payload) == (ws.OP_PONG, b"Hello")


@parser_has_no_caller_in_src
def test_a_close_frame_carries_a_two_byte_status_code() -> None:
    """RFC §5.5.1: the code is a 16-bit unsigned integer in network order."""
    assert ws.close_frame(ws.CLOSE_NORMAL, "bye") == bytes.fromhex("880503e8627965")
    assert ws.close_frame(ws.CLOSE_TOO_BIG) == bytes.fromhex("880203f1")

    going_away = bytes([0x88, 0x80 | 2]) + bytes(4) + (1001).to_bytes(2, "big")
    frame, _ = ws.parse_frame(going_away)
    assert frame is not None and frame.opcode == ws.OP_CLOSE
    assert ws.close_code(frame) == 1001

    empty = bytes([0x88, 0x80]) + bytes(4)
    frame, _ = ws.parse_frame(empty)
    assert frame is not None and ws.close_code(frame) is None


@parser_has_no_caller_in_src
def test_a_one_byte_close_payload_is_refused() -> None:
    """RFC §5.5.1: a close payload of exactly one byte is a protocol error."""
    truncated = bytes([0x88, 0x80 | 1]) + bytes(4) + b"\x03"
    with pytest.raises(ws.WebSocketClosed) as raised:
        ws.parse_frame(truncated)
    assert raised.value.code == ws.CLOSE_PROTOCOL_ERROR


# ----- the layer rule (D25, D35) ----------------------------------------------


def test_ws_resolves_no_capability_itself() -> None:
    """The framer is handed a stream; it reaches for nothing below L4 (DP4)."""
    tree = ast.parse(WS_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert {name for name in imported if name.startswith("shepherd")} == set()
    # self-check: the same scan bites on a module that reaches for the runner.
    leak = ast.parse("from shepherd.runner.local import LocalRunner\n")
    leaked = {
        node.module or ""
        for node in ast.walk(leak)
        if isinstance(node, ast.ImportFrom)
    }
    assert {name for name in leaked if name.startswith("shepherd")}


# ==============================================================================
# T19 — clause 10's deterministic half: the framer does not mutate bytes.
#
# Seam: the WebSocket wire. A raw socket to the live loopback server, the same
# surface a browser has; nothing below reaches into a handler.
#
# **Why every byte-identity claim here carries a `\xff`.** T18 planted
# `decode(errors="replace").encode()` inside `terminal_snapshot` and it
# **survived**: the captures are valid UTF-8, so that round trip is the identity
# on them and a byte-identity test over a clean capture is green on a broken
# tree. The screen under test is therefore the real capture **plus one `\xff`**
# — a byte a terminal emits and UTF-8 cannot represent — and the test asserts,
# before comparing anything, that the round trip really does destroy it. Without
# that arrival assertion the sentinel is a decoration.
# ==============================================================================

import threading
import time
from collections.abc import Iterator

import pytest

from shepherd.runner.base import ByteStream
from shepherd.testkit.scripted_runner import ScriptedRunner
from web.conftest import Client, seed
from web.test_routes_m3 import _upgrade, owned
from web.test_session_page import READ_ONLY_BANNER, attached_branch

#: P-M3-10's six, named in full. **Not T6's six** — the two sets overlap in four
#: and each is named where it is used, which is what revision 2 fixed.
P_M3_10_CAPTURES = (
    "01-trust-dialog.ansi",
    "02-after-trust.ansi",
    "03-after-stop.ansi",
    "06-permission-dialog.ansi",
    "08-prompt-with-suggestion.ansi",
    "09-resize-after-70x30.ansi",
)

PROBES = Path(__file__).resolve().parents[2] / "docs" / "probes"

#: A byte a terminal emits and UTF-8 cannot represent. `0xFF` is not a legal
#: byte anywhere in UTF-8, so no decode/encode round trip returns it — which is
#: the whole reason it is here.
UNREPRESENTABLE = b"\xff"


def capture_bytes(name: str) -> bytes:
    """One capture, resolved **by name** rather than by path (T13-3).

    Citing a capture by its path trips `tests/signals/test_verdict.py`'s
    `MODEL_ID` rule on a real probe directory name; resolving by name with
    `rglob` avoids that and asserts the corpus holds exactly one of each.
    """
    found = sorted(PROBES.rglob(name))
    assert len(found) == 1, found
    raw = found[0].read_bytes()
    assert raw != b""
    return raw


class _WatchedStream:
    """A `ByteStream` that records its own teardown and can be held open.

    `ScriptedRunner`'s stream yields the screen once and stops, which cannot
    express "the client left while bytes were still coming" — the only state in
    which tearing the pane down is observable at all.
    """

    def __init__(self, live: tuple[bytes, ...], heartbeat: bool) -> None:
        self.live = live
        self.heartbeat = heartbeat
        self.closed = threading.Event()
        self.closes = 0

    def chunks(self) -> Iterator[bytes]:
        yield from self.live
        if not self.heartbeat:
            return
        deadline = time.monotonic() + 10.0
        while not self.closed.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
            yield b"."

    def close(self) -> None:
        self.closes += 1
        self.closed.set()


class _StreamingRunner:
    """The conftest's `ScriptedRunner` with two members made steerable.

    Only `snapshot` and `attach` are replaced — the two the terminal path calls
    — and every other member is the real double's, so a test cannot pass here
    against a runner that answers nothing else. It is a `Runner` by structure,
    which is what the seam asks for.
    """

    def __init__(self, inner: ScriptedRunner) -> None:
        self._inner = inner
        self.screen = inner.screen
        self.stream = _WatchedStream(live=(), heartbeat=False)
        self.attaches = 0
        self.scrollbacks: list[int] = []

    def snapshot(self, handle: object, scrollback: int) -> bytes:
        self.scrollbacks.append(scrollback)
        return self.screen

    def attach(self, handle: object) -> ByteStream:
        self.attaches += 1
        return self.stream

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


@pytest.fixture()
def scripted_runner(request: pytest.FixtureRequest) -> _StreamingRunner:
    """Overrides the conftest fixture **for this module only**.

    The autouse `tools` fixture registers M3's twelve against whatever this
    returns, so overriding here is how the terminal path gets a steerable pane
    without a second registration or a second server.
    """
    inner = request.getfixturevalue("__scripted_runner_base")
    return _StreamingRunner(inner)


@pytest.fixture()
def __scripted_runner_base(store: object, tmp_path: Path) -> ScriptedRunner:
    """The conftest's own fixture body, reached under a different name."""
    from shepherd.core.runner import PaneState, ProcState
    from shepherd.runner.pane import parse_pane_fields, read_pane

    from web.conftest import LIVE_FIELDS, NOW

    capture = capture_bytes("03-after-stop.ansi")
    pane: PaneState = read_pane(capture, parse_pane_fields(LIVE_FIELDS), [])
    return ScriptedRunner(
        panes=(pane,),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=capture,
        owned_panes=(),
    )


def test_the_captures_p_m3_10_names_are_all_there_and_are_six() -> None:
    """The table states its own case count, before anything is asserted over it."""
    assert len(P_M3_10_CAPTURES) == 6
    assert len(set(P_M3_10_CAPTURES)) == 6
    for name in P_M3_10_CAPTURES:
        assert capture_bytes(name) != b""


def test_the_first_frame_is_the_snapshot_byte_for_byte(
    client: Client, store: object, scripted_runner: _StreamingRunner
) -> None:
    """P-M3-10. Six captures, each framed and compared to itself plus `\\xff`.

    **What this proves:** nothing between the `Runner` seam and the WebSocket
    frame decodes, escapes or re-encodes a pane byte. **What it does not
    prove:** what `capture-pane` returns on this host — the fixture is a
    checked-in file compared to itself, and that half is T24's live
    `test_the_live_snapshot_frame_is_the_bytes_capture_pane_returned`
    (P-M3-17). Clause 10 says which proof carries which half; this one does not
    claim the other.
    """
    session_id = owned(store, scripted_runner)
    checked = 0
    hyperlinks = 0
    nbsp = 0
    for name in P_M3_10_CAPTURES:
        raw = capture_bytes(name)
        screen = raw + UNREPRESENTABLE

        # Arrival, before absence: the sentinel is a byte no round trip
        # survives. If this ever stops holding, every comparison below is
        # satisfiable by a tree that decodes and re-encodes — which is exactly
        # the mutation that survived T18.
        assert UNREPRESENTABLE not in raw, name
        assert screen.decode("utf-8", errors="replace").encode("utf-8") != screen
        assert b"\x1b[" in raw, name  # and the capture carries escapes at all

        hyperlinks += b"\x1b]8;" in raw
        nbsp += b"\xc2\xa0" in raw

        scripted_runner.screen = screen
        scripted_runner.stream = _WatchedStream(live=(), heartbeat=False)
        status, frames = _upgrade(client, f"/api/sessions/{session_id}/terminal")

        assert status == 101, name
        assert frames, f"{name}: no frame arrived after the handshake"
        opcode, payload = frames[0]
        assert opcode == ws.OP_BINARY, name
        assert payload == screen, name
        # And the capture's own bytes are in there unaltered, not merely equal
        # in length: the sentinel is the last byte and everything before it is
        # the file.
        assert payload[: len(raw)] == raw, name
        assert payload[len(raw) :] == UNREPRESENTABLE, name
        checked += 1

    assert checked == 6
    # P-M3-10 names two shapes specifically; a corpus that lost them would make
    # "the framer does not mutate bytes" a claim about plain ASCII.
    assert hyperlinks >= 1, "no OSC 8 hyperlink in any capture"
    assert nbsp >= 1, "no NBSP after ❯ in any capture"


def test_the_snapshot_is_taken_at_the_depth_the_seam_states(
    client: Client, store: object, scripted_runner: _StreamingRunner
) -> None:
    """T9-1: the argument is a **scrollback depth**, and it is the §9 one."""
    from shepherd.toolsurface.tools_terminal import SNAPSHOT_SCROLLBACK

    session_id = owned(store, scripted_runner)
    _upgrade(client, f"/api/sessions/{session_id}/terminal")
    assert scripted_runner.scrollbacks == [SNAPSHOT_SCROLLBACK]
    assert SNAPSHOT_SCROLLBACK == 2000


def test_live_chunks_arrive_in_order_and_stop_on_close(
    client: Client, store: object, scripted_runner: _StreamingRunner
) -> None:
    """Flow C3: the snapshot, then `pipe-pane`'s bytes **in order**, then close.

    Order is asserted as a list and not as a set: a transport that delivered the
    right bytes in the wrong order would satisfy a membership check and produce
    a scrambled screen.
    """
    session_id = owned(store, scripted_runner)
    scripted_runner.screen = b"SCREEN" + UNREPRESENTABLE
    scripted_runner.stream = _WatchedStream(
        live=(b"one", b"two", b"three"), heartbeat=False
    )
    status, frames = _upgrade(client, f"/api/sessions/{session_id}/terminal")

    assert status == 101
    assert [payload for _, payload in frames[:4]] == [
        b"SCREEN" + UNREPRESENTABLE,
        b"one",
        b"two",
        b"three",
    ]
    assert [opcode for opcode, _ in frames[:4]] == [ws.OP_BINARY] * 4
    # The stream ends with a close frame rather than a dropped socket, and the
    # pane is released either way.
    assert frames[-1][0] == ws.OP_CLOSE
    # **Waited for, not assumed.** `_upgrade` returns at the server's close
    # frame, which it writes *before* `finally: stream.close()` runs — so the
    # old bare `closes == 1` was sequenced by luck: the previous `_upgrade` read
    # to EOF, and EOF happened to mean the handler had already finished. Reading
    # to the ending the server actually writes (T25's honesty fix) removed that
    # accident and the assertion failed 1 run in 5.
    #
    # This is an **arrival wait on an event that must happen**, not a retry into
    # green: if the pane is never released the wait expires and the test fails,
    # which is exactly what it is here to detect.
    assert scripted_runner.stream.closed.wait(5.0), "the pane was never released"
    assert scripted_runner.stream.closes == 1


def test_the_stream_is_torn_down_with_the_last_client(
    client: Client, store: object, scripted_runner: _StreamingRunner
) -> None:
    """Clause 10: the pane's stream is released when the browser goes away.

    The stream is held open (a pane with output still coming) and the client
    hangs up mid-stream — the only state in which "torn down with the last
    client" is observable. Probabilistic in timing and bounded: the assertion
    polls for at most five seconds and fails rather than waits forever.
    """
    session_id = owned(store, scripted_runner)
    scripted_runner.stream = _WatchedStream(live=(b"live",), heartbeat=True)

    _upgrade_and_hang_up(client, f"/api/sessions/{session_id}/terminal")

    assert scripted_runner.attaches == 1, "arrival: nothing was ever attached"
    assert scripted_runner.stream.closed.wait(timeout=5.0), "the pane was not released"
    assert scripted_runner.stream.closes >= 1


def _upgrade_and_hang_up(client: Client, path: str) -> None:
    """Upgrade, read the snapshot frame, then close the socket like a shut tab."""
    import socket

    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {client.host}:{client.port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: {client.origin}\r\n"
        "\r\n"
    ).encode("ascii")
    with socket.create_connection((client.host, client.port), timeout=10) as sock:
        sock.sendall(request)
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += sock.recv(65536)
        assert raw.split(b" ")[1] == b"101", raw[:64]
        sock.settimeout(5)
        assert sock.recv(65536) != b""  # the snapshot really arrived first


def test_an_attached_session_is_refused_with_the_banner(
    client: Client, store: object, scripted_runner: _StreamingRunner
) -> None:
    """§9: an attached session has no pane of ours, so it gets no terminal.

    Both halves, because either alone is satisfiable by a page that shows
    nothing: the **server** refuses the upgrade for an attached row, and the
    **page** carries §9's banner wording for it.
    """
    row = seed(store)
    status, frames = _upgrade(client, f"/api/sessions/{row.id}/terminal")
    assert status == 404
    assert frames == []
    assert scripted_runner.attaches == 0

    session_js = (
        Path(__file__).resolve().parents[2]
        / "src" / "shepherd" / "web" / "static" / "session.js"
    ).read_text(encoding="utf-8")
    # The branch's body, not the file: a banner constant that nothing assigns
    # is a sentence in a file, and mutation `m7` showed the difference.
    assert "READ_ONLY_BANNER" in attached_branch(session_js)
    assert READ_ONLY_BANNER in session_js


# ----- what these tests do and do not prove (BLOCKER-T19-c) -------------------


def functions_touching(names: frozenset[str] | None, path: Path) -> frozenset[str]:
    """Every `test_*` in `path` that names one of `names`, by AST (`None`: all).

    Derived from the source rather than read off the decorators, so that this
    and `PARSER_TESTS` are two independent answers to the same question. A test
    that starts exercising the reader and is not marked makes them disagree.
    """
    found: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        used = {
            child.attr if isinstance(child, ast.Attribute) else child.id
            for child in ast.walk(node)
            if isinstance(child, (ast.Attribute, ast.Name))
        }
        if names is None or used & names:
            found.add(node.name)
    return frozenset(found)


def test_the_module_docstring_says_what_this_server_actually_does() -> None:
    """`ws.py` may not claim a behaviour the tree does not have.

    It used to: *"an unmasked frame fails the connection with 1002"* is true of
    `parse_frame` and false of this server, which never looks at a client frame
    (BLOCKER-T19-c). The same defect shape as a test whose name promises more
    than its body, in the place a reader trusts most.
    """
    docstring = ast.get_docstring(ast.parse(WS_MODULE.read_text(encoding="utf-8")))

    # Arrival: there is a module docstring and it is the framer's.
    assert docstring is not None
    assert "RFC 6455" in docstring

    # The claim, and where the claim is enforced.
    assert "T19-c" in docstring, docstring
    assert "never reads" in docstring, docstring
    assert "parse_frame" in docstring, docstring


def test_every_test_of_the_uncalled_parser_says_it_is_uncalled() -> None:
    """The count BLOCKER-T19-c records, kept live instead of quoted.

    Fourteen of this module's tests exercise `parse_frame` and its vocabulary,
    and **nothing in `src/` calls any of it**. They are all kept and none is
    weakened; each one carries `@parser_has_no_caller_in_src`, which is the
    single place that sentence is written.

    The fourteen is asserted below. The **total** is asserted only as a floor
    (`>= 25`), and this sentence carries no total at all on purpose: it used to
    say "twenty-five tests", the file now collects **27**, and the floor meant
    the assertion could not catch its own docstring. A number in prose beside a
    number in an assertion is the smaller of the two claims going stale in
    silence — the milestone's own recurring defect, one line down.
    """
    here = Path(__file__).resolve()
    derived = functions_touching(READ_HALF, here)
    every = functions_touching(None, here)

    # Arrival: the file really was read and really does hold this module's tests.
    assert len(every) >= 25, sorted(every)
    assert "test_the_handshake_matches_rfc6455_and_checks_origin" in every
    assert derived < every

    assert PARSER_TESTS == derived, {
        "marked but does not touch the reader": sorted(PARSER_TESTS - derived),
        "touches the reader and is not marked": sorted(derived - PARSER_TESTS),
    }
    assert len(derived) == 14, sorted(derived)
