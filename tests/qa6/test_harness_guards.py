"""Harness guards (env-plan §4 step 1a) — not scenarios, and not optional.

The runner runs this file before any wave and stops the run if it fails:

* the two wait helpers yield `FAIL(bound)` and `BLOCKED` distinctly, and the
  recorder ranks FAIL over BLOCKED and refuses an empty scenario;
* the report gate refuses GREEN on a synthetic lane exit 1 without a verdict, a
  crashed lane, a teardown problem, a record count other than 161, and any
  BLOCKED — and says GREEN on the one clean synthetic run;
* the catalog reconciles with the plan (161 ids; wave sizes; tier split) and no
  scenario id is implemented twice or is not a plan id;
* the package names the forbidden port only in its refusal constant, offers no
  JS-synthesised user action outside a `js_*` function, and its conftest is
  import-inert; the default lane deselects qa6; `pytest-randomly` is refused;
* each of the five helpers copied from `tests/qa5` is re-proved: its proof
  passes on the copy, and fails naming the expected assertion when the inert
  mutation fixture `fixtures/mutations/<module>.json` is applied to a temp copy
  of the package (never to this tree, never imported here);
* **host safety (SI-1, INC-1)**: every env the harness builds for a child that
  carries the real HOME has no `XDG_*`, and every env carries
  `DISABLE_AUTOUPDATER=1` (`test_proof_host_safe_envs`, re-proved by three
  planted mutations of `sandbox.py`); no module builds such an env or execs the
  real engine outside the shared builders (`test_guard_no_ad_hoc_real_home_env`);
  the real-engine resolution order and the run-start link comparison hold
  (`test_proof_real_claude_resolution`).
"""

from __future__ import annotations

import ast
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import get_args

import pytest

from . import paths
from .catalog import BY_ID, SCENARIOS, wave_ids
from .sandbox import (
    HOST_SAFETY_ENV,
    REAL_HOME_SAFETY_ENV,
    TMP_CANONICAL,
    InstanceRoot,
    PathMode,
    RunContext,
    host_safety_problems,
    pytest_process_env,
    real_home_env,
    sandbox_env,
)
from .report import LaneExit, decide_status
from .verdict import Blocked, ProductFail, Recorder, Sourced, await_env, classify_blown_bound

pytestmark = pytest.mark.qa6

PACKAGE = paths.QA6_DIR
PLAN_WAVES = {1: 6, 2: 27, 3: 23, 4: 18, 5: 20, 6: 34, 7: 19, 8: 11, 9: 3}
PLAN_TIERS = {"integration": 8, "e2e_backend": 96, "ui": 57}


def package_files() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def mutation_log() -> Path:
    run_dir = os.environ.get("QA6_RUN_DIR")
    base = Path(run_dir) if run_dir else paths.DEFAULT_REPORT_DIR / "guards"
    base.mkdir(parents=True, exist_ok=True)
    return base / "mutations.jsonl"


# ----- wait helpers and the recorder ------------------------------------------------


def test_guard_wait_helpers_distinguish_fail_bound_from_blocked() -> None:
    assert isinstance(classify_blown_bound("x", Sourced(2.0, "scan cadence"), None), ProductFail)
    assert isinstance(classify_blown_bound("x", 5.0, 0.1), ProductFail), "5 s >= 10 x 0.1 s must be FAIL(bound)"
    assert isinstance(classify_blown_bound("x", 5.0, 1.0), Blocked), "5 s < 10 x 1.0 s must be BLOCKED"
    assert isinstance(classify_blown_bound("x", 5.0, None), Blocked), "no control must be BLOCKED"
    with pytest.raises(Blocked):
        await_env(lambda: None, 0.2, "never")
    assert await_env(lambda: 7, 0.2, "at once") == 7


