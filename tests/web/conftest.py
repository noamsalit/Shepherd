"""One live loopback server per test, wired to a real store through `invoke()`.

The seam is HTTP: every assertion in `tests/web/` goes through a socket to a
`ThreadingHTTPServer` bound on an ephemeral 127.0.0.1 port, because that is the
only surface a browser has. Nothing here reaches into a handler.
"""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from chokepoint_fixture import install_test_chokepoint

from shepherd.core.states import Origin, Ownership
from shepherd.orchestration.master_turn import TurnRefused, TurnStarted
from shepherd.orchestration.dialog_keys import SidecarState
from shepherd.store.db import Store, open_store
from shepherd.testkit.scripted_runner import ScriptedRunner
from shepherd.store.models import Session
from shepherd.toolsurface.registry import reset_registry
from shepherd.toolsurface.stream import reset_stream
from shepherd.toolsurface.tools_m1 import register_read_tools
from shepherd.toolsurface.approvals import ApprovalStore
from shepherd.toolsurface.tools_m3 import register_m3_tools
from shepherd.toolsurface.tools_master import register_master_tools
from shepherd.web import server as web_server

NOW = "2026-09-16T10:00:30Z"

#: `14-list-sessions-after-sigterm.txt`, `probe_a`: alive, alternate screen on.
LIVE_FIELDS = "1|0||✳ shp-probe-title-1|160|45|4041880"


def _no_fork(argv: list[str], *, timeout_ms: int) -> object:
    """`can_fork` is `False` in these fixtures, so nothing may reach this."""
    raise AssertionError("no web test forks a process")


STATIC_ROOT = Path(__file__).resolve().parents[2] / "src" / "shepherd" / "web" / "static"


@pytest.fixture(autouse=True)
def clean_toolsurface() -> Iterator[None]:
    """The registry and the ring are module-global by ADR-7."""
    reset_registry()
    reset_stream()
    yield
    reset_registry()
    reset_stream()


@pytest.fixture()
def store(tmp_path: Path) -> Iterator[Store]:
    opened = open_store(tmp_path / "data" / "shepherd.db")
    try:
        yield opened
    finally:
        opened.close()


@pytest.fixture()
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture()
def scripted_runner() -> ScriptedRunner:
    """The pane driver `web/` reaches through L4. A test that needs an owned
    session adds its pane to `live`, which is the same dict `start()` writes."""
    from shepherd.core.runner import PaneState, ProcState
    from shepherd.runner.pane import parse_pane_fields, read_pane

    capture = (
        Path(__file__).resolve().parents[2]
        / "docs" / "probes" / "2026-09-14-schemas" / "tmux-tui"
        / "run-20260914T154946Z" / "03-after-stop.ansi"
    ).read_bytes()
    pane: PaneState = read_pane(capture, parse_pane_fields(LIVE_FIELDS), [])
    return ScriptedRunner(
        panes=(pane,),
        proc=ProcState(
            alive=True, pid=4041880, exit_code=None, exit_signal=None, observed_at=NOW
        ),
        screen=capture,
        owned_panes=(),
    )


@pytest.fixture(autouse=True)
def tools(
    store: Store,
    projects_root: Path,
    tmp_path: Path,
    scripted_runner: ScriptedRunner,
    master_doubles: MasterDoubles,
) -> None:
    """M1's read tools **and** M3's twelve (T18).

    Both are registered because the composition root registers both, and
    `web/test_routes.py::test_every_api_route_names_a_registered_tool` asserts
    that every route names a tool the registry actually has — a fixture that
    registered only half would make that check pass on a tree where half the
    routes 500.

    **And the chokepoint** (T6, DP13): M3's set carries `local_write` and
    `local_destructive` tools, and since T6 a non-`local_read` class is refused
    when no chokepoint is installed. The composition root installs one, so the
    fixture that stands in for it installs one too.
    """
    install_test_chokepoint()
    register_read_tools(
        store=store,
        projects_root=projects_root,
        clock=lambda: NOW,
        pending_approvals=lambda: (),
    )
    register_m3_tools(
        store=store,
        runner=scripted_runner,
        now=lambda: NOW,
        sleep=lambda seconds: None,
        publish=lambda event: None,
        ensure_server=lambda: None,
        engine_config_home=tmp_path / "engine-home",
        run_fork=_no_fork,
        binary="claude",
        projects_root=projects_root,
        can_fork=False,
        read_sidecar=lambda engine_session_id: SidecarState.WAITING,
    )
    # …and T23's ten (T24). Same reason as M3's twelve: `test_every_api_route_
    # names_a_registered_tool` asserts every route names a tool the registry
    # actually has, and the chat page's five routes name five of these.
    register_master_tools(
        store=store,
        approvals=master_doubles.approvals,
        audit_root=master_doubles.audit_root,
        send_turn=master_doubles.send_turn,
        interrupt_master=master_doubles.interrupt,
        now=lambda: NOW,
    )
    return None


