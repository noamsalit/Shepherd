"""SUB controld instances, named sessiond instances, and the DB seams around them.

**SUB** (test-plan §1 lanes): the shipped console script,
`.venv/bin/shepherd-controld --port 0`, as a subprocess with the allow-listed
sandbox env. The port is parsed from its first stdout line. Readiness is the
four signals of test-plan §0 row 1 **together**:

1. the start line `controld: http://127.0.0.1:<port> · <sock>` arrives while
   `Popen.poll()` is still `None` (so `PYTHONUNBUFFERED` really took effect);
2. the control socket file exists;
3. `GET /api/fleet` answers 200 with `ok:true`;
4. `app_state.discovery_status.last_scan_at` strictly increases across two
   reads at least 2.0 s apart (the sourced scan cadence).

A readiness failure is `Blocked` with the controld stdout/stderr tail: an
under-gated environment produces failures that look like product bugs.

**Signals** go only to the recorded `Popen` pid of a child this module spawned,
never to a pid found by name (env-plan §9; CLAUDE.md).

**sessiond** (env-plan §1 "sessiond instances"): at most one per controld
instance at any moment. Before every start the manager asserts the socket is
absent and no recorded sessiond pid for the instance is alive; a violation is
`Blocked`, never a verdict. The product's `bind_listener` unlinks an existing
socket without a live-owner check, so two would silently steal frames.
"""

from __future__ import annotations

import json
import re
import signal
import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from shepherd.host.mac import MacHost
from shepherd.store.db import open_store

from . import paths
from .httpclient import Client
from .sandbox import InstanceRoot, PathMode, RunContext, checked_env, mint_instance, real_home_env, sandbox_env
from .verdict import Blocked, await_env

START_LINE = re.compile(r"^controld: http://127\.0\.0\.1:(\d+) · (\S+)$")
STOP_LINE = re.compile(r"^controld stopped: (.*)$")
SESSIOND_STOP_LINE = re.compile(
    r"^sessiond stopped: delivered=(\d+) buffered=(\d+) overflowed=(\d+) schema_mismatch=(\d+)$"
)

#: Harness bounds (not product SLOs). The product's own bind wait is 10 s.
READY_BOUND_S = 15.0
STOP_BOUND_S = 15.0
SESSIOND_STOP_BOUND_S = 5.0
#: The sourced discovery cadence (discovery_loop.py `REGISTRY_SCAN_INTERVAL_S`).
SCAN_INTERVAL_S = 2.0


# ----- the DB, read-only and pre-start ---------------------------------------


def seed_db(instance: InstanceRoot, *, runner_socket: str, master_model: str | None = None) -> None:
    """Create and migrate the instance DB and write the knobs **before** start.

    env-plan §4 step 4: `open_store` through the product's own path computation
    (`MacHost(environ).dirs().data_dir`), then the runner socket, then close.
    Raises `Blocked` if the fresh DB does not hold exactly the Unassigned
    workspace, or the knob does not read back.
    """
    host = MacHost(environ={"HOME": str(instance.home), "TMPDIR": str(instance.tmpdir)})
    db_path = host.dirs().data_dir / "shepherd.db"
    if db_path != instance.db_path:
        raise Blocked(f"MacHost puts the DB at {db_path}, the harness expected {instance.db_path}")
    store = open_store(db_path)
    try:
        store.set_app_state("runner_socket", runner_socket)
        if master_model is not None:
            store.set_app_state("master_model", master_model)
        workspaces = [workspace.id for workspace in store.list_workspaces()]
        socket_back = store.get_app_state("runner_socket")
    finally:
        store.close()
    if workspaces != ["unassigned"]:
        raise Blocked(f"a fresh DB should hold only 'unassigned'; it holds {workspaces}")
    if socket_back != runner_socket:
        raise Blocked(f"runner_socket read back {socket_back!r}, wrote {runner_socket!r}")


