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


TEST_PLAN = paths.DEFAULT_REPORT_DIR.parent / "test-plan.md"
HEADING = re.compile(r"^### ([A-Z]\d+) — (.+)$")
TIER_LINE = re.compile(r"^\*\*Tier:\*\* (\S+) ·")
WAVE_ROW = re.compile(r"^\| (\d) \| (.+?) — \*\*(\d+)\*\*")


def _expand(cell: str) -> list[str]:
    """`C1–C3, C5` → [C1, C2, C3, C5] (the §3 table's own range spelling)."""
    found: list[str] = []
    for token in (t.strip() for t in cell.split(",")):
        match = re.fullmatch(r"([A-Z])(\d+)–([A-Z])(\d+)", token)
        if match and match.group(1) == match.group(3):
            found.extend(f"{match.group(1)}{i}" for i in range(int(match.group(2)), int(match.group(4)) + 1))
        elif re.fullmatch(r"[A-Z]\d+", token):
            found.append(token)
        else:
            raise AssertionError(f"unreadable §3 scenario token {token!r} in {cell!r}")
    return found


def parse_plan(text: str) -> tuple[list[str], dict[str, str], dict[str, int], dict[int, int]]:
    """(§4 heading ids in order, id → tier, id → wave from §3, wave → the §3 bold total)."""
    section4 = text[text.index("\n## 4. Scenarios"):text.index("\n## 5. ")]
    ids: list[str] = []
    tiers: dict[str, str] = {}
    current: str | None = None
    for line in section4.splitlines():
        heading = HEADING.match(line)
        if heading:
            current = heading.group(1)
            ids.append(current)
            continue
        tier = TIER_LINE.match(line)
        if tier and current is not None and current not in tiers:
            tiers[current] = tier.group(1)
    section3 = text[text.index("\n## 3. Build order"):text.index("\n## 4. Scenarios")]
    waves: dict[str, int] = {}
    totals: dict[int, int] = {}
    for line in section3.splitlines():
        row = WAVE_ROW.match(line)
        if row:
            wave = int(row.group(1))
            totals[wave] = int(row.group(3))
            for sid in _expand(row.group(2)):
                waves[sid] = wave
    return ids, tiers, waves, totals


def test_guard_catalog_reconciles_with_the_plan() -> None:
    """The catalog is pinned against the plan DOCUMENT, parsed (review 8), not constants typed in here."""
    assert TEST_PLAN.exists(), f"{TEST_PLAN} is missing: the catalog cannot be reconciled with its plan"
    ids, tiers, waves, totals = parse_plan(TEST_PLAN.read_text(encoding="utf-8"))
    assert len(ids) == len(set(ids)) == 161 == len(SCENARIOS), f"§4 headings: {len(ids)} ({len(set(ids))} distinct)"
    assert sorted(s.id for s in SCENARIOS) == sorted(ids), "catalog ids != the §4 headings"
    assert {s.id: s.tier for s in SCENARIOS} == tiers, "catalog tiers != the §4 Tier lines"
    assert {s.id: s.wave for s in SCENARIOS} == waves, "catalog waves != the §3 build-order table"
    assert {wave: len(wave_ids(wave)) for wave in totals} == totals, f"wave sizes != the §3 totals {totals}"
    assert sum(totals.values()) == 161 and dict(Counter(s.tier for s in SCENARIOS)) == PLAN_TIERS


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


JS_USER_ACTION = re.compile(
    r"\.click\(|\.close\(|dispatchEvent|\.submit\(|\.requestSubmit\(|\.focus\(|"
    r"\.open\s*=\s*(false|true)|removeAttribute\(\s*['\"]open|setAttribute\(\s*['\"]open"
)
EVAL_ATTRS = ("evaluate", "evaluate_handle", "eval_on_selector", "eval_on_selector_all", "add_init_script")
#: Playwright calls that synthesise an event without real input.
SYNTHETIC_EVENT_ATTRS = ("dispatch_event",)


def _string_parts(node: ast.AST) -> list[str]:
    """The literal text of a string expression: a constant, an f-string's constant parts, a concatenation."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return ["".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _string_parts(node.left) + _string_parts(node.right)
    return []


def _assigned_strings(scope: ast.AST, name: str) -> list[str]:
    """Every string literal assigned to `name` anywhere in `scope` (a function or the module)."""
    found: list[str] = []
    for node in ast.walk(scope):
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is not None and any(isinstance(t, ast.Name) and t.id == name for t in targets):
            found.extend(_string_parts(value))
    return found


def _enclosing_function(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parents.get(current)
    return None


def js_action_offenders(tree: ast.Module, where: str) -> list[str]:
    """Review finding 8: JS-synthesised user actions anywhere in a module (module level, async
    def, lambdas), whether the script is a literal, an f-string, a concatenation or a name
    bound to one; plus Playwright's `dispatch_event`. Only a `js_*` function may hold one."""
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        function = _enclosing_function(node, parents)
        if function is not None and function.name.startswith("js_"):
            continue
        label = f"{where}:{node.lineno} in {function.name if function else '<module>'}"
        if node.func.attr in SYNTHETIC_EVENT_ATTRS:
            offenders.append(f"{label}: {node.func.attr}()")
            continue
        if node.func.attr not in EVAL_ATTRS:
            continue
        for arg in [*node.args, *(k.value for k in node.keywords)]:
            texts = _string_parts(arg)
            if isinstance(arg, ast.Name):
                texts = _assigned_strings(function, arg.id) if function is not None else []
                texts += _assigned_strings(tree, arg.id)
            if any(JS_USER_ACTION.search(text) for text in texts):
                offenders.append(label)
    return offenders


