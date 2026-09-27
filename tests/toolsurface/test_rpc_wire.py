"""ADR-QR-1 / D68: the CLI↔daemon wire, pure — bytes in, bytes out.

Seam: `answer_request(raw) -> bytes` (the server half) and the two codec
helpers the client half is built from (`encode_request`, `decode_reply`). No
socket, no process, no clock: `invoke()` is the real one, over a registry this
file fills with tools that record who called them.

PP4 is proved here: every request that reaches `invoke` is HUMAN with caller id
`cli` whatever it says about itself, and a request that does not decode reaches
nothing and writes no audit row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import pytest
from chokepoint_fixture import install_test_chokepoint

from shepherd.toolsurface.registry import register
from shepherd.toolsurface.rpc import (
    MAX_REQUEST_BYTES,
    RPC_CALLER_ID,
    RPC_WIRE_VERSION,
    answer_request,
    decode_reply,
    encode_request,
)
from shepherd.toolsurface.types import (
    ActorKind,
    Audience,
    BlastClass,
    CallerContext,
    Failure,
    ToolArgs,
    ToolArgumentRefused,
    ToolDef,
    ToolResult,
)

CORRELATION_ID = "0123456789abcdef0123456789abcdef"

#: Every argument a test below sends; `invoke` refuses an undeclared one.
TEST_PROPERTIES: Mapping[str, object] = {
    "x": {"type": "integer"},
    "k": {"type": "string"},
    "a": {"type": "boolean"},
    "pad": {"type": "string"},
}


class Seen:
    """Every caller a registered handler was handed, in order."""

    def __init__(self) -> None:
        self.calls: list[tuple[Mapping[str, object], CallerContext]] = []

    def handler(self, args: ToolArgs, ctx: CallerContext) -> object:
        self.calls.append((dict(args), ctx))
        return {"echo": dict(args)}


def a_tool(name: str, handler: object, audiences: frozenset[Audience]) -> ToolDef:
    assert callable(handler)
    return ToolDef(
        name=name,
        description=f"the {name} test tool",
        input_schema={"type": "object", "properties": TEST_PROPERTIES},
        blast_class=BlastClass.LOCAL_READ,
        handler=handler,
        audiences=audiences,
    )


def request(**fields: object) -> bytes:
    body: dict[str, object] = {
        "v": RPC_WIRE_VERSION,
        "tool": "echo",
        "args": {},
        "correlation_id": CORRELATION_ID,
    }
    body.update(fields)
    return json.dumps(body).encode("utf-8")


def reply_of(raw: bytes) -> dict[str, object]:
    decoded = json.loads(raw)
    assert isinstance(decoded, dict)
    return decoded


def test_a_request_is_invoked_as_human_whatever_it_says() -> None:
    """PP4, first half. The request has no audience field, and one it sends
    anyway is ignored: the server builds the caller, never the client."""
    seen = Seen()
    register(a_tool("echo", seen.handler, frozenset({Audience.HUMAN})))
    records = install_test_chokepoint()

    raw = request(args={"x": 1}, audience="master", caller_id="master-agent", actor_kind="worker")
    reply = reply_of(answer_request(raw))

    assert reply == {"v": 1, "ok": True, "data": {"echo": {"x": 1}}, "error": None, "failure": None}
    assert len(seen.calls) == 1
    args, ctx = seen.calls[0]
    assert args == {"x": 1}
    assert ctx.audience is Audience.HUMAN
    assert ctx.caller_id == RPC_CALLER_ID == "cli"
    assert ctx.correlation_id == CORRELATION_ID
    assert ctx.actor_kind is None
    # …and the audit row the chokepoint wrote says the same thing.
    assert [(r.actor_kind, r.actor_id, r.correlation_id) for r in records] == [
        (ActorKind.HUMAN, "cli", CORRELATION_ID)
    ]


def test_a_master_only_tool_is_not_reachable_over_the_wire() -> None:
    """The audience is forced, so a tool registered for the master alone is
    exactly as absent here as it is from the web UI."""
    seen = Seen()
    register(a_tool("echo", seen.handler, frozenset({Audience.MASTER})))

    reply = reply_of(answer_request(request(audience="master")))

    assert reply["ok"] is False
    assert reply["failure"] == "unavailable"
    assert seen.calls == []


BAD_REQUESTS: dict[str, bytes] = {
    "not_json": b"{this is not json",
    "not_utf8": b"\xff\xfe\x00",
    "empty": b"",
    "not_an_object": b"[1, 2, 3]",
    "too_big": request(args={"pad": "x" * MAX_REQUEST_BYTES}),
    "wrong_version": request(v=2),
    "version_is_a_bool": request(v=True),
    "missing_v": json.dumps({"tool": "echo", "args": {}, "correlation_id": CORRELATION_ID}).encode(),
    "missing_tool": json.dumps({"v": 1, "args": {}, "correlation_id": CORRELATION_ID}).encode(),
    "missing_args": json.dumps({"v": 1, "tool": "echo", "correlation_id": CORRELATION_ID}).encode(),
    "missing_correlation_id": json.dumps({"v": 1, "tool": "echo", "args": {}}).encode(),
    "empty_tool": request(tool=""),
    "long_tool": request(tool="t" * 129),
    "tool_not_a_string": request(tool=7),
    "args_not_an_object": request(args=["x"]),
    "uppercase_correlation_id": request(correlation_id=CORRELATION_ID.upper()),
    "short_correlation_id": request(correlation_id="abc123"),
    "correlation_id_not_a_string": request(correlation_id=12),
}


@pytest.mark.parametrize("case", sorted(BAD_REQUESTS))
def test_a_malformed_request_invokes_nothing(case: str) -> None:
    """PP4, second half: nothing is invoked, and so nothing is audited."""
    seen = Seen()
    register(a_tool("echo", seen.handler, frozenset({Audience.HUMAN})))
    records = install_test_chokepoint()

    reply = reply_of(answer_request(BAD_REQUESTS[case]))

    assert reply["v"] == 1
    assert reply["ok"] is False
    assert reply["failure"] == "refused"
    assert reply["data"] is None
    error = reply["error"]
    assert isinstance(error, str) and error.startswith("bad request (correlation_id="), error
    assert seen.calls == []
    assert records == []


def test_a_bad_request_carries_its_own_correlation_id_when_it_sent_a_valid_one() -> None:
    reply = reply_of(answer_request(request(v=9)))
    assert reply["error"] == f"bad request (correlation_id={CORRELATION_ID})"


def test_a_bad_request_without_one_is_given_a_minted_id() -> None:
    reply = reply_of(answer_request(b"nope"))
    error = reply["error"]
    assert isinstance(error, str)
    minted = error.removeprefix("bad request (correlation_id=").removesuffix(")")
    assert len(minted) == 32 and set(minted) <= set("0123456789abcdef"), error


def refuse(args: ToolArgs, ctx: CallerContext) -> object:
    raise ToolArgumentRefused("--since 30d is not a date")


def explode(args: ToolArgs, ctx: CallerContext) -> object:
    raise RuntimeError("the handler raised half way through")


def test_a_reply_round_trips_ok_refused_failed_and_unavailable() -> None:
    """The client's decode of the server's encode is the `ToolResult` that
    `invoke` returned — every field, for each of the four endings."""
    seen = Seen()
    register(a_tool("echo", seen.handler, frozenset({Audience.HUMAN})))
    register(a_tool("refuse", refuse, frozenset({Audience.HUMAN})))
    register(a_tool("explode", explode, frozenset({Audience.HUMAN})))

    def over_the_wire(name: str) -> ToolResult:
        return decode_reply(answer_request(encode_request(name, {"k": "v"}, CORRELATION_ID)))

    assert over_the_wire("echo") == ToolResult(ok=True, data={"echo": {"k": "v"}}, error=None)
    assert over_the_wire("refuse") == ToolResult(
        ok=False,
        data=None,
        error=f"--since 30d is not a date (correlation_id={CORRELATION_ID})",
        failure=Failure.REFUSED,
    )
    assert over_the_wire("explode") == ToolResult(
        ok=False,
        data=None,
        error=f"request failed (correlation_id={CORRELATION_ID})",
        failure=Failure.FAILED,
    )
    assert over_the_wire("absent") == ToolResult(
        ok=False,
        data=None,
        error=f"request failed (correlation_id={CORRELATION_ID})",
        failure=Failure.UNAVAILABLE,
    )


def test_the_request_the_client_encodes_names_no_audience() -> None:
    body = json.loads(encode_request("echo", {"a": True}, CORRELATION_ID))
    assert body == {"v": 1, "tool": "echo", "args": {"a": True}, "correlation_id": CORRELATION_ID}


def test_untransportable_data_is_a_failed_reply() -> None:
    register(a_tool("stream", lambda args, ctx: object(), frozenset({Audience.HUMAN})))

    reply = reply_of(answer_request(request(tool="stream")))

    assert reply == {"v": 1, "ok": False, "data": None, "error": "not transportable", "failure": "failed"}


@pytest.mark.parametrize(
    "raw",
    [b"", b"not json", b"[]", b'{"v": 2, "ok": true, "data": null, "error": null, "failure": null}',
     b'{"v": 1, "ok": "yes", "data": null, "error": null, "failure": null}',
     b'{"v": 1, "ok": false, "data": null, "error": null, "failure": "exploded"}',
     b'{"v": 1, "ok": false, "data": null, "error": 3, "failure": "failed"}'],
)
def test_a_reply_that_does_not_decode_is_a_value_error(raw: bytes) -> None:
    """The client's half refuses a reply it cannot read rather than guessing;
    `call_remote` turns that into a FAILED result (the socket tests)."""
    with pytest.raises(ValueError):
        decode_reply(raw)