def db_connect_ro(db_path: Path) -> sqlite3.Connection:
    """A read-only connection. Never a writer while controld runs (env-plan §8)."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def db_rows(db_path: Path, sql: str, params: Sequence[object] = ()) -> list[dict[str, object]]:
    connection = db_connect_ro(db_path)
    try:
        return [dict(row) for row in connection.execute(sql, tuple(params)).fetchall()]
    finally:
        connection.close()


def app_state(db_path: Path, key: str) -> object | None:
    rows = db_rows(db_path, "SELECT value FROM app_state WHERE key = ?", (key,))
    if not rows:
        return None
    raw = rows[0]["value"]
    decoded: object = json.loads(str(raw))
    return decoded


def last_scan_at(db_path: Path) -> str | None:
    status = app_state(db_path, "discovery_status")
    if isinstance(status, dict):
        value = status.get("last_scan_at")
        return value if isinstance(value, str) else None
    return None


def schema_version(db_path: Path) -> int:
    rows = db_rows(db_path, "SELECT MAX(version) AS v FROM schema_migration")
    value = rows[0]["v"] if rows else None
    return int(value) if isinstance(value, int) else 0


# ----- a drained child ---------------------------------------------------------


class Drained:
    """A child whose stdout/stderr are drained by threads into lists and files.

    Without the drain a chatty child blocks on a full pipe; without the lists a
    scenario cannot assert on a line while the process is still alive.
    """

    def __init__(self, popen: subprocess.Popen[bytes], log_dir: Path, name: str) -> None:
        self.popen = popen
        self.name = name
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self._lock = threading.Lock()
        log_dir.mkdir(parents=True, exist_ok=True)
        self._threads = [
            threading.Thread(
                target=self._drain, args=(popen.stdout, self.stdout, log_dir / f"{name}.out"), daemon=True
            ),
            threading.Thread(
                target=self._drain, args=(popen.stderr, self.stderr, log_dir / f"{name}.err"), daemon=True
            ),
        ]
        for thread in self._threads:
            thread.start()

    def _drain(self, stream: object, sink: list[str], path: Path) -> None:
        readline = getattr(stream, "readline", None)
        if readline is None:
            return
        with open(path, "ab") as log:
            while True:
                raw = readline()
                if not isinstance(raw, bytes) or raw == b"":
                    return
                log.write(raw)
                log.flush()
                with self._lock:
                    sink.append(raw.decode("utf-8", "replace").rstrip("\n"))

    @property
    def pid(self) -> int:
        return self.popen.pid

    def alive(self) -> bool:
        return self.popen.poll() is None

    def lines(self, which: str = "stdout") -> list[str]:
        with self._lock:
            return list(self.stdout if which == "stdout" else self.stderr)

    def tail(self, count: int = 20) -> str:
        return f"stdout={self.lines('stdout')[-count:]!r} stderr={self.lines('stderr')[-count:]!r}"

    def join_drains(self, timeout_s: float = 5.0) -> None:
        for thread in self._threads:
            thread.join(timeout=timeout_s)

    def terminate_and_wait(self, bound_s: float) -> int | None:
        """SIGTERM to our own recorded child, then wait. `None` = did not exit."""
        if self.popen.poll() is None:
            self.popen.send_signal(signal.SIGTERM)
        try:
            code = self.popen.wait(timeout=bound_s)
        except subprocess.TimeoutExpired:
            return None
        self.join_drains()
        return code

    def kill_and_wait(self) -> int | None:
        if self.popen.poll() is None:
            self.popen.kill()
        try:
            return self.popen.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            return None


def spawn_drained(
    run: RunContext, argv: list[str], env: Mapping[str, str], cwd: Path, log_dir: Path, name: str, kind: str
) -> Drained:
    popen = subprocess.Popen(
        argv,
        env=checked_env(env, f"spawning {kind} {argv[:1]}"),
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    run.record_pid(popen.pid, kind, argv)
    return Drained(popen, log_dir, name)


# ----- controld ---------------------------------------------------------------


@dataclass
class Controld:
    """One SUB controld: the child, its root, and what readiness learned."""

    run: RunContext
    root: InstanceRoot
    child: Drained
    env: dict[str, str]
    argv: list[str]
    port: int = 0
    socket_path: Path | None = None
    start_line_at: float | None = None
    start_line_while_alive: bool = False
    stop_code: int | None = None
    stop_line: str | None = None
    ready_notes: list[str] = field(default_factory=list)

    @property
    def client(self) -> Client:
        return Client(self.port, refusals_log=self.run.port_refusals)

    @property
    def db(self) -> Path:
        return self.root.db_path

    def start_line(self, bound_s: float = READY_BOUND_S) -> re.Match[str] | None:
        """Wait for the start line; record whether the process was alive then."""

        def seen() -> re.Match[str] | None:
            for line in self.child.lines("stdout"):
                match = START_LINE.match(line)
                if match:
                    return match
            return None

        deadline = time.monotonic() + bound_s
        while time.monotonic() < deadline:
            match = seen()
            if match is not None:
                if self.start_line_at is None:
                    self.start_line_at = time.monotonic()
                    self.start_line_while_alive = self.child.alive()
                return match
            if not self.child.alive():
                self.child.join_drains(2.0)
                return seen()
            time.sleep(0.02)
        return None

    def wait_ready(self, bound_s: float = READY_BOUND_S) -> None:
        """The four readiness signals, or `Blocked` naming the one that failed."""
        match = self.start_line(bound_s)
        if match is None:
            raise Blocked(f"controld k={self.root.k}: no start line within {bound_s}s; {self.child.tail()}")
        if not self.start_line_while_alive:
            raise Blocked(f"controld k={self.root.k}: start line arrived only after exit; {self.child.tail()}")
        self.port = int(match.group(1))
        self.socket_path = Path(match.group(2))
        if self.port in (0, paths.FORBIDDEN_PORT):
            raise Blocked(f"controld k={self.root.k} printed port {self.port}")
        await_env(lambda: self.socket_path is not None and self.socket_path.exists(), 5.0,
                  f"controld k={self.root.k} socket {self.socket_path}")
        fleet = await_env(lambda: self._fleet_ok(), 5.0, f"controld k={self.root.k} GET /api/fleet ok")
        self.ready_notes.append(f"fleet ok: {sorted(fleet)}")
        first = await_env(lambda: last_scan_at(self.db), 5.0, f"controld k={self.root.k} first scan")
        time.sleep(SCAN_INTERVAL_S)  # the sourced cadence: two reads >= 2.0 s apart (§0 row 1)
        second = await_env(
            lambda: (value if (value := last_scan_at(self.db)) and value > first else None),
            SCAN_INTERVAL_S * 3,
            f"controld k={self.root.k} last_scan_at advancing past {first}",
        )
        self.ready_notes.append(f"last_scan_at {first} -> {second}")
        if not self.child.alive():
            raise Blocked(f"controld k={self.root.k} exited during readiness; {self.child.tail()}")

    def _fleet_ok(self) -> dict[str, object] | None:
        try:
            response = self.client.get("/api/fleet")
        except OSError:
            return None
        if response.status != 200:
            return None
        body = response.json()
        return body if body.get("ok") is True else None

    def healthcheck(self) -> None:
        """Between-module check: alive, fleet 200, and a scan advancing."""
        if not self.child.alive():
            raise Blocked(f"controld k={self.root.k} is not running; {self.child.tail()}")
        if self._fleet_ok() is None:
            raise Blocked(f"controld k={self.root.k} /api/fleet not ok")
        before = last_scan_at(self.db)
        await_env(
            lambda: (value if (value := last_scan_at(self.db)) and value != before else None),
            SCAN_INTERVAL_S * 3,
            f"controld k={self.root.k} scanning",
        )

    def stop(self, bound_s: float = STOP_BOUND_S) -> int | None:
        """SIGTERM, await exit, capture the stop line. SIGKILL (recorded) on hang."""
        if self.stop_code is not None or not self.child.alive():
            if self.stop_code is None:
                self.stop_code = self.child.popen.returncode
                self.child.join_drains()
            self._read_stop_line()
            return self.stop_code
        code = self.child.terminate_and_wait(bound_s)
        if code is None:
            self.run.teardown_problem(
                f"controld k={self.root.k}", f"did not exit {bound_s}s after SIGTERM; SIGKILLed"
            )
            code = self.child.kill_and_wait()
            if self.socket_path is not None and self.socket_path.exists():
                self.socket_path.unlink()
        self.stop_code = code
        self._read_stop_line()
        return code

    def _read_stop_line(self) -> None:
        for line in self.child.lines("stdout"):
            if STOP_LINE.match(line):
                self.stop_line = line


#: The product's port refusal (controld.py `main`: "controld refuses to start: port N is not
#: available (<OSError>)"). It labels EVERY OSError that way, so the errno text decides (H2).
PORT_REFUSAL = re.compile(r"^controld refuses to start: port \d+ is not available \((.*)\)$")
EADDRINUSE_TEXT = ("[Errno 48]", "Address already in use")


class RestartFailed(AssertionError):
    """A restart on the same root did not come up, and the OS did not refuse the port: the product's."""