def test_guard_recorder_ranks_fail_over_blocked_and_refuses_empty() -> None:
    both = Recorder("X")
    both.block("a", "unreachable")
    both.check("b", False, 1, 2)
    with pytest.raises(AssertionError) as raised:
        both.finish()
    assert not isinstance(raised.value, ProductFail)
    only_blocked = Recorder("Y")
    only_blocked.block("a", "unreachable")
    with pytest.raises(Blocked):
        only_blocked.finish()
    with pytest.raises(Blocked):
        Recorder("Z").finish()
    bound = Recorder("W")
    bound.fail_bound("c", "a frame", 10.0, "control 0.1 s")
    with pytest.raises(ProductFail):
        bound.finish()
    passing = Recorder("V")
    passing.check("ok", True, 1, 1)
    passing.finish()


# ----- the publish gate -----------------------------------------------------------------


def _records(verdicts: dict[str, str], lane: str = "sub-w1") -> list[dict[str, object]]:
    return [{"id": sid, "verdict": verdict, "lane_process": lane} for sid, verdict in verdicts.items()]


def test_guard_report_gate_green_only_when_everything_holds() -> None:
    planned = [s.id for s in SCENARIOS]
    clean = _records({sid: "PASS" for sid in planned})
    ok_exit = [LaneExit("sub", "1", 0, ())]
    assert decide_status(clean, ok_exit, [], planned).status == "GREEN"
    assert decide_status(clean, [LaneExit("sub", "1", 1, ())], [], planned).status == "INCOMPLETE", "exit 1 with no FAIL/BLOCKED"
    assert decide_status(clean, [LaneExit("sub", "1", 3, ())], [], planned).status == "INCOMPLETE", "a crashed lane"
    assert decide_status(clean, ok_exit, ["leak"], planned).status == "INCOMPLETE", "a teardown problem"
    assert decide_status(clean[:-1], ok_exit, [], planned).status == "INCOMPLETE", "160 records"
    blocked = _records({**{sid: "PASS" for sid in planned}, planned[0]: "BLOCKED"})
    assert decide_status(blocked, ok_exit, [], planned).status == "INCOMPLETE", "a BLOCKED"
    failed = _records({**{sid: "PASS" for sid in planned}, planned[1]: "FAIL"})
    assert decide_status(failed, [LaneExit("sub", "1", 1, ())], [], planned).status == "RED"
    duplicate: list[dict[str, object]] = [*clean, {"id": planned[0], "verdict": "PASS", "lane_process": "sub-w1"}]
    assert decide_status(duplicate, ok_exit, [], planned).status == "INCOMPLETE", "a duplicate record"


# ----- the catalog and the id set ---------------------------------------------------------


def test_guard_catalog_reconciles_with_the_plan() -> None:
    assert len(SCENARIOS) == 161 and len(BY_ID) == 161
    assert {wave: len(wave_ids(wave)) for wave in PLAN_WAVES} == PLAN_WAVES
    assert dict(Counter(s.tier for s in SCENARIOS)) == PLAN_TIERS


def implemented() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in package_files():
        if not path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
                        and decorator.func.id in ("scenario", "live_scenario") and decorator.args
                        and isinstance(decorator.args[0], ast.Constant)):
                    sid = str(decorator.args[0].value)
                    found.append((sid, f"{path.relative_to(PACKAGE)}::{node.name}"))
                    assert node.name.startswith(f"test_{sid.lower()}_"), (
                        f"{node.name} must be named test_{sid.lower()}_… (the runner's collection convention)"
                    )
    return found


def test_guard_every_scenario_id_is_planned_and_implemented_once() -> None:
    found = implemented()
    ids = [sid for sid, _where in found]
    unknown = sorted(set(ids) - set(BY_ID))
    duplicates = sorted(sid for sid, n in Counter(ids).items() if n > 1)
    assert not unknown, f"not test-plan ids: {unknown}"
    assert not duplicates, f"implemented more than once: {duplicates}"