def test_guard_no_js_synthesised_user_action_outside_js_functions() -> None:
    offenders: list[str] = []
    for path in package_files():
        if path.name == "test_harness_guards.py":
            continue
        offenders.extend(js_action_offenders(ast.parse(path.read_text(encoding="utf-8")), str(path.relative_to(PACKAGE))))
    assert not offenders, f"JS user actions outside js_* functions: {offenders}"


def test_proof_js_action_guard_sees_every_spelling() -> None:
    """The guard itself, on planted sources (parsed, never run): each spelling review 8 named is caught."""
    planted = {
        "variable": "def f(page):\n    script = 'el => el.click()'\n    page.evaluate(script)\n",
        "fstring": "def f(page, x):\n    page.evaluate(f'document.querySelector({x}).click()')\n",
        "async": "async def f(page):\n    await page.evaluate('d => d.requestSubmit()')\n",
        "module_level": "page.evaluate(\"d => d.removeAttribute('open')\")\n",
        "lambda": "g = lambda page: page.evaluate('d => d.open = false')\n",
        "dispatch_event": "def f(locator):\n    locator.dispatch_event('click')\n",
        "module_constant": "SCRIPT = 'el => el.focus()'\ndef f(page):\n    page.evaluate(SCRIPT)\n",
    }
    missed = [name for name, source in planted.items() if not js_action_offenders(ast.parse(source), name)]
    allowed = "def js_open(page):\n    page.evaluate('d => d.click()')\ndef f(page):\n    page.evaluate('d => d.open === true')\n"
    assert not missed, f"proof_js_guard.catches_every_spelling: missed {missed}"
    assert not js_action_offenders(ast.parse(allowed), "allowed"), "proof_js_guard.allows_js_functions_and_reads"


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
    """tmux argv are judged by the socket tmux would actually contact (tmux 3.6a's getopt rules).

    Pure: every argv below is data handed to a predicate; nothing is executed.
    The four `reviewer_*` rows are the harness review's finding 1, each of which
    the first-`-L`-wins parser scored clean while real tmux reaches `default` or
    `shepherd` (confirmed against tmux 3.6a with made-up socket names).
    """
    from .tmuxctl import effective_socket, pane_argv_violations, product_argv_violations

    pid = 424242
    ours = f"shepherd-m3-q6{pid}-3"
    ours_env = f"{paths.TMUX_SOCKET_DIR}/{ours},12345,0"
    default_path = f"{paths.TMUX_SOCKET_DIR}/default"
    planted: list[dict[str, object]] = [
        {"argv": ["tmux", "display-message", "-p", "#{client_termtype}"], "tmux": ours_env},
        {"argv": ["tmux", "-L", "shepherd", "list-sessions"], "tmux": ours_env},
        {"argv": ["tmux", "show", "-gv", "focus-events"], "tmux": f"{paths.TMUX_SOCKET_DIR}/default,1,0"},
        {"argv": ["tmux", "-S", "/elsewhere/shepherd-m3-q6424242-3", "ls"], "tmux": ours_env},
        {"argv": ["tmux", "-V"], "tmux": ours_env},
    ]
    flagged = [entry["argv"] for entry in pane_argv_violations(planted, pid)]
    problems: list[str] = []
    if planted[0]["argv"] in flagged or planted[4]["argv"] in flagged:
        problems.append("proof_pane_argv.allows_our_socket_via_TMUX")
    for index, label in ((1, "flags_user_socket_in_pane"), (2, "flags_default_via_TMUX"), (3, "flags_foreign_S_path")):
        if planted[index]["argv"] not in flagged:
            problems.append(f"proof_pane_argv.{label}")
    if effective_socket(["tmux", "-V"], None) is not None or effective_socket(["tmux", "ls"], None) != "default":
        problems.append("proof_pane_argv.version_contacts_nothing_and_bare_is_default")
    reviewer = {
        "reviewer_S_beats_L": (["tmux", "-L", ours, "-S", default_path, "kill-server"], "default"),
        "reviewer_last_L_wins": (["tmux", "-L", ours, "-L", "default", "kill-server"], "default"),
        "reviewer_clustered_uL": (["tmux", "-uL", "default", "kill-server"], "default"),
        "reviewer_clustered_2uL": (["tmux", "-2uL", "shepherd", "ls"], "shepherd"),
    }
    for label, (argv, reached) in reviewer.items():
        if effective_socket(argv, ours_env) != reached:
            problems.append(f"proof_pane_argv.{label}: reaches {effective_socket(argv, ours_env)!r}, tmux reaches {reached!r}")
        if argv not in [entry["argv"] for entry in pane_argv_violations([{"argv": argv, "tmux": ours_env}], pid)]:
            problems.append(f"proof_pane_argv.{label}_flagged_in_pane")
        if product_argv_violations([argv], pid) != [argv]:
            problems.append(f"proof_pane_argv.{label}_flagged_as_product_argv")
    allowed = {
        "ours_plain": ["tmux", "-L", ours, "ls"],
        "ours_clustered": ["tmux", "-uL", ours, "ls"],
        "ours_fused": ["tmux", f"-L{ours}", "ls"],
        "ours_after_a_foreign_L": ["tmux", "-L", "default", "-L", ours, "ls"],
        "ours_S_beats_a_foreign_L": ["tmux", "-L", "shepherd", "-S", f"{paths.TMUX_SOCKET_DIR}/{ours}", "ls"],
        "ours_after_a_valued_global": ["tmux", "-f", "/dev/null", "-L", ours, "ls"],
    }
    for label, argv in allowed.items():
        if product_argv_violations([argv], pid):
            problems.append(f"proof_pane_argv.allows_{label}")
    refused = {
        "valued_global_eats_L": ["tmux", "-f", "-L", ours, "ls"],
        "double_dash_stops_options": ["tmux", "--", "-L", ours],
        "missing_value": ["tmux", "-L"],
        "unknown_option": ["tmux", "-Z", "-L", ours, "ls"],
        "no_server_but_not_plain_V": ["tmux", "-uV"],
    }
    for label, argv in refused.items():
        if product_argv_violations([argv], pid) != [argv]:
            problems.append(f"proof_pane_argv.refuses_{label}")
    assert not problems, f"tmux argv judgement: {problems}"


