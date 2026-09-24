"""Wave 4 support (no scenarios): owned-session instances, spawn, tmux reads, a WS tap.

Named `test_wave4_0_*` only because STAGE B's write surface is `test_wave4_*.py`;
it defines **no test** (pytest collects it and finds nothing). The wave-4
scenario modules import the helpers below by name — never a `test_*` function,
so nothing is collected twice.

Everything here reads or drives the product through its own front doors:

* spawns go through `POST /api/sessions` (the HUMAN web layer), with the plan's
  75 s hang guard (O1: the product's own bound is `SPAWN_TIMEOUT_S` = 60 s, after
  which it answers `needs_you`; the harness bound only turns a hang into
  BLOCKED);
* the harness's own tmux reads (`list-sessions`, `capture-pane`, `send-keys`)
  go through `tmuxctl`, which refuses any socket but this run's and never
  passes through the logging shim, so the shim log stays "what the product ran";
* the WS tap speaks raw RFC 6455 with `wsclient`'s request/handshake/decoder and
  keeps the connection open while a scenario acts (T1, T3, T4 need that).
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.runner.local import OWNED_SESSION_RE
from shepherd.runner.tmux_cmd import SESSION_PREFIX

from .. import tmuxctl, wsclient
from ..auditprobe import AuditProbe
from ..httpclient import Client, Response, as_dict
from ..instance import Controld, Helper, db_rows
from ..pool import InstancePool
from ..sandbox import InstanceRoot, RunContext
from ..sessions import await_session, sidecar, write_sidecar
from ..sse_rig import Frame, Subscriber, subscribe
from ..verdict import CONTROL_MULTIPLE, Blocked, Recorder, await_env, observe

#: test-plan O1: "A harness `await_env` of 75 s guards only against a hang (BLOCKED)".
SPAWN_HANG_GUARD_S = 75.0
#: A plain call's client timeout (not a product bound: a liveness guard).
CALL_TIMEOUT_S = 20.0


@dataclass
class Owned:
    """One SUB instance prepared for owned sessions: a project holding `alpha`."""

    controld: Controld
    run: RunContext
    pool: InstancePool
    stream: Subscriber
    audit: AuditProbe
    project_id: str
    alpha: Path
    notes: list[str] = field(default_factory=list)

    @property
    def client(self) -> Client:
        return self.controld.client

    @property
    def socket(self) -> str:
        return self.run.runner_socket(self.controld.root.k)

    @property
    def root(self) -> InstanceRoot:
        return self.controld.root


def open_owned(pool: InstancePool, run: RunContext, name: str, *, controld: Controld | None = None) -> Owned:
    """A ready instance (or the one given), a project `QA6-<name>-Alpha` holding alpha, a stream."""
    instance = controld if controld is not None else pool.ready()
    client = instance.client
    created = client.create_project(f"QA6-{name}-Alpha")
    project_id = str(as_dict(created.get("project")).get("project_id"))
    alpha = Path(os.path.realpath(run.repos / "alpha"))
    added = client.add_repo(project_id, str(alpha))
    if added.get("added") is not True:
        raise Blocked(f"{name}: add_repo(alpha) did not land: {added!r}")
    stream = subscribe(name, instance.port)
    return Owned(controld=instance, run=run, pool=pool, stream=stream,
                 audit=AuditProbe.for_instance(instance.root), project_id=project_id, alpha=alpha)


# ----- HTTP helpers ------------------------------------------------------------


def post_json(client: Client, path: str, body: Mapping[str, object], timeout_s: float = CALL_TIMEOUT_S) -> Response:
    """`Client.post` with an explicit timeout (spawn can legitimately take up to 60 s)."""
    payload = json.dumps(dict(body)).encode("utf-8")
    headers = {"Host": client.host, "Origin": client.origin, "Content-Type": "application/json"}
    try:
        return client.request("POST", path, body=payload, headers=headers, timeout_s=timeout_s)
    except TimeoutError as error:
        raise Blocked(f"POST {path} did not answer within {timeout_s}s (a hang guard): {error}") from error


@dataclass(frozen=True)
class Spawned:
    status: int
    data: dict[str, object]
    latency_s: float
    body: dict[str, object]

    @property
    def session_id(self) -> str | None:
        value = self.data.get("session_id")
        return value if isinstance(value, str) else None

    @property
    def spawned(self) -> bool:
        return self.data.get("spawned") is True


def spawn(
    env: Owned,
    *,
    title: str | None = None,
    brief: str | None = None,
    cwd: str | None = None,
    workspace_id: str | None = None,
    parent: str | None = None,
) -> Spawned:
    """`POST /api/sessions`, timed. A non-200 answer comes back as `data == {}`."""
    body: dict[str, object] = {"workspace_id": workspace_id if workspace_id is not None else env.project_id,
                               "cwd": cwd if cwd is not None else str(env.alpha)}
    for key, value in (("title", title), ("brief", brief), ("parent_session_id", parent)):
        if value is not None:
            body[key] = value
    started = time.monotonic()
    response = post_json(env.client, "/api/sessions", body, timeout_s=SPAWN_HANG_GUARD_S)
    latency = time.monotonic() - started
    data = response.data() if response.status == 200 else {}
    return Spawned(status=response.status, data=data, latency_s=latency, body=body)


def spawn_ok(env: Owned, title: str, brief: str | None = None, **kwargs: str) -> str:
    """A spawn that must succeed for the scenario to be about anything (else BLOCKED)."""
    made = spawn(env, title=title, brief=brief, **kwargs)
    if not made.spawned or made.session_id is None:
        raise Blocked(f"precondition: spawn {title!r} did not succeed: HTTP {made.status} {made.data!r}")
    return made.session_id


def kill(env: Owned, session_id: str) -> Response:
    return post_json(env.client, f"/api/sessions/{session_id}/kill", {})


def fleet_anomaly(client: Client, name: str) -> int:
    value = as_dict(client.fleet().get("anomalies")).get(name)
    return int(value) if isinstance(value, int) else -1


def session_count(env: Owned) -> int:
    rows = db_rows(env.controld.db, "SELECT COUNT(*) AS n FROM session")
    value = rows[0]["n"]
    return int(value) if isinstance(value, int) else -1


def session_db_row(env: Owned, session_id: str) -> dict[str, object] | None:
    rows = db_rows(env.controld.db, "SELECT * FROM session WHERE id = ?", (session_id,))
    return rows[0] if rows else None


def app_state_rows(env: Owned) -> dict[str, object]:
    return {str(r["key"]): r["value"] for r in db_rows(env.controld.db, "SELECT key, value FROM app_state")}


# ----- tmux: the real server on this instance's socket ---------------------------


def tmux_name(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


def owned_panes(env: Owned) -> list[str]:
    """Owned sessions on this instance's socket (the bootstrap session excluded)."""
    return sorted(name for name in tmuxctl.sessions(env.socket, env.run.pid) if OWNED_SESSION_RE.fullmatch(name))


