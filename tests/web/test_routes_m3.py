"""T18's route half: the first POST routes there have ever been, and the WS.

Seam: HTTP. Every assertion goes through a socket to a live loopback server,
because that is the only surface a browser has — a route table that resolves
correctly in a unit test and is never reached by `do_POST` is a table nobody
can use.

Two properties are load-bearing and each is the reason a rule exists:

* **§13's origin check applies to the new verb.** M1 exposed no POST, so the
  check was proved on the stream handshake and *inherited* here. Inheritance is
  a claim until something asserts it, which is what this file does.
* **An undeclared field is dropped, never forwarded.** A body is bigger than a
  query string and a mutation is on the other end, so a smuggled argument is
  how a caller reaches a handler past `invoke()`'s schema check (D53).
"""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

import pytest
from web.conftest import Client

from shepherd.core.states import Origin
from shepherd.runner.base import PaneRef
from shepherd.store.db import Store
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.toolsurface.registry import registered_tools
from shepherd.toolsurface.tools_m3 import M3_TOOL_NAMES
from shepherd.web import routes, ws

WEB_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web"

OWNED_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFG"
OWNED_NAME = f"shepherd_{OWNED_ID}"


def owned(store: Store, runner: ScriptedRunner) -> str:
    """A real owned row with a real handle, and the pane the driver answers for.

    Both halves, because a row whose pane the driver does not know is T12's
    orphan and every terminal call against it is refused — which would make the
    assertions below pass for the wrong reason.
    """
    from shepherd.core.runner import RunnerHandle
    from shepherd.testkit.scripted_runner import RUNNER_NAME, SCRIPTED_SOCKET

    workspace = store.create_project(name="owned", description=None)
    store.create_owned_session(
        session_id=OWNED_ID,
        engine_session_id="11111111-2222-3333-4444-555555555555",
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/tmp",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.USER_UI,
        parent_session_id=None,
        depth=0,
        ephemeral=False,
        title=None,
        title_source="brief",
        handle=RunnerHandle(
            runner=RUNNER_NAME, socket=SCRIPTED_SOCKET, session_name=OWNED_NAME
        ),
        model=None,
        effort=None,
    )
    runner.live[OWNED_NAME] = PaneRef(
        session_name=OWNED_NAME, session_id=OWNED_ID, pane_pid=4041880, dead=False
    )
    return OWNED_ID


# ----- the table --------------------------------------------------------------


def test_the_route_table_declares_every_query_and_body_field() -> None:
    """Every POST route has a `BODY_ARGS` entry, and every declared field is a
    property of the tool's own schema.

    The second half is what makes the rule bite: a body field declared here that
    the schema does not name would be forwarded and then refused by `invoke()`
    as an unknown argument — a 400 nobody could explain. `rename_session` is
    registered by T20, so its schema cannot be checked yet and its **route** is
    checked instead, which is exactly the split revision 2 made.

    Goes red if a route is added without declaring its body, and if a declared
    field is not a real property of the tool it forwards to.
    """
    assert set(routes.BODY_ARGS) == set(routes.POST_ROUTES)
    assert set(routes.QUERY_ARGS) <= set(routes.API_ROUTES)

    available = registered_tools()
    checked = 0
    for template, tool_name in routes.POST_ROUTES.items():
        tool = available.get(tool_name)
        if tool is None:
            assert tool_name == "rename_session", tool_name
            continue
        properties = tool.input_schema["properties"]
        assert isinstance(properties, dict)
        for field in routes.BODY_ARGS[template]:
            assert field in properties, (template, field)
        checked += 1
    # Arrival: the loop really checked the fifteen that exist today — M3's
    # six, plus T24's three, plus the Projects page's six (five at T4.1 and
    # `set_project_description` at T3.4), minus `rename_session`, whose schema
    # is T20's. Recomputed from the table rather than copied: sixteen POST
    # routes, one of them unregistered here.
    assert checked == len(routes.POST_ROUTES) - 1 == 15


def test_every_api_and_query_field_is_a_property_of_its_tool() -> None:
    """The same rule on the GET side, including M3's two new read routes."""
    available = registered_tools()
    for template, names in routes.QUERY_ARGS.items():
        properties = available[routes.API_ROUTES[template]].input_schema["properties"]
        assert isinstance(properties, dict)
        for field in names:
            assert field in properties, (template, field)


