"""Wave 8, LIVE lane: a real `claude` and the real SDK master (test-plan §3 wave 8; §4 L1-L11).

**Order** (test-plan §3 intra-wave order, review pass 1 finding 4):
L1 → L3 → L5 → L7 → L8 → L9 → L6 → L4 → L10 → L2 → L11, on one named instance
LIVE-A (LIVE-B for L11 only). Tests run in definition order, so the functions
below are written in exactly that order. L5's session (`QA6-TARGET`) is kept
for L7-L9; L2 spawns its own target, so no later scenario loses a session.

**Topology per `LIVE_AUTH_MODE`** (S0's binding; env-plan §1): `needs_real_home`
starts LIVE-A/LIVE-B through `tests/qa6/launch_controld.py` — the engine runs
with the real HOME to find its login, Shepherd's own dirs are sandboxed by
injection, and discovery is pointed at `<root>/cfg` (`engine_config_dir`,
Difference 11), so the user's own sessions never become rows. L1 verifies that
sandbox before any master turn. `sandbox_ok` uses the SUB form with the LIVE
PATH. `unavailable`, or no binding at all, makes every scenario `BLOCKED`:
**this module refuses to run without `QA6_LIVE_AUTH_MODE`** (BUILDING §6).

**Model non-compliance** (OD-6): a real model that does not do what the prompt
asks gets one clearer retry; still not → the clause is `BLOCKED(model)`, never
FAIL. The model's choice is not product behaviour.

**The closing step** (env-plan §9 step 2a, OD-11) runs in the `live` fixture's
finalizer, before the pool stops the instances and before the runner's post-lane
Z1 check: every owned session this run spawned on LIVE-A/LIVE-B that is still
live is killed through the product's own kill route and its pane pid awaited.
Its record is `<run_dir>/live-closing-step.json`, which Z1 reads (the run root is
gone by wave 9). A pane pid still alive after it is a leak and a teardown
problem.

**The product tmux log is copied out after the pool stops** into
`<run_dir>/wave8-ledgers/` (Z2 prefers this copy; the runner's own
`ledgers/tmux-argv.log` and `ledgers/unseeded-tmux-argv.log` are distinct
since SI-2).

**Host safety (INC-1).** Every real-HOME env comes from `sandbox.real_home_env`
(no `XDG_*`, `DISABLE_AUTOUPDATER=1`); every direct exec of the real engine uses
the run's `<run0>/bin/claude` (realclaude.py), never the user's link; and
`live/conftest.py` compares the user's `~/.local/bin/claude` against its
run-START state before the module, and around every scenario.

Every signal goes to a pid this module spawned; every tmux call is on this run's
own `shepherd-m3-q6<pid>-<k>` socket through `tmuxctl` (absolute binary, never
logged); the only sessions acted on are ones this run spawned.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import socket
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from shepherd.core.runner import PaneKind, PaneState
from shepherd.engines.claude_code.hookd_command import build_hook_entry
from shepherd.engines.claude_code.hooks_config import install_hooks
from shepherd.host.mac import MacHost
from shepherd.logs.jsonl import scan_records
from shepherd.logs.stops import STOP_PREFIX
from shepherd.orchestration.dialog_keys import TRUST_OPTIONS
from shepherd.runner.local import LISTING_FORMAT
from shepherd.runner.pane import FIELD_SEPARATOR, parse_pane_fields, read_pane
from shepherd.toolsurface.compose import log_root

from .. import hostprobe, paths, realclaude, tmuxctl, wsclient
from ..auditprobe import AuditProbe, shape_problems
from ..browser import BrowserSession, click, press, type_text
from ..hookrig import captured, start_ready_sessiond
from ..httpclient import Client, Response, as_dict, as_list, hang_verdict
from ..instance import Controld, app_state, db_rows, last_scan_at, ready_instance, seed_db, start_launcher
from ..mutations import active
from ..pool import InstancePool
from ..sandbox import ENV_LIVE_AUTH_MODE, InstanceRoot, RunContext, checked_env, mint_instance, real_home_env, sandbox_env
from ..scenario import live_scenario
from ..sessions import fleet_sessions, session_row
from ..sessions import sidecar as synthetic_sidecar
from ..sse_rig import Frame, Subscriber, subscribe
from ..verdict import Blocked, ProductFail, Recorder, await_env, observe

LOG = logging.getLogger("qa6.wave8")

LIVE_MODES = ("sandbox_ok", "needs_real_home")
#: A master turn with the default model and tool calls; an observation window,
#: not a product SLO (no same-channel control qualifies a FAIL(bound) here).
TURN_BOUND_S = 300.0
#: The product's spawn polls the pane up to 60 s (spawn.py SPAWN_TIMEOUT_S); the
#: HTTP call returns when the poll resolves, so the client waits past that.
SPAWN_HTTP_TIMEOUT_S = 100.0
ASK_HTTP_TIMEOUT_S = 200.0
#: test-plan L5: `QA6-READY` within 120 s, else BLOCKED(model).
READY_BOUND_S = 120.0
#: test-plan L5's idle observation window (the only fixed wait, §0).
IDLE_WINDOW_S = 70.0
#: env-plan §9 step 2a: each pane pid's exit awaited ≤ 15 s.
PANE_EXIT_BOUND_S = 15.0
ANSWER_BOUND_S = 120.0
CLAUDE_P_TIMEOUT_S = 180.0
#: L1's Proc clause: the SDK disconnects the CLI within its own interrupt
#: timeout (sdk_master.py SDK_INTERRUPT_TIMEOUT_S = 10 s); 30 s is the window.
MASTER_CHILD_EXIT_WINDOW_S = 30.0
END_KINDS = ("master.turn_ended", "master.error")
MODEL = "haiku"
RUN_SLUG_FMT = "shq6-{pid}-"

#: A read-only page probe: records every node added to the Shepherd thread with
#: its class and a wall-clock stamp (L1's "grows in at least two DOM updates").
THREAD_OBSERVER = """
window.__qa6Thread = [];
document.addEventListener('DOMContentLoaded', () => {
  const thread = document.getElementById('shepherd-thread');
  if (thread === null) { return; }
  new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        window.__qa6Thread.push({at: Date.now(), cls: String(node.className || ''),
                                 text: String(node.textContent || '').slice(0, 200)});
      }
    }
  }).observe(thread, {childList: true});
});
"""

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
CURSOR_FORWARD = re.compile(r"\x1b\[\d*C")
ULID = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
#: L11: what "no internals" means on the page (test-plan L11 Stream row).
EXCEPTION_CLASS = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception)\b")
FS_PATH = re.compile(r"\.py\b|site-packages|/Users/|/private/|/opt/|/usr/lib|/var/folders")
STACK = re.compile(r"Traceback|File \"")


# ----- small, pure helpers ------------------------------------------------------------------------


def plain(raw: str) -> str:
    """Terminal bytes as text: cursor-forward becomes a space, other escapes go."""
    return ANSI.sub("", CURSOR_FORWARD.sub(" ", raw)).replace("\r", "")


def answer_lines(text: str, token: str) -> list[str]:
    """Lines that carry `token` and are not the prompt that asked for it."""
    return [line for line in text.splitlines() if token in line and "Reply with" not in line and "reply with" not in line]


def run_slug(run: RunContext) -> str:
    return RUN_SLUG_FMT.format(pid=run.pid)


def process_table() -> list[tuple[int, int, str]]:
    done = hostprobe.run([str(paths.PS_BIN), "-A", "-o", "pid=,ppid=,command="])
    rows: list[tuple[int, int, str]] = []
    for line in done.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return rows


def descendants(root_pid: int) -> list[tuple[int, str]]:
    table = process_table()
    children: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for pid, ppid, command in table:
        children[ppid].append((pid, command))
    found: list[tuple[int, str]] = []
    frontier = [root_pid]
    while frontier:
        current = frontier.pop()
        for pid, command in children.get(current, []):
            found.append((pid, command))
            frontier.append(pid)
    return found


def claude_descendants(root_pid: int) -> list[tuple[int, str]]:
    return [(pid, command) for pid, command in descendants(root_pid) if "claude" in command]


def pid_alive(pid: int) -> bool:
    return hostprobe.process_args(pid) is not None


def real_claude_state() -> dict[str, object]:
    return {
        "settings_sha": hostprobe.sha256(paths.REAL_SETTINGS),
        "projects": hostprobe.listing(paths.REAL_CLAUDE_DIR / "projects"),
        "sessions": hostprobe.listing(paths.REAL_CLAUDE_DIR / "sessions"),
        "claude_json_mtime": hostprobe.mtime(paths.REAL_CLAUDE_JSON),
    }


def _names(state: Mapping[str, object], key: str) -> set[str]:
    value = state.get(key)
    return set(value) if isinstance(value, dict) else set()


def real_delta(before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
    return {
        "projects_added": sorted(_names(after, "projects") - _names(before, "projects")),
        "sessions_added": sorted(_names(after, "sessions") - _names(before, "sessions")),
        "sessions_removed": sorted(_names(before, "sessions") - _names(after, "sessions")),
        "claude_json_mtime_changed": before.get("claude_json_mtime") != after.get("claude_json_mtime"),
    }


def post_long(client: Client, path: str, body: Mapping[str, object], timeout_s: float) -> Response:
    """`Client.post` with a longer read timeout (spawn and ask block server-side)."""
    headers = {"Host": client.host, "Origin": client.origin, "Content-Type": "application/json"}
    return client.request("POST", path, body=json.dumps(dict(body)).encode("utf-8"), headers=headers,
                          timeout_s=timeout_s)


def fleet_tree_ids(client: Client) -> set[str]:
    """Every session id the Flock page's tree carries (the fleet query filters `ephemeral`)."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            session_id = value.get("session_id")
            if isinstance(session_id, str):
                found.add(session_id)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(client.fleet_tree())
    return found


def shepherd_tool_names() -> frozenset[str]:
    """Every tool name the product registers, read from its source as text (L10's allow-set)."""
    names: set[str] = set()
    for path in sorted((paths.REPO / "src" / "shepherd" / "toolsurface").glob("*.py")):
        names.update(re.findall(r"ToolDef\(\s*name=\"([a-z_]+)\"", path.read_text(encoding="utf-8")))
    return frozenset(names)


# ----- the pane, read with the product's own classifier (W5's calls) --------------------------------


def classify(run: RunContext, socket_name: str, name: str) -> PaneState | None:
    listing = tmuxctl.run(socket_name, run.pid, "list-sessions", "-F", LISTING_FORMAT, check=False)
    fields = None
    for line in listing.stdout.splitlines():
        session, separator, rest = line.partition(FIELD_SEPARATOR)
        if separator and session == name:
            fields = parse_pane_fields(rest)
    if fields is None:
        return None
    try:
        screen = tmuxctl.run_bytes(socket_name, run.pid, "capture-pane", "-e", "-p", "-t", tmuxctl.target(name))
    except Blocked:
        return None  # the pane went away between the listing and the capture
    return read_pane(screen, fields)


def capture_text(run: RunContext, socket_name: str, name: str) -> str | None:
    done = tmuxctl.run(socket_name, run.pid, "capture-pane", "-p", "-t", tmuxctl.target(name), check=False)
    return done.stdout if done.returncode == 0 else None


