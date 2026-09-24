"""The run's own preflight, T1 → T4 in tier order (env-plan §3, §4 step 1).

No tier begins until the previous one is fully green. Nothing here boots a
service: T4 is a type check, a collection, the harness guards, and a chromium
launch/close in a child process. Each check is `{tier, command, expected,
actual, result, classification}`; a missing prerequisite is BLOCKED for the
run, never a product verdict.

The settings-sha row is special: a mismatch **stops** the run (U2 names the
exact value; a different one means the user changed it, and that is not ours to
judge — env-plan §3).
"""

from __future__ import annotations

import os
import socket
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from shepherd.host.mac import MacHost

from . import hostprobe, paths, realclaude
from .catalog import BY_ID
from .sandbox import HOST_SAFETY_ENV, REAL_HOME_SAFETY_ENV, refuse_unsafe


@dataclass(frozen=True)
class Check:
    tier: str
    name: str
    command: str
    expected: str
    actual: str
    ok: bool
    classification: str = ""
    stop: bool = False

    def as_json(self) -> dict[str, object]:
        return {
            "tier": self.tier, "name": self.name, "command": self.command, "expected": self.expected,
            "actual": self.actual[:1500], "result": "pass" if self.ok else "fail",
            "classification": self.classification, "stop": self.stop,
        }


def claude_probe_env() -> dict[str, str]:
    """The env for `<real claude> --version`: real HOME, so no `XDG_*` and the SI-1 opt-outs."""
    env = {"HOME": str(paths.REAL_HOME), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8",
           **HOST_SAFETY_ENV, **REAL_HOME_SAFETY_ENV}
    refuse_unsafe(env, "the preflight claude probe env")
    return env


def _run(argv: list[str], timeout_s: float = 60.0, cwd: Path | None = None,
         env: Mapping[str, str] | None = None) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, check=False,
                              cwd=str(cwd) if cwd else None, env=dict(env) if env is not None else None)
    except (OSError, subprocess.TimeoutExpired) as error:
        return -1, f"{type(error).__name__}: {error}"
    return done.returncode, (done.stdout + done.stderr).strip()


def _exists(tier: str, name: str, path: Path, executable: bool = True) -> Check:
    ok = path.exists() and (not executable or path.stat().st_mode & 0o111 != 0)
    return Check(tier, name, f"test -{'x' if executable else 'e'} {path}", "present", "present" if ok else "absent",
                 ok, "" if ok else "missing-input")


def tier1() -> list[Check]:
    checks: list[Check] = []
    rc, out = _run([str(paths.GIT_BIN), "-C", str(paths.REPO), "rev-parse", "--abbrev-ref", "HEAD"], 10)
    checks.append(Check("T1", "branch", "git rev-parse --abbrev-ref HEAD", "qa/round6-full", out, rc == 0 and out == "qa/round6-full", "wrong-guess"))
    rc, out = _run([str(paths.GIT_BIN), "-C", str(paths.REPO), "merge-base", "--is-ancestor", "dc913fc", "HEAD"], 10)
    checks.append(Check("T1", "descends from dc913fc", "git merge-base --is-ancestor dc913fc HEAD", "exit 0", f"exit {rc}", rc == 0, "wrong-guess"))
    rc, out = _run([str(paths.PYTHON), "-c", "import sys, shepherd, playwright.sync_api; sys.stdout.write(shepherd.__file__)"], 30)
    checks.append(Check("T1", "venv imports", ".venv/bin/python -c 'import shepherd, playwright.sync_api'",
                        "src/shepherd", out, rc == 0 and "src/shepherd" in out, "missing-input"))
    for name, path in (("controld", paths.CONTROLD_BIN), ("sessiond", paths.SESSIOND_BIN), ("cli", paths.SHEPHERD_BIN),
                       ("pytest", paths.PYTEST), ("mypy", paths.VENV_BIN / "mypy"), ("tmux", paths.TMUX_BIN),
                       ("perl", paths.PERL_BIN), ("nc", paths.NC_BIN), ("lsof", paths.LSOF_BIN), ("ps", paths.PS_BIN),
                       ("git", paths.GIT_BIN)):
        checks.append(_exists("T1", name, path))
    checks.append(real_claude_check(realclaude.resolve(os.environ)))
    shell = paths.BROWSERS_PATH / "chromium_headless_shell-1243"
    checks.append(_exists("T1", "chromium-headless-shell 1243", shell, executable=False))
    for probe in (paths.PROMPT_READY_FRAME, paths.DIALOG_CAPTURE, paths.SIDECAR_CAPTURE, paths.HOOKS_LIVE / "S01_startup_tools" / "events.jsonl"):
        checks.append(_exists("T1", f"probe {probe.name}", probe, executable=False))
    sha = hostprobe.sha256(paths.REAL_SETTINGS)
    ok = sha == paths.EXPECTED_SETTINGS_SHA
    checks.append(Check("T1", "real settings sha (U2)", f"shasum -a 256 {paths.REAL_SETTINGS}", paths.EXPECTED_SETTINGS_SHA,
                        sha, ok, "" if ok else "missing-input", stop=not ok))
    budget_path = MacHost(environ={"HOME": "/tmp/x", "TMPDIR": "/private/tmp/shq6-99999999-999/t"}).control_socket("controld").path
    size = len(str(budget_path).encode())
    checks.append(Check("T1", "socket budget", "MacHost(environ).control_socket('controld')", "<= 103 bytes",
                        f"{size} bytes: {budget_path}", size <= 103, "wrong-guess"))
    return checks


