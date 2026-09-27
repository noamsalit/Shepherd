"""D68 / ruling 1 (BC-05): the `shepherd` commands reach a running `controld`.

Seam: `cli.main.main(argv, out, err, host)` — the one every CLI test uses —
against a real `controld.start(host, 0)` over the `scripted_host` helper. The
daemon and the CLI share this interpreter, so they share its registry too; the
proof that an answer crossed the socket is therefore taken at the CLI's **own**
`invoke`: `shepherd.cli.commands.invoke` is replaced by a tripwire, and every
command below still answers. (The fall-back test is the reverse: no daemon, and
the local `invoke` is the one that answers.)

The audit rows are read off the daemon's real audit log, by correlation id.
"""

from __future__ import annotations

import io
import json
import socket
import threading
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from cli.conftest import register_tools, scripted_host
from project_fixture import the_project

from shepherd.cli import commands
from shepherd.cli.main import EXIT_OK, EXIT_USAGE, main
from shepherd.core.states import Origin, Ownership
from shepherd.daemons import controld
from shepherd.store.db import Store
from shepherd.testkit.scripted_host import ScriptedHost
from shepherd.toolsurface.audit import AUDIT_PREFIX
from shepherd.toolsurface.compose import LOGS_DIRNAME
from shepherd.toolsurface.rpc import RPC_SOCKET_NAME
from shepherd.toolsurface.types import CallerContext, ToolResult

CEILING_S = 5.0
CID = "c0ffee00c0ffee00c0ffee00c0ffee00"


@dataclass(frozen=True)
class Daemon:
    running: controld.Controld
    host: ScriptedHost
    data_dir: Path


@pytest.fixture()
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Daemon]:
    """A real `controld` on a scripted host under `tmp_path`, stopped in a `finally`."""
    engine_config = tmp_path / "engine-config"
    (engine_config / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(engine_config))  # never the real one
    data_dir = tmp_path / "data"
    host = scripted_host(runtime_dir=tmp_path / "run", data_dir=data_dir)
    running = controld.start(host, 0, engine_config_dir=engine_config)
    try:
        yield Daemon(running=running, host=host, data_dir=data_dir)
    finally:
        controld.stop(running)


@pytest.fixture()
def no_local_invoke(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The CLI's own `invoke`, replaced by a tripwire that records the name."""
    called: list[str] = []

    def tripwire(name: str, args: Mapping[str, object], ctx: CallerContext) -> ToolResult:
        called.append(name)
        raise AssertionError(f"the CLI invoked {name!r} locally beside a running daemon")

    monkeypatch.setattr(commands, "invoke", tripwire)
    return called


def run(argv: list[str], host: ScriptedHost) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, out=out, err=err, host=host, correlation_id=CID)
    return code, out.getvalue(), err.getvalue()


def audit_rows(data_dir: Path) -> list[dict[str, object]]:
    """This test's rows of the daemon's audit log (`<data>/logs/audit/<day>.jsonl`),
    in the order they were written."""
    rows: list[dict[str, object]] = []
    for path in sorted((data_dir / LOGS_DIRNAME / AUDIT_PREFIX).glob("*.jsonl")):
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                decoded = json.loads(line)
                if isinstance(decoded, dict) and decoded.get("correlation_id") == CID:
                    rows.append(decoded)
    return rows


def seed_session(store: Store, engine_session_id: str) -> str:
    return store.register_session(
        engine_session_id=engine_session_id,
        workspace_id=the_project(store),
        repo_id=None,
        cwd="/root/rpc",
        started_at="2026-09-27T10:00:00Z",
        origin=Origin.EXTERNAL,
        ownership=Ownership.ATTACHED,
    ).id


def test_status_reads_the_daemons_fleet_through_the_socket(
    daemon: Daemon, no_local_invoke: list[str]
) -> None:
    session_id = seed_session(daemon.running.store, "eng-rpc-1")

    code, out, err = run(["status"], daemon.host)

    assert code == EXIT_OK, err
    assert out.startswith("fleet: 1 sessions · "), out
    assert session_id in out
    assert err == ""
    assert no_local_invoke == []
    assert [(r["tool"], r["actor_kind"], r["actor_id"]) for r in audit_rows(daemon.data_dir)] == [
        ("fleet_summary", "human", "cli"),
        ("list_sessions", "human", "cli"),
    ]