#: Fake `tmux` for the shim proof: records that it was exec'd and its argv, and does nothing else.
_FAKE_TMUX = """#!/bin/sh
printf 'EXEC' >> "$(dirname "$0")/exec.log"
for word in "$@"; do printf ' %s' "$word" >> "$(dirname "$0")/exec.log"; done
printf '\n' >> "$(dirname "$0")/exec.log"
"""


def test_proof_tmux_shim_refuses() -> None:
    """The rendered logging shim agrees with `tmuxctl.argv_violation`, refuses (97, no exec), logs
    every call, and fails CLOSED (98, no exec) when it cannot log.

    Run against a FAKE binary rendered into the shim's `@TMUX@`: nothing here can
    reach a tmux server, and the argv use only `ls` / `display-message` (no
    teardown verb is ever executed, CLAUDE.md mutation rule 3 — the kill-server
    shapes are proved by predicate in `test_proof_pane_argv_effective_socket`).
    """
    from .shims import tmux_shim_text
    from .tmuxctl import argv_violation

    pid = 424242
    ours = f"shepherd-m3-q6{pid}-3"
    ours_env = f"{paths.TMUX_SOCKET_DIR}/{ours},12345,0"
    battery: list[tuple[str, list[str], str | None]] = [
        ("plain_ours", ["-L", ours, "ls"], None),
        ("clustered_ours", ["-uL", ours, "ls"], None),
        ("fused_ours", [f"-L{ours}", "ls"], None),
        ("last_L_ours", ["-L", "default", "-L", ours, "ls"], None),
        ("S_beats_L_ours", ["-L", "shepherd", "-S", f"{paths.TMUX_SOCKET_DIR}/{ours}", "ls"], None),
        ("version", ["-V"], None),
        ("pane_ours_via_TMUX", ["display-message", "-p", "x"], ours_env),
        ("S_beats_L_default", ["-L", ours, "-S", f"{paths.TMUX_SOCKET_DIR}/default", "ls"], None),
        ("last_L_default", ["-L", ours, "-L", "default", "ls"], None),
        ("clustered_uL_default", ["-uL", "default", "ls"], None),
        ("clustered_2uL_shepherd", ["-2uL", "shepherd", "ls"], None),
        ("bare_default", ["ls"], None),
        ("pane_default_via_TMUX", ["display-message", "-p", "x"], f"{paths.TMUX_SOCKET_DIR}/default,1,0"),
        ("pane_user_socket_by_L", ["-L", "shepherd", "ls"], ours_env),
        ("valued_global_eats_L", ["-f", "-L", ours, "ls"], None),
        ("double_dash", ["--", "-L", ours], None),
        ("missing_value", ["-L"], None),
        ("unknown_option", ["-Z", "-L", ours, "ls"], None),
        ("no_server_not_plain_V", ["-uV"], None),
        ("foreign_S_path", ["-S", f"/elsewhere/{ours}", "ls"], None),
    ]
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qa6shim-", dir="/tmp") as scratch:
        base = Path(scratch)
        fake = base / "fake-tmux"
        fake.write_text(_FAKE_TMUX, encoding="utf-8")
        fake.chmod(0o755)
        product_log, pane_log, exec_log = base / "tmux-argv.log", base / "pane-tmux-argv.log", base / "exec.log"
        text = tmux_shim_text(pid, product_log, pane_log, fake)
        assert str(paths.TMUX_BIN) not in text, "the proof shim must exec the fake binary, never the real tmux"
        shim = base / "tmux"
        shim.write_text(text, encoding="utf-8")
        shim.chmod(0o755)
        for label, words, tmux_env in battery:
            env = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8", **({"TMUX": tmux_env} if tmux_env else {})}
            before = exec_log.read_text(encoding="utf-8") if exec_log.exists() else ""
            logs_before = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in (product_log, pane_log) if p.exists())
            done = subprocess.run([str(shim), *words], env=env, capture_output=True, text=True, timeout=15, check=False)
            after = exec_log.read_text(encoding="utf-8") if exec_log.exists() else ""
            logs_after = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in (product_log, pane_log) if p.exists())
            execed = after != before
            python_allows = argv_violation(["tmux", *words], tmux_env, pid) is None
            if logs_after != logs_before + 1:
                problems.append(f"proof_tmux_shim.logs_every_call: {label} added {logs_after - logs_before} line(s)")
            if python_allows and not (done.returncode == 0 and execed and after.endswith(" ".join(["EXEC", *words]) + "\n")):
                problems.append(f"proof_tmux_shim.execs_allowed_unchanged: {label}: rc={done.returncode} err={done.stderr!r}")
            if not python_allows and (done.returncode != 97 or execed or "refused" not in done.stderr):
                problems.append(f"proof_tmux_shim.refuses_without_exec: {label}: rc={done.returncode} execed={execed} "
                                f"err={done.stderr!r}")
        pane_lines = pane_log.read_text(encoding="utf-8").splitlines() if pane_log.exists() else []
        if not any(json.loads(line).get("tmux") == ours_env for line in pane_lines):
            problems.append("proof_tmux_shim.pane_calls_go_to_the_pane_log_with_TMUX")
        blind_dir = base / "a-directory-not-a-file"
        blind_dir.mkdir()
        blind = base / "tmux-blind"
        blind.write_text(tmux_shim_text(pid, blind_dir, pane_log, fake), encoding="utf-8")
        blind.chmod(0o755)
        before = exec_log.read_text(encoding="utf-8") if exec_log.exists() else ""
        done = subprocess.run([str(blind), "-L", ours, "ls"], env={"PATH": "/usr/bin:/bin"}, capture_output=True,
                              text=True, timeout=15, check=False)
        after = exec_log.read_text(encoding="utf-8") if exec_log.exists() else ""
        if done.returncode != 98 or after != before:
            problems.append(f"proof_tmux_shim.fails_closed_when_it_cannot_log: rc={done.returncode} "
                            f"execed={after != before} err={done.stderr!r}")
    assert not problems, f"tmux shim: {problems}"