def test_guard_modules_follow_the_lane_naming_convention() -> None:
    lanes = {"sub", "unit", "cli", "live", "inproc", "inproc_long", "host"}
    for path in package_files():
        if path.name.startswith("test_") and path.parent != PACKAGE:
            assert path.parent.name in lanes, f"{path} is not in a lane directory {sorted(lanes)}"
            assert re.match(r"^test_wave[1-9]_[A-Za-z0-9_]+\.py$", path.name), f"{path.name} must be test_wave<N>_<topic>.py"
            wave = int(path.name[len("test_wave")])
            for sid, where in implemented():
                if where.startswith(str(path.relative_to(PACKAGE))):
                    assert BY_ID[sid].wave == wave, f"{sid} is a wave-{BY_ID[sid].wave} scenario in {path.name}"


# ----- static hygiene ------------------------------------------------------------------------


def test_guard_forbidden_port_named_only_in_the_refusal_constant() -> None:
    allowed = {
        "paths.py": "FORBIDDEN_PORT, the refusal constant",
        "launch_controld.py": "the launcher's own refusal (it runs as a script outside the package)",
        "catalog.py": "the test plan's Z3 title, as data",
    }
    offenders: list[str] = []
    for path in package_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "8787" not in line:
                continue
            if path.name in allowed or path.name == "test_harness_guards.py":
                continue
            offenders.append(f"{path.relative_to(PACKAGE)}:{number}")
    assert not offenders, f"8787 spelled outside the refusal constant: {offenders}"


JS_USER_ACTION = re.compile(r"\.click\(|\.close\(|dispatchEvent|\.submit\(|\.focus\(")


def test_guard_no_js_synthesised_user_action_outside_js_functions() -> None:
    offenders: list[str] = []
    for path in package_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef) or function.name.startswith("js_"):
                continue
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("evaluate", "eval_on_selector", "eval_on_selector_all", "add_init_script")):
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and JS_USER_ACTION.search(arg.value):
                            offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno} in {function.name}")
    assert not offenders, f"JS user actions outside js_* functions: {offenders}"


def test_guard_shims_carry_no_signal_or_teardown_verb() -> None:
    for template in (PACKAGE / "shims").glob("*.sh.in"):
        text = template.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        for verb in ("kill", "pkill", "killall", "kill-server", "shutdown", "reboot"):
            assert not re.search(rf"\b{re.escape(verb)}\b", body), f"{template.name} carries {verb!r}"