def restart_failure(stdout_lines: Sequence[str], readiness: str) -> Blocked | RestartFailed:
    """How a failed restart readiness is classified (hunter H2). Pure.

    BLOCKED only when the child printed the product's port refusal with an
    `EADDRINUSE` error (the OS would not re-bind the port: an environment
    fact). Any other non-ready state — no start line, an exit, a scan that
    does not advance, a traceback — is the product failing to restart on a
    root it just ran on, which the first start's readiness controls: FAIL.
    """
    for line in stdout_lines:
        match = PORT_REFUSAL.match(line)
        if match and any(text in match.group(1) for text in EADDRINUSE_TEXT):
            return Blocked(f"the OS would not re-bind the port (EADDRINUSE): {line!r}; readiness: {readiness}")
    return RestartFailed(f"the restart on the same root did not come up, and it was not an EADDRINUSE refusal "
                         f"(the first start on this root was ready): {readiness}")


def wait_restart_ready(controld: Controld) -> None:
    """`wait_ready` for a restart: `Blocked` only for EADDRINUSE, else `RestartFailed` (FAIL)."""
    try:
        controld.wait_ready()
    except Blocked as blocked:
        if not controld.child.alive():
            controld.child.join_drains(2.0)
        raise restart_failure(controld.child.lines("stdout"), blocked.reason) from blocked