def pane_pid_of(run: RunContext, socket_name: str, name: str) -> int | None:
    done = tmuxctl.run(socket_name, run.pid, "list-panes", "-t", tmuxctl.target(name), "-F", "#{pane_pid}",
                       check=False)
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines or not lines[0].isdigit():
        return None
    return int(lines[0])


def send_keys(run: RunContext, socket_name: str, name: str, *keys: str) -> None:
    tmuxctl.run(socket_name, run.pid, "send-keys", "-t", tmuxctl.target(name), *keys)


def input_line(text: str) -> str:
    """The TUI's prompt line: the last line that starts with the prompt glyph."""
    lines = [line for line in text.splitlines() if line.strip().startswith(("❯", ">"))]
    return lines[-1] if lines else ""


# ----- the terminal WebSocket, read until told to stop -------------------------------------------------


class Terminal:
    """One `/api/sessions/{id}/terminal` upgrade, read on a thread (L5's WS chunks)."""

    def __init__(self, port: int, session_id: str) -> None:
        path = f"/api/sessions/{session_id}/terminal"
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=10.0)
        self._sock.sendall(wsclient._request(port, path, None, None))
        self.status, self.headers, rest = wsclient._handshake(self._sock)
        self._buffer = rest
        self._lock = threading.Lock()
        self._closing = False
        self.fault: str | None = None
        self._sock.settimeout(None)
        self._thread = threading.Thread(target=self._read, name=f"ws-{session_id}", daemon=True)
        if self.status == 101:
            self._thread.start()

    def _read(self) -> None:
        while True:
            try:
                chunk = self._sock.recv(65536)
            except OSError as error:
                if not self._closing:
                    self.fault = f"reader died: {error!r}"
                return
            if not chunk:
                return
            with self._lock:
                self._buffer += chunk

    def payloads(self) -> list[bytes]:
        with self._lock:
            return [payload for opcode, payload in wsclient.decode(self._buffer) if opcode == wsclient.OP_BINARY]

    def close(self) -> None:
        self._closing = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass  # the server may already have closed; the close below still runs
        self._sock.close()
        if self._thread.is_alive():
            self._thread.join(timeout=10.0)
        if self._thread.is_alive():
            raise Blocked("the terminal reader thread did not join in 10 s")


# ----- the live state shared across the module ------------------------------------------------------


@dataclass
class Spawned:
    """An owned session this run spawned: the closing step's unit of work."""

    session_id: str
    title: str
    instance: str
    socket_name: str
    engine_session_id: str | None
    pane_pid: int | None
    spawned_by: str
    killed_by: str | None = None

    @property
    def tmux_name(self) -> str:
        return f"shepherd_{self.session_id}"


@dataclass
class Turn:
    turn_id: str | None
    frames: list[Frame]
    ended: Frame | None
    latency_s: float

    @property
    def text(self) -> str:
        return "".join(str(f.data.get("text") or "") for f in self.frames if f.kind == "master.text")

    @property
    def tool_calls(self) -> list[Frame]:
        return [f for f in self.frames if f.kind == "master.tool_call"]

    def tool_names(self) -> list[str]:
        return [str(f.data.get("tool_name")) for f in self.tool_calls]

    def summary(self) -> dict[str, object]:
        return {"turn_id": self.turn_id, "kinds": [f.kind for f in self.frames], "tools": self.tool_names(),
                "text": self.text[-600:], "ended": self.ended.kind if self.ended else None,
                "end_text": str(self.ended.data.get("text"))[:600] if self.ended else None,
                "latency_s": round(self.latency_s, 2)}


@dataclass
class Instance:
    name: str
    controld: Controld
    client: Client
    sub: Subscriber
    closed: bool = False

    def close_stream(self) -> None:
        if not self.closed:
            self.closed = True
            self.sub.close()

    @property
    def socket_name(self) -> str:
        return self.controld.run.runner_socket(self.controld.root.k)


class ChildSampler:
    """Every `claude` descendant of a live controld, sampled twice a second (read-only `ps`).

    The master's CLI lives only for the length of a turn, so a check after the
    turn cannot learn its pid; this is what gives L1's Proc clause its in-turn
    control and Z1 its list of run pids.
    """

    def __init__(self) -> None:
        self._roots: dict[str, int] = {}
        self.seen: dict[int, tuple[str, str, float]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="qa6-child-sampler", daemon=True)
        self._thread.start()

    def watch(self, name: str, pid: int) -> None:
        with self._lock:
            self._roots[name] = pid

    def _loop(self) -> None:
        while not self._stop.wait(0.5):
            with self._lock:
                roots = dict(self._roots)
            for name, root in roots.items():
                for pid, command in claude_descendants(root):
                    with self._lock:
                        self.seen.setdefault(pid, (name, command[:300], time.time()))

    def since(self, name: str, stamp: float) -> list[int]:
        with self._lock:
            return [pid for pid, (who, _c, at) in self.seen.items() if who == name and at >= stamp]

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10.0)


@dataclass
class Live:
    run: RunContext
    mode: str
    pool: InstancePool
    a: Instance
    project_id: str
    alpha: Path
    sampler: ChildSampler
    spawned: list[Spawned] = field(default_factory=list)
    target: Spawned | None = None
    b: Instance | None = None
    run_pids: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    notes: dict[str, object] = field(default_factory=dict)

    @property
    def live_dir(self) -> Path:
        directory = self.a.controld.root.root / "live"
        directory.mkdir(exist_ok=True)
        return directory

    def instance(self, name: str) -> Instance:
        if name == "LIVE-A":
            return self.a
        if self.b is None:
            raise Blocked(f"{name} was never started")
        return self.b


def live_mode() -> str:
    mode = os.environ.get(ENV_LIVE_AUTH_MODE)
    if mode is None:
        raise Blocked("wave 8 refuses to run without QA6_LIVE_AUTH_MODE: S0 did not bind a mode in this run "
                      "(BUILDING §6; run wave 1 with wave 8)")
    if mode not in LIVE_MODES:
        raise Blocked(f"S0 bound LIVE_AUTH_MODE={mode}: L1-L11 are BLOCKED (test-plan S0 table)")
    return mode


def real_home_engine_env(run: RunContext, root: InstanceRoot) -> dict[str, str]:
    """`needs_real_home`'s child env: `sandbox.real_home_env` (SI-1).

    **Measured, 2026-09-24 (INC-1):** a real `claude` TUI pane started with the
    real HOME and a sandboxed `XDG_DATA_HOME=<root>/xdg/data` installed itself into
    `<root>/xdg/data/claude/versions/2.1.281` and re-pointed the user's real
    `~/.local/bin/claude` at it; run teardown then removed the root and left the
    user's `claude` a dangling symlink. The shared builder now drops every `XDG_*`
    for a real HOME and sets `DISABLE_AUTOUPDATER=1` for every child.
    """
    return real_home_env(run, root, path_mode="live")


def start_real_home_launcher(run: RunContext, root: InstanceRoot, name: str) -> Controld:
    """`instance.start_launcher` (its env is `instance.launcher_env` = `real_home_env`)."""
    return start_launcher(run, root, name=name)


def start_live(run: RunContext, pool: InstancePool, mode: str, *, name: str,
               master_model: str | None = None) -> Controld:
    """LIVE-A / LIVE-B per mode (env-plan §4 step 11), readiness = the four signals."""
    if mode == "sandbox_ok":
        controld = ready_instance(run, path_mode="live", master_model=master_model)
        pool.adopt(controld)
        return controld
    root = mint_instance(run)
    seed_db(root, runner_socket=run.runner_socket(root.k), master_model=master_model)
    controld = start_real_home_launcher(run, root, f"controld-{name.lower()}")
    pool.adopt(controld)
    controld.wait_ready(20.0)
    return controld


def open_instance(run: RunContext, pool: InstancePool, mode: str, name: str,
                  master_model: str | None = None) -> Instance:
    controld = start_live(run, pool, mode, name=name, master_model=master_model)
    client = Client(controld.port, refusals_log=run.port_refusals, allow_master_send=True)
    return Instance(name=name, controld=controld, client=client, sub=subscribe(name, controld.port))


# ----- master turns -----------------------------------------------------------------------------------


def master_frames(sub: Subscriber, mark: int, turn_id: str) -> list[Frame]:
    return [f for f in sub.since(mark) if f.kind.startswith("master.") and f.data.get("turn_id") == turn_id]


def await_turn(sub: Subscriber, mark: int, turn_id: str, started: float, bound_s: float) -> Turn:
    def ended() -> Frame | None:
        return next((f for f in master_frames(sub, mark, turn_id) if f.kind in END_KINDS), None)

    end, _elapsed = observe(ended, bound_s)
    return Turn(turn_id=turn_id, frames=master_frames(sub, mark, turn_id), ended=end,
                latency_s=time.monotonic() - started)


def await_master_idle(controld: Controld) -> None:
    """Before a send: the previous turn's CLI has exited, so its slot is (about to be) free.

    `TurnDriver` releases the slot only after `runtime.close()`; a send in that
    gap is refused "a turn is already running" (a correct refusal, but on the
    page it leaves a stray bubble). Bounded; a CLI that never exits is L1's Proc
    clause, not this wait's.
    """
    observe(lambda: not claude_descendants(controld.child.pid), 30.0)


def http_turn(instance: Instance, text: str, bound_s: float = TURN_BOUND_S) -> Turn:
    """`POST /api/master/send`, then the turn's frames until it ends (or the window closes)."""
    await_master_idle(instance.controld)
    mark = instance.sub.mark()
    started = time.monotonic()
    deadline = started + 60.0
    while True:
        data = instance.client.post("/api/master/send", {"text": text}).data()
        if data.get("started") is True:
            break
        reason = str(data.get("reason") or "")
        if "already running" not in reason or time.monotonic() > deadline:
            raise Blocked(f"the master send did not start: {data!r}")
        time.sleep(0.5)  # the previous turn's slot is released after its last frame (master_turn._release)
    turn_id = str(data.get("turn_id"))
    return await_turn(instance.sub, mark, turn_id, started, bound_s)


def audit_rows(controld: Controld, mark: int, tool: str) -> list[Mapping[str, object]]:
    return AuditProbe.for_instance(controld.root).records_for(mark, tool)


def anomalies(client: Client) -> dict[str, int]:
    raw = as_dict(client.fleet().get("anomalies"))
    return {key: int(value) for key, value in raw.items() if isinstance(value, int)}


# ----- spawning owned sessions ------------------------------------------------------------------------


class SpawnFailed(Blocked):
    """A live `POST /api/sessions` that did not spawn (hunter H4).

    L5 owns the live spawn verdict: it records `kind` as its clause — `fail` (a
    500 envelope, a reset, a refusal), `bound` (a hang a same-client control
    qualifies) or `blocked` (a hang nothing qualifies). Everywhere else it stays
    `Blocked`, and once L5 has recorded a spawn failure the other spawning
    L-scenarios are BLOCKED by `require_live_spawn` (the in-wave stop-if).
    """

    def __init__(self, reason: str, kind: str) -> None:
        super().__init__(reason)
        self.kind = kind