def test_guard_conftest_is_import_inert() -> None:
    probe = (
        "import sys; sys.path.insert(0, 'tests'); import qa6.conftest, qa6.scenario, qa6.catalog, qa6.paths;"
        "import qa6.sandbox, qa6.verdict;"
        "sys.stdout.write(str(sorted(m for m in sys.modules if m.startswith('playwright') or m in ('qa6.bootstrap', 'qa6.browser'))))"
    )
    before = sorted(p.name for p in Path("/private/tmp").glob("shq6-*"))
    env = {key: value for key, value in os.environ.items() if not key.startswith("QA6_")}
    done = subprocess.run([sys.executable, "-c", probe], cwd=str(paths.REPO), env=env, capture_output=True, text=True,
                          timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[]", f"importing the conftest pulled in {done.stdout.strip()}"
    assert sorted(p.name for p in Path("/private/tmp").glob("shq6-*")) == before, "importing created a run root"


def _pytest(*args: str, randomly: bool = False) -> subprocess.CompletedProcess[str]:
    argv = [str(paths.PYTEST), *([] if randomly else ["-p", "no:randomly"]), "-p", "no:cacheprovider", *args]
    env = {key: value for key, value in os.environ.items() if not key.startswith("QA6_")}
    return subprocess.run(argv, cwd=str(paths.REPO), env=env, capture_output=True, text=True, timeout=180, check=False)


def test_guard_default_lane_deselects_qa6() -> None:
    # addopts already carries `-q`, so a bare `--collect-only` prints node ids.
    default = _pytest("--collect-only", "tests/qa6")
    selected = [line for line in default.stdout.splitlines() if "::test_" in line]
    assert selected == [] and "no tests collected" in default.stdout, f"the default lane collected qa6 items: {selected[:5]}"
    explicit = _pytest("--collect-only", "-m", "qa6 or qa6live", "tests/qa6")
    assert any("::test_" in line for line in explicit.stdout.splitlines()), explicit.stdout[-500:]


def test_guard_randomly_is_refused_for_qa6_items() -> None:
    done = _pytest("--collect-only", "-m", "qa6", "tests/qa6/test_harness_guards.py", randomly=True)
    assert done.returncode != 0 and "no:randomly" in (done.stdout + done.stderr), (done.returncode, done.stdout[-400:])


# ----- host safety (SI-1 / INC-1) --------------------------------------------------------------


def _guard_run() -> tuple[RunContext, InstanceRoot]:
    """A RunContext/InstanceRoot pair for pure env building: nothing is created on disk."""
    run = RunContext(pid=424242, run_id="qa6-guard", run0=TMP_CANONICAL / "shq6-424242-0",
                     run_dir=Path("/nonexistent-qa6-guard-run-dir"))
    return run, InstanceRoot(k=1, root=run.instance_root(1))


def host_env_builders() -> dict[str, tuple[bool, Callable[[], Mapping[str, str]]]]:
    """name -> (carries the real HOME?, builder) for every env the harness gives a child."""
    from .instance import launcher_env
    from .live.test_wave1_s0_auth_probe import probe_envs
    from .live.test_wave8_1_live import real_home_engine_env
    from .preflight import claude_probe_env

    run, root = _guard_run()
    builders: dict[str, tuple[bool, Callable[[], Mapping[str, str]]]] = {}
    def sandboxed(mode: PathMode) -> Callable[[], Mapping[str, str]]:
        return lambda: sandbox_env(run, root, path_mode=mode)

    for mode in get_args(PathMode):
        builders[f"sandbox_env[{mode}]"] = (False, sandboxed(mode))
    builders["sandbox.real_home_env"] = (True, lambda: real_home_env(run, root))
    builders["sandbox_env(home=REAL_HOME)"] = (True, lambda: sandbox_env(run, root, path_mode="live", home=paths.REAL_HOME,
                                                                         config_dir="unset"))
    builders["instance.launcher_env"] = (True, lambda: launcher_env(run, root))
    builders["S0 probe_envs[sandboxed]"] = (False, lambda: probe_envs(run, root)[0])
    builders["S0 probe_envs[real]"] = (True, lambda: probe_envs(run, root)[1])
    builders["wave8 real_home_engine_env"] = (True, lambda: real_home_engine_env(run, root))
    builders["preflight.claude_probe_env"] = (True, claude_probe_env)
    builders["sandbox.pytest_process_env (a real-HOME base carrying XDG_*)"] = (
        True, lambda: pytest_process_env({"HOME": str(paths.REAL_HOME), "PATH": "/usr/bin:/bin",
                                          "XDG_DATA_HOME": "/planted/xdg/data", "XDG_CONFIG_HOME": "/planted/xdg/cfg"}, {}))
    return builders


def test_proof_host_safe_envs() -> None:
    """SI-1: no real-HOME child env carries XDG_*; every child env carries DISABLE_AUTOUPDATER=1.

    Every sub-check is collected and named, so each planted mutation of
    `sandbox.py` (fixtures/mutations/sandbox_*.json) is seen to falsify the
    specific one it targets.
    """
    real = str(paths.REAL_HOME)
    problems: list[str] = []
    # The checker itself, on planted inputs (dicts only: nothing is executed).
    if not host_safety_problems({"HOME": real, "XDG_DATA_HOME": "/planted", **HOST_SAFETY_ENV, **REAL_HOME_SAFETY_ENV}):
        problems.append("proof_host_safe_envs.checker_flags_planted_xdg: a real-HOME env with XDG_DATA_HOME passed")
    if not host_safety_problems({"HOME": real + "/", "XDG_STATE_HOME": "/planted", **HOST_SAFETY_ENV, **REAL_HOME_SAFETY_ENV}):
        problems.append("proof_host_safe_envs.checker_flags_planted_xdg: the real HOME spelled with a trailing / passed")
    if not host_safety_problems({"HOME": "/private/tmp/shq6-1-1/home"}):
        problems.append("proof_host_safe_envs.checker_flags_missing_autoupdater: an env without DISABLE_AUTOUPDATER passed")
    if host_safety_problems({"HOME": "/private/tmp/shq6-1-1/home", "XDG_DATA_HOME": "/x", **HOST_SAFETY_ENV}):
        problems.append("proof_host_safe_envs.checker_allows_sandboxed_xdg: a sandboxed HOME with its own XDG was refused")
    # Every builder, checked independently of the checker.
    for name, (carries_real_home, build) in host_env_builders().items():
        try:
            env = dict(build())
        except ValueError as refused:
            problems.append(f"proof_host_safe_envs.builder_refused_its_own_env: {name}: {refused}")
            continue
        is_real = os.path.realpath(env.get("HOME", "")) == os.path.realpath(real)
        if is_real != carries_real_home:
            problems.append(f"proof_host_safe_envs.builder_home: {name}: HOME={env.get('HOME')!r}")
        if env.get("DISABLE_AUTOUPDATER") != "1":
            problems.append(f"proof_host_safe_envs.every_env_disables_autoupdater: {name}: "
                            f"DISABLE_AUTOUPDATER={env.get('DISABLE_AUTOUPDATER')!r}")
        xdg = sorted(key for key in env if key.startswith("XDG_"))
        if is_real and xdg:
            problems.append(f"proof_host_safe_envs.real_home_env_has_no_xdg: {name}: {xdg}")
        if is_real and env.get("DISABLE_INSTALLATION_CHECKS") != "1":
            problems.append(f"proof_host_safe_envs.real_home_env_disables_installation_checks: {name}")
    assert not problems, f"host-unsafe envs: {problems}"


def test_guard_no_ad_hoc_real_home_env() -> None:
    """Only sandbox.py spells XDG_* or passes home=REAL_HOME; nothing execs the user's claude link."""
    offenders: list[str] = []
    for path in package_files():
        if path.name == "test_harness_guards.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        where = str(path.relative_to(PACKAGE))
        for node in ast.walk(tree):
            if (where != "sandbox.py" and isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and re.fullmatch(r"XDG_[A-Z_]+", node.value)):
                offenders.append(f"{where}:{node.lineno} spells {node.value!r} (build envs with sandbox.py)")
            if (where != "sandbox.py" and isinstance(node, ast.keyword) and node.arg == "home"
                    and isinstance(node.value, ast.Attribute) and node.value.attr == "REAL_HOME"):
                offenders.append(f"{where}:{node.value.lineno} passes home=REAL_HOME (use sandbox.real_home_env)")
            if isinstance(node, ast.Attribute) and node.attr == "REAL_CLAUDE_BIN" and where not in ("paths.py", "realclaude.py"):
                if not _only_described(node, parents):
                    offenders.append(f"{where}:{node.lineno} uses REAL_CLAUDE_BIN outside a message (exec run.real_claude)")
    assert not offenders, f"ad-hoc real-HOME env or real-engine exec: {offenders}"


def _only_described(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """True when the node is only formatted into a message: an f-string or a logging call argument."""
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.JoinedStr, ast.FormattedValue)):
            return True
        if (isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute)
                and current.func.attr in ("debug", "info", "warning", "error")):
            return True
        if isinstance(current, (ast.stmt, ast.Call)):
            return False
        current = parents.get(current)
    return False