def start_controld(
    run: RunContext,
    root: InstanceRoot,
    *,
    port: int = 0,
    path_mode: PathMode = "shims",
    env: Mapping[str, str] | None = None,
    extra_args: Sequence[str] = (),
    name: str = "controld",
) -> Controld:
    """Start the console script. No readiness wait: callers choose."""
    if port == paths.FORBIDDEN_PORT:
        run.ledger(run.port_refusals, {"refused": port, "at": time.time()})
        raise Blocked(f"refusing to start controld on port {port} (R1)")
    child_env = dict(env) if env is not None else sandbox_env(run, root, path_mode=path_mode)
    argv = [str(paths.CONTROLD_BIN), "--port", str(port), *extra_args]
    run.ledger(run.controld_argv_ledger, {"k": root.k, "argv": argv, "at": time.time()})
    child = spawn_drained(run, argv, child_env, root.cwd, root.logs, name, "controld")
    return Controld(run=run, root=root, child=child, env=child_env, argv=argv)


def ready_instance(
    run: RunContext,
    *,
    path_mode: PathMode = "shims",
    sessions_dir: bool = True,
    master_model: str | None = None,
    configure: Callable[[InstanceRoot], None] | None = None,
) -> Controld:
    """Mint a root, seed the DB, start, and wait for the four signals."""
    root = mint_instance(run, sessions_dir=sessions_dir)
    seed_db(root, runner_socket=run.runner_socket(root.k), master_model=master_model)
    if configure is not None:
        configure(root)
    controld = start_controld(run, root, path_mode=path_mode)
    try:
        controld.wait_ready()
    except Blocked:
        controld.stop()
        raise
    return controld


# ----- sessiond ---------------------------------------------------------------


@dataclass
class SessiondRun:
    name: str
    child: Drained
    schema: int
    stop_code: int | None = None
    stop_line: str | None = None

    def counts(self) -> dict[str, int] | None:
        if self.stop_line is None:
            return None
        match = SESSIOND_STOP_LINE.match(self.stop_line)
        if match is None:
            return None
        delivered, buffered, overflowed, mismatch = (int(group) for group in match.groups())
        return {
            "delivered": delivered,
            "buffered": buffered,
            "overflowed": overflowed,
            "schema_mismatch": mismatch,
        }