def test_the_new_read_routes_name_m3_tools() -> None:
    assert routes.API_ROUTES["/api/sessions/{session_id}/output"] == "get_session_output"
    assert routes.API_ROUTES["/api/mailbox"] == "list_mailbox"
    assert {"get_session_output", "list_mailbox"} <= set(M3_TOOL_NAMES)


def test_the_terminal_path_is_not_reachable_as_a_call() -> None:
    """An upgrade is not a call, exactly as `SSE_PATH` is not one."""
    assert routes.TERMINAL_WS_PATH not in routes.API_ROUTES
    assert routes.TERMINAL_WS_PATH not in routes.POST_ROUTES
    assert routes.resolve_terminal(f"/api/sessions/{OWNED_ID}/terminal") == OWNED_ID
    assert routes.resolve_terminal("/api/sessions/terminal") is None
    assert routes.resolve(f"/api/sessions/{OWNED_ID}/terminal", {}) is None


# ----- the POST verb ----------------------------------------------------------


def test_a_post_reaches_the_capability_through_invoke(
    client: Client, store: Store, tmp_path: Path
) -> None:
    """The first mutation `web/` has ever had, end to end."""
    root = tmp_path / "work"
    (root / "repo").mkdir(parents=True)
    workspace = store.create_project(name="spawnable", description=None)
    # §13's allowlist after D57 is the project's registered repo paths alone.
    store.add_repo(
        workspace_id=workspace.id,
        root_path=str(root),
        name="work",
        git_common_dir=str(root / ".git"),
        vcs_remote=None,
    )

    response = client.post(
        "/api/sessions", {"workspace_id": workspace.id, "cwd": str(root / "repo")}
    )
    assert response.status == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert isinstance(data, dict)
    assert data["spawned"] is True
    assert isinstance(data["session_id"], str)