def pane_alive(env: Owned, session_id: str) -> bool:
    return tmux_name(session_id) in owned_panes(env)


def capture(env: Owned, session_id: str) -> str:
    done = tmuxctl.run(env.socket, env.run.pid, "capture-pane", "-p", "-t", tmuxctl.target(tmux_name(session_id)),
                       check=False)
    return done.stdout if done.returncode == 0 else ""


def send_keys(env: Owned, session_id: str, *keys: str) -> None:
    tmuxctl.run(env.socket, env.run.pid, "send-keys", "-t", tmuxctl.target(tmux_name(session_id)), *keys)


def pane_pid(env: Owned, session_id: str) -> int | None:
    done = tmuxctl.run(env.socket, env.run.pid, "list-panes", "-t", tmuxctl.target(tmux_name(session_id)),
                       "-F", "#{pane_pid}", check=False)
    text = done.stdout.strip().splitlines()
    return int(text[0]) if done.returncode == 0 and text and text[0].isdigit() else None


def bounded(rec: Recorder, name: str, seen: bool, what: str, bound_s: float, control_s: float | None,
            control_what: str, actual: object) -> None:
    """One clause under test-plan Difference 1: PASS, FAIL(bound) when a same-channel
    control in this run qualifies the bound (>= 10x its latency), else BLOCKED."""
    if seen:
        rec.check(name, True, f"{what} within {bound_s}s", actual)
    elif control_s is not None and bound_s >= CONTROL_MULTIPLE * control_s:
        rec.fail_bound(name, what, bound_s, f"{control_what} took {control_s:.3f}s on the same channel")
    else:
        rec.block(name, f"{what} not observed within {bound_s}s and no same-channel control qualifies the bound "
                        f"({control_what}: {control_s!r}); Difference 1 makes this BLOCKED; last seen: {actual!r}"[:600])


def capture_latency(env: Owned, session_id: str, marker: str, bound_s: float = 5.0) -> float | None:
    """A same-channel positive control: harness keystrokes, seen by `capture-pane`."""
    send_keys(env, session_id, marker)
    seen, elapsed = observe(lambda: marker in capture(env, session_id) or None, bound_s)
    return max(elapsed, 1e-3) if seen else None


# ----- the product's argv, as the shims logged it ----------------------------------


def tmux_argvs(run: RunContext) -> list[list[str]]:
    """Every tmux argv the product ran (the logging shim's JSON arrays)."""
    if not run.tmux_argv_log.exists():
        return []
    found: list[list[str]] = []
    for line in run.tmux_argv_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, list):
                found.append([str(word) for word in decoded])
    return found


def claude_argvs(run: RunContext) -> list[list[str]]:
    """Every fake-`claude` invocation's argv (the shim's JSON objects)."""
    if not run.claude_argv_log.exists():
        return []
    found: list[list[str]] = []
    for line in run.claude_argv_log.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decoded: object = json.loads(line)
            if isinstance(decoded, dict) and isinstance(decoded.get("argv"), list):
                found.append([str(word) for word in decoded["argv"]])
    return found


def argvs_naming(argvs: Sequence[Sequence[str]], *words: str) -> list[list[str]]:
    return [list(argv) for argv in argvs if all(word in argv for word in words)]