def test_install_hooks_dry_run_and_yes_run_in_the_daemon(
    daemon: Daemon, no_local_invoke: list[str], tmp_path: Path
) -> None:
    target = tmp_path / "hooks" / "settings.json"
    target.parent.mkdir()

    dry = run(["install-hooks", "--settings", str(target), "--dry-run"], daemon.host)
    assert dry[0] == EXIT_OK, dry[2]
    assert "would install" in dry[1]
    assert "this run changed nothing. Pass --yes to apply it." in dry[1]
    assert not target.exists()

    applied = run(["install-hooks", "--settings", str(target), "--yes"], daemon.host)
    assert applied[0] == EXIT_OK, applied[2]
    assert "installed our dispatcher entry" in applied[1]
    assert "_shepherd_managed" in target.read_text(encoding="utf-8")
    assert (dry[2], applied[2]) == ("", "")
    assert no_local_invoke == []
    assert [(r["tool"], r["actor_kind"]) for r in audit_rows(daemon.data_dir)] == [
        ("install_hooks", "human"),
        ("install_hooks", "human"),
    ]


def test_uninstall_hooks_runs_in_the_daemon(
    daemon: Daemon, no_local_invoke: list[str], tmp_path: Path
) -> None:
    target = tmp_path / "hooks" / "settings.json"
    target.parent.mkdir()
    assert run(["install-hooks", "--settings", str(target), "--yes"], daemon.host)[0] == EXIT_OK
    installed = target.read_text(encoding="utf-8")
    before = len(audit_rows(daemon.data_dir))

    dry = run(["uninstall-hooks", "--settings", str(target), "--dry-run"], daemon.host)
    assert dry[0] == EXIT_OK, dry[2]
    assert "would remove" in dry[1]
    assert target.read_text(encoding="utf-8") == installed, "a dry run changed the file"

    removed = run(["uninstall-hooks", "--settings", str(target), "--yes"], daemon.host)
    assert removed[0] == EXIT_OK, removed[2]
    assert "removed" in removed[1]
    assert "_shepherd_managed" not in target.read_text(encoding="utf-8")
    assert no_local_invoke == []
    assert [(r["tool"], r["actor_kind"]) for r in audit_rows(daemon.data_dir)[before:]] == [
        ("inspect_hooks", "human"),
        ("uninstall_hooks", "human"),
    ]


def test_doctor_discovery_and_hooks_lines_come_from_the_daemon(
    daemon: Daemon, no_local_invoke: list[str], tmp_path: Path
) -> None:
    seed_session(daemon.running.store, "eng-rpc-doctor")
    target = tmp_path / "hooks" / "settings.json"
    target.parent.mkdir()
    target.write_text("{}", encoding="utf-8")

    code, out, err = run(["doctor", "--settings", str(target)], daemon.host)

    lines = {line.split(":", 1)[0]: line for line in out.splitlines() if ":" in line}
    assert code == EXIT_OK, (out, err)
    assert lines["discovery"].startswith("discovery: hooks "), lines["discovery"]
    assert lines["hooks"].startswith(f"hooks: not installed in {target}"), lines["hooks"]
    assert lines["fleet"].startswith("fleet: 1 sessions"), lines["fleet"]
    assert "schema version" in lines["database"] and "unknown" not in lines["database"]
    assert no_local_invoke == []
    called = {str(r["tool"]) for r in audit_rows(daemon.data_dir)}
    assert {"fleet_summary", "inspect_hooks", "schema_status", "engine_version"} <= called, called
    assert {(r["actor_kind"], r["actor_id"]) for r in audit_rows(daemon.data_dir)} == {("human", "cli")}


@pytest.mark.parametrize("command", ["replay", "recompute"])
def test_replay_and_recompute_run_in_the_daemon(
    daemon: Daemon, no_local_invoke: list[str], command: str
) -> None:
    code, out, err = run([command, "--since", "2026-09-17"], daemon.host)

    assert code == EXIT_OK, err
    assert "read 0 records" in out
    assert "did not answer" not in err and err == ""
    assert no_local_invoke == []
    assert [(r["tool"], r["actor_kind"]) for r in audit_rows(daemon.data_dir)] == [("replay", "human")]


