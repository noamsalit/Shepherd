"""D68 / ADR-QR-1: the CLI↔daemon wire — one JSON request, one JSON reply.

A `shepherd` process the daemon did not start has an empty registry, so every
fleet line it printed was an honest *unknown* (T18-1, BC-05). This is how it
reaches the daemon's surface instead: the client writes one JSON object and
shuts its write side, the server reads to EOF, calls `invoke()` and writes one
JSON object back.

* **The audience is the server's, never the client's.** The request has no
  audience field, and one it sends anyway is ignored: every call that reaches
  `invoke` is `HUMAN` with caller id `cli` (`registry.py`'s rejected origin
  argument, one hop out). The socket is owner-only (0600 in a 0700 dir), so the
  same uid is the same trust as the loopback page — and nothing more (D68).
* **A malformed request reaches nothing.** Bad JSON, too big, the wrong `v`, a
  missing or ill-typed field: the reply is `refused`, and `invoke` is not
  called, so no audit row is written for a call nobody made.
* **Nothing is logged.** `src/` has no logger and D25 keeps `toolsurface/` from
  importing `shepherd.logs`: a refusal is the reply's returned value. A call
  that is invoked is audited by `invoke`, exactly as the web UI's are.

`answer_request` is pure apart from `invoke`; `call_remote` is the client.
"""

from __future__ import annotations

import json
import re
import socket
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from shepherd.toolsurface.registry import invoke
from shepherd.toolsurface.types import Audience, CallerContext, Failure, ToolResult

#: The socket's name under the runtime dir. PP15: no longer than
#: `CONTROL_SOCKET_NAME`, so wherever the control socket fits, this one fits.
RPC_SOCKET_NAME = "rpc"
RPC_WIRE_VERSION = 1
MAX_REQUEST_BYTES = 1 << 20
RPC_CALLER_ID = "cli"
MAX_TOOL_NAME = 128

BAD_REQUEST = "bad request"
NOT_TRANSPORTABLE = "not transportable"
NO_ANSWER = "the daemon did not answer"

_CORRELATION_ID = re.compile(r"[0-9a-f]{32}")
_FAILURES = frozenset(member.value for member in Failure)
_RECV_CHUNK = 65_536


class ReplyMalformed(ValueError):
    """A reply the client cannot read as the wire's one reply shape."""


@dataclass(frozen=True)
class RpcRequest:
    tool: str
    args: Mapping[str, object]
    correlation_id: str


# --- the server half ----------------------------------------------------------


def _decode_json(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _valid_correlation_id(value: object) -> str | None:
    return value if isinstance(value, str) and _CORRELATION_ID.fullmatch(value) else None


def _is_version(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == RPC_WIRE_VERSION


def decode_request(raw: bytes) -> tuple[RpcRequest | None, str | None]:
    """`(request, correlation id)`. The id is returned even when the request is
    not, so a refusal can carry the id the caller will look for."""
    body = _decode_json(raw) if len(raw) <= MAX_REQUEST_BYTES else None
    if not isinstance(body, dict):
        return None, None
    correlation_id = _valid_correlation_id(body.get("correlation_id"))
    tool, args = body.get("tool"), body.get("args")
    if (
        correlation_id is None
        or not _is_version(body.get("v"))
        or not isinstance(tool, str)
        or not 1 <= len(tool) <= MAX_TOOL_NAME
        or not isinstance(args, dict)
    ):
        return None, correlation_id
    arguments = {str(key): value for key, value in args.items()}
    return RpcRequest(tool=tool, args=arguments, correlation_id=correlation_id), correlation_id


def _encode_reply(ok: bool, data: object, error: str | None, failure: Failure | None) -> bytes:
    body = {
        "v": RPC_WIRE_VERSION,
        "ok": ok,
        "data": data,
        "error": error,
        "failure": None if failure is None else failure.value,
    }
    return json.dumps(body).encode("utf-8")


def encode_result(result: ToolResult) -> bytes:
    """The reply for one invoked call. Data JSON cannot carry (a
    `TerminalStream`, say) is a `failed` reply, never a half-written one."""
    try:
        return _encode_reply(result.ok, result.data, result.error, result.failure)
    except (TypeError, ValueError):
        return _encode_reply(False, None, NOT_TRANSPORTABLE, Failure.FAILED)


def answer_request(raw: bytes) -> bytes:
    """One request's bytes → one reply's bytes. Never raises on bad input."""
    request, correlation_id = decode_request(raw)
    if request is None:
        cid = correlation_id if correlation_id is not None else uuid.uuid4().hex
        return _encode_reply(False, None, f"{BAD_REQUEST} (correlation_id={cid})", Failure.REFUSED)
    ctx = CallerContext(
        audience=Audience.HUMAN, caller_id=RPC_CALLER_ID, correlation_id=request.correlation_id
    )
    return encode_result(invoke(request.tool, request.args, ctx))


# --- the client half ----------------------------------------------------------


def encode_request(name: str, args: Mapping[str, object], correlation_id: str) -> bytes:
    """The request `call_remote` sends. It names no audience: it has none to name."""
    body = {"v": RPC_WIRE_VERSION, "tool": name, "args": dict(args), "correlation_id": correlation_id}
    return json.dumps(body).encode("utf-8")


def _optional_text(body: Mapping[str, object], key: str) -> str | None:
    value = body.get(key)
    if value is not None and not isinstance(value, str):
        raise ReplyMalformed(f"{key} is not a string")
    return value


def decode_reply(raw: bytes) -> ToolResult:
    """The `ToolResult` a reply carries, or `ReplyMalformed` (a `ValueError`)."""
    body = _decode_json(raw)
    if not isinstance(body, dict) or not _is_version(body.get("v")):
        raise ReplyMalformed("not a version-1 reply")
    ok, failure = body.get("ok"), body.get("failure")
    if not isinstance(ok, bool):
        raise ReplyMalformed("ok is not a boolean")
    if failure is not None and failure not in _FAILURES:
        raise ReplyMalformed("failure is not a known kind")
    return ToolResult(
        ok=ok,
        data=body.get("data"),
        error=_optional_text(body, "error"),
        failure=None if failure is None else Failure(failure),
    )


def _read_reply(conn: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while chunk := conn.recv(_RECV_CHUNK):
        chunks.append(chunk)
    return b"".join(chunks)


def _no_answer(error: Exception) -> ToolResult:
    message = f"{NO_ANSWER}: {type(error).__name__}"
    return ToolResult(ok=False, data=None, error=message, failure=Failure.FAILED)


def call_remote(
    path: Path,
    name: str,
    args: Mapping[str, object],
    ctx: CallerContext,
    timeout_s: float = 120.0,
) -> ToolResult | None:
    """The daemon's answer, or `None` when there is no daemon to ask.

    Only "nothing is listening" is `None` — no socket file, or a stale one — so
    the caller falls back to its own `invoke`. Every failure after the connect
    is a `FAILED` result naming its class: a daemon that took the call and then
    went quiet may have half done it, and a silent local answer would hide that.
    """
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with conn:
        conn.settimeout(timeout_s)
        try:
            conn.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            return None
        except OSError as error:
            return _no_answer(error)
        try:
            conn.sendall(encode_request(name, args, ctx.correlation_id))
            conn.shutdown(socket.SHUT_WR)
            return decode_reply(_read_reply(conn))
        except (OSError, ValueError, TypeError) as error:
            return _no_answer(error)
