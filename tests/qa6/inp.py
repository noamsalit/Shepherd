"""The INP composition: `controld.start(MacHost(environ=sandbox), 0)` in this pytest process.

env-plan §1 INP rows and §4 step 9. **One composition per pytest process**
(T3: the tool registry, chokepoint and stream ring are module globals), so the
fixture is session-scoped and each INP lane (INP #1 wave 5, INP-long M17,
INP #2 wave 7) is its own pytest process started by the runner.

What is real: the tool surface, gate, approvals, audit, SSE, HTTP, discovery,
runner (the logging tmux shim on PATH), fake `claude` shim on PATH. What is
replaced: **only** `shepherd.daemons.controld.build_master`, patched to
`qa6.inproc.master.build_tool_calling_master` before `start()` reads it, and
restored after `stop()`.

Some product code reads the process environment rather than the injected host
(`claude_config_dir()` reads `CLAUDE_CONFIG_DIR`; spawn and tmux resolve through
`PATH`), so for the composition's life this process's `os.environ` gets the
instance's `HOME`, `TMPDIR`, `CLAUDE_CONFIG_DIR`, `XDG_*` and shim `PATH`. It
is restored in the finaliser, before the root conftest's session-end settings
guard reads `CLAUDE_CONFIG_DIR` again.

Readiness (§4 step 9): `start()` returned (its own bind wait), the control
socket exists, `GET /api/fleet` is ok, `last_scan_at` advances across two
reads ≥ 2.0 s apart, the master's exported tool set is non-empty, and a no-op
scripted turn (`Turn(says="QA6-READY")`) produces `master.turn_ended` on SSE.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from shepherd.daemons import controld as controld_module
from shepherd.host.mac import MacHost
from shepherd.toolsurface import client as master_client

from .httpclient import Client
from .instance import SCAN_INTERVAL_S, last_scan_at, seed_db
from .inproc.master import BOOK, ScriptBook, Turn, build_tool_calling_master
from .pool import close_tmux_socket
from .sandbox import InstanceRoot, RunContext, mint_instance, sandbox_env
from .sse_rig import Subscriber, subscribe
from .verdict import Blocked, await_env

READY_TURN = "QA6-READY"
#: The one patch point (test-plan §1 reality check: controld.start passes the
#: module-global name `build_master` to compose_tool_surface, controld.py:31, 76).
PATCH_POINT = "build_master"
_REAL_BUILD_MASTER: object = getattr(controld_module, PATCH_POINT)


def patched() -> bool:
    """True while `shepherd.daemons.controld.build_master` is the ToolCallingMaster factory."""
    current: object = getattr(controld_module, PATCH_POINT)
    return current is build_tool_calling_master


@dataclass
class Inp:
    run: RunContext
    root: InstanceRoot
    running: controld_module.Controld
    book: ScriptBook
    port: int
    stop_outcome: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def client(self) -> Client:
        """A client that may POST /api/master/send: the master here is scripted."""
        if not patched():
            raise Blocked("build_master is not the ToolCallingMaster; refusing to allow a master send")
        return Client(self.port, refusals_log=self.run.port_refusals, allow_master_send=True)

    def subscribe(self, name: str) -> Subscriber:
        return subscribe(name, self.port)

    def send_turn(self, turn: Turn, text: str = "QA6 scripted turn") -> dict[str, object]:
        self.book.push(turn)
        return self.client.post("/api/master/send", {"text": text}).data()


def start_composition(run: RunContext) -> tuple[Inp, dict[str, str]]:
    root = mint_instance(run)
    seed_db(root, runner_socket=run.runner_socket(root.k))
    saved = dict(os.environ)
    env = sandbox_env(run, root, path_mode="shims")
    for name in list(os.environ):
        if name.startswith(("CLAUDE", "ANTHROPIC", "AI_AGENT", "TMUX")):
            del os.environ[name]
    os.environ.update(env)
    setattr(controld_module, PATCH_POINT, build_tool_calling_master)
    host = MacHost(environ={"HOME": str(root.home), "TMPDIR": str(root.tmpdir)})
    try:
        running = controld_module.start(host, 0)
    except BaseException as error:
        # Restore before raising (hunter L3): a sandboxed os.environ or a patched build_master left
        # behind would make the root settings guard compare the wrong path.
        setattr(controld_module, PATCH_POINT, _REAL_BUILD_MASTER)
        os.environ.clear()
        os.environ.update(saved)
        if isinstance(error, OSError):
            raise Blocked(f"INP controld.start failed: {error}") from error
        raise
    inp = Inp(run=run, root=root, running=running, book=BOOK, port=running.port)
    return inp, saved


def ready(inp: Inp) -> None:
    if not inp.running.control_socket_path.exists():
        raise Blocked("INP: the control socket does not exist after start()")
    await_env(lambda: inp.client.get("/api/fleet").status == 200 or None, 5.0, "INP /api/fleet")
    first = await_env(lambda: last_scan_at(inp.root.db_path), 5.0, "INP first scan")
    time.sleep(SCAN_INTERVAL_S)  # the two reads must be >= 2.0 s apart (§0 row 1)
    await_env(lambda: (v if (v := last_scan_at(inp.root.db_path)) and v > first else None), 6.0, "INP scan advancing")
    if not master_client.master_tools():
        raise Blocked("INP: the master's exported tool set is empty")
    stream = inp.subscribe("INP-ready")
    try:
        answer = inp.send_turn(Turn(says=READY_TURN))
        turn_id = answer.get("turn_id")
        await_env(lambda: any(f.kind == "master.turn_ended" and f.data.get("turn_id") == turn_id for f in stream.snapshot())
                  or None, 10.0, "INP no-op turn's master.turn_ended")
    finally:
        stream.close()
    inp.notes.append(f"INP ready on port {inp.port}, k={inp.root.k}")


def stop_composition(inp: Inp, saved: dict[str, str]) -> list[str]:
    problems: list[str] = []
    try:
        inp.stop_outcome = str(controld_module.stop(inp.running))
    finally:
        setattr(controld_module, PATCH_POINT, _REAL_BUILD_MASTER)
        os.environ.clear()
        os.environ.update(saved)
    if "did not exit" in (inp.stop_outcome or ""):
        problems.append(f"INP stop: {inp.stop_outcome}")
    if inp.running.control_socket_path.exists():
        problems.append("INP left its control socket")
    problems.extend(close_tmux_socket(inp.run, inp.run.runner_socket(inp.root.k)))
    return problems


def session(run: RunContext) -> Iterator[Inp]:
    """The body of each INP lane conftest's session-scoped `inp` fixture."""
    composition, saved = start_composition(run)
    try:
        ready(composition)
        yield composition
    finally:
        problems = stop_composition(composition, saved)
        for problem in problems:
            run.teardown_problem("INP", problem)