#: The turn `master_send` reports when the driver double accepts one. A literal,
#: because a test that read it back out of the double would be asserting that the
#: double is itself (T23's and T27's tautology).
TURN_ID = "turn-01JCHAT"
TURN_STARTED_AT = "2026-09-16T10:00:31Z"


@dataclass
class MasterDoubles:
    """T24's stand-in for T25's composition root, and nothing more.

    `web/` reaches `master_send` / `interrupt_master` through `invoke()` like
    every other capability, so what a web test needs is the two callables T25
    will inject and the approval store the rail reads. They are recorded rather
    than mocked at the seam below: the assertions are about what crossed the
    HTTP boundary, and the driver itself is T27's, tested there.
    """

    sent: list[str]
    interrupted: list[bool]
    approvals: ApprovalStore
    audit_root: Path
    refusal: str | None = None

    def send_turn(self, text: str) -> TurnStarted | TurnRefused:
        self.sent.append(text)
        if self.refusal is not None:
            return TurnRefused(reason=self.refusal)
        return TurnStarted(turn_id=TURN_ID, started_at=TURN_STARTED_AT)

    def interrupt(self) -> bool:
        self.interrupted.append(True)
        return True


@pytest.fixture()
def master_doubles(tmp_path: Path) -> MasterDoubles:
    root = tmp_path / "logs" / "audit"
    root.mkdir(parents=True)
    return MasterDoubles(sent=[], interrupted=[], approvals=ApprovalStore(), audit_root=root)


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: str

    def json(self) -> dict[str, object]:
        decoded: object = json.loads(self.body)
        assert isinstance(decoded, dict)
        return decoded


class Client:
    """A minimal HTTP client against the bound address."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    def request(
        self,
        path: str,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request(method, path, headers=dict(headers or {}))
            raw = connection.getresponse()
            body = raw.read().decode("utf-8")
            return Response(
                status=raw.status,
                headers={key.lower(): value for key, value in raw.getheaders()},
                body=body,
            )
        finally:
            connection.close()

    def post(
        self,
        path: str,
        body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Response:
        """A JSON POST. The `Origin` header is sent unless a test overrides it,
        because §13's check is on by default and a test that had to opt in would
        be testing the opt-in."""
        sent = {"Content-Type": "application/json", "Origin": self.origin}
        sent.update(dict(headers or {}))
        payload = json.dumps(body or {}).encode("utf-8")
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        try:
            connection.request("POST", path, body=payload, headers=sent)
            raw = connection.getresponse()
            return Response(
                status=raw.status,
                headers={key.lower(): value for key, value in raw.getheaders()},
                body=raw.read().decode("utf-8"),
            )
        finally:
            connection.close()

    def frames(
        self,
        path: str,
        count: int,
        headers: Mapping[str, str] | None = None,
        read_timeout: float = 10.0,
    ) -> list[dict[str, str]]:
        """Read `count` SSE frames, then hang up — what a browser tab does.

        Comment lines (`:`) are keep-alives, not messages: they are skipped, so
        "no frame arrived" stays distinguishable from "the socket is alive".
        """
        connection = http.client.HTTPConnection(self.host, self.port, timeout=read_timeout)
        collected: list[dict[str, str]] = []
        try:
            connection.request("GET", path, headers=dict(headers or {}))
            raw = connection.getresponse()
            assert raw.status == 200, raw.status
            current: dict[str, str] = {}
            while len(collected) < count:
                line = raw.fp.readline().decode("utf-8") if raw.fp else ""
                if line == "":
                    break
                stripped = line.rstrip("\n")
                if stripped == "":
                    if current:
                        collected.append(current)
                        current = {}
                    continue
                if stripped.startswith(":"):
                    continue
                field, _, value = stripped.partition(":")
                current[field] = value.lstrip(" ")
        except TimeoutError:
            pass
        finally:
            connection.close()
        return collected


@pytest.fixture()
def server() -> Iterator[ThreadingHTTPServer]:
    bound = web_server.create_server(host="127.0.0.1", port=0, static_root=STATIC_ROOT)
    thread = threading.Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    try:
        yield bound
    finally:
        bound.shutdown()
        bound.server_close()
        thread.join(timeout=5)


@pytest.fixture()
def client(server: ThreadingHTTPServer) -> Client:
    host, port = server.server_address[0], server.server_address[1]
    return Client(host=str(host), port=int(port))


def seed(store: Store, engine_session_id: str = "eng-1") -> Session:
    workspace = store.create_project(name="shepherd", description=None)
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=workspace.id,
        repo_id=None,
        cwd="/root/Shepherd",
        started_at="2026-09-16T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    )