def socket_ok(argv: Sequence[str], socket_name: str) -> bool:
    """argv[1..2] == `-L <this instance's runner socket>` (PP-7)."""
    return len(argv) >= 3 and argv[0] == "tmux" and argv[1] == "-L" and argv[2] == socket_name


# ----- an attached (sidecar-registered) session ---------------------------------------


@dataclass(frozen=True)
class Attached:
    helper: Helper
    body: dict[str, object]
    session_id: str
    engine_id: str


def attached(env: Owned, cwd: Path, name: str) -> Attached:
    """A D1-shaped attached session: a harness helper and its sidecar (a harness-shaped input, G5)."""
    helper = env.pool.helper()
    body = sidecar(pid=helper.pid, proc_start=helper.start_token, cwd=str(cwd), name=name)
    write_sidecar(env.root.sessions, body)
    engine = str(body["sessionId"])
    row = await_session(env.controld, engine, 8.0, state="running")
    return Attached(helper=helper, body=body, session_id=str(row["id"]), engine_id=engine)


def end_attached(env: Owned, one: Attached) -> None:
    one.helper.end()
    target = env.root.sessions / f"{one.body['pid']}.json"
    if target.exists():
        target.unlink()


# ----- frames ---------------------------------------------------------------------


def frames(stream: Subscriber, mark: int, kind: str, session_id: str | None = None) -> list[Frame]:
    return [f for f in stream.since(mark) if f.kind == kind and (session_id is None or f.session_id == session_id)]


def await_frame(stream: Subscriber, mark: int, kind: str, session_id: str | None, bound_s: float) -> Frame | None:
    found, _ = observe(lambda: next(iter(frames(stream, mark, kind, session_id)), None), bound_s)
    return found


# ----- the WS tap --------------------------------------------------------------------


@dataclass
class WsFrame:
    opcode: int
    payload: bytes
    at: float


class WsTap:
    """One terminal WebSocket held open on a reader thread.

    `wsclient.upgrade` reads N frames and hangs up; T1/T3/T4 must act *while*
    the stream is open, so this keeps the socket and records every server frame
    with its arrival time. Unmasked server frames are decoded by `wsclient.decode`
    (the re-proved copy), never by the product's client-frame parser.
    """

    def __init__(self, port: int, path: str, origin: str | None = None) -> None:
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10.0)
        self.sock.sendall(wsclient._request(port, path, origin, None))
        self.status, self.headers, rest = wsclient._handshake(self.sock)
        self._raw = rest
        self.frames: list[WsFrame] = []
        self.eof = False
        self.fault: str | None = None
        self._stop = False
        self._lock = threading.Lock()
        self._absorb(b"")
        self._thread: threading.Thread | None = None
        if self.status == 101:
            self._thread = threading.Thread(target=self._read, name="qa6-ws-tap", daemon=True)
            self._thread.start()

    def _absorb(self, chunk: bytes) -> None:
        now = time.monotonic()
        with self._lock:
            self._raw += chunk
            decoded = wsclient.decode(self._raw)
            for opcode, payload in decoded[len(self.frames):]:
                self.frames.append(WsFrame(opcode, payload, now))

    def _read(self) -> None:
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                chunk = self.sock.recv(65536)
            except TimeoutError:
                continue
            except OSError as error:
                if not self._stop:
                    self.fault = repr(error)
                return
            if not chunk:
                self.eof = True
                return
            self._absorb(chunk)

    def snapshot(self) -> list[WsFrame]:
        with self._lock:
            return list(self.frames)

    def binary_text(self, start: int = 0) -> str:
        return b"".join(f.payload for f in self.snapshot()[start:] if f.opcode == wsclient.OP_BINARY).decode(
            "utf-8", "replace")

    def close_code(self) -> int | None:
        for frame in self.snapshot():
            if frame.opcode == wsclient.OP_CLOSE and len(frame.payload) >= 2:
                return int.from_bytes(frame.payload[:2], "big")
        return None

    def wait(self, predicate: Callable[[], bool], bound_s: float) -> float | None:
        started = time.monotonic()
        seen, _ = observe(lambda: predicate() or None, bound_s)
        return time.monotonic() - started if seen else None

    def send(self, data: bytes) -> None:
        self.sock.sendall(data)

    def close(self) -> None:
        self._stop = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass  # the server may already have closed its half; the close below still runs
        self.sock.close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                raise Blocked("the WS tap reader did not join within 5 s")


def await_attach(run: RunContext, session_id: str, mark: int, bound_s: float = 5.0) -> None:
    """Environment gate: the product ran `pipe-pane -o` for this pane (the live stream is attached).

    Keystrokes sent before the attach land in the snapshot, not in a later
    frame, and T1/T3/T4 would then be about the wrong thing.
    """
    target = tmuxctl.target(tmux_name(session_id))
    await_env(lambda: any("pipe-pane" in argv and "-o" in argv and target in argv for argv in tmux_argvs(run)[mark:])
              or None, bound_s, f"the product's pipe-pane -o for {session_id}")