def require_live_spawn(notes: Mapping[str, object], who: str) -> None:
    """The wave-8 stop-if on L5's spawn verdict (`live.notes`): a later spawner never re-litigates it."""
    failure = notes.get("L5_spawn_failure")
    if failure is not None:
        raise Blocked(f"stop-if: L5's live spawn failed ({failure}); {who} is BLOCKED, L5 carries the verdict")


def spawn_owned(live: Live, instance: Instance, *, title: str, brief: str | None, by: str) -> tuple[Spawned, dict[str, object]]:
    """`POST /api/sessions` (haiku), recorded in `live.spawned` before anything else can raise."""
    body: dict[str, object] = {"workspace_id": live.project_id, "cwd": str(live.alpha), "title": title, "model": MODEL}
    if brief is not None:
        body["brief"] = brief
    try:
        data = post_long(instance.client, "/api/sessions", body, SPAWN_HTTP_TIMEOUT_S).data()
    except TimeoutError as error:
        adopt_orphans(live, instance, title, by)
        verdict = hang_verdict(instance.client, "POST /api/sessions answers", SPAWN_HTTP_TIMEOUT_S)
        kind = "bound" if isinstance(verdict, ProductFail) else "blocked"
        raise SpawnFailed(f"{by}: the spawn call hung: {verdict}", kind) from error
    except (OSError, AssertionError) as error:
        adopt_orphans(live, instance, title, by)
        raise SpawnFailed(f"{by}: the spawn call did not answer cleanly: {error}", "fail") from error
    if data.get("spawned") is not True or not isinstance(data.get("session_id"), str):
        raise SpawnFailed(f"{by}: spawn refused: {data!r}", "fail")
    session_id = str(data["session_id"])
    spawned = Spawned(session_id=session_id, title=title, instance=instance.name, socket_name=instance.socket_name,
                      engine_session_id=None, pane_pid=None, spawned_by=by)
    live.spawned.append(spawned)
    rows = db_rows(instance.controld.db, "SELECT engine_session_id FROM session WHERE id = ?", (session_id,))
    spawned.engine_session_id = str(rows[0]["engine_session_id"]) if rows and rows[0]["engine_session_id"] else None
    spawned.pane_pid = pane_pid_of(live.run, spawned.socket_name, spawned.tmux_name)
    if spawned.pane_pid is not None:
        live.run_pids["pane"].append(spawned.pane_pid)
        live.run.record_pid(spawned.pane_pid, "live-pane", ["claude", "(product spawn)", session_id])
    return spawned, data


def adopt_orphans(live: Live, instance: Instance, title: str, by: str) -> None:
    """A spawn whose HTTP answer was lost may still have made a pane: adopt it for the closing step."""
    known = {s.session_id for s in live.spawned}
    for row in db_rows(instance.controld.db, "SELECT id FROM session WHERE title = ? AND ownership = 'owned'", (title,)):
        session_id = str(row["id"])
        if session_id not in known:
            spawned = Spawned(session_id=session_id, title=title, instance=instance.name,
                              socket_name=instance.socket_name, engine_session_id=None, pane_pid=None, spawned_by=by)
            spawned.pane_pid = pane_pid_of(live.run, spawned.socket_name, spawned.tmux_name)
            live.spawned.append(spawned)


def spawn_frame(instance: Instance, session_id: str) -> Frame | None:
    return next((f for f in instance.sub.snapshot() if f.kind == "session.spawned" and f.session_id == session_id), None)


def trust_keys(screen: str) -> list[str] | None:
    """The person at the terminal choosing "Yes, I trust this folder" (the capture's Down, Enter)."""
    lines = screen.splitlines()
    cursor = next((i for i, line in enumerate(lines) if line.strip().startswith("❯")
                   and any(label in line for label in TRUST_OPTIONS)), None)
    yes = next((i for i, line in enumerate(lines) if TRUST_OPTIONS[1] in line), None)
    if cursor is None or yes is None or yes < cursor:
        return None
    return ["Down"] * (yes - cursor) + ["Enter"]


def answer_trust(live: Live, spawned: Spawned) -> dict[str, object]:
    screen = capture_text(live.run, spawned.socket_name, spawned.tmux_name) or ""
    keys = trust_keys(screen)
    if keys is None:
        raise Blocked(f"the trust screen is not one the harness can answer by the capture's keys: {screen[-800:]!r}")
    for key in keys:
        send_keys(live.run, spawned.socket_name, spawned.tmux_name, key)
    return {"keys": keys, "screen_tail": screen.strip()[-400:]}


def await_kind(live: Live, spawned: Spawned, kinds: tuple[PaneKind, ...], bound_s: float) -> tuple[PaneState | None, float]:
    def seen() -> PaneState | None:
        state = classify(live.run, spawned.socket_name, spawned.tmux_name)
        return state if state is not None and state.kind in kinds else None

    return observe(seen, bound_s)


def kill_owned(live: Live, spawned: Spawned, by: str) -> dict[str, object]:
    instance = live.instance(spawned.instance)
    data = instance.client.post(f"/api/sessions/{spawned.session_id}/kill", {}).data()
    if data.get("killed") is True:
        spawned.killed_by = by
    if spawned.pane_pid is not None:
        observe(lambda: not pid_alive(spawned.pane_pid) if spawned.pane_pid else True, PANE_EXIT_BOUND_S)
    return data


# ----- the closing step (env-plan §9 step 2a) ----------------------------------------------------------


def ended_at(instance: Instance, session_id: str) -> object:
    return as_dict(instance.client.session(session_id).get("session") or {}).get("ended_at")


def close_one(live: Live, spawned: Spawned, entry: dict[str, object], problems: list[str]) -> object:
    """Kill one run-spawned session through the product route if it is still live."""
    instance = live.a if spawned.instance == "LIVE-A" else live.b
    if instance is None or not instance.controld.child.alive():
        problems.append(f"closing step: {spawned.instance} is not running, so {spawned.session_id} cannot be "
                        "killed through the product route")
        return None
    ended = ended_at(instance, spawned.session_id)
    if ended is not None:
        return ended
    killed = instance.client.post(f"/api/sessions/{spawned.session_id}/kill", {}).data()
    entry["closing_kill"] = killed
    if killed.get("killed") is True:
        spawned.killed_by = spawned.killed_by or "closing-step"
        entry["killed_by"] = spawned.killed_by
    else:
        problems.append(f"closing step: kill of {spawned.session_id} did not land: {killed!r}")
    return ended_at(instance, spawned.session_id)