# ----- remfix 2: the verdict path (hunter H1-H6, review 4-7) -----------------------------------------


def test_proof_outcome_classification() -> None:
    """`verdict.classify_outcome`: a failed clause outranks a later Blocked/skip/crash (H1); a crash with
    no failed clause is FAIL(harness_error) (review 7, M9); a scenario without `rec` is BLOCKED (review 6)."""
    from .verdict import classify_outcome

    problems: list[str] = []
    failed = Recorder("X")
    failed.check("tmux.both_panes_after_stop", False, "both", "one")
    verdict, kind, _reason = classify_outcome(Blocked("the restart did not come up"), "call", failed, is_scenario=True)
    if (verdict, kind) != ("FAIL", "assert"):
        problems.append(f"proof_outcome.failed_clause_outranks_a_later_blocked: {(verdict, kind)}")
    verdict, kind, _reason = classify_outcome(KeyError("x"), "call", failed, is_scenario=True)
    if (verdict, kind) != ("FAIL", "assert"):
        problems.append(f"proof_outcome.failed_clause_outranks_a_harness_crash: {(verdict, kind)}")
    unfinished = Recorder("U")
    unfinished.check("c", False, 1, 2)
    if classify_outcome(None, "call", unfinished, is_scenario=True)[0] != "FAIL":
        problems.append("proof_outcome.failed_clause_outranks_a_missing_finish")
    bound = Recorder("B")
    bound.fail_bound("c", "a frame", 10.0, "control 0.1 s")
    if classify_outcome(Blocked("later"), "call", bound, is_scenario=True)[:2] != ("FAIL", "bound"):
        problems.append("proof_outcome.bound_clause_keeps_its_kind")
    clean = Recorder("C")
    clean.check("c", True, 1, 1)
    if classify_outcome(Blocked("env"), "call", clean, is_scenario=True)[0] != "BLOCKED":
        problems.append("proof_outcome.blocked_without_a_failed_clause_stays_blocked")
    verdict, kind, _reason = classify_outcome(KeyError("x"), "call", clean, is_scenario=True)
    if (verdict, kind) != ("FAIL", "harness_error"):
        problems.append(f"proof_outcome.harness_crash_is_harness_error: {(verdict, kind)}")
    if classify_outcome(None, "call", None, is_scenario=True)[0] != "BLOCKED":
        problems.append("proof_outcome.no_rec_is_blocked")
    if classify_outcome(RuntimeError("x"), "setup", failed, is_scenario=True)[0] != "BLOCKED":
        problems.append("proof_outcome.setup_error_is_blocked")
    if classify_outcome(ProductFail("w", 1.0, 0.01, "s"), "call", clean, is_scenario=True)[:2] != ("FAIL", "bound"):
        problems.append("proof_outcome.product_fail_is_bound")
    assert not problems, f"outcome classification: {problems}"