def real_claude_check(resolution: realclaude.Resolution) -> Check:
    """T1: the real engine resolves (QA6_REAL_CLAUDE → which → newest versions/*; INC-1 noted)."""
    actual = f"{resolution.path} via {resolution.source}: {resolution.why}"
    return Check("T1", "real claude resolves", "realclaude.resolve(os.environ)",
                 "an executable outside every run root (the source and why are recorded)",
                 actual, resolution.path is not None, "" if resolution.path is not None else "missing-input")


def tier2() -> list[Check]:
    checks: list[Check] = []
    rc, out = _run([str(paths.TMUX_BIN), "-V"], 10)
    checks.append(Check("T2", "tmux -V", "/opt/homebrew/bin/tmux -V", "tmux 3.6a", out, rc == 0 and out.startswith("tmux "), "missing-input"))
    engine = realclaude.resolve(os.environ).path
    if engine is None:
        rc, out = -1, "no real claude resolved (T1)"
    else:
        rc, out = _run([engine, "--version"], 20, env=claude_probe_env())
    checks.append(Check("T2", "claude --version (recorded)", f"{engine} --version (real HOME, no XDG_*, DISABLE_AUTOUPDATER=1)",
                        "a version (recorded)", out, rc == 0, "missing-input"))
    rc, out = _run([str(paths.GIT_BIN), "--version"], 5)
    checks.append(Check("T2", "git without CLT prompt", "/usr/bin/git --version", "exit 0 in 5 s", out, rc == 0, "missing-input"))
    rc, out = _run([str(paths.PERL_BIN), "-MTime::HiRes", "-e1"], 10)
    checks.append(Check("T2", "perl Time::HiRes", "perl -MTime::HiRes -e1", "exit 0", f"exit {rc} {out}", rc == 0, "missing-input"))
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))
        bound = probe.getsockname()[1]
    finally:
        probe.close()
    checks.append(Check("T2", "loopback ephemeral bind", "bind(127.0.0.1, 0)", "a port", str(bound), bound > 0))
    owners = hostprobe.port_listener_pids(paths.FORBIDDEN_PORT)
    checks.append(Check("T2", f"port {paths.FORBIDDEN_PORT} owner (recorded)", f"lsof -nP -iTCP:{paths.FORBIDDEN_PORT} -sTCP:LISTEN -t", "recorded", str(owners), True))
    return checks


def tier3() -> list[Check]:
    try:
        connection = socket.create_connection(("api.anthropic.com", 443), timeout=5)
        connection.close()
        actual, ok = "connected", True
    except OSError as error:
        actual, ok = f"{error!r}", False
    # Recorded, not gating: S0 decides what it means (env-plan §3).
    return [Check("T3", "api.anthropic.com:443 (recorded)", "create_connection(api.anthropic.com:443, 5s)", "recorded", actual, True,
                  "" if ok else "missing-input")]


def tier4(collect_only: Callable[[], tuple[int, str]] | None = None) -> list[Check]:
    checks: list[Check] = []
    rc, out = _run([str(paths.VENV_BIN / "mypy"), "--strict", "tests/qa6"], 300, cwd=paths.REPO)
    checks.append(Check("T4", "mypy --strict tests/qa6", ".venv/bin/mypy --strict tests/qa6", "Success", out[-1500:], rc == 0, "defect"))
    rc, out = _run([str(paths.PYTEST), "--collect-only", "-m", "qa6 or qa6live", "tests/qa6", "-p", "no:randomly",
                    "-p", "no:cacheprovider"], 120, cwd=paths.REPO)
    unknown, duplicates, found = collected_ids(out)
    ok = rc == 0 and not unknown and not duplicates
    checks.append(Check("T4", "collection", "pytest --collect-only -m 'qa6 or qa6live' tests/qa6 (addopts supplies -q)",
                        "exit 0; every scenario id a plan id, each at most once",
                        f"exit {rc}; {len(found)} scenario ids; unknown={unknown}; duplicates={duplicates}", ok, "defect"))
    rc, out = _run([str(paths.PYTHON), "-c",
                    "from playwright.sync_api import sync_playwright\n"
                    "import sys\n"
                    "p=sync_playwright().start(); b=p.chromium.launch(headless=True); v=b.version; b.close(); p.stop()\n"
                    "sys.stdout.write(v)"],
                   120)
    checks.append(Check("T4", "chromium launch/close", "python -c 'sync_playwright … launch; close'", "a version", out[-300:], rc == 0 and bool(out), "missing-input"))
    return checks


def collected_ids(output: str) -> tuple[list[str], list[str], list[str]]:
    """From `--collect-only -q` node ids, the scenario ids by the `test_<id>_` name convention."""
    import re

    found: list[str] = []
    for line in output.splitlines():
        match = re.search(r"::test_([a-z]+\d+)_", line)
        if match:
            found.append(match.group(1).upper())
    unknown = sorted({sid for sid in found if sid not in BY_ID})
    seen: dict[str, int] = {}
    for sid in found:
        seen[sid] = seen.get(sid, 0) + 1
    duplicates = sorted(sid for sid, count in seen.items() if count > 1)
    return unknown, duplicates, found


def run_tiers(include_t4: bool = True) -> tuple[list[Check], str]:
    """Run T1..T4 in order; stop at the first tier with a failure. Returns (checks, highest tier)."""
    done: list[Check] = []
    reached = "T0"
    tiers: list[tuple[str, Callable[[], list[Check]]]] = [("T1", tier1), ("T2", tier2), ("T3", tier3)]
    if include_t4:
        tiers.append(("T4", tier4))
    for name, tier in tiers:
        results = tier()
        done.extend(results)
        reached = name
        if not all(check.ok for check in results):
            break
    return done, reached