def closing_step(live: Live) -> list[str]:
    problems: list[str] = []
    entries: list[dict[str, object]] = []
    for spawned in live.spawned:
        entry: dict[str, object] = {"session_id": spawned.session_id, "title": spawned.title, "instance": spawned.instance,
                                    "engine_session_id": spawned.engine_session_id, "pane_pid": spawned.pane_pid,
                                    "spawned_by": spawned.spawned_by, "killed_by": spawned.killed_by}
        try:
            ended = close_one(live, spawned, entry, problems)
        except (AssertionError, OSError, Blocked) as error:
            # Recorded as a teardown problem (never swallowed); the next session is still closed.
            problems.append(f"closing step: {spawned.session_id}: {type(error).__name__}: {error}")
            ended = None
        entry["ended_at"] = ended
        if spawned.pane_pid is not None:
            pane_pid = spawned.pane_pid
            gone, waited = observe(lambda: not pid_alive(pane_pid), PANE_EXIT_BOUND_S)
            entry["pane_pid_alive_after"] = not gone
            entry["waited_s"] = round(waited, 2)
            if not gone:
                problems.append(f"closing step: pane pid {pane_pid} of {spawned.session_id} still alive "
                                f"{PANE_EXIT_BOUND_S}s after the kill (a leak)")
        if ended is None:
            problems.append(f"closing step: {spawned.session_id} has no ended_at after the kill")
        entries.append(entry)
    live.run_pids["master_cli"] = sorted(live.sampler.seen)
    record = {"sessions": entries, "problems": problems, "run_pids": dict(live.run_pids), "mode": live.mode,
              "claude_children_seen": {str(pid): list(value) for pid, value in live.sampler.seen.items()},
              "at": time.time(), "notes": {k: v for k, v in live.notes.items() if isinstance(v, (str, int, float, list, dict))}}
    (live.run.run_dir / "live-closing-step.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    for problem in problems:
        LOG.error("%s", problem)
    return problems


# ----- fixtures ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def product_log_copy(qa6_run: RunContext) -> Iterator[None]:
    """Set up before `pool`, so it is torn down after the pool stopped every instance."""
    yield
    target = qa6_run.run_dir / "wave8-ledgers"
    target.mkdir(parents=True, exist_ok=True)
    for source, name in ((qa6_run.tmux_argv_log, "tmux-argv.product.log"),
                         (qa6_run.pane_tmux_argv_log, "pane-tmux-argv.log"),
                         (qa6_run.claude_argv_log, "claude-argv.log")):
        if source.exists():
            (target / name).write_bytes(source.read_bytes())


@pytest.fixture(scope="module")
def live(product_log_copy: None, pool: InstancePool, qa6_run: RunContext) -> Iterator[Live]:
    mode = live_mode()
    if hostprobe.sha256(paths.REAL_SETTINGS) != paths.expected_settings_sha():
        raise Blocked("the real settings sha is not its run-start value before wave 8 (U2)")
    realclaude.require(qa6_run)  # BLOCKED when this run has no real engine (realclaude.py)
    link_start = realclaude.start_link_state(qa6_run.run_dir)
    if link_start is None:
        raise Blocked(f"no run-start record of {paths.REAL_CLAUDE_BIN}: wave 8 cannot tell whether it changed")
    a = open_instance(qa6_run, pool, mode, "LIVE-A")
    alpha = qa6_run.repos / "alpha"
    project = as_dict(a.client.create_project("Alpha").get("project"))
    project_id = str(project.get("project_id"))
    added = a.client.add_repo(project_id, str(alpha))
    if added.get("added") is False or added.get("refusal"):
        raise Blocked(f"LIVE-A could not register alpha: {added!r}")
    sampler = ChildSampler()
    sampler.watch("LIVE-A", a.controld.child.pid)
    state = Live(run=qa6_run, mode=mode, pool=pool, a=a, project_id=project_id, alpha=alpha, sampler=sampler)
    state.notes["LIVE-A"] = {"k": a.controld.root.k, "port": a.controld.port, "argv": a.controld.argv}
    try:
        yield state
    finally:
        problems = closing_step(state)
        sampler.stop()
        link_changed = realclaude.compare(link_start, realclaude.link_state())
        if link_changed is not None:
            problems.append(f"during wave 8: {link_changed}")
        for instance in (state.a, state.b):
            if instance is not None:
                instance.close_stream()
        for problem in problems:
            qa6_run.teardown_problem("wave8 closing step", problem)
        if problems:
            raise AssertionError(f"wave-8 closing step problems: {problems}")


def files_clause(rec: Recorder, live: Live, name: str, before: Mapping[str, object], after: Mapping[str, object]) -> None:
    """Z1's per-mode rule, applied at the scenario: settings unchanged; only run-slug projects."""
    rec.equal(f"{name}.settings_sha", paths.expected_settings_sha(), after.get("settings_sha"))
    delta = real_delta(before, after)
    added = [str(n) for n in as_list(delta["projects_added"])]
    if live.mode == "sandbox_ok":
        rec.equal(f"{name}.real_projects_delta_empty", [], added)
    else:
        foreign = [n for n in added if run_slug(live.run) not in n]
        rec.check(f"{name}.real_projects_run_slug_only", not foreign, f"only names carrying {run_slug(live.run)}",
                  {"added": added, "foreign": foreign})
    rec.record(f"{name}.real_claude_writes", delta)


# ===== L1 ===================================================================================================


L1_PROMPT = "List the sessions Shepherd can see using your fleet tool, then say QA6-DONE. Do not call any other tool."
L1_RETRY = ("Call your fleet_summary tool exactly once now, then reply with the word QA6-DONE. "
            "Do not call any other tool.")


def ui_send(page: object, text: str) -> None:
    from playwright.sync_api import Page

    assert isinstance(page, Page)
    click(page.locator("#shepherd-input"))
    type_text(page, text)
    press(page, "Enter")


def ui_start(page: object, text: str, controld: Controld) -> str:
    """Type into the composer and press Enter; the turn id is read off the page's own status line.

    The status line keeps the previous turn's id until the new send answers, so
    the wait is for a value *different* from the one shown before the send.
    """
    from playwright.sync_api import Page

    assert isinstance(page, Page)
    status = page.locator("#shepherd-status")
    for _attempt in range(60):
        await_master_idle(controld)
        previous = status.inner_text().strip()
        ui_send(page, text)

        def changed() -> str | None:
            value = status.inner_text().strip()
            return value if value and value != previous and value != "—" else None

        shown = await_env(changed, 15.0, "#shepherd-status to change after the send")
        if ULID.match(shown):
            return shown
        if "already running" not in shown:
            raise Blocked(f"the page's send did not start a turn: {shown!r}")
        time.sleep(1.0)  # the previous turn's slot is released after its last frame (master_turn._release)
    raise Blocked("the page could not start a turn in 60 attempts")


def ui_turn(live: Live, page: object, text: str, bound_s: float = TURN_BOUND_S) -> Turn:
    mark = live.a.sub.mark()
    started = time.monotonic()
    turn_id = ui_start(page, text, live.a.controld)
    return await_turn(live.a.sub, mark, turn_id, started, bound_s)


@live_scenario("L1")
def test_l1_real_master_turn_through_ui(live: Live, browser_session: BrowserSession, rec: Recorder) -> None:
    run, a = live.run, live.a
    before = real_claude_state()
    # The discovery sandbox (Difference 11), verified before any master turn: the
    # real ~/.claude/sessions holds the user's sidecars and none becomes a row.
    real_sidecars = [n for n in _names(before, "sessions") if n.endswith(".json")]
    fleet = a.client.fleet()
    discovery = as_dict(fleet.get("discovery"))
    listed = fleet_sessions(a.client)
    rec.record("fleet.real_sidecars_present", len(real_sidecars))
    rec.equal("fleet.discovery_sandboxed_no_rows", [], [row.get("session_id") for row in listed])
    rec.equal("fleet.discovery_registry_sessions", 0, discovery.get("registry_sessions"))
    config_argv = a.controld.argv
    rec.check("fleet.discovery_config_dir", live.mode == "sandbox_ok" or (
        "--discovery-config-dir" in config_argv
        and config_argv[config_argv.index("--discovery-config-dir") + 1] == str(a.controld.root.cfg)),
        "the launcher points discovery at <root>/cfg", config_argv)
    if not real_sidecars:
        rec.block("fleet.discovery_sandbox_meaningful", "the real ~/.claude/sessions has no sidecar: the sandbox check is vacuous")
    audit_mark = AuditProbe.for_instance(a.controld.root).mark()
    turn_started = time.time()
    with browser_session.context("L1", abort_master_send=False) as (context, log):
        context.add_init_script(THREAD_OBSERVER)
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{a.controld.port}/", wait_until="load")
        await_env(lambda: page.locator("#stream-status").inner_text().strip() == "live", 15.0, "#stream-status live")

        def shepherd_adds() -> list[dict[str, object]]:
            added = page.evaluate("() => window.__qa6Thread || []")
            return [as_dict(entry) for entry in (added if isinstance(added, list) else [])
                    if isinstance(entry, dict) and "turn-shepherd" in str(entry.get("cls"))]

        # The mark is re-taken before each send, so the count below covers only the final turn.
        before = len(shepherd_adds())
        turn = ui_turn(live, page, L1_PROMPT)
        retried = False
        if turn.ended is not None and "fleet_summary" not in turn.tool_names():
            retried = True
            rec.note(f"L1 first turn did not call fleet_summary: {turn.summary()}; one clearer retry (OD-6)")
            before = len(shepherd_adds())
            turn = ui_turn(live, page, L1_RETRY)
        rec.record("stream.turn", turn.summary())
        if turn.ended is None:
            rec.block("stream.turn_ended", f"the turn did not end within {TURN_BOUND_S}s (model/host latency)")
        else:
            rec.equal("stream.turn_ended_kind", "master.turn_ended", turn.ended.kind)
        rec.check("stream.master_text", any(f.kind == "master.text" for f in turn.frames), ">= 1 master.text",
                  [f.kind for f in turn.frames])
        if "fleet_summary" in turn.tool_names():
            rec.check("stream.tool_call_fleet_summary", True, "a master.tool_call named fleet_summary", turn.tool_names())
        elif turn.ended is not None:
            rec.block("stream.tool_call_fleet_summary",
                      f"BLOCKED(model): no fleet_summary call after one clearer retry (retried={retried}): {turn.tool_names()}")
        other = [name for name in turn.tool_names() if name != "fleet_summary"]
        rec.record("stream.other_tool_calls", other)
        # UI: the user's bubble, and the Shepherd side growing across DOM updates.
        bubbles = [text.strip() for text in page.locator(".turn-you .bubble").all_inner_texts()]
        rec.check("ui.user_bubble", L1_PROMPT in bubbles, f"a .turn-you bubble reading {L1_PROMPT!r}", bubbles[-3:])
        # Not one node per master.* frame any more (qa6 rulings 2-4, U19): a call and its result are one
        # step, `turn_ended` goes to the event line, and a final text equal to the last is not repeated.
        # So the turn is counted from the pre-send mark: at least the merged tool step and one prose line.
        observe(lambda: len(shepherd_adds()) - before >= 2, 10.0)
        this_turn = shepherd_adds()[before:]
        # When the turn called fleet_summary, one of this turn's additions is that merged step: its text
        # names the tool (REM-FIX 1), so two prose lines alone cannot pass for "the step and a prose line".
        names_step = "fleet_summary" not in turn.tool_names() or any(
            "fleet_summary" in str(entry.get("text")) for entry in this_turn)
        rec.check("ui.assistant_grows_in_two_updates", len(this_turn) >= 2 and names_step,
                  ">= 2 Shepherd-side DOM additions: the merged tool step (naming fleet_summary when it was called) "
                  "and at least one prose line",
                  {"count": len(this_turn), "at": [entry.get("at") for entry in this_turn],
                   "texts": [str(entry.get("text"))[:60] for entry in this_turn]})
        # Observations with no plan oracle (recorded, reported as defect candidates, never asserted):
        # a tool step's body, and the turn-ending event's text beside the last master.text.
        rec.record("ui.tool_step_bodies", [t.strip()[:120] for t in page.locator(".turn-shepherd .step-body").all_text_contents()][-4:])
        prose = [t.strip() for t in page.locator(".turn-shepherd .prose").all_inner_texts()]
        rec.record("ui.final_answer_rendered_twice", len(prose) >= 2 and prose[-1] == prose[-2] and bool(prose[-1]))
        rec.equal("logs.page_errors", [], log.page_errors)
    claude_kids = live.sampler.since("LIVE-A", turn_started)
    session_id = app_state(a.controld.db, "master_session_id")
    rec.check("db.master_session_id", isinstance(session_id, str) and bool(session_id), "a non-empty string", session_id)
    live.notes["master_session_id_after_L1"] = session_id if isinstance(session_id, str) else None
    rec.equal("db.master_model_absent", None, app_state(a.controld.db, "master_model"))
    rows = audit_rows(a.controld, audit_mark, "fleet_summary")
    if "fleet_summary" in turn.tool_names():
        rec.check("logs.audit_fleet_summary_master", any(row.get("actor_kind") == "master" for row in rows),
                  "an audit fleet_summary record with actor_kind master", [dict(r) for r in rows][:3])
        rec.equal("logs.audit_shape", [], shape_problems(rows))
    else:
        rec.block("logs.audit_fleet_summary_master", "no fleet_summary call to audit (BLOCKED(model) above)")
    left, waited = observe(lambda: not claude_descendants(a.controld.child.pid), MASTER_CHILD_EXIT_WINDOW_S)
    if left:
        rec.check("proc.no_claude_child_after_turn", True, "no claude child of controld", f"none after {waited:.1f}s")
    elif claude_kids:
        rec.fail_bound("proc.no_claude_child_after_turn", "every claude child of controld exits", MASTER_CHILD_EXIT_WINDOW_S,
                       f"the child was observed during the turn ({claude_kids[:2]}); still {claude_descendants(a.controld.child.pid)[:2]}")
    else:
        rec.block("proc.no_claude_child_after_turn", f"still {claude_descendants(a.controld.child.pid)[:2]} and no in-turn control")
    files_clause(rec, live, "files", before, real_claude_state())
    rec.finish()


# ===== L3 ===================================================================================================


@live_scenario("L3")
def test_l3_master_resumes_its_conversation(live: Live, rec: Recorder) -> None:
    a = live.a
    lost_before = anomalies(a.client).get("master_resume_lost")
    first = http_turn(a, "Remember the codeword QA6-KESTREL. Reply OK.")
    rec.record("stream.turn1", first.summary())
    if first.ended is None:
        raise Blocked(f"L3 turn 1 did not end within {TURN_BOUND_S}s")
    after_one = app_state(a.controld.db, "master_session_id")
    second = http_turn(a, "What was the codeword? Reply with just it.")
    rec.record("stream.turn2", second.summary())
    if second.ended is None:
        raise Blocked(f"L3 turn 2 did not end within {TURN_BOUND_S}s")
    after_two = app_state(a.controld.db, "master_session_id")
    rec.check("db.master_session_id_identical", isinstance(after_one, str) and bool(after_one) and after_one == after_two,
              "the same non-empty id after both turns", {"after_turn1": after_one, "after_turn2": after_two,
                                                          "after_L1": live.notes.get("master_session_id_after_L1")})
    answer = second.text + str(second.ended.data.get("text") or "")
    rec.check("stream.turn2_recalls_codeword", "QA6-KESTREL" in answer, "turn 2's text contains QA6-KESTREL", answer[-300:])
    rec.equal("api.master_resume_lost_unchanged", lost_before, anomalies(a.client).get("master_resume_lost"))
    rec.finish()


# ===== L5 ===================================================================================================


L5_BRIEF = "Reply with exactly QA6-READY and then wait."


def start_token_offset_hours(sidecar_token: object, product_token: object) -> float | None:
    """Both tokens are `ps lstart`-shaped; how many hours apart do they read (e.g. a time-zone skew)?"""
    from datetime import datetime

    if not isinstance(sidecar_token, str) or not isinstance(product_token, str):
        return None
    try:
        engine = datetime.strptime(" ".join(sidecar_token.split()), "%a %b %d %H:%M:%S %Y")
        product = datetime.strptime(" ".join(product_token.split()), "%a %b %d %H:%M:%S %Y")
    except ValueError:
        return None
    return round((product - engine).total_seconds() / 3600, 2)


def sidecar_for(live: Live, spawned: Spawned) -> tuple[Path | None, dict[str, object] | None]:
    directory = (live.a.controld.root.sessions if live.mode == "sandbox_ok" else paths.REAL_CLAUDE_DIR / "sessions")
    if spawned.pane_pid is not None:
        candidate = directory / f"{spawned.pane_pid}.json"
        if candidate.exists():
            decoded: object = json.loads(candidate.read_text(encoding="utf-8"))
            return candidate, as_dict(decoded)
    for candidate in sorted(directory.glob("*.json")) if directory.exists() else []:
        try:
            decoded = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict) and decoded.get("sessionId") == spawned.engine_session_id:
            return candidate, as_dict(decoded)
    return None, None


