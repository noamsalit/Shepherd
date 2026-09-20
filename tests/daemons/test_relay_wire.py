"""T10b: the hop's wire format, as a pure codec.

One long-lived connection carries many frames, so this hop is framed —
newline-delimited JSON, one object per line, payload base64-encoded so the
framing is binary-safe no matter what a hook sends. The payload used here is a
real captured hook frame (data-schemas §"Common input fields"), and the 40 KB
case is the size Result 2 of `docs/probes/2026-09-16-hookd-latency.md` verified
arrives byte-complete over the ingest socket.
"""

from __future__ import annotations

import json

import pytest

from shepherd.core.frames import Frame
from shepherd.engines.claude_code.relay_wire import (
    Hello,
    WireError,
    decode_frame,
    decode_hello,
    encode_frame,
    encode_hello,
)

CORPUS_PAYLOAD = (
    b'{"session_id":"8bbcceab-0b3e-4e24-98c9-ec146b1ca8c6","cwd":'
    b'"/tmp/shp-hooks-base-dwqg6d95","hook_event_name":"PreToolUse",'
    b'"tool_name":"Bash"}\n'
)


def test_relay_wire_roundtrip() -> None:
    """Every frame survives the round trip, including the two shapes that break
    naive framing: a 40 KB payload and one carrying embedded newlines."""
    cases = [
        Frame(payload=CORPUS_PAYLOAD, received_at="2026-09-14T16:22:01+00:00", peer_pid=4048291),
        Frame(payload=b'{"pad":"' + b"x" * 40_000 + b'"}\n', received_at="2026-09-16T00:00:00+00:00", peer_pid=None),
        Frame(payload=b'{"a":1}\n{"b":2}\n\n', received_at="2026-09-16T00:00:01+00:00", peer_pid=7),
        Frame(payload=b"\x00\xff\x80not-utf8\n", received_at="2026-09-16T00:00:02+00:00", peer_pid=0),
    ]
    for frame in cases:
        line = encode_frame(frame)
        assert line.endswith(b"\n")
        assert line.count(b"\n") == 1, "one object per line, whatever the payload holds"
        assert decode_frame(line) == frame


def test_encoded_frame_is_the_documented_object() -> None:
    """The three keys the plan writes down, spelled exactly."""
    frame = Frame(payload=b"hi", received_at="2026-09-16T00:00:00+00:00", peer_pid=12)
    obj = json.loads(encode_frame(frame).decode("utf-8"))
    assert obj == {
        "payload_b64": "aGk=",  # base64 of b"hi", from the spec's alphabet, not from the code
        "received_at": "2026-09-16T00:00:00+00:00",
        "peer_pid": 12,
    }


def test_hello_roundtrip_is_the_documented_object() -> None:
    line = encode_hello(Hello(schema_version=1, pid=4048291))
    assert json.loads(line.decode("utf-8")) == {
        "hello": "controld",
        "schema_version": 1,
        "pid": 4048291,
    }
    assert decode_hello(line) == Hello(schema_version=1, pid=4048291)


@pytest.mark.parametrize(
    "line",
    [
        b"not json\n",
        b"[]\n",
        b'{"received_at":"x","peer_pid":null}\n',
        b'{"payload_b64":"!!not-base64!!","received_at":"x","peer_pid":null}\n',
        b'{"payload_b64":"aGk=","received_at":7,"peer_pid":null}\n',
        b'{"payload_b64":"aGk=","received_at":"x","peer_pid":"nine"}\n',
    ],
)
def test_decode_frame_refuses_a_malformed_line(line: bytes) -> None:
    """A bad line is a named refusal, never a driver exception leaking upward."""
    with pytest.raises(WireError):
        decode_frame(line)


@pytest.mark.parametrize(
    "line",
    [b"not json\n", b'{"hello":"controld","pid":1}\n', b'{"hello":"sessiond","schema_version":1,"pid":1}\n'],
)
def test_decode_hello_refuses_a_malformed_line(line: bytes) -> None:
    with pytest.raises(WireError):
        decode_hello(line)