def test_guard_every_scenario_takes_rec() -> None:
    """Review finding 6: a scenario function without a `rec` parameter could record nothing."""
    offenders: list[str] = []
    for path in package_files():
        if not path.name.startswith("test_"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorated = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                            and d.func.id in ("scenario", "live_scenario") for d in node.decorator_list)
            if decorated and "rec" not in [arg.arg for arg in node.args.args]:
                offenders.append(f"{path.relative_to(PACKAGE)}::{node.name}")
    assert not offenders, f"scenarios that do not take rec: {offenders}"


def test_proof_gate_harness_error_and_crash() -> None:
    """A FAIL(harness_error) or a runner crash makes the gate INCOMPLETE, never RED or GREEN (review 7, H6)."""
    planned = [s.id for s in SCENARIOS]
    ok_exit = [LaneExit("sub", "1", 0, ())]
    crashed: list[dict[str, object]] = [{"id": sid, "verdict": "PASS", "lane_process": "sub-w1"} for sid in planned]
    crashed[0] = {"id": planned[0], "verdict": "FAIL", "fail_kind": "harness_error", "lane_process": "sub-w1"}
    problems: list[str] = []
    if decide_status(crashed, ok_exit, [], planned).status != "INCOMPLETE":
        problems.append("proof_gate.harness_error_is_incomplete")
    real = [dict(r) for r in crashed]
    real[1] = {"id": planned[1], "verdict": "FAIL", "fail_kind": "assert", "lane_process": "sub-w1"}
    if decide_status(real, ok_exit, [], planned).status != "RED":
        problems.append("proof_gate.a_product_fail_beside_a_harness_error_is_red")
    clean = [{"id": sid, "verdict": "PASS", "lane_process": "sub-w1"} for sid in planned]
    if decide_status(clean, ok_exit, [], planned, harness_problems=["selfcheck failed"]).status != "INCOMPLETE":
        problems.append("proof_gate.harness_problem_is_incomplete")
    if decide_status(real, ok_exit, [], planned, runner_crash="RuntimeError: x").status != "INCOMPLETE":
        problems.append("proof_gate.runner_crash_is_incomplete")
    assert not problems, f"gate: {problems}"


def test_proof_runner_always_finishes() -> None:
    """H6: a crash in the waves still runs the finalizer, which receives the crash."""
    from . import run as runner

    seen: list[str | None] = []

    def body() -> None:
        raise KeyError("planted crash in the waves (a pure raise: nothing is started)")

    def finish(crash: str | None) -> int:
        seen.append(crash)
        return 7

    try:
        code = runner.guarded(body, finish)
    except Exception as escaped:  # noqa: BLE001 - the named assertion below says what went wrong
        raise AssertionError(f"proof_runner.finish_runs_with_the_crash: guarded() raised {escaped!r}") from escaped
    assert code == 7 and len(seen) == 1 and seen[0] is not None and "KeyError" in seen[0], (
        f"proof_runner.finish_runs_with_the_crash: code={code} seen={seen}")
    seen.clear()
    assert runner.guarded(lambda: None, finish) == 7 and seen == [None], f"proof_runner.finish_runs_clean: {seen}"


def test_proof_restart_failure_is_blocked_only_for_eaddrinuse() -> None:
    """H2: a restart that did not come up is FAIL unless the product printed an EADDRINUSE port refusal."""
    from .instance import RestartFailed, restart_failure

    refused = ["controld refuses to start: port 51234 is not available ([Errno 48] Address already in use)"]
    other = ["controld refuses to start: port 51234 is not available ([Errno 13] Permission denied)"]
    problems: list[str] = []
    if not isinstance(restart_failure(refused, "no start line"), Blocked):
        problems.append("proof_restart.eaddrinuse_is_blocked")
    for label, lines in (("traceback", ["Traceback (most recent call last):"]), ("other_oserror", other), ("silent", [])):
        if not isinstance(restart_failure(lines, "no start line"), RestartFailed):
            problems.append(f"proof_restart.{label}_is_fail")
    assert not problems, f"restart classification: {problems}"