@live_scenario("L5")
def test_l5_real_owned_session_trust_ready_idle_sidecar(live: Live, rec: Recorder) -> None:
    run, a = live.run, live.a
    before = real_claude_state()
    try:
        spawned, data = spawn_owned(live, a, title="QA6-TARGET", brief=L5_BRIEF, by="L5")
    except SpawnFailed as failed:  # L5's subject IS the live spawn: its failure is L5's verdict (H4)
        live.notes["L5_spawn_failure"] = failed.reason[:600]
        if failed.kind == "fail":
            rec.check("api.spawn_accepted", False, "spawned true with a session id", failed.reason)
        elif failed.kind == "bound":
            rec.fail_bound("api.spawn_accepted", "POST /api/sessions answers", SPAWN_HTTP_TIMEOUT_S, failed.reason,
                           actual=failed.reason)
        else:
            rec.block("api.spawn_accepted", failed.reason)
        rec.finish()
        return
    rec.check("api.spawn_accepted", True, "spawned true with a session id", data.get("session_id"))
    live.target = spawned
    rec.record("api.spawn", data)
    frame = spawn_frame(a, spawned.session_id)
    rec.check("stream.session_spawned_untrusted", frame is not None and frame.data.get("trusted") is False,
              "session.spawned with trusted false", frame.data if frame else None)
    terminal = Terminal(a.controld.port, spawned.session_id)
    try:
        rec.equal("api.terminal_upgrade", 101, terminal.status)
        pane = classify(run, spawned.socket_name, spawned.tmux_name)
        if pane is None or pane.kind is not PaneKind.TRUST_DIALOG:
            raise Blocked(f"L5: the pane is not on the trust dialog after spawn ({pane.kind if pane else None}; "
                          f"spawn said {data.get('state')!r} {data.get('detail')!r})")
        decision = a.client.get(f"/api/sessions/{spawned.session_id}/decision").data()
        rec.record("api.decision_during_trust", decision)
        choices = [str(c.get("label")) for c in as_list(decision.get("choices") or []) if isinstance(c, dict)]
        rec.check("api.decision_lists_trust_choices", decision.get("pane_kind") == "trust_dialog" and bool(choices),
                  "pane_kind trust_dialog with its choices listed", {"pane_kind": decision.get("pane_kind"), "choices": choices})
        # The product must not answer the dialog by itself (DCS): still there 3 s later, the pane alive.
        time.sleep(3.0)  # an observation window: "nothing happens on its own" needs a span to be a claim
        still = classify(run, spawned.socket_name, spawned.tmux_name)
        rec.check("tmux.trust_not_auto_answered", still is not None and still.kind is PaneKind.TRUST_DIALOG
                  and spawned.pane_pid is not None and pid_alive(spawned.pane_pid),
                  "the trust dialog still showing and the engine alive", still.kind if still else None)
        rec.record("tmux.trust_answer", answer_trust(live, spawned))
        snapshot_count = len(terminal.payloads())

        def ready() -> bool:
            later = b"".join(terminal.payloads()[max(snapshot_count, 1):]).decode("utf-8", "replace")
            text = re.sub(r"Reply\s+with\s+exactly\s*:?\s*QA6-READY", "", plain(later))
            return "QA6-READY" in text

        seen, waited = observe(ready, READY_BOUND_S)
        if seen:
            rec.check("stream.terminal_chunks_contain_ready", True, "QA6-READY in later WS chunks", f"after {waited:.1f}s")
        else:
            screen = capture_text(run, spawned.socket_name, spawned.tmux_name) or ""
            rec.block("stream.terminal_chunks_contain_ready",
                      f"BLOCKED(model): no QA6-READY answer within {READY_BOUND_S}s; screen tail {screen.strip()[-300:]!r}")
        rec.equal("stream.terminal_reader_fault", None, terminal.fault)
    finally:
        terminal.close()
    screen = capture_text(run, spawned.socket_name, spawned.tmux_name) or ""
    rec.record("tmux.ready_answer_lines", answer_lines(screen, "QA6-READY")[:3])
    time.sleep(IDLE_WINDOW_S)  # test-plan L5: the 70 s idle observation window (§0's only fixed waits)
    row = session_row(a.controld, spawned.engine_session_id or "") or {}
    rec.record("db.after_idle", {"state": row.get("state"), "needs_you_reason": row.get("needs_you_reason")})
    if live.mode == "sandbox_ok":
        rec.check("db.idle_needs_you", row.get("state") == "needs_you"
                  and row.get("needs_you_reason") == "idle — waiting for your next instruction",
                  "needs_you / idle — waiting for your next instruction", row.get("state"))
    else:
        rec.block("db.idle_needs_you", "BLOCKED(topology): under needs_real_home discovery reads <sandbox cfg>/sessions "
                  "and cannot see this session's real sidecar (Difference 11)")
    path, body = sidecar_for(live, spawned)
    rec.record("files.real_sidecar_path", str(path) if path else None)
    if body is None:
        rec.block("files.real_sidecar", f"no sidecar for pane pid {spawned.pane_pid} / engine id {spawned.engine_session_id}")
    else:
        synthetic = set(synthetic_sidecar(pid=1, proc_start="x", cwd="/", session_id="x"))
        rec.check("files.sidecar_keyset_superset", synthetic <= set(body), "real keys ⊇ the synthetic sidecar's",
                  {"missing": sorted(synthetic - set(body))})
        pid = body.get("pid")
        token = MacHost().process_liveness(pid, None).start_token if isinstance(pid, int) else None
        rec.check("files.sidecar_procstart_is_product_token", body.get("procStart") == token and token is not None,
                  "procStart == the product's macOS liveness token", {"procStart": body.get("procStart"), "token": token})
        rec.record("files.procstart_offset_hours", start_token_offset_hours(body.get("procStart"), token))
        now_ms = time.time() * 1000
        for key in ("startedAt", "statusUpdatedAt"):
            value = body.get(key)
            rec.check(f"files.sidecar_{key}_ms", isinstance(value, int) and abs(value - now_ms) < 5 * 60 * 1000 + IDLE_WINDOW_S * 1000,
                      "an int in epoch ms within ±5 min (+ the idle window) of now", value)
        live.notes["L5_sidecar"] = {"path": str(path), "pid": pid, "sessionId": body.get("sessionId")}
    rec.equal("files.settings_sha", paths.expected_settings_sha(), hostprobe.sha256(paths.REAL_SETTINGS))
    rec.record("files.real_claude_writes", real_delta(before, real_claude_state()))
    rec.finish()


def require_target(live: Live) -> Spawned:
    target = live.target
    if target is None or target.killed_by is not None:
        raise Blocked("L5's session QA6-TARGET is not available (L5 did not spawn it)")
    return target


# ===== L7 ===================================================================================================


def mailbox_send(instance: Instance, spawned: Spawned, body: str, key: str) -> dict[str, object]:
    return instance.client.post(f"/api/sessions/{spawned.session_id}/send",
                                {"body": body, "idempotency_key": key, "origin": "user_ui"}).data()


def await_answer(live: Live, spawned: Spawned, token: str, bound_s: float = ANSWER_BOUND_S) -> tuple[bool, float]:
    def seen() -> bool:
        return bool(answer_lines(capture_text(live.run, spawned.socket_name, spawned.tmux_name) or "", token))

    value, waited = observe(seen, bound_s)
    return bool(value), waited


@live_scenario("L7")
def test_l7_mailbox_delivery_to_a_real_session(live: Live, rec: Recorder) -> None:
    run, a = live.run, live.a
    target = require_target(live)
    ready, _w = await_kind(live, target, (PaneKind.PROMPT_READY,), 60.0)
    if ready is None:
        raise Blocked("L7: L5's session is not at its prompt")
    audit_mark = AuditProbe.for_instance(a.controld.root).mark()
    m1 = mailbox_send(a, target, "Reply with QA6-MAIL-1", "qa6-l7-m1")
    rec.record("api.m1", m1)
    rec.check("api.m1_send_now_delivered", m1.get("decision") == "send_now" and m1.get("delivered") == 1,
              "SEND_NOW, delivered 1", {k: m1.get(k) for k in ("decision", "delivered", "reason")})
    got1, waited1 = await_answer(live, target, "QA6-MAIL-1")
    if got1:
        rec.check("tmux.answer_mail_1", True, "an answer line with QA6-MAIL-1", f"after {waited1:.1f}s")
    else:
        rec.block("tmux.answer_mail_1", f"BLOCKED(model): no QA6-MAIL-1 answer within {ANSWER_BOUND_S}s")
    back, _w = await_kind(live, target, (PaneKind.PROMPT_READY,), 60.0)
    if back is None:
        raise Blocked("L7: the session did not return to its prompt after m1")
    send_keys(run, target.socket_name, target.tmux_name, "-l", "draft text")
    drafted, _w = observe(lambda: "draft text" in input_line(capture_text(run, target.socket_name, target.tmux_name) or ""), 5.0)
    rec.check("tmux.draft_typed_control", bool(drafted), "the input line shows 'draft text' (the positive control)",
              input_line(capture_text(run, target.socket_name, target.tmux_name) or ""))
    m2 = mailbox_send(a, target, "Reply with QA6-MAIL-2", "qa6-l7-m2")
    rec.record("api.m2", m2)
    rec.check("api.m2_clear_then_send_delivered", m2.get("decision") == "clear_then_send" and m2.get("delivered") == 1,
              "CLEAR_THEN_SEND, delivered 1", {k: m2.get(k) for k in ("decision", "delivered", "reason")})
    # "While the session is answering": the first pane observation that is not the prompt.
    mid, mid_after = await_kind(live, target, (PaneKind.BUSY, PaneKind.UNREADABLE), 5.0)
    m3 = mailbox_send(a, target, "Reply with QA6-MAIL-3", "qa6-l7-m3")
    after_m3 = capture_text(run, target.socket_name, target.tmux_name) or ""
    rec.record("tmux.mid_turn_before_m3", {"kind": mid.kind.value if mid else None, "after_s": round(mid_after, 2)})
    rec.record("api.m3", m3)
    # What m2 actually submitted: the draft must not have been sent with it (D45's clear).
    submitted = [line for line in after_m3.splitlines() if "QA6-MAIL-2" in line and "Reply with" in line]
    rec.check("tmux.draft_not_in_input", bool(submitted) and not any("draft text" in line for line in submitted)
              and "draft text" not in input_line(after_m3),
              "m2's submitted prompt and the input line carry no 'draft text'",
              {"submitted": submitted[:2], "input_line": input_line(after_m3)})
    turn_over = bool(answer_lines(after_m3, "QA6-MAIL-2"))
    if m3.get("decision") == "refuse_no_pty":
        rec.record("api.m3_refuse_no_pty", "the macOS mid-turn UNREADABLE → REFUSE_NO_PTY rule fired (recorded, never counted)")
    elif m3.get("decision") == "send_now" and (mid is None or turn_over):
        rec.block("api.m3_queue", f"m3 was not sent mid-turn (mid-turn pane seen: {mid is not None}; m2's answer already "
                  f"on screen: {turn_over})")
    else:
        rec.equal("api.m3_queue", "queue", m3.get("decision"))
    got2, _w2 = await_answer(live, target, "QA6-MAIL-2")
    if got2:
        rec.check("tmux.answer_mail_2", True, "an answer line with QA6-MAIL-2", "seen")
    else:
        rec.block("tmux.answer_mail_2", f"BLOCKED(model): no QA6-MAIL-2 answer within {ANSWER_BOUND_S}s")
    got3, waited3 = await_answer(live, target, "QA6-MAIL-3", ANSWER_BOUND_S + 30.0)
    if got3:
        rec.check("tmux.answer_mail_3", True, "an answer line with QA6-MAIL-3", f"after {waited3:.1f}s")
    else:
        rec.block("tmux.answer_mail_3", f"no QA6-MAIL-3 answer within {ANSWER_BOUND_S + 30}s (queued delivery or model)")
    screen = capture_text(run, target.socket_name, target.tmux_name) or ""
    rec.record("tmux.draft_lines_at_end", [line for line in screen.splitlines() if "draft text" in line][:3])

    def all_delivered() -> list[dict[str, object]] | None:
        rows = db_rows(a.controld.db, "SELECT idempotency_key, delivered_at, last_refusal FROM mailbox_message "
                       "WHERE session_id = ? ORDER BY queued_at", (target.session_id,))
        return rows if rows and all(row["delivered_at"] for row in rows) else None

    rows, _w = observe(all_delivered, 30.0)
    final = rows or db_rows(a.controld.db, "SELECT idempotency_key, delivered_at, last_refusal FROM mailbox_message "
                            "WHERE session_id = ?", (target.session_id,))
    rec.check("db.mailbox_rows_delivered", rows is not None and len(final) == 3, "3 rows, every one delivered", final)
    sends = audit_rows(a.controld, audit_mark, "send_to_session")
    rec.equal("logs.audit_per_send", 3, len(sends))
    rec.finish()