def test_proof_real_claude_resolution() -> None:
    """QA6_REAL_CLAUDE -> which -> newest versions/*; run-root targets refused; link compare vs START."""
    from . import realclaude

    with tempfile.TemporaryDirectory(prefix="qa6rc-", dir="/tmp") as scratch:
        base = Path(scratch)
        versions = base / "versions"
        versions.mkdir()
        for name in ("2.1.9", "2.1.281", "2.1.30", "notaversion"):
            engine = versions / name
            engine.write_text("#!/bin/sh\n", encoding="utf-8")
            engine.chmod(0o755)
        bindir = base / "bin"
        bindir.mkdir()
        empty = base / "empty"
        empty.mkdir()
        dangling = bindir / "claude"
        dangling.symlink_to(base / "gone" / "claude")
        fallback = realclaude.resolve({"PATH": str(bindir)}, versions)
        assert (fallback.source, fallback.path, fallback.inc1_fallback) == (
            "versions_fallback", os.path.realpath(versions / "2.1.281"), True), (
            f"proof_real_claude.newest_by_version_when_which_finds_nothing: {fallback}")
        dangling.unlink()
        dangling.symlink_to(versions / "2.1.9")
        which = realclaude.resolve({"PATH": f"{empty}:{bindir}"}, versions)
        assert (which.source, which.path) == ("which", os.path.realpath(versions / "2.1.9")), f"proof_real_claude.which_first: {which}"
        explicit = realclaude.resolve({"PATH": str(bindir), realclaude.ENV_REAL_CLAUDE: str(versions / "2.1.30")}, versions)
        assert (explicit.source, explicit.path) == (realclaude.ENV_REAL_CLAUDE, os.path.realpath(versions / "2.1.30")), (
            f"proof_real_claude.explicit_first: {explicit}")
        bad = realclaude.resolve({"PATH": str(bindir), realclaude.ENV_REAL_CLAUDE: str(base / "missing")}, versions)
        assert bad.path is None, f"proof_real_claude.explicit_never_guessed_past: {bad}"
    start = {"is_symlink": True, "target": "/private/tmp/shq6-9314-1/x", "resolved": "/private/tmp/shq6-9314-1/x", "exists": False}
    assert realclaude.compare(start, dict(start)) is None, "proof_real_claude.unchanged_dangling_link_is_not_a_change"
    moved = {**start, "target": "/elsewhere", "resolved": "/elsewhere", "exists": True}
    changed = realclaude.compare(start, moved)
    assert changed is not None and "ln -sfn" in changed, f"proof_real_claude.a_repair_or_repoint_is_a_change: {changed}"