def test_proof_hang_guard_is_qualified() -> None:
    """H3: a blown hang guard is FAIL(bound) when a same-client control answers fast, else BLOCKED."""
    from .httpclient import Client, hang_verdict

    client = Client(1)  # never contacted: the control is injected
    fast = hang_verdict(client, "POST /x answers", 20.0, control=lambda _c: 0.01)
    slow = hang_verdict(client, "POST /x answers", 20.0, control=lambda _c: 5.0)
    none = hang_verdict(client, "POST /x answers", 20.0, control=lambda _c: None)
    assert isinstance(fast, ProductFail), f"proof_hang_guard.fast_control_is_fail_bound: {fast!r}"
    assert isinstance(slow, Blocked) and isinstance(none, Blocked), f"proof_hang_guard.unqualified_is_blocked: {slow!r} {none!r}"


def test_proof_live_spawn_stop_if() -> None:
    """H4: once L5 records a spawn failure, the other spawning L-scenarios are BLOCKED by the stop-if."""
    from .live.test_wave8_1_live import require_live_spawn

    require_live_spawn({}, "L6")
    with pytest.raises(Blocked):
        require_live_spawn({"L5_spawn_failure": "L5: spawn refused: {}"}, "L6")
        raise AssertionError("proof_live_spawn.stop_if_blocks_after_L5_failed")


def test_proof_teardown_signals_only_token_matches() -> None:
    """Review finding 4: a recorded pid is signalled only when its start token matches exactly. Pure."""
    from .teardown import signal_decision

    entry: dict[str, object] = {"pid": 4242, "kind": "controld", "argv": ["python"], "start_token": "Thu Sep 24 04:00:00 2026"}
    problems: list[str] = []
    if signal_decision(entry, "Thu Sep 24 04:00:00 2026") is not None:
        problems.append("proof_teardown.matching_token_is_signalled")
    if signal_decision(entry, "Thu Sep 24 05:11:11 2026") is None:
        problems.append("proof_teardown.reused_pid_not_signalled")
    if signal_decision(entry, None) is None:
        problems.append("proof_teardown.dead_pid_not_signalled")
    if signal_decision({**entry, "start_token": None}, "Thu Sep 24 04:00:00 2026") is None:
        problems.append("proof_teardown.no_recorded_token_not_signalled")
    if signal_decision({**entry, "pid": 1}, "x") is None:
        problems.append("proof_teardown.never_pid_1")
    assert not problems, f"teardown signal decision: {problems}"


def test_proof_local_tree_guard() -> None:
    """Review finding 3: names, kinds, mtimes and link targets under ~/.local are compared; only a
    foreign version's lock file is attributed to the user's sessions. Pure (planted snapshots)."""
    from .hostprobe import local_tree_changes

    start: dict[str, object] = {
        ".local/bin/claude": ["link", 1.0, "/private/tmp/shq6-9314-1/xdg/data/claude/versions/2.1.281"],
        ".local/share/claude/versions/2.1.281": ["file", 2.0, None],
        ".local/state/claude/locks/2.1.280.lock": ["file", 3.0, None],
    }
    problems: list[str] = []
    if local_tree_changes(start, dict(start), "2.1.281")[0]:
        problems.append("proof_local_tree.unchanged_dangling_link_is_not_a_change")
    relinked = {**start, ".local/bin/claude": ["link", 9.0, "/Users/x/.local/share/claude/versions/2.1.281"]}
    if ".local/bin/claude" not in local_tree_changes(start, relinked, "2.1.281")[0]:
        problems.append("proof_local_tree.link_target_change_is_a_change")
    pruned = {k: v for k, v in start.items() if not k.endswith("2.1.281")}
    if ".local/share/claude/versions/2.1.281" not in local_tree_changes(start, pruned, "2.1.281")[0]:
        problems.append("proof_local_tree.removed_version_is_a_change")
    touched = {**start, ".local/share/claude/versions/2.1.281": ["file", 5.0, None]}
    if not local_tree_changes(start, touched, "2.1.281")[0]:
        problems.append("proof_local_tree.mtime_change_is_a_change")
    user_lock = {**start, ".local/state/claude/locks/2.1.278.lock": ["file", 4.0, None]}
    changes, attributed = local_tree_changes(start, user_lock, "2.1.281")
    if changes or ".local/state/claude/locks/2.1.278.lock" not in attributed:
        problems.append("proof_local_tree.foreign_version_lock_is_attributed")
    own_lock = {**start, ".local/state/claude/locks/2.1.281.lock": ["file", 4.0, None]}
    if ".local/state/claude/locks/2.1.281.lock" not in local_tree_changes(start, own_lock, "2.1.281")[0]:
        problems.append("proof_local_tree.run_engine_lock_is_a_change")
    assert not problems, f"local tree guard: {problems}"