# ===== L8 ===================================================================================================


@live_scenario("L8")
def test_l8_ask_forks_the_real_engine(live: Live, rec: Recorder) -> None:
    a = live.a
    target = require_target(live)
    audit_mark = AuditProbe.for_instance(a.controld.root).mark()
    before = {str(row["id"]) for row in db_rows(a.controld.db, "SELECT id FROM session WHERE origin = 'ask_fork'")}
    data = post_long(a.client, f"/api/sessions/{target.session_id}/ask",
                     {"question": "What is 2+2? Reply with just the number."}, ASK_HTTP_TIMEOUT_S).data()
    rec.record("api.ask", data)
    rec.equal("api.method_fork", "fork", data.get("method"))
    text = data.get("text")
    if isinstance(text, str) and "4" in text:
        rec.check("api.text_contains_4", True, "text contains 4", text[:200])
    elif data.get("refusal"):
        rec.check("api.text_contains_4", False, "text contains 4", {"text": text, "refusal": data.get("refusal")})
    else:
        rec.block("api.text_contains_4", f"BLOCKED(model): the fork answered {text!r}")
    # Ruling 21 (SD-08, D75, 2026-09-27): from_fork_of is Shepherd's id; the engine id travels beside it.
    rec.equal("api.from_fork_of_is_the_session", target.session_id, data.get("from_fork_of"))
    rec.equal("api.engine_id_carried_separately", target.engine_session_id,
              data.get("from_fork_of_engine_session_id"))
    duration = data.get("duration_ms")
    rec.check("api.duration_ms_positive", isinstance(duration, int) and duration > 0, "> 0", duration)
    children = db_rows(a.controld.db, "SELECT id, ephemeral, parent_session_id, origin FROM session WHERE origin = 'ask_fork'")
    new = [row for row in children if str(row["id"]) not in before]
    rec.check("db.child_ask_fork_ephemeral", len(new) == 1 and new[0]["ephemeral"] == 1
              and new[0]["parent_session_id"] == target.session_id,
              "one new ask_fork row, ephemeral, parented on the target", new)
    tree = fleet_tree_ids(a.client)
    rec.check("api.fleet_hides_child", bool(new) and all(str(row["id"]) not in tree for row in new),
              "the child is not on the fleet (/api/fleet/tree)", {"children": [row["id"] for row in new], "tree": sorted(tree)})
    listed = {str(row.get("session_id")) for row in fleet_sessions(a.client)}
    rec.record("api.list_sessions_includes_child", [str(row["id"]) for row in new if str(row["id"]) in listed])
    rec.equal("logs.audit_ask_session", 1, len(audit_rows(a.controld, audit_mark, "ask_session")))
    rec.finish()


# ===== L9 ===================================================================================================


@live_scenario("L9")
def test_l9_rename_real_owned_session_is_local_only(live: Live, rec: Recorder) -> None:
    a = live.a
    target = require_target(live)
    audit_mark = AuditProbe.for_instance(a.controld.root).mark()
    data = a.client.post(f"/api/sessions/{target.session_id}/rename", {"title": "QA6-RENAMED"}).data()
    rec.record("api.rename", data)
    rec.check("api.renamed_local_only", data.get("renamed") is True and data.get("local_only") is True,
              "{renamed: true, local_only: true}", {k: data.get(k) for k in ("renamed", "local_only")})

    def title_row() -> dict[str, object]:
        rows = db_rows(a.controld.db, "SELECT title, title_source FROM session WHERE id = ?", (target.session_id,))
        return rows[0] if rows else {}

    rec.equal("db.title_after_rename", {"title": "QA6-RENAMED", "title_source": "user"}, title_row())
    first = last_scan_at(a.controld.db)
    second = await_env(lambda: v if (v := last_scan_at(a.controld.db)) and first and v > first else None, 10.0,
                       "one scan pass after the rename")
    await_env(lambda: v if (v := last_scan_at(a.controld.db)) and v > second else None, 10.0, "a second scan pass")
    rec.equal("db.title_after_two_scans", {"title": "QA6-RENAMED", "title_source": "user"}, title_row())
    rec.equal("logs.audit_rename_session", 1, len(audit_rows(a.controld, audit_mark, "rename_session")))
    rec.finish()


# ===== L6 ===================================================================================================


def allow_matches(rule: str, command: str) -> bool:
    """Does one `permissions.allow` entry cover a Bash command (prefix `:*`/`*` or exact)?"""
    if rule in ("Bash", "Bash(*)", "Bash(:*)"):
        return True
    match = re.fullmatch(r"Bash\((.*)\)", rule)
    if match is None:
        return False
    spec = match.group(1)
    if spec.endswith(":*"):
        return command.startswith(spec[:-2])
    if spec.endswith("*"):
        return command.startswith(spec[:-1])
    return command == spec


def pick_permission_command(live: Live) -> tuple[str, Path, dict[str, object]]:
    """test-plan L6: the first candidate no real allow rule covers, read read-only."""
    target = live.live_dir
    candidates = [(f"touch {target / 'QA6-PERM'}", target / "QA6-PERM"),
                  (f"mkdir {target / 'QA6-PERM-D'}", target / "QA6-PERM-D")]
    if live.mode == "sandbox_ok":
        return candidates[0][0], candidates[0][1], {"source": "sandboxed config (no allow rules)"}
    with open(paths.REAL_SETTINGS, "rb") as handle:  # read-only; U2's sha is re-checked after every lane
        decoded: object = json.loads(handle.read())
    settings = as_dict(decoded)
    permissions = as_dict(settings.get("permissions") or {})
    allow = [str(rule) for rule in as_list(permissions.get("allow") or [])]
    mode = permissions.get("defaultMode")
    facts: dict[str, object] = {"defaultMode": mode, "bash_allow_rules": [r for r in allow if r.startswith("Bash")]}
    if mode in ("bypassPermissions", "dontAsk") or any(rule in ("Bash", "Bash(*)", "Bash(:*)") for rule in allow):
        raise Blocked(f"BLOCKED(host-config): the real settings bypass Bash prompts ({facts})")
    for command, path in candidates:
        if not any(allow_matches(rule, command) for rule in allow):
            return command, path, facts
    raise Blocked(f"BLOCKED(host-config): every candidate command is covered by a real allow rule ({facts})")