def test_proof_pane_argv_effective_socket() -> None:
    """In-pane tmux calls are judged by the socket tmux would actually contact (-S, -L, else $TMUX)."""
    from .tmuxctl import effective_socket, pane_argv_violations

    pid = 424242
    ours = f"{paths.TMUX_SOCKET_DIR}/shepherd-m3-q6{pid}-3,12345,0"
    planted: list[dict[str, object]] = [
        {"argv": ["tmux", "display-message", "-p", "#{client_termtype}"], "tmux": ours},
        {"argv": ["tmux", "-L", "shepherd", "list-sessions"], "tmux": ours},
        {"argv": ["tmux", "show", "-gv", "focus-events"], "tmux": f"{paths.TMUX_SOCKET_DIR}/default,1,0"},
        {"argv": ["tmux", "-S", "/elsewhere/shepherd-m3-q6424242-3", "ls"], "tmux": ours},
        {"argv": ["tmux", "-V"], "tmux": ours},
    ]
    flagged = [entry["argv"] for entry in pane_argv_violations(planted, pid)]
    problems: list[str] = []
    if planted[0]["argv"] in flagged:
        problems.append("proof_pane_argv.allows_our_socket_via_TMUX")
    for index, label in ((1, "flags_user_socket_in_pane"), (2, "flags_default_via_TMUX"), (3, "flags_foreign_S_path")):
        if planted[index]["argv"] not in flagged:
            problems.append(f"proof_pane_argv.{label}")
    if effective_socket(["tmux", "-V"], None) is not None or effective_socket(["tmux", "ls"], None) != "default":
        problems.append("proof_pane_argv.version_contacts_nothing_and_bare_is_default")
    assert not problems, f"pane argv judgement: {problems}"


