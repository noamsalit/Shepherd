"""T10b: the wire format of the `sessiond` → `controld` hop. Pure — no I/O.

Two hops, two formats, and the difference is deliberate. The ingest socket
(T10) is **one connection per frame, read to EOF**: that is the hook contract
(data-schemas §"Hook runtime contract" — the dispatcher writes and closes) and
it stays. This hop is **one long-lived connection carrying many frames**, so it
needs framing of its own: newline-delimited JSON, one object per line, with the
payload base64-encoded so the framing is binary-safe regardless of what a hook
sends. A hook payload is arbitrary bytes; a captured one already contains
newlines, and `Frame.payload` is `bytes`, not `str`.

```text
controld → sessiond, first line:   {"hello":"controld","schema_version":<int>,"pid":<int>}
sessiond → controld, each frame:   {"payload_b64":"<base64>","received_at":"<iso8601>","peer_pid":<int|null>}
```

Pure by construction (ADR-1's purity map): no socket, no clock, no filesystem.
Both halves of the hop import this one module, which is what keeps T10 and T10b
independent of each other rather than circular.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from shepherd.core.frames import Frame

#: The greeting's fixed tag. `controld` is the only speaker of this line: it is
#: the process that owns the database and therefore the only one that can
#: report a schema version (D37, §7 migration rule 3).
HELLO_TAG = "controld"


class WireError(ValueError):
    """A line that is not a frame, or not a hello.

    Named here so a malformed line is a refusal this system owns, rather than a
    `JSONDecodeError`, a `UnicodeDecodeError` or a `binascii.Error` leaking
    upward from three different libraries (D33's rule, applied to the wire).
    """


@dataclass(frozen=True)
class Hello:
    """What `controld` reports about itself before any frame may be sent."""

    schema_version: int
    pid: int


def _object(line: bytes) -> dict[str, object]:
    """The line as a JSON object, or a `WireError`. Never returns a non-object."""
    try:
        parsed: object = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return _refuse(f"line is not JSON: {error}")
    if not isinstance(parsed, dict):
        return _refuse(f"line is a {type(parsed).__name__}, not an object")
    return {str(key): value for key, value in parsed.items()}


def _refuse(detail: str) -> dict[str, object]:
    raise WireError(detail)


def _int_field(obj: dict[str, object], key: str) -> int:
    value = obj.get(key)
    # `bool` is an `int` in Python and a pid is not a flag, so it is refused.
    if not isinstance(value, int) or isinstance(value, bool):
        raise WireError(f"{key!r} is {value!r}, expected an int")
    return value


def _str_field(obj: dict[str, object], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str):
        raise WireError(f"{key!r} is {value!r}, expected a string")
    return value


def encode_hello(hello: Hello) -> bytes:
    payload = {"hello": HELLO_TAG, "schema_version": hello.schema_version, "pid": hello.pid}
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def decode_hello(line: bytes) -> Hello:
    obj = _object(line)
    tag = _str_field(obj, "hello")
    if tag != HELLO_TAG:
        raise WireError(f"hello tag is {tag!r}, expected {HELLO_TAG!r}")
    return Hello(schema_version=_int_field(obj, "schema_version"), pid=_int_field(obj, "pid"))


def encode_frame(frame: Frame) -> bytes:
    payload = {
        "payload_b64": base64.b64encode(frame.payload).decode("ascii"),
        "received_at": frame.received_at,
        "peer_pid": frame.peer_pid,
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def decode_frame(line: bytes) -> Frame:
    obj = _object(line)
    encoded = _str_field(obj, "payload_b64")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise WireError(f"payload_b64 is not base64: {error}") from error
    peer_pid = obj.get("peer_pid")
    if peer_pid is not None and (not isinstance(peer_pid, int) or isinstance(peer_pid, bool)):
        raise WireError(f"'peer_pid' is {peer_pid!r}, expected an int or null")
    return Frame(
        payload=payload,
        received_at=_str_field(obj, "received_at"),
        peer_pid=peer_pid,
    )