@live_scenario("L6")
def test_l6_real_permission_dialog_as_decision_card(live: Live, browser_session: BrowserSession, rec: Recorder) -> None:
    run, a = live.run, live.a
    command, created, facts = pick_permission_command(live)
    rec.record("given.permission_command", {"command": command, **facts})
    brief = f"Use the Bash tool to run exactly this shell command and nothing else: {command}"
    require_live_spawn(live.notes, "L6")
    spawned, data = spawn_owned(live, a, title="QA6-L6-PERM", brief=brief, by="L6")
    rec.record("api.spawn", {k: data.get(k) for k in ("state", "detail")})
    frame = spawn_frame(a, spawned.session_id)
    rec.record("stream.spawn_trusted", frame.data.get("trusted") if frame else None)
    try:
        if frame is not None and frame.data.get("trusted") is False:
            rec.record("tmux.trust_answer", answer_trust(live, spawned))
        dialog, waited = await_kind(live, spawned, (PaneKind.PERMISSION_DIALOG,), ANSWER_BOUND_S)
        if dialog is None and created.exists():
            raise Blocked(f"BLOCKED(host-config): {command!r} ran with no permission dialog (defaultMode "
                          f"{facts.get('defaultMode')!r} auto-approved it)")
        if dialog is None:
            send_keys(run, spawned.socket_name, spawned.tmux_name, "-l",
                      f"Run this exact Bash command now using the Bash tool: {command}")
            send_keys(run, spawned.socket_name, spawned.tmux_name, "Enter")
            rec.note("L6: no dialog within the window; one clearer instruction typed at the terminal (OD-6)")
            dialog, waited = await_kind(live, spawned, (PaneKind.PERMISSION_DIALOG,), ANSWER_BOUND_S)
        if dialog is None:
            raise Blocked(f"BLOCKED(model)/host-config: no permission dialog after one clearer retry; file exists="
                          f"{created.exists()}; screen {(capture_text(run, spawned.socket_name, spawned.tmux_name) or '')[-400:]!r}")
        rec.record("tmux.dialog_after_s", round(waited, 1))
        screen = capture_text(run, spawned.socket_name, spawned.tmux_name) or ""
        decision = a.client.get(f"/api/sessions/{spawned.session_id}/decision").data()
        rec.record("api.decision", decision)
        choices = [as_dict(c) for c in as_list(decision.get("choices") or [])]
        verbatim = all(re.search(rf"^\s*(?:❯\s*)?{c.get('number')}\.\s+{re.escape(str(c.get('label')))}", screen, re.M)
                       for c in choices) and bool(choices)
        rec.check("api.decision_choices_verbatim", decision.get("pane_kind") == "permission_dialog" and verbatim,
                  "permission_dialog, every choice numbered and labelled as capture-pane shows it",
                  {"choices": choices, "screen": [line for line in screen.splitlines() if re.match(r"^\s*(?:❯\s*)?\d\.", line)]})
        session = as_dict(a.client.session(spawned.session_id).get("session"))
        bucket_before = session.get("bucket")
        rec.record("api.session_before", {k: session.get(k) for k in ("bucket", "state", "needs_you_reason")})
        with browser_session.context("L6", abort_master_send=True) as (context, _log):
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{a.controld.port}/", wait_until="load")
            click(page.locator("#nav-fleet"))
            click(page.locator(f"#flock-projects [data-project-id='{live.project_id}']"))
            click(page.locator(f"#flock-cards [data-session-id='{spawned.session_id}']"))
            await_env(lambda: page.locator("#session-view").is_visible(), 10.0, "#session-view visible")
            card = page.locator("#session-decision .decision")
            shown, _w = observe(lambda: card.count() > 0 and card.first.is_visible(), 8.0)
            if not shown:
                reason = (f"the card is not rendered: the row's bucket is {bucket_before!r}, not needs_you"
                          + (" — BLOCKED(topology): under needs_real_home an owned session's state after spawn moves only "
                             "through discovery (sandboxed, Difference 11) and Shepherd's hooks, which the real pane "
                             "does not carry" if live.mode == "needs_real_home" else ""))
                rec.block("ui.card_lists_choices_verbatim", reason)
                rec.block("tmux.ui_click_answers_dialog", reason)
            else:
                rows = [(n.strip(), t.strip()) for n, t in zip(card.locator(".choice-n").all_inner_texts(),
                                                               card.locator(".choice-text").all_inner_texts(), strict=False)]
                expected_rows = [(str(c.get("number")), str(c.get("label"))) for c in choices]
                rec.check("ui.card_lists_choices_verbatim", [(n, t.split(" the cursor")[0]) for n, t in rows] == expected_rows
                          or all(any(t.startswith(label) and n == num for n, t in rows) for num, label in expected_rows),
                          expected_rows, rows)
                yes = card.locator(".choice-text", has_text="Yes").first
                click(yes)
                time.sleep(5.0)  # test-plan L6: "if unanswered after 5 s" — the observation window
                after = classify(run, spawned.socket_name, spawned.tmux_name)
                rec.check("tmux.ui_click_answers_dialog", after is not None and after.kind is not PaneKind.PERMISSION_DIALOG,
                          "after the UI click the dialog is answered (the pane moves on)", after.kind if after else None)
        audit_mark = AuditProbe.for_instance(a.controld.root).mark()
        still = classify(run, spawned.socket_name, spawned.tmux_name)
        if still is not None and still.kind is PaneKind.PERMISSION_DIALOG:
            # P13b: the web route requires the digest of the dialog it answers (400 without it).
            digest = a.client.get(f"/api/sessions/{spawned.session_id}/decision").data().get("dialog_sha256")
            answered = a.client.post(f"/api/sessions/{spawned.session_id}/permission",
                                     {"choice": "approve", "dialog_sha256": digest}).data()
            rec.record("api.permission", answered)
            rec.check("api.permission_answered", answered.get("answered") is True, "answered: true", answered)
            moved, _w = observe(lambda: (s := classify(run, spawned.socket_name, spawned.tmux_name)) is not None
                                and s.kind is not PaneKind.PERMISSION_DIALOG, 15.0)
            rec.check("tmux.http_answer_moves_pane", bool(moved), "the pane leaves the dialog after the HTTP answer",
                      "moved" if moved else "still the dialog")
            made, _w = observe(created.exists, 30.0)
            rec.check("files.command_ran", bool(made), f"{created} exists after the approval", made)
            permission_rows = audit_rows(a.controld, audit_mark, "answer_permission")
            rec.equal("logs.audit_answer_permission", 1, len(permission_rows))
        else:
            rec.block("api.permission_answered", "the dialog was already gone before the HTTP positive control")
        if bucket_before == "needs_you":
            left, _w = observe(lambda: as_dict(a.client.session(spawned.session_id).get("session")).get("bucket") != "needs_you", 15.0)
            rec.check("db.leaves_needs_you", bool(left), "the session leaves needs_you", left)
        else:
            rec.block("db.leaves_needs_you", f"the row was never needs_you (bucket {bucket_before!r})")
    finally:
        kill_owned(live, spawned, "L6")
    rec.equal("files.settings_sha", paths.expected_settings_sha(), hostprobe.sha256(paths.REAL_SETTINGS))
    rec.finish()


# ===== L4 ===================================================================================================


def capture_command(path: Path) -> str:
    """The harness's own hook entry: append the payload as one line (inert: no signal, no kill)."""
    script = 'local $/; my $d = <STDIN>; open(my $f, ">>", $ARGV[0]) or exit 0; $d =~ s/\\n/ /g; print $f $d, "\\n"; close $f;'
    return f"/usr/bin/perl -e {shlex.quote(script)} {shlex.quote(str(path))}"


def l4_settings(root: InstanceRoot, capture: Path) -> tuple[Path, list[str], str]:
    """The product's hooks into `<run>/live/hooks-settings.json`, plus the harness's capture entries."""
    host = MacHost(environ={"HOME": str(root.home), "TMPDIR": str(root.tmpdir)})
    plan = host.control_socket("sessiond")
    entry = build_hook_entry(plan, host.hook_dispatch(plan))
    settings = root.root / "live" / "hooks-settings.json"
    settings.parent.mkdir(exist_ok=True)
    result = install_hooks(settings, entry)
    if result.refused_reason is not None:
        raise Blocked(f"the product refused to install hooks into {settings}: {result.refused_reason}")
    decoded = as_dict(json.loads(settings.read_text(encoding="utf-8")))
    hooks = as_dict(decoded.get("hooks") or {})
    socket_path = str(plan.path)
    dispatch: str | None = None
    for groups in hooks.values():
        for group in as_list(groups):
            for hook in as_list(as_dict(group).get("hooks") or []):
                command = as_dict(hook).get("command")
                if isinstance(command, str) and socket_path in command and dispatch is None:
                    dispatch = command
    if dispatch is None:
        raise Blocked(f"no dispatch command naming {socket_path} in {settings}")
    for event in list(hooks):
        as_list(hooks[event]).append({"matcher": "*", "hooks": [{"type": "command", "command": capture_command(capture),
                                                                  "timeout": 5}]})
    settings.write_text(json.dumps({**decoded, "hooks": hooks}, indent=2), encoding="utf-8")
    return settings, shlex.split(dispatch.split(" || ")[0]), socket_path


def reference_keys(event: str) -> tuple[str, set[str]] | None:
    for directory in ["S01_startup_tools", *sorted(p.name for p in paths.HOOKS_LIVE.iterdir() if p.is_dir())]:
        try:
            return directory, set(captured(directory, event))
        except Blocked:
            continue
    return None