# ----- the proofs of the five copied qa5 helpers -----------------------------------------------


class _EventServer:
    """A one-connection SSE server: `: open`, one frame, one keep-alive, then holds."""

    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = int(self.listener.getsockname()[1])
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        connection, _ = self.listener.accept()
        with connection:
            connection.recv(65536)
            body = json.dumps({"seq": 7, "at": "t", "type": "project.created", "session_id": None,
                               "project_id": "P7", "data": {"x": 1}})
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n"
                + b": open\n\n" + f"id: 7\ndata: {body}\n\n".encode() + b": keep-alive\n\n"
            )
            while connection.recv(65536):
                pass

    def close(self) -> None:
        self.listener.close()
        self.thread.join(timeout=5)


def test_proof_sse_rig() -> None:
    from .sse_rig import Refusal, open_stream

    server = _EventServer()
    try:
        sub = open_stream("proof", server.port)
        assert not isinstance(sub, Refusal)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and (not sub.frames or len(sub.comments) < 2):
            time.sleep(0.02)
        frames, comments = sub.snapshot(), [c.text for c in sub.comment_snapshot()]
        sub.close()
    finally:
        server.close()
    assert [(f.seq, f.kind, f.project_id) for f in frames] == [(7, "project.created", "P7")], "proof_sse_rig.frame_parsed"
    assert sorted(frames[0].raw_fields) == ["data", "id"], "proof_sse_rig.fields_id_and_data"
    assert comments == [": open", ": keep-alive"], f"proof_sse_rig.comments_recorded: {comments}"
    assert sub.parse_failures == [], "proof_sse_rig.no_parse_failures"


def test_proof_auditprobe() -> None:
    from .auditprobe import AuditProbe

    with tempfile.TemporaryDirectory(prefix="qa6aud-", dir="/tmp") as scratch:
        root = Path(scratch) / "logs" / "audit"
        root.mkdir(parents=True)
        log = root / "2026-09-24.jsonl"
        log.write_text(json.dumps({"at": "a", "tool": "create_project"}) + "\n", encoding="utf-8")
        probe = AuditProbe(root=root)
        mark = probe.mark()
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": "b", "tool": "rename_project"}) + "\n")
            handle.write(json.dumps({"at": "c", "tool": "fleet_summary"}) + "\n")
        assert mark == 1, "proof_auditprobe.mark_counts_existing"
        assert probe.tools_since(mark) == ["rename_project", "fleet_summary"], (
            f"proof_auditprobe.since_mark_counts_new_records: {probe.tools_since(mark)}"
        )
        assert [r.get("tool") for r in probe.mutations_since(mark)] == ["rename_project"], "proof_auditprobe.mutations_only"


def test_proof_wsclient() -> None:
    from .wsclient import OP_BINARY, OP_CLOSE, decode

    small = bytes([0x80 | OP_BINARY, 5]) + b"hello"
    payload = b"x" * 300
    large = bytes([0x80 | OP_BINARY, 126]) + len(payload).to_bytes(2, "big") + payload
    close = bytes([0x80 | OP_CLOSE, 2]) + (1000).to_bytes(2, "big")
    frames = decode(small + large + close)
    assert frames[:1] == [(OP_BINARY, b"hello")], "proof_wsclient.decodes_short_frame"
    assert len(frames) == 3 and frames[1] == (OP_BINARY, payload), f"proof_wsclient.decodes_126_length_frame: {len(frames)}"
    assert frames[2] == (OP_CLOSE, (1000).to_bytes(2, "big")), "proof_wsclient.decodes_close"


