"""T7b — the live-session registry scanner (Decision pressure 5).

Every fixture in this file is built from a **real capture** under
`docs/probes/2026-09-14-schemas/tmux-tui/run-20260914T154946Z/`; the captures are
read-only evidence and are never modified to make a test pass. The one live
assertion reads this host's real `~/.claude/sessions/*.json` and asserts only
that it parses — never a session count, which changes between runs.
"""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path

import pytest

from shepherd.engines.claude_code.registry import (
    AGENTS_ARGV,
    CLI_ENTRYPOINT,
    SDK_CLI_ENTRYPOINT,
    SESSIONS_DIRNAME,
    RegistryEntry,
    agents_json_fallback,
    is_attached_interactive,
    parse_sidecar,
    scan_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURES = (
    REPO_ROOT
    / "docs"
    / "probes"
    / "2026-09-14-schemas"
    / "tmux-tui"
    / "run-20260914T154946Z"
)
SRC_ROOT = REPO_ROOT / "src" / "shepherd"

#: The four captured sidecars of one real session, pid 4041880.
AFTER_TRUST = CAPTURES / "02-sidecar-after-trust.json"
IDLE = CAPTURES / "04-sidecar-idle.json"
PERMISSION = CAPTURES / "06-sidecar-permission.json"
RUNNING = CAPTURES / "07-sidecar-running.json"


def capture(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    return {str(key): value for key, value in decoded.items()}


def sessions_dir(root: Path) -> Path:
    directory = root / SESSIONS_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def write_sidecar(root: Path, fields: dict[str, object]) -> Path:
    path = sessions_dir(root) / f"{fields['pid']}.json"
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path


def test_parse_sidecar_reads_every_documented_field() -> None:
    """data-schemas §"Live-session registry `~/.claude/sessions/<pid>.json`"."""
    entry = parse_sidecar(PERMISSION.read_text(encoding="utf-8"))
    assert isinstance(entry, RegistryEntry)
    assert entry.pid == 4041880
    assert entry.session_id == "71757dd1-5375-4801-b467-7898a0bc1194"
    assert entry.cwd == "/tmp/shp-tui-A-4tvrx00n"
    assert entry.proc_start == "543824210"  # == /proc/<pid>/stat field 22 (E31)
    assert entry.version == "2.1.270"
    assert entry.kind == "interactive"
    assert entry.entrypoint == CLI_ENTRYPOINT
    assert entry.status == "waiting"
    assert entry.waiting_for == "permission prompt"
    assert entry.name == "shp-tui-a-4tvrx00n-00"
    assert entry.name_source == "derived"
    assert entry.started_at_ms == 1789401012996
    assert entry.status_updated_at_ms == 1789401085541
    assert entry.updated_at_ms == 1789401085541
    assert entry.tmux == "probe_a:@0.%0"
    assert entry.pid_domain is not None


def test_waiting_for_is_absent_unless_status_is_waiting() -> None:
    entry = parse_sidecar(RUNNING.read_text(encoding="utf-8"))
    assert isinstance(entry, RegistryEntry)
    assert entry.status == "busy"
    assert entry.waiting_for is None


def test_scan_registry_reads_a_directory_of_sidecars(tmp_path: Path) -> None:
    base = capture(IDLE)
    write_sidecar(tmp_path, base)
    other = dict(base)
    other["pid"] = 4041881
    other["sessionId"] = "22222222-5375-4801-b467-7898a0bc1194"
    write_sidecar(tmp_path, other)

    entries, anomalies = scan_registry(tmp_path)

    assert sorted(entry.pid for entry in entries) == [4041880, 4041881]
    assert anomalies == ()


def test_absent_sessions_directory_is_empty_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E29/P16: absence is "not running or not trusted", never a stop.

    A missing directory is the one place the `claude agents --json` fallback is
    consulted — so the subprocess is stubbed here rather than forking a real
    `claude` (E33: it is one-shot, and a test is not a timer either).
    """
    import subprocess

    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    entries, anomalies = scan_registry(tmp_path / "nothing-here")

    assert entries == []
    assert [anomaly.kind for anomaly in anomalies] == []
    assert calls == [list(AGENTS_ARGV)], "the one-shot fallback is the missing-dir branch"


def test_present_sessions_directory_never_forks_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E33/G11 — with sidecars on disk the fallback is not consulted at all."""
    import subprocess

    write_sidecar(tmp_path, capture(IDLE))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("scan_registry forked a process"),
    )
    entries, _ = scan_registry(tmp_path)
    assert [entry.pid for entry in entries] == [4041880]


def test_malformed_sidecar_is_counted(tmp_path: Path) -> None:
    """D25/principle 5 — a half-written file is counted, never raised."""
    write_sidecar(tmp_path, capture(IDLE))
    (sessions_dir(tmp_path) / "9999.json").write_text('{"pid": 9999, "ses', encoding="utf-8")

    entries, anomalies = scan_registry(tmp_path)

    assert [entry.pid for entry in entries] == [4041880]
    assert len(anomalies) == 1
    assert "9999.json" in anomalies[0].detail


def test_sdk_cli_entrypoint_is_skipped_by_the_predicate() -> None:
    """E35/probe Finding 1 — `kind` is `interactive` for `-p` too."""
    headless = capture(IDLE)
    headless["entrypoint"] = SDK_CLI_ENTRYPOINT
    entry = parse_sidecar(json.dumps(headless))
    assert isinstance(entry, RegistryEntry)

    assert entry.kind == "interactive"  # the field that would have lied
    assert is_attached_interactive(entry) is False
    interactive = parse_sidecar(IDLE.read_text(encoding="utf-8"))
    assert isinstance(interactive, RegistryEntry)
    assert is_attached_interactive(interactive) is True


def test_registry_never_opens_key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P15/E32 — the sibling `<pid>.<64hex>.key` holds a peer token."""
    write_sidecar(tmp_path, capture(IDLE))
    key = sessions_dir(tmp_path) / f"4041880.{'a' * 64}.key"
    key.write_text("peer-token", encoding="utf-8")

    opened: list[str] = []
    real_open = io.open

    def recording_open(file: object, *args: object, **kwargs: object) -> object:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr(io, "open", recording_open)
    entries, _ = scan_registry(tmp_path)
    monkeypatch.undo()

    assert [entry.pid for entry in entries] == [4041880]
    assert opened != [], "the reader was not instrumented"
    assert [path for path in opened if path.endswith(".key")] == []


def test_scan_makes_no_writes_under_claude_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_sidecar(tmp_path, capture(IDLE))
    modes: list[str] = []
    real_open = io.open

    def recording_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        modes.append(mode)
        return real_open(file, mode, *args, **kwargs)  # type: ignore[call-overload,no-any-return]

    monkeypatch.setattr(io, "open", recording_open)
    scan_registry(tmp_path)
    monkeypatch.undo()

    assert modes != []
    assert [mode for mode in modes if set(mode) & set("wxa+")] == []


def test_liveness_ignores_file_mtime(tmp_path: Path) -> None:
    """E30 — mtime is never an input; the scan does not read it at all."""
    path = write_sidecar(tmp_path, capture(IDLE))
    import os

    os.utime(path, (0, 0))

    entries, _ = scan_registry(tmp_path)

    assert [entry.pid for entry in entries] == [4041880]
    assert "mtime" not in registry_source()
    assert "st_mtime" not in registry_source()


def registry_source() -> str:
    return (SRC_ROOT / "engines" / "claude_code" / "registry.py").read_text(encoding="utf-8")


def calls_to(tree: ast.Module, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
    ]


def test_agents_json_is_one_shot_not_a_timer() -> None:
    """E33/G11 — mechanism, not adjective: one call site, inside the missing-dir branch."""
    call_sites = [
        (module, call)
        for module in sorted(SRC_ROOT.rglob("*.py"))
        for call in calls_to(ast.parse(module.read_text(encoding="utf-8")), "agents_json_fallback")
    ]
    assert len(call_sites) == 1, call_sites
    module, _ = call_sites[0]
    assert module.name == "registry.py"

    # (b) the one call site is lexically inside `scan_registry`.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    enclosing = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and calls_to(ast.Module(body=node.body, type_ignores=[]), "agents_json_fallback")
    ]
    assert enclosing == ["scan_registry"]

    # (c) the scan interval is named by exactly one module.
    owners = [
        module
        for module in sorted(SRC_ROOT.rglob("*.py"))
        if "REGISTRY_SCAN_INTERVAL_S" in module.read_text(encoding="utf-8")
    ]
    assert [module.name for module in owners] == ["discovery_loop.py"]


def test_agents_json_timeout_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    seen: list[object] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        seen.append(kwargs.get("timeout"))
        assert "shell" not in kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    entries, anomalies = agents_json_fallback(timeout_s=0.25)

    assert entries == []
    assert anomalies == ()
    assert isinstance(seen[0], list)
    assert seen[1] == 0.25


def test_agents_json_failure_is_counted_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def boom(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 0.25)

    monkeypatch.setattr(subprocess, "run", boom)
    entries, anomalies = agents_json_fallback(timeout_s=0.25)

    assert entries == []
    assert len(anomalies) == 1


@pytest.mark.live
def test_real_registry_parses() -> None:
    """Read-only, against this host's own registry. Never asserts a count."""
    home = Path.home() / ".claude"
    if not (home / SESSIONS_DIRNAME).is_dir():
        pytest.skip("no live registry on this host")
    entries, anomalies = scan_registry(home)
    for entry in entries:
        assert isinstance(entry.pid, int)
        assert isinstance(entry.session_id, str)
        assert isinstance(entry.proc_start, str)
        assert isinstance(entry.status, str)
    assert all(anomaly.detail for anomaly in anomalies)


def test_claude_config_dir_is_the_engines_dir_not_shepherds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The sidecars live under the **engine's** config dir, not `HostDirs.config_dir`.

    `HostDirs.config_dir` is Shepherd's own (`~/.config/shepherd`, ADR-2). Claude
    Code writes `sessions/<pid>.json` under `$CLAUDE_CONFIG_DIR` or `~/.claude`
    — scanning the wrong one finds nothing on the machine this task exists for.
    """
    from shepherd.engines.claude_code.registry import claude_config_dir

    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    assert claude_config_dir() == Path.home() / ".claude"

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "elsewhere"))
    assert claude_config_dir() == tmp_path / "elsewhere"