def test_proof_host_field_deltas() -> None:
    """H7: the baseline vs after-teardown comparators Z1/Z3 use see an added name, a moved mtime and a gone pid."""
    from .hostprobe import listing_delta, pid_delta

    before: dict[str, object] = {"shepherd.db": 1.0, "logs": 2.0}
    problems: list[str] = []
    delta = listing_delta(before, {**before, "extra.db": 3.0})
    if delta["added"] != ["extra.db"]:
        problems.append("proof_host_deltas.added_name_seen")
    if not listing_delta(before, {**before, "shepherd.db": 9.0})["mtime_moved"]:
        problems.append("proof_host_deltas.moved_mtime_seen")
    if pid_delta([[11, "shepherd-controld"], [12, "x"]], [[12, "x"]])["gone"] != [11]:
        problems.append("proof_host_deltas.gone_pid_seen")
    if pid_delta([5], [5, 6])["new"] != [6]:
        problems.append("proof_host_deltas.new_pid_seen")
    assert not problems, f"host deltas: {problems}"


def test_proof_spawn_chokepoint_refuses_unsafe_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review finding 5: `spawn_drained` re-checks the env AT the spawn; an unsafe env never reaches Popen.

    `Popen` is replaced by a recorder that raises: nothing is started either way.
    """
    from . import instance

    started: list[object] = []

    def refuse_to_start(*args: object, **kwargs: object) -> None:
        started.append(args)
        raise RuntimeError("proof_spawn_chokepoint: Popen was reached")

    monkeypatch.setattr(subprocess, "Popen", refuse_to_start)  # the module instance.py calls through
    run, root = _guard_run()
    unsafe = {"HOME": str(paths.REAL_HOME), "XDG_DATA_HOME": "/planted", "PATH": "/usr/bin:/bin"}
    with pytest.raises(ValueError):
        instance.spawn_drained(run, ["/usr/bin/true"], unsafe, Path("/"), Path("/nonexistent-qa6-logs"), "x", "proof")
    assert not started, "proof_spawn_chokepoint.refused_before_popen"


def test_proof_probes_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """M3: a probe that exits with an error is `ProbeUnknown`, never an empty (clean) listing."""
    from . import hostprobe

    answers = {"error": subprocess.CompletedProcess(["x"], 2, "", "pgrep: bad option"),
               "none": subprocess.CompletedProcess(["x"], 1, "", ""),
               "found": subprocess.CompletedProcess(["x"], 0, "123 cmd\n", "")}
    chosen: list[str] = ["none"]
    monkeypatch.setattr(hostprobe, "run", lambda argv, timeout_s=15.0: answers[chosen[0]])
    assert hostprobe.pgrep("x") == [], "proof_probes.no_match_is_empty"
    chosen[0] = "found"
    assert hostprobe.pgrep("x") == [(123, "cmd")], "proof_probes.match_parsed"
    chosen[0] = "error"
    with pytest.raises(hostprobe.ProbeUnknown):
        hostprobe.pgrep("x")
        raise AssertionError("proof_probes.error_is_unknown_not_clean")
    from . import tmuxctl

    ours = "shepherd-m3-q6424242-3"
    monkeypatch.setattr(tmuxctl, "run", lambda *a, **k: tmuxctl.TmuxResult((), 1, "", "error connecting to x (No such file)"))
    assert tmuxctl.server_running(ours, 424242) is False, "proof_probes.tmux_no_server_is_not_running"
    monkeypatch.setattr(tmuxctl, "run", lambda *a, **k: tmuxctl.TmuxResult((), 1, "", "lost server"))
    with pytest.raises(Blocked):
        tmuxctl.server_running(ours, 424242)
        raise AssertionError("proof_probes.tmux_unknown_is_not_not_running")


def test_proof_scenario_mutation_outcome() -> None:
    """M7: `assertion_falsified` needs a passing unmutated control, APPLIED, a failed clause and a clean teardown."""
    from .mutations import mutation_outcome

    problems: list[str] = []
    if mutation_outcome("pass", "fail", True, [])[0] != "assertion_falsified":
        problems.append("proof_mutation_outcome.falsified")
    if mutation_outcome("fail", "fail", True, [])[0] != "blocked":
        problems.append("proof_mutation_outcome.needs_a_passing_control")
    if mutation_outcome("pass", "fail", True, ["leak"])[0] != "blocked":
        problems.append("proof_mutation_outcome.needs_a_clean_teardown")
    if mutation_outcome("pass", "fail", False, [])[0] != "blocked":
        problems.append("proof_mutation_outcome.needs_applied")
    if mutation_outcome("pass", "pass", True, [])[0] != "survived":
        problems.append("proof_mutation_outcome.survivor")
    assert not problems, f"mutation outcome: {problems}"


# ----- the proofs of the five copied qa5 helpers -----------------------------------------------


class _EventServer:
    """A one-connection SSE server: `: open`, one frame, one keep-alive, then holds."""

    def __init__(self, stream: bytes | None = None, close_after: bool = False) -> None:
        self.stream = stream
        self.close_after = close_after
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
            events = self.stream if self.stream is not None else (
                f"id: 7\ndata: {body}\n\n".encode() + b": keep-alive\n\n")
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\n"
                + b": open\n\n" + events
            )
            if self.close_after:
                return
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
        # The raw tape (not `snapshot()`, which now refuses a tape with parse failures): each
        # named assertion below must be able to fire on its own.
        frames, comments = list(sub.frames), [c.text for c in sub.comment_snapshot()]
        sub.close()
    finally:
        server.close()
    assert [(f.seq, f.kind, f.project_id) for f in frames] == [(7, "project.created", "P7")], "proof_sse_rig.frame_parsed"
    assert sorted(frames[0].raw_fields) == ["data", "id"], "proof_sse_rig.fields_id_and_data"
    assert comments == [": open", ": keep-alive"], f"proof_sse_rig.comments_recorded: {comments}"
    assert sub.parse_failures == [], "proof_sse_rig.no_parse_failures"


def test_proof_sse_rig_fails_closed() -> None:
    """H5: a product frame that does not parse is FAIL; an EOF after a green control is FAIL; before one, BLOCKED."""
    from .sse_rig import Refusal, open_stream

    def settle(sub: object, done: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not done():
            time.sleep(0.02)

    problems: list[str] = []
    bad = _EventServer(stream=b"id: x\ndata: not json\n\n")
    try:
        opened = open_stream("proof-bad", bad.port)
        assert not isinstance(opened, Refusal)
        sub = opened
        settle(sub, lambda: bool(opened.parse_failures))
        try:
            sub.snapshot()
            problems.append("proof_sse_rig.unparseable_frame_is_fail: snapshot returned")
        except AssertionError:
            pass
        sub.close()
    finally:
        bad.close()
    for green in (True, False):
        server = _EventServer(close_after=True)
        try:
            eof = open_stream("proof-eof", server.port)
            assert not isinstance(eof, Refusal)
            if green:
                eof.mark_green("planted control")
            settle(eof, lambda: eof.reader_fault is not None)
            try:
                eof.snapshot()
                problems.append(f"proof_sse_rig.eof_is_reported (green={green}): snapshot returned")
            except AssertionError:
                if not green:
                    problems.append("proof_sse_rig.eof_before_a_control_is_blocked: got FAIL")
            except Blocked:
                if green:
                    problems.append("proof_sse_rig.eof_after_a_green_control_is_fail: got BLOCKED")
            eof.close()
        finally:
            server.close()
    assert not problems, f"sse rig: {problems}"


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
        absent = AuditProbe(root=Path(scratch) / "no-such-logs" / "audit")
        assert absent.mark() == 0, "proof_auditprobe.mark_before_the_first_request_is_zero"
        with pytest.raises(Blocked):
            absent.since(0)
            raise AssertionError("proof_auditprobe.absent_dir_is_not_an_empty_audit")


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


#: Every inert module-mutation fixture is proved: adding one is enough to add its proof run.
MODULE_MUTATIONS: list[str] = sorted(path.stem for path in (PACKAGE / "fixtures" / "mutations").glob("*.json"))


def test_guard_module_mutation_floor_is_present() -> None:
    """The copied-helper floor and the remfix-2 guard/verdict-path floor are all registered."""
    required = {"sse_rig", "auditprobe", "wsclient", "constants", "tmuxctl", "sandbox_xdg", "sandbox_checker",
                "sandbox_autoupdater", "tmuxctl_pane", "tmuxctl_getopt_last_L", "tmuxctl_getopt_S_over_L",
                "tmuxctl_getopt_cluster", "shim_refusal", "shim_fail_open", "verdict_h1_rank", "verdict_harness_error",
                "verdict_no_rec", "report_harness_error", "report_runner_crash", "report_harness_problem", "run_guarded",
                "instance_restart", "httpclient_hang", "live_spawn_stop_if", "teardown_token",
                "hostprobe_lock_attribution", "hostprobe_link_target", "hostprobe_listing_delta",
                "hostprobe_probe_unknown", "tmuxctl_server_unknown", "instance_spawn_chokepoint",
                "sse_rig_parse_failure", "sse_rig_eof_after_control", "mutations_control", "auditprobe_absent"}
    missing = sorted(required - set(MODULE_MUTATIONS))
    assert not missing, f"module mutations not registered: {missing}"


@pytest.mark.parametrize("module", MODULE_MUTATIONS)
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