def test_proof_constants() -> None:
    from .constants import load

    points = load()
    # Independent source: test-plan §1 "Codebase reality check" (app.css re-read at r2):
    # 600 → dialog.sheet; 760 → the shell and .panes2; 900 → Flock (.herd).
    assert (points.sheet, points.panes2, points.shell, points.herd) == (600, 760, 760, 900), (
        f"proof_constants.breakpoints_match_the_plan: {points}"
    )


def test_proof_tmuxctl() -> None:
    from .tmuxctl import _argv

    pid = 424242
    ours = f"shepherd-m3-q6{pid}-3"
    assert _argv(ours, pid, "list-sessions")[:3] == [str(paths.TMUX_BIN), "-L", ours], "proof_tmuxctl.builds_our_argv"
    for foreign in ("shepherd", "default", f"shepherd-m3-q6{pid + 1}-3", "shepherd-runner"):
        with pytest.raises(Blocked):
            _argv(foreign, pid, "list-sessions")
            raise AssertionError(f"proof_tmuxctl.refuses_the_user_socket: {foreign} accepted")
    for spelling in ("kill-server", "kill-serv", "kill-s"):
        with pytest.raises(Blocked):
            _argv(ours, pid, spelling)
    with pytest.raises(Blocked):
        _argv(ours, pid, "list-sessions", "-Lshepherd")
    assert _argv(ours, pid, "kill-server", allow_kill_server=True)[-1] == "kill-server", "proof_tmuxctl.backstop_on_ours"


# ----- the mutation drivers ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mutation_results() -> Iterator[list[dict[str, object]]]:
    results: list[dict[str, object]] = []
    yield results
    with open(mutation_log(), "a", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, sort_keys=True) + "\n")


@pytest.mark.parametrize("module", ["sse_rig", "auditprobe", "wsclient", "constants", "tmuxctl",
                                    "sandbox_xdg", "sandbox_checker", "sandbox_autoupdater", "tmuxctl_pane"])
def test_mutation_reproves_copied_module(module: str, mutation_results: list[dict[str, object]]) -> None:
    from .mutations import load_module_mutation, run_module_mutation

    mutation = load_module_mutation(module)
    clean_rc, clean_out, clean_cache = run_module_mutation(mutation, mutated=False)
    mutated_rc, mutated_out, mutated_cache = run_module_mutation(mutation, mutated=True)
    live = mutation.expect in mutated_out
    result: dict[str, object] = {
        "module": module, "targets": f"{mutation.proof} ({mutation.expect})", "file": mutation.file,
        "old": mutation.old, "new": mutation.new, "clean_rc": clean_rc, "mutated_rc": mutated_rc,
        "applied_evidence": mutated_out[-1200:], "failing_assertion": mutation.expect,
        "failing_lines": [line[:600] for line in mutated_out.splitlines() if mutation.expect in line][:3],
        "stale_pycache": clean_cache + mutated_cache,
        "outcome": "assertion_falsified" if clean_rc == 0 and mutated_rc not in (0, -1) and live else (
            "survived" if mutated_rc == 0 else "blocked"),
    }
    mutation_results.append(result)
    assert not clean_cache and not mutated_cache, "a __pycache__ existed in the temp copy (CLAUDE.md rule 4)"
    assert clean_rc == 0, f"{module}: the proof fails on the UNmutated copy: {clean_out[-800:]}"
    assert mutated_rc not in (0, -1), f"{module}: the mutation SURVIVED (proof passed on the mutated copy)"
    assert live, f"{module}: the proof failed, but not on {mutation.expect!r}: {mutated_out[-800:]}"