def test_the_cli_falls_back_to_local_reads_with_no_daemon(
    store: Store, projects_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No socket file at all: `call_remote` says "no daemon" and the CLI's own
    `invoke` answers, exactly as it did before D68."""
    register_tools(store, projects_root)
    seed_session(store, "eng-local")
    seen: list[str] = []
    real = commands.invoke

    def spy(name: str, args: Mapping[str, object], ctx: CallerContext) -> ToolResult:
        seen.append(name)
        return real(name, args, ctx)

    monkeypatch.setattr(commands, "invoke", spy)
    host = scripted_host(runtime_dir=tmp_path / "run")
    assert not host.control_socket(RPC_SOCKET_NAME).path.exists()

    code, out, err = run(["status"], host)

    assert code == EXIT_OK, err
    assert out.startswith("fleet: 1 sessions")
    assert seen == ["fleet_summary", "list_sessions"]


def test_an_over_budget_rpc_path_is_no_daemon(
    store: Store, projects_root: Path, tmp_path: Path
) -> None:
    """E-QR-3: the seam refuses the path, and the CLI reads that as "no daemon"
    rather than failing a command that never needed the socket."""
    register_tools(store, projects_root)
    host = scripted_host(runtime_dir=tmp_path / ("r" * 120))

    code, out, err = run(["status"], host)

    assert code == EXIT_OK, err
    assert out.startswith("fleet: 0 sessions")


class ListenerDouble:
    """A socket at the RPC path that records every connect and answers each
    with one canned reply. Not a daemon: it proves what the CLI **sent**."""

    def __init__(self, path: Path, reply: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(path))
        self.listener.listen(8)
        self.listener.settimeout(0.05)
        self.reply = json.dumps(reply).encode("utf-8")
        self.requests: list[dict[str, object]] = []
        self.connects = 0
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stopping.is_set():
            try:
                conn, _ = self.listener.accept()
            except TimeoutError:
                continue
            with conn:
                self.connects += 1
                conn.settimeout(CEILING_S)
                chunks = []
                while chunk := conn.recv(65_536):
                    chunks.append(chunk)
                decoded = json.loads(b"".join(chunks))
                assert isinstance(decoded, dict)
                self.requests.append(decoded)
                conn.sendall(self.reply)

    def close(self) -> None:
        self.stopping.set()
        self.thread.join(CEILING_S)
        self.listener.close()


REPLAY_REPLY: Mapping[str, object] = {
    "v": 1,
    "ok": True,
    "data": {"read": 3, "reclassified": 1, "changed": 0, "changes": [], "applied": False},
    "error": None,
    "failure": None,
}


@pytest.fixture()
def listener_double(tmp_path: Path) -> Iterator[tuple[ListenerDouble, ScriptedHost]]:
    host = scripted_host(runtime_dir=tmp_path / "run")
    double = ListenerDouble(host.control_socket(RPC_SOCKET_NAME).path, REPLAY_REPLY)
    try:
        yield double, host
    finally:
        double.close()


@pytest.mark.parametrize("value", ["2026-13-45", "2026-02-30", "30d", "2026-9-17", "２０２６-09-17"])
def test_an_impossible_since_date_is_a_usage_error(
    listener_double: tuple[ListenerDouble, ScriptedHost], value: str
) -> None:
    """C5 / E-QR-19: refused in the CLI, before any call — no connect reaches
    the listener double, stdout stays empty, and stderr is the one sentence."""
    double, host = listener_double

    code, out, err = run(["replay", "--since", value], host)

    assert code == EXIT_USAGE
    assert out == ""
    assert err == f"shepherd: --since {value} is an invalid date (expected YYYY-MM-DD)\n", err
    assert double.connects == 0
    assert double.requests == []


def test_a_valid_since_date_is_forwarded(
    listener_double: tuple[ListenerDouble, ScriptedHost],
) -> None:
    double, host = listener_double

    code, out, err = run(["replay", "--since", "2026-09-17"], host)

    assert code == EXIT_OK, err
    assert "read 3 records" in out
    assert double.requests == [
        {"v": 1, "tool": "replay", "args": {"apply": False, "since": "2026-09-17"}, "correlation_id": CID}
    ]
