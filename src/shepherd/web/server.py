"""The stdlib HTTP server behind the fleet page (D51, §12, §13).

`http.server` and nothing else: D51 chose the stdlib after finding the stack
line promised "stdlib plus one runtime dependency" and then specified a
WebSocket. The one runtime dependency is `xterm.js`, and it arrives at M3.

Three of §13's rules are load-bearing here and each is enforced in code rather
than documented:

* **`127.0.0.1` only, with no config knob to bind wider in v1.** `create_server`
  refuses any other address — there is no setting, no environment variable and
  no flag that widens it. A container reaches this by port-forward, which keeps
  the rule literally true.
* **Origin-checked mutations.** `Origin` and `Host` are validated against the
  bound address on every request that is not a plain page read. M1 exposes no
  POST, so the check is proved on the stream handshake and inherited by M4's
  mutations rather than written for the first time under deadline.
* **A generic error literal plus a correlation id.** No stack trace, no path and
  no environment value reaches a response body; the detail stays in the process.

Every JSON body is a `ToolResult` from `invoke()`. There is no handler with
business logic in this module, and `tests/web/test_routes.py` asserts that
structurally.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from shepherd.toolsurface.registry import GENERIC_ERROR, invoke
from shepherd.toolsurface.tools_terminal import TerminalStream
from shepherd.toolsurface.types import Audience, CallerContext
from shepherd.web import routes, sse, ws

#: §13: the only address this server will ever bind. Not a default — the value.
LOOPBACK_HOST = "127.0.0.1"

#: Who `web/` is to L4 (ADR-3). M4's gate reads this; M1 has no gate (D38).
WEB_CALLER_ID = "web"

INDEX_FILE = "index.html"
STATIC_PREFIX = "/static/"

_CONTENT_TYPES: Mapping[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}

JSON_TYPE = "application/json"

#: The largest request body this server will read. The bodies are a brief, a
#: message or a title; the cap is generous by two orders of magnitude and still
#: bounds what one `Content-Length` header can make this process allocate.
MAX_BODY_BYTES = 1 << 20

#: The tool the WebSocket path resolves to. It is **not** in `API_ROUTES`: an
#: upgrade is not a call, so the name is spelled once, here, beside the one
#: handler that may use it.
TERMINAL_TOOL = "terminal_stream"


class BindAddressRefused(ValueError):
    """§13: an attempt to bind anything but loopback. There is no knob."""


class FleetServer(ThreadingHTTPServer):
    """The bound server, carrying the one piece of configuration there is."""

    daemon_threads = True

    #: `SO_REUSEADDR`, and it is D37's other half rather than a convenience.
    #:
    #: The fleet page holds an SSE connection for as long as the tab is open and
    #: the server closes it on the way out, so a socket in `TIME_WAIT` bearing
    #: this port as its *local* address is the ordinary end state of any run a
    #: human watched. Without the flag, `restart the control plane, keep the
    #: agents` fails with a raw `EADDRINUSE` traceback for up to two minutes —
    #: in the common case, not an edge one.
    #:
    #: It does not widen §13: `create_server` still refuses every address but
    #: loopback, and `SO_REUSEADDR` does not permit two live listeners on one
    #: port (that is `SO_REUSEPORT`, which is not set). What it permits is
    #: re-binding an address whose only remaining claimant is a closed
    #: connection of our own. `tests/web/test_restart.py` is the proof.
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], static_root: Path) -> None:
        self.static_root = static_root.resolve()
        super().__init__(address, FleetHandler)

    @property
    def bound_origins(self) -> frozenset[str]:
        """The origins a browser may legitimately claim (§13 origin check)."""
        host, port = self.server_address[0], self.server_address[1]
        authority = f"{host!s}:{port!s}"
        return frozenset({f"http://{authority}", f"https://{authority}"})


class FleetHandler(BaseHTTPRequestHandler):
    """Static assets, JSON routes and the one stream. No business logic."""

    protocol_version = "HTTP/1.1"
    server_version = "shepherd"
    sys_version = ""

    # ----- plumbing ----------------------------------------------------------

    def log_message(self, format: str, *args: object) -> None:
        """§13 Errors: request detail belongs in the local log, not on stderr."""

    @property
    def fleet_server(self) -> FleetServer:
        server = self.server
        assert isinstance(server, FleetServer)
        return server

    def _correlation_id(self) -> str:
        return uuid.uuid4().hex

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: Mapping[str, object]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), JSON_TYPE)

    def _fail(self, status: int, correlation_id: str) -> None:
        """§13 Errors: one generic literal and an id, whatever went wrong."""
        self._send_json(
            status, {"ok": False, "data": None, "error": GENERIC_ERROR,
                     "correlation_id": correlation_id}
        )

    # ----- the origin check (§13) -------------------------------------------

    def _origin_is_allowed(self) -> bool:
        """`Origin` and `Host` must both name the address we actually bound.

        A browser omits `Origin` on a same-origin navigation, so an absent one
        is allowed only when `Host` already matches — which is what stops a
        page on another origin from driving the fleet while leaving a plain
        page load working.
        """
        allowed = self.fleet_server.bound_origins
        host = self.headers.get("Host")
        if host is None or not any(origin.endswith(f"//{host}") for origin in allowed):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in allowed

    # ----- requests ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's contract
        correlation_id = self._correlation_id()
        parsed = urlparse(self.path)
        path = parsed.path
        if path == routes.SSE_PATH:
            self._stream(correlation_id)
            return
        terminal = routes.resolve_terminal(path)
        if terminal is not None:
            self._terminal(terminal, correlation_id)
            return
        resolved = routes.resolve(path, parse_qs(parsed.query))
        if resolved is not None:
            self._call(resolved, correlation_id)
            return
        self._static(path, correlation_id)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's contract
        """M3's mutations. The origin check runs **first**, before the body is
        read, so a cross-origin page cannot even make this process allocate."""
        correlation_id = self._correlation_id()
        if not self._origin_is_allowed():
            self._fail(403, correlation_id)
            return
        body = self._json_body()
        if body is None:
            self._fail(400, correlation_id)
            return
        resolved = routes.resolve_post(urlparse(self.path).path, body)
        if resolved is None:
            self._fail(404, correlation_id)
            return
        self._call(resolved, correlation_id)

    def _json_body(self) -> Mapping[str, object] | None:
        """The request body as a JSON object, or `None` if it is not one.

        A body that is a list, a number or nothing at all is refused here rather
        than being coerced into `{}`: a mutation whose arguments silently became
        empty is a mutation aimed at whatever the defaults are.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            return None
        if length == 0:
            return {}
        try:
            decoded: object = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(decoded, dict):
            return None
        return {str(key): value for key, value in decoded.items()}

    def _call(self, resolved: routes.Resolved, correlation_id: str) -> None:
        """The whole of `web/`'s access to the system (D19, D35)."""
        context = CallerContext(
            audience=Audience.HUMAN,
            caller_id=WEB_CALLER_ID,
            correlation_id=correlation_id,
        )
        result = invoke(resolved.tool, resolved.args, context)
        if not result.ok:
            self._fail(400, correlation_id)
            return
        try:
            body = json.dumps(
                {"ok": True, "data": result.data, "error": None,
                 "correlation_id": correlation_id}
            ).encode("utf-8")
        except (TypeError, ValueError):
            self._fail(500, correlation_id)
            return
        self._send(200, body, JSON_TYPE)

    def _stream(self, correlation_id: str) -> None:
        """§12's one stream. The connection stays open; nothing here polls.

        §13's origin check runs here rather than only on mutations: M1 exposes
        no POST, so this is the one live surface that can prove the check works
        — and M4's mutations inherit it instead of writing it under deadline.
        """
        if not self._origin_is_allowed():
            self._fail(403, correlation_id)
            return
        self.send_response(200)
        self.send_header("Content-Type", sse.SSE_CONTENT_TYPE)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        since_seq = sse.parse_last_event_id(self.headers.get("Last-Event-ID"))
        try:
            for chunk in sse.stream(since_seq):
                self.wfile.write(chunk)
                self.wfile.flush()
        except OSError:  # a closed tab, from in here, is a write that fails
            self.close_connection = True

    def _terminal(self, session_id: str, correlation_id: str) -> None:
        """§12's page 3: the pane's real bytes, framed, over one connection.

        The order matters and is the security property: origin, then handshake
        validity, then the capability — and only then is a byte of the
        connection handed over. A 101 written before `invoke()` answered would
        leave a browser holding an upgraded socket to a session it may not have.

        **The first frame is the snapshot**, taken with the attach rather than
        after it, so no live chunk can describe a screen the snapshot never
        showed. It is written as it came back: this module does not decode,
        escape or re-encode a pane byte, which is what T19's
        `test_the_first_frame_is_the_snapshot_byte_for_byte` holds.
        """
        if not self._origin_is_allowed():
            self._fail(403, correlation_id)
            return
        accepted = ws.handshake_response(
            dict(self.headers), self.fleet_server.bound_origins
        )
        if accepted is None:
            self._fail(403, correlation_id)
            return
        result = invoke(
            TERMINAL_TOOL,
            {"session_id": session_id},
            CallerContext(
                audience=Audience.HUMAN,
                caller_id=WEB_CALLER_ID,
                correlation_id=correlation_id,
            ),
        )
        if not result.ok or not isinstance(result.data, TerminalStream):
            self._fail(404, correlation_id)
            return
        stream = result.data
        self.close_connection = True
        try:
            self.wfile.write(accepted)
            self.wfile.write(ws.build_frame(stream.snapshot, opcode=ws.OP_BINARY))
            self.wfile.flush()
            for chunk in stream.chunks():
                self.wfile.write(ws.build_frame(chunk, opcode=ws.OP_BINARY))
                self.wfile.flush()
            self.wfile.write(ws.close_frame(ws.CLOSE_NORMAL))
            self.wfile.flush()
        except OSError:  # a closed tab, from in here, is a write that fails
            pass
        finally:
            stream.close()

    def _static(self, path: str, correlation_id: str) -> None:
        """`/` and `/static/*`, served from the package — no build step (D51)."""
        root = self.fleet_server.static_root
        if path in ("/", f"/{INDEX_FILE}"):
            target = root / INDEX_FILE
        elif path.startswith(STATIC_PREFIX):
            target = (root / path[len(STATIC_PREFIX) :]).resolve()
        else:
            self._fail(404, correlation_id)
            return
        content_type = _CONTENT_TYPES.get(target.suffix)
        if content_type is None or not target.is_file() or not target.is_relative_to(root):
            self._fail(404, correlation_id)
            return
        self._send(200, target.read_bytes(), content_type)


def create_server(host: str, port: int, static_root: Path) -> ThreadingHTTPServer:
    """Bind the fleet server. `host` must be loopback — §13 offers no wider one.

    The parameter exists so the refusal is a call the caller can see fail, not
    so an address can be configured: every other value raises.
    """
    if host != LOOPBACK_HOST:
        raise BindAddressRefused(
            f"shepherd binds {LOOPBACK_HOST} only in v1; remote access arrives with the"
            " auth seam, not a bind address"
        )
    return FleetServer((host, port), static_root)