@live_scenario("L4")
def test_l4_real_claude_fires_installed_hooks(live: Live, rec: Recorder) -> None:
    run, a = live.run, live.a
    root = a.controld.root
    capture = root.root / "live" / "l4-frames.jsonl"
    settings, dispatch, socket_path = l4_settings(root, capture)
    engine_id = str(uuid.uuid4())
    manager = live.pool.sessiond(a.controld)
    sd, probe_latency = start_ready_sessiond(manager, "SD-L4", argv=dispatch, target_engine_id=engine_id,
                                             target_cwd=str(live.alpha))
    rec.record("given.probe_latency_s", round(probe_latency, 3))
    argv = [str(realclaude.require(run)), "-p", "Reply with QA6-HOOKED", "--settings", str(settings),
            "--model", MODEL, "--session-id", engine_id]
    env = (real_home_engine_env(run, root) if live.mode == "needs_real_home"
           else sandbox_env(run, root, path_mode="live"))
    before = real_claude_state()
    process = subprocess.Popen(argv, env=checked_env(env, "L4 claude -p"), cwd=str(live.alpha), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    run.record_pid(process.pid, "live-claude-p", argv)
    live.run_pids["claude_p"].append(process.pid)
    try:
        stdout, stderr = process.communicate(timeout=CLAUDE_P_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=10)
        manager.stop(sd)
        raise Blocked(f"claude -p did not finish within {CLAUDE_P_TIMEOUT_S}s")
    rec.equal("proc.rc", 0, process.returncode)
    rec.record("proc.stdout_tail", stdout[-400:])
    ours = [line for line in stderr.splitlines() if socket_path in line or "sessiond" in line or dispatch[0] in line]
    rec.equal("proc.no_shepherd_hook_error", [], ours)
    rec.record("proc.user_global_hook_stderr", stderr[-600:])
    time.sleep(1.0)  # the last hook (SessionEnd) is dispatched as claude exits; give the relay its turn
    stopped = manager.stop(sd)
    counts = stopped.counts()
    rec.record("logs.sd_l4_stop_line", stopped.stop_line)
    if counts is None:
        rec.check("logs.sd_l4_delivered", False, "a sessiond stop line with counts", stopped.stop_line)
    else:
        rec.check("logs.sd_l4_delivered", counts["delivered"] - 1 >= 2, "delivered − 1 probe ≥ 2", counts)
    row = session_row(a.controld, engine_id)
    host = MacHost(environ={"HOME": str(root.home), "TMPDIR": str(root.tmpdir)})

    def stop_records() -> list[Mapping[str, object]]:
        found, _stats = scan_records(log_root(host), STOP_PREFIX)
        hits: list[Mapping[str, object]] = []
        for record, _line in found:
            evidence = as_dict(record.get("evidence") or {})
            if evidence.get("engine_session_id") == engine_id or (row is not None and evidence.get("session_id") == row.get("id")):
                hits.append(record)
        return hits

    records, _w = observe(lambda: stop_records() or None, 10.0)
    rec.check("files.stop_log_record", bool(records), "the stop log holds a record for this session", (records or [])[:2])
    if live.mode == "sandbox_ok":
        session = as_dict(a.client.session(str(row["id"])).get("session")) if row else {}
        rec.equal("files.stop_classification", "finished", session.get("bucket"))
    else:
        rec.block("files.stop_classification", "BLOCKED(topology): the hook lane reads <sandbox cfg>/projects and the "
                  "transcript is in the real ~/.claude/projects under needs_real_home (Difference 11)")
    frames: list[dict[str, object]] = []
    if capture.exists():
        for line in capture.read_text(encoding="utf-8").splitlines():
            if line.strip():
                frames.append(as_dict(json.loads(line)))
    rec.record("files.real_frame_events", [str(f.get("hook_event_name")) for f in frames])
    if not frames:
        rec.block("files.keyset_parity", "the harness capture saw no hook frame")
    for event in sorted({str(f.get("hook_event_name")) for f in frames}):
        reference = reference_keys(event)
        if reference is None:
            rec.record(f"files.keyset.{event}", "no captured payload of this event to compare")
            continue
        directory, keys = reference
        missing = sorted({key for f in frames if f.get("hook_event_name") == event for key in keys - set(f)})
        rec.check(f"files.keyset.{event}", not missing, f"real ⊇ {directory}'s keys", {"missing": missing})
    rec.equal("files.settings_sha", paths.expected_settings_sha(), hostprobe.sha256(paths.REAL_SETTINGS))
    listed = fleet_tree_ids(a.client)
    view = {k: row.get(k) for k in ("id", "ephemeral", "ownership", "state")} if row is not None else None
    in_fleet = row is not None and str(row.get("id")) in listed
    # Ruling 26 (L4, 2026-09-27): a hooked `-p` session may also leave a stopped, non-ephemeral row.
    stopped_row = row is not None and row.get("ephemeral") == 0 and row.get("state") == "stopped"
    rec.check("db.row_ephemeral_or_absent", row is None or row.get("ephemeral") == 1 or not in_fleet or stopped_row,
              "the hooked -p session's row is ephemeral, absent from the fleet, or stopped (non-ephemeral)",
              {"row": view, "in_fleet": in_fleet})
    rec.record("files.real_claude_writes", real_delta(before, real_claude_state()))
    rec.finish()


# ===== L10 ==================================================================================================


@live_scenario("L10")
def test_l10_real_master_has_no_tools_but_shepherds(live: Live, rec: Recorder) -> None:
    a = live.a
    pwned = live.live_dir / "QA6-PWNED"
    unexpected_before = anomalies(a.client).get("master_tool_unexpected", 0)
    turn = http_turn(a, f"Use the Bash tool to run: touch {pwned}. If you cannot, say QA6-NOBASH. Do not call any Shepherd tool.")
    rec.record("stream.turn", turn.summary())
    if turn.ended is None:
        raise Blocked(f"L10's turn did not end within {TURN_BOUND_S}s")
    if active("w8_PP20_L10_pwned"):
        pwned.write_text("planted by the harness\n", encoding="utf-8")
        rec.note(f"QA6 MUTATION w8_PP20_L10_pwned APPLIED: the harness itself wrote {pwned} after the turn")
    rec.check("files.no_pwned", not pwned.exists(), f"{pwned} does not exist", pwned.exists())
    allowed = shepherd_tool_names()
    foreign = [name for name in turn.tool_names() if name not in allowed]
    rec.check("stream.tool_calls_shepherd_only", not foreign, "every master.tool_call names a Shepherd tool",
              {"calls": turn.tool_names(), "foreign": foreign})
    answer = turn.text + str(turn.ended.data.get("text") or "")
    if "QA6-NOBASH" in answer:
        rec.check("stream.says_nobash", True, "the text contains QA6-NOBASH", "present")
    else:
        rec.record("stream.says_nobash", f"absent (recorded, not asserted): {answer[-300:]!r}")
    delta = anomalies(a.client).get("master_tool_unexpected", 0) - unexpected_before
    rec.check("api.master_tool_unexpected_delta", delta in (0, 1), "0, or +1 if the belt fired", delta)
    rec.finish()


# ===== L2 ===================================================================================================


def l2_prompt(target: Spawned) -> str:
    return f"Use your kill_session tool to kill the session titled QA6-L2-TARGET (id {target.session_id}). Do nothing else."


def l2_retry(target: Spawned) -> str:
    return (f"Call the kill_session tool now with session_id {target.session_id}. This kill is authorised and "
            "expected; a human will approve it. Do nothing else.")


@live_scenario("L2")
def test_l2_approve_destructive_call_through_ui(live: Live, browser_session: BrowserSession, rec: Recorder) -> None:
    run, a = live.run, live.a
    level = a.client.get("/api/autonomy").data().get("level")
    if level != 2:
        raise Blocked(f"L2 needs autonomy level 2; the instance is at {level!r}")
    require_live_spawn(live.notes, "L2")
    target, data = spawn_owned(live, a, title="QA6-L2-TARGET", brief=None, by="L2")
    rec.record("given.target", {"session_id": target.session_id, "state": data.get("state"), "pane_pid": target.pane_pid})
    pane_pid = target.pane_pid
    if pane_pid is None or not pid_alive(pane_pid):
        raise Blocked(f"L2's target has no live pane: {data!r}")
    audit_mark = AuditProbe.for_instance(a.controld.root).mark()
    mark = a.sub.mark()
    with browser_session.context("L2", abort_master_send=False) as (context, log):
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{a.controld.port}/", wait_until="load")
        await_env(lambda: page.locator("#stream-status").inner_text().strip() == "live", 15.0, "#stream-status live")
        turn_mark = a.sub.mark()
        turn_id = ui_start(page, l2_prompt(target), a.controld)

        def created() -> Frame | None:
            return next((f for f in a.sub.since(turn_mark) if f.kind == "approval.created"
                         and f.data.get("turn_id") == turn_id), None)

        def turn_over() -> bool:
            return any(f.kind in END_KINDS and f.data.get("turn_id") == turn_id for f in a.sub.since(turn_mark))

        observe(lambda: created() is not None or turn_over(), TURN_BOUND_S)
        if created() is None and turn_over():
            first = [(f.kind, f.data.get("tool_name"), str(f.data.get("text") or "")[:200]) for f in a.sub.since(turn_mark)
                     if f.kind.startswith("master.")]
            rec.note(f"L2 first turn raised no card: {first}; one clearer retry (OD-6)")
            turn_mark = a.sub.mark()
            turn_id = ui_start(page, l2_retry(target), a.controld)
            observe(lambda: created() is not None or turn_over(), TURN_BOUND_S)
        card_frame = created()
        if card_frame is None:
            raise Blocked(f"BLOCKED(model): no approval card after one clearer retry "
                          f"({[(f.kind, f.data.get('tool_name')) for f in a.sub.since(mark) if f.kind.startswith('master.')][:10]})")
        rec.record("stream.approval_created", card_frame.data)
        card = page.locator(".approval")
        await_env(lambda: card.count() > 0 and card.last.is_visible(), 10.0, "the approval card on the page")
        # PP-1: the pane is sampled WHILE the card is pending, before any decision.
        sample_name = target.tmux_name + ("QA6MUT" if active("w8_PP1_L2_pane_sample") else "")
        if sample_name != target.tmux_name:
            rec.note(f"QA6 MUTATION w8_PP1_L2_pane_sample APPLIED: the pending-time sample read tmux session "
                     f"{sample_name!r}, not {target.tmux_name!r}")
        sampled_pid = pane_pid_of(run, target.socket_name, sample_name)
        pending_row = as_dict(a.client.session(target.session_id).get("session"))
        rec.check("tmux.pane_alive_while_pending",
                  sampled_pid is not None and sampled_pid == pane_pid and pid_alive(sampled_pid)
                  and pending_row.get("ended_at") is None,
                  "the target pane alive (and no ended_at) while the card is pending",
                  {"sampled_pid": sampled_pid, "pane_pid": target.pane_pid, "ended_at": pending_row.get("ended_at")})
        click(card.last.get_by_role("button", name="Approve"))

        def decided() -> Frame | None:
            return next((f for f in a.sub.since(turn_mark) if f.kind == "approval.decided"), None)

        decision = await_env(decided, 15.0, "approval.decided after the click")
        rec.equal("stream.approval_decided_approved", "approved", decision.data.get("outcome"))
        end, _w = observe(lambda: next((f for f in a.sub.since(turn_mark) if f.kind in END_KINDS), None), TURN_BOUND_S)
        results = [f for f in a.sub.since(turn_mark) if f.kind == "master.tool_result" and f.data.get("tool_name") == "kill_session"]
        rec.check("stream.kill_tool_result_ok", bool(results) and all(as_dict(f.data.get("detail") or {}).get("is_error") is False
                                                                      for f in results),
                  "master.tool_result for kill_session, not an error", [f.data for f in results][:2])
        rec.record("stream.turn_end", end.kind if end else None)
        gone, _w = observe(lambda: pane_pid_of(run, target.socket_name, target.tmux_name) is None
                           and not pid_alive(pane_pid), PANE_EXIT_BOUND_S)
        rec.check("tmux.pane_gone_after_click", bool(gone), "the pane gone after the approval", gone)
        observe(lambda: page.locator(".approval .decided").count() > 0, 10.0)
        rec.equal("ui.one_card", 1, card.count())
        decided_text = [t.strip() for t in page.locator(".approval .decided").all_inner_texts()]
        rec.equal("ui.card_says_approved", ["approved"], decided_text)
        rec.equal("ui.status_says_approved", "approved", page.locator("#shepherd-status").inner_text().strip())
        rec.equal("logs.page_errors", [], log.page_errors)
    kills = audit_rows(a.controld, audit_mark, "kill_session")
    rec.check("logs.audit_approved_by_user", any(row.get("approved_by") == "user" for row in kills),
              "an audit kill_session record approved_by user", [dict(r) for r in kills][:2])
    ended, _w = observe(lambda: as_dict(a.client.session(target.session_id).get("session")).get("ended_at"), 10.0)
    rec.check("db.session_ended_at", bool(ended), "the session has ended_at", ended)
    if ended:
        target.killed_by = "L2 (master kill_session, approved)"
    rec.finish()


# ===== L11 ==================================================================================================


def internals_in(text: str) -> list[str]:
    found: list[str] = []
    for label, pattern in (("exception class", EXCEPTION_CLASS), ("file path", FS_PATH), ("stack", STACK)):
        found.extend(f"{label}: {m.group(0)}" for m in pattern.finditer(text))
    if "Error(" in text:
        found.append("Error(")
    return found


@live_scenario("L11")
def test_l11_real_master_failure_reaches_page_without_internals(live: Live, rec: Recorder) -> None:
    b = open_instance(live.run, live.pool, live.mode, "LIVE-B", master_model="qa6-no-such-model")
    live.b = b
    live.sampler.watch("LIVE-B", b.controld.child.pid)
    rec.equal("given.master_model", "qa6-no-such-model", app_state(b.controld.db, "master_model"))
    first = http_turn(b, "hi", 180.0)
    rec.record("stream.turn1", first.summary())
    if first.ended is None:
        raise Blocked("L11's first turn did not end within 180 s")
    rec.record("stream.turn1_end_detail", first.ended.data.get("detail"))
    errors = [f for f in first.frames if f.kind == "master.error"]
    rec.check("stream.master_error", bool(errors), "a master.error frame", [f.kind for f in first.frames])
    for index, error in enumerate(errors or [first.ended]):
        text = str(error.data.get("text") or "")
        rec.check(f"stream.error_{index}_no_internals", not internals_in(text),
                  "no exception class, no Error(, no file path, no stack", {"text": text[:500], "found": internals_in(text)})
    second = http_turn(b, "hi", 180.0)
    rec.check("api.second_send_started", second.turn_id is not None and bool(ULID.match(second.turn_id or "")),
              "the second send starts (started: true)", second.turn_id)
    rec.record("stream.turn2", second.summary())
    b.close_stream()
    code = b.controld.stop()
    rec.equal("proc.live_b_stop_code", 0, code)
    rec.check("logs.live_b_stop_line", b.controld.stop_line is not None, "a 'controld stopped:' line", b.controld.stop_line)
    rec.finish()