def test_a_post_without_a_matching_origin_is_refused(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """§13, inherited from the stream handshake and now asserted on the verb.

    Arrival before absence: the same request **with** a matching origin reaches
    the capability, so the 403 below is the check firing and not a 403 every
    POST would get.

    Goes red if the origin check is skipped for the new verb, and if it is
    applied after the body is dispatched.
    """
    session_id = owned(store, scripted_runner)
    allowed = client.post(f"/api/sessions/{session_id}/interrupt")
    assert allowed.status == 200
    assert allowed.json()["ok"] is True

    for header in ({"Origin": "http://evil.invalid"}, {"Origin": "null"}):
        refused = client.post(f"/api/sessions/{session_id}/interrupt", headers=header)
        assert refused.status == 403, header
        assert refused.json()["error"] == "request failed"

    # A `Host` that is not the bound address is refused too — the other half of
    # the check, and the one a same-origin fetch with no `Origin` relies on.
    spoofed = client.post(
        f"/api/sessions/{session_id}/interrupt",
        headers={"Host": "evil.invalid", "Origin": client.origin},
    )
    assert spoofed.status == 403


def test_an_undeclared_body_field_is_dropped(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """D53: a caller cannot smuggle an argument past `invoke()`'s schema check.

    `choice` is a real property of `answer_permission` and a real danger — it is
    the positional digit P4 was run to pin down. Sent to `interrupt`, which does
    not declare it, it must be **dropped**: forwarded, `invoke()` would refuse
    the whole call as an unknown argument, which is a 400 nobody can explain and
    a route that works or not depending on what a page happens to send.

    Goes red if `BODY_ARGS` stops filtering.
    """
    session_id = owned(store, scripted_runner)
    response = client.post(
        f"/api/sessions/{session_id}/interrupt", {"choice": "deny", "anything": 1}
    )
    assert response.status == 200
    data = response.json()["data"]
    assert isinstance(data, dict)
    assert data["interrupted"] is True

    # …and the drop happens in the table, not only in the server.
    resolved = routes.resolve_post(
        f"/api/sessions/{session_id}/interrupt", {"choice": "deny", "anything": 1}
    )
    assert resolved is not None
    assert resolved.args == {"session_id": session_id}


def path_parameters(template: str) -> tuple[str, ...]:
    """The `{…}` segments of one template — the property's subject, **derived**.

    The guard used to enumerate two names (`routes.SESSION_ID` and
    `routes.PROJECT_ID`) and check them against every template's fields. Two of
    the three path parameters this table has: `approval_id` was covered by a
    comment and nothing else. Worse, the check was keyed on constants no
    production code reads, so a typo in one of them made the assertion
    **vacuous and green** — it would have gone on checking that a name nothing
    uses is absent from every route.

    Reading the parameters off the template cannot go vacuous and cannot miss
    one: every present and future path parameter is in its own template.
    """
    return tuple(
        part[1:-1]
        for part in template.split("/")
        if part.startswith("{") and part.endswith("}")
    )


def shadowing(table: Mapping[str, tuple[str, ...]]) -> list[tuple[str, str]]:
    """Every (template, field) where a declared field is spelled like one of
    that template's own path parameters."""
    return [
        (template, parameter)
        for template, names in table.items()
        for parameter in path_parameters(template)
        if parameter in names
    ]


def test_no_declared_field_shadows_a_path_parameter() -> None:
    """No route declares one of its **own** path parameters as a field.

    This is the property that actually keeps a body from redirecting a kill,
    and it was found by mutation: reversing the merge order inside
    `resolve_post` **survived**, because `BODY_ARGS` had already dropped the
    colliding field. The guard was held incidentally, so the property it was
    held by is asserted here by name (T11's method).

    **Both tables, and every parameter** (T3.4). The route gate one file over
    checks `BODY_ARGS` against the tool's schema and never looks at path
    parameters, so a shadowing field passes every gate this repo has and
    disagrees with the URL only at run time, in a browser. `QUERY_ARGS` is the
    same table with a different verb in front of it and is now checked the same
    way.

    The counts are stated so a route added without a declared body fails here
    rather than shrinking the evidence silently.
    """
    assert shadowing(routes.BODY_ARGS) == []
    assert shadowing(routes.QUERY_ARGS) == []
    # M3's seven, T24's three, and the Projects page's six.
    assert len(routes.BODY_ARGS) == 16
    assert len(routes.QUERY_ARGS) == 3
    # The derivation is not vacuous: the templates it reads really do carry
    # path parameters, and one of them is the `approval_id` the enumeration
    # never covered.
    assert path_parameters("/api/approvals/{approval_id}") == ("approval_id",)
    assert path_parameters("/api/projects") == ()


def test_the_shadow_guard_catches_the_parameter_the_enumeration_missed() -> None:
    """The gate, seen to fail — on the case the enumerated version survived.

    `approval_id` was named in a comment and checked by nothing. A table that
    declares it as a body field is flagged here; under the two-name enumeration
    it was green, and `decide_approval` would have taken its target from the
    body.
    """
    planted = {**routes.BODY_ARGS, "/api/approvals/{approval_id}": ("choice", "approval_id")}
    assert shadowing(planted) == [("/api/approvals/{approval_id}", "approval_id")]
    # …and the same loop bites on a query parameter, which nothing checked at all.
    assert shadowing({"/api/sessions/{session_id}": ("session_id",)}) == [
        ("/api/sessions/{session_id}", "session_id")
    ]


def test_the_path_parameter_wins_over_a_body_that_names_another_session(
    monkeypatch: object,
) -> None:
    """…and the ordering holds even where a body field *is* declared.

    The test above says no route declares `session_id` today. This one says the
    merge order is right anyway, by declaring it for one route and watching the
    path win — the belt beside the braces, and now falsifiable: reversing the
    merge in `resolve_post` turns this red.
    """
    import pytest as _pytest

    assert isinstance(monkeypatch, _pytest.MonkeyPatch)
    widened = dict(routes.BODY_ARGS)
    widened["/api/sessions/{session_id}/kill"] = ("session_id",)
    monkeypatch.setattr(routes, "BODY_ARGS", widened)

    resolved = routes.resolve_post(
        "/api/sessions/wanted/kill", {"session_id": "somebody-else", "body": "x"}
    )
    assert resolved is not None
    assert resolved.tool == "kill_session"
    assert resolved.args == {"session_id": "wanted"}


def test_the_path_parameter_wins_over_a_query_that_names_another_session(
    monkeypatch: object,
) -> None:
    """The same property on the **GET** side, which is where it was half true.

    `routes.py`'s own docstring states it table-wide — *"a path parameter always
    wins"* — and only `resolve_post` held it: `resolve` merged the query
    **after** the captured path, so a declared query parameter spelled like a
    path one would overwrite the URL's value. Nothing was exploitable, because
    no GET template collides with its own `QUERY_ARGS` today; an invariant that
    holds by the absence of a collision is an invariant that ends the day
    somebody declares one.

    Declared here for one route and watched, exactly as the POST twin above
    does, so reversing the merge inside `resolve` turns this red rather than
    surviving on a field nobody declared.
    """
    import pytest as _pytest

    assert isinstance(monkeypatch, _pytest.MonkeyPatch)
    widened = dict(routes.QUERY_ARGS)
    widened["/api/sessions/{session_id}"] = ("session_id",)
    monkeypatch.setattr(routes, "QUERY_ARGS", widened)

    resolved = routes.resolve("/api/sessions/wanted", {"session_id": ["somebody-else"]})
    assert resolved is not None
    assert resolved.tool == "get_session"
    assert resolved.args == {"session_id": "wanted"}


def test_an_unknown_post_path_is_a_404(client: Client) -> None:
    response = client.post("/api/sessions/x/nope", {})
    assert response.status == 404


# ----- the WebSocket upgrade --------------------------------------------------


def test_the_terminal_upgrade_opens_and_the_first_frame_is_binary(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """The upgrade, and that the snapshot is the **first** thing on the wire.

    **Ownership note:** the byte-for-byte claim over P-M3-10's six `.ansi`
    captures is **T19's** `test_the_first_frame_is_the_snapshot_byte_for_byte`,
    and is deliberately not duplicated here — revision 2 gave that test one
    home. What this asserts is the property T19's test needs to be about
    anything: that a 101 is returned, that a binary frame arrives before any
    other, and that it is not empty.
    """
    session_id = owned(store, scripted_runner)
    status, frames = _upgrade(client, f"/api/sessions/{session_id}/terminal")
    assert status == 101
    assert frames, "the handshake succeeded and the server framed nothing at all"
    opcode, payload = frames[0]
    assert opcode == ws.OP_BINARY
    assert payload != b""
    # The stream ended the way `_terminal` ends one — stated here as well as
    # enforced in `_upgrade`, because a caller that asserts only `frames[0]`
    # reads a truncated stream as a complete one (the sibling idiom in
    # `test_ws.py::test_live_chunks_arrive_in_order_and_stop_on_close`).
    assert frames[-1][0] == ws.OP_CLOSE


def test_a_terminal_upgrade_from_another_origin_is_refused(
    client: Client, store: Store, scripted_runner: ScriptedRunner
) -> None:
    """§13 again, on the one surface that carries raw pane bytes."""
    session_id = owned(store, scripted_runner)
    status, frames = _upgrade(
        client, f"/api/sessions/{session_id}/terminal", origin="http://evil.invalid"
    )
    assert status == 403
    assert frames == []

    # The **`Host`** half, which `ws.handshake_response` does not check: it
    # validates `Origin` only, so removing `_origin_is_allowed` from the upgrade
    # left the origin case green. Found by mutation, and this is the assertion
    # that makes the server-side check load-bearing rather than duplicated.
    spoofed, spoofed_frames = _upgrade(
        client, f"/api/sessions/{session_id}/terminal", host="evil.invalid"
    )
    assert spoofed == 403
    assert spoofed_frames == []


class TruncatedRead(AssertionError):
    """The read ended some way other than the close frame `_terminal` writes.

    Its own exception rather than a bare `assert`, because the two short
    endings are different diagnoses — a timeout and a hang-up — and a caller
    that saw `frames == []` used to report both as "no frame arrived".
    """


def _ends_with_close(buffer: bytes) -> bool:
    """Has the server's own ending — `ws.close_frame` — arrived whole?"""
    frames = _server_frames(buffer)
    return bool(frames) and frames[-1][0] == ws.OP_CLOSE


def _upgrade(
    client: Client,
    path: str,
    origin: str | None = None,
    host: str | None = None,
    read_timeout: float = 5.0,
) -> tuple[int, list[tuple[int, bytes]]]:
    """One WebSocket upgrade over a raw socket, then every frame that arrives.

    Raw rather than `http.client`, because a 101 hands the connection over and
    `http.client` will not read past its own response.

    **It reads to the ending the server actually writes**, which is
    `server.py::_terminal`'s `ws.close_frame(CLOSE_NORMAL)` — not to EOF, and
    not to a clock. The older loop read until EOF *or* a 5 s timeout and then
    decoded whatever had arrived, so a slow server handed the caller an empty
    list and the caller said "no frame arrived after the handshake", naming a
    cause that had not happened. A short read now raises `TruncatedRead` saying
    which short it was, and a timeout reports as a timeout.
    """
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host or f'{client.host}:{client.port}'}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: {origin or client.origin}\r\n"
        "\r\n"
    ).encode("ascii")
    with socket.create_connection((client.host, client.port), timeout=10) as sock:
        sock.sendall(request)
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(65536)
            if not chunk:
                break
            raw += chunk
        head, _, rest = raw.partition(b"\r\n\r\n")
        status = int(head.split(b" ")[1])
        if status != 101:
            return status, []
        sock.settimeout(read_timeout)
        buffer, timed_out = rest, False
        while not _ends_with_close(buffer):
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                timed_out = True
                break
            except OSError:
                break
            if not chunk:
                break
            buffer += chunk
    frames = _server_frames(buffer)
    if not _ends_with_close(buffer):
        seen = f"{len(frames)} frame" + ("" if len(frames) == 1 else "s")
        raise TruncatedRead(
            f"the read timed out after {read_timeout}s with {seen} and no close"
            " frame: a truncated read, not a complete stream"
            if timed_out
            else f"the server hung up after {seen} without a close frame:"
            " `_terminal` ends every stream with `ws.close_frame`"
        )
    return status, frames


def _server_frames(buffer: bytes) -> list[tuple[int, bytes]]:
    """Decode **unmasked server** frames: `(opcode, payload)` in order.

    Hand-decoded rather than run through `ws.parse_frame`, on purpose twice
    over. `parse_frame` is the *client*-frame reader and fails an unmasked frame
    by design (RFC §5.1), so it cannot read a server frame at all — and a test
    that round-tripped this module's own writer through this module's own reader
    would prove self-consistency and nothing else.
    """
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


# ----- the helper's own honesty -----------------------------------------------


@contextmanager
def _stub_upgrade_server(after_handshake: bytes, *, hold: bool) -> Iterator[Client]:
    """A loopback server that answers one upgrade with exactly `after_handshake`.

    `hold=True` then keeps the socket open and sends nothing more — the slow
    server this helper must not mistake for a finished one. `hold=False` hangs
    up, which is the other way a read can end short.
    """
    release = threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve() -> None:
        connection, _ = listener.accept()
        with connection:
            raw = b""
            while b"\r\n\r\n" not in raw:
                chunk = connection.recv(65536)
                if not chunk:
                    return
                raw += chunk
            connection.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n" + after_handshake
            )
            if hold:
                release.wait(30.0)

    thread = threading.Thread(target=serve, name="stub-upgrade", daemon=True)
    thread.start()
    try:
        yield Client("127.0.0.1", listener.getsockname()[1])
    finally:
        release.set()
        thread.join(timeout=10)
        listener.close()