class SessiondManager:
    """The named sessiond instances of one controld instance, one at a time."""

    def __init__(self, controld: Controld) -> None:
        self.controld = controld
        self.history: list[SessiondRun] = []
        self.current: SessiondRun | None = None

    @property
    def socket(self) -> Path:
        return self.controld.root.sessiond_socket

    def _assert_clear(self, name: str) -> None:
        if self.socket.exists():
            raise Blocked(f"{name}: sessiond socket {self.socket} exists before start (two sessionds would steal frames)")
        alive = [run.name for run in self.history if run.child.alive()]
        if alive:
            raise Blocked(f"{name}: a recorded sessiond is still alive: {alive}")

    def start(self, name: str, schema: int = 4, argv_override: Sequence[str] | None = None) -> SessiondRun:
        self._assert_clear(name)
        argv = list(argv_override) if argv_override is not None else [
            str(paths.SESSIOND_BIN), "--expected-schema-version", str(schema)
        ]
        child = spawn_drained(
            self.controld.run, argv, self.controld.env, self.controld.root.cwd,
            self.controld.root.logs, f"sessiond-{name}", "sessiond",
        )
        run = SessiondRun(name=name, child=child, schema=schema)
        self.history.append(run)
        self.current = run
        return run

    def wait_socket(self, run: SessiondRun, bound_s: float = 5.0) -> None:
        await_env(lambda: self.socket.exists() or not run.child.alive(), bound_s, f"{run.name} socket")
        if not run.child.alive():
            raise Blocked(f"{run.name} exited before binding: {run.child.tail()}")

    def stop(self, run: SessiondRun) -> SessiondRun:
        code = run.child.terminate_and_wait(SESSIOND_STOP_BOUND_S)
        if code is None:
            self.controld.run.teardown_problem(run.name, "sessiond did not exit 5 s after SIGTERM; SIGKILLed")
            code = run.child.kill_and_wait()
        run.stop_code = code
        for line in run.child.lines("stderr"):
            if SESSIOND_STOP_LINE.match(line):
                run.stop_line = line
        if self.current is run:
            self.current = None
        return run

    def stop_all(self) -> None:
        for run in self.history:
            if run.child.alive():
                self.stop(run)


# ----- helper children (sleep 3600) --------------------------------------------


@dataclass
class Helper:
    """A harness-owned `/bin/sleep 3600` standing in for an engine process."""

    popen: subprocess.Popen[bytes]
    start_token: str

    @property
    def pid(self) -> int:
        return self.popen.pid

    def end(self) -> None:
        if self.popen.poll() is None:
            self.popen.terminate()
        try:
            self.popen.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self.popen.kill()
            self.popen.wait(timeout=5.0)


def start_helper(run: RunContext) -> Helper:
    """Spawn a helper and read its start token with the **product's** liveness function."""
    popen = subprocess.Popen([str(paths.SLEEP_BIN), "3600"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run.record_pid(popen.pid, "helper", [str(paths.SLEEP_BIN), "3600"])
    liveness = MacHost().process_liveness(popen.pid, None)
    if not liveness.alive or liveness.start_token is None:
        popen.terminate()
        popen.wait(timeout=5.0)
        raise Blocked(f"the product's liveness probe does not see helper {popen.pid} alive")
    return Helper(popen=popen, start_token=liveness.start_token)


# ----- the needs_real_home launcher (env-plan §1 Difference 2 / 6) -------------------


LAUNCHER = paths.QA6_DIR / "launch_controld.py"


def launcher_env(run: RunContext, root: InstanceRoot) -> dict[str, str]:
    """The launcher's child env: `sandbox.real_home_env` with the LIVE `PATH`.

    Real `HOME`, `CLAUDE_CONFIG_DIR` **unset**, `TMPDIR` = the instance's, the
    LIVE `PATH` (logging tmux + `<run0>/bin/claude`), **no `XDG_*`**,
    `DISABLE_AUTOUPDATER=1` (SI-1: the INC-1 shape can never recur here), and
    everything else allow-listed.
    """
    return real_home_env(run, root, path_mode="live")


def start_launcher(run: RunContext, root: InstanceRoot, *, port: int = 0, name: str = "launcher") -> Controld:
    """Start `launch_controld.py` with the real HOME and a sandboxed Shepherd.

    Env: `launcher_env` (real `HOME`, no `XDG_*`, the SI-1 opt-outs). Discovery
    is pointed at `<root>/cfg`.
    """
    if port == paths.FORBIDDEN_PORT:
        run.ledger(run.port_refusals, {"refused": port, "at": time.time()})
        raise Blocked(f"refusing to start the launcher on port {port} (R1)")
    env = launcher_env(run, root)
    argv = [
        str(paths.PYTHON), str(LAUNCHER), "--port", str(port),
        "--shepherd-home", str(root.home), "--shepherd-tmpdir", str(root.tmpdir),
        "--discovery-config-dir", str(root.cfg),
    ]
    run.ledger(run.controld_argv_ledger, {"k": root.k, "argv": argv, "at": time.time(), "launcher": True})
    child = spawn_drained(run, argv, env, root.cwd, root.logs, name, "launcher")
    return Controld(run=run, root=root, child=child, env=env, argv=argv)