def test_the_upgrade_helper_reports_a_timeout_as_a_timeout() -> None:
    """A slow server must not read as a finished one.

    The old helper read until EOF *or* a five-second timeout and then decoded
    whatever had arrived, so a server that was merely slow produced
    `frames == []` and the caller's message — "no frame arrived after the
    handshake" — named a cause that had not happened.
    """
    snapshot = ws.build_frame(b"SCREEN", opcode=ws.OP_BINARY)
    with _stub_upgrade_server(snapshot, hold=True) as client:
        with pytest.raises(TruncatedRead) as caught:
            _upgrade(client, "/api/sessions/x/terminal", read_timeout=0.25)

    assert "timed out" in str(caught.value)
    assert "0.25" in str(caught.value)
    # …and it says what it *did* see, so a real hang is distinguishable from a
    # server that never wrote anything at all.
    assert "1 frame" in str(caught.value), str(caught.value)


def test_the_upgrade_helper_will_not_read_a_hang_up_as_a_finished_stream() -> None:
    """EOF is not an ending: `_terminal` ends with `ws.close_frame`, always."""
    snapshot = ws.build_frame(b"SCREEN", opcode=ws.OP_BINARY)
    with _stub_upgrade_server(snapshot, hold=False) as client:
        with pytest.raises(TruncatedRead) as caught:
            _upgrade(client, "/api/sessions/x/terminal", read_timeout=5.0)

    assert "without a close frame" in str(caught.value)
    assert "timed out" not in str(caught.value)


def test_the_upgrade_helper_accepts_the_ending_the_server_actually_writes() -> None:
    """Arrival, before either absence: the complete stream is read as complete.

    Without this, both assertions above are satisfied by a helper that raises
    on everything.
    """
    ended = ws.build_frame(b"SCREEN", opcode=ws.OP_BINARY) + ws.close_frame(
        ws.CLOSE_NORMAL
    )
    with _stub_upgrade_server(ended, hold=True) as client:
        status, frames = _upgrade(client, "/api/sessions/x/terminal", read_timeout=5.0)

    assert status == 101
    assert [opcode for opcode, _ in frames] == [ws.OP_BINARY, ws.OP_CLOSE]
    assert frames[0][1] == b"SCREEN"
