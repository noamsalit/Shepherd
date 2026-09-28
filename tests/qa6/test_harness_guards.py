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
  (`test_proof_real_claude_resolution`);
* **the settings guard (U2, INC-3)**: the runner measures the real settings sha
  once at run start and exports it to every lane; a change after that stops the
  run even when it restores the owner's value (`test_proof_settings_mid_run_change_stops`);
  with no exported value the owner's value is the expectation
  (`test_proof_settings_env_unset_uses_owner`); and a sha other than the owner's is
  a published, non-stopping WARN, never silence (`test_proof_settings_owner_mismatch_warns`,
  `test_proof_preflight_warn_is_published`).
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
from .hostprobe import Baseline
from .report import LaneExit, decide_status
from .verdict import Blocked, ProductFail, Recorder, Sourced, await_env, classify_blown_bound

pytestmark = pytest.mark.qa6

#: The binary's name, assembled — for the reason `tests/boundaries/test_tmux_blast_radius.py`'s
#: docstring gives for its own `TMUX`: this file sits inside the tree that module scans, and the
#: argvs below are **data handed to the socket judge** (`tmuxctl.effective_socket`,
#: `*_argv_offenders`, `unseeded_excused`) — several deliberately name the user's socket or a
#: teardown verb so the judge can be seen to refuse them. None is ever executed; the one proof
#: that execs anything (`test_proof_tmux_shim_refuses`) execs a FAKE binary behind the shim. A
#: literal here would make the judge's own test corpus read as argvs reaching `shepherd`.
TMUX = "tm" + "ux"

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


def test_guard_every_scenario_id_is_planned_and_implemented_once() -> None:
    """Every `@scenario`/`@live_scenario` id is a plan id, implemented once, named for the runner, and
    lives in a module of its own wave.

    The AST walk is this test's own working, a closure and not a module-level helper: it reads qa6's
    test modules only, and `tests/boundaries/test_one_definition_site.py` counts a module-level
    source-reading function as a boundary rule that needs an inventory entry.
    """

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

    found = implemented()
    assert found, "the scan found no @scenario at all: an empty scan proves nothing about duplicates"
    ids = [sid for sid, _where in found]
    unknown = sorted(set(ids) - set(BY_ID))
    duplicates = sorted(sid for sid, n in Counter(ids).items() if n > 1)
    assert not unknown, f"not test-plan ids: {unknown}"
    assert not duplicates, f"implemented more than once: {duplicates}"
    for sid, where in found:
        module = Path(where.split("::", 1)[0])
        named = re.match(r"^test_wave([1-9])_", module.name)
        if len(module.parts) > 1 and named is not None:
            assert BY_ID[sid].wave == int(named.group(1)), f"{sid} is a wave-{BY_ID[sid].wave} scenario in {module.name}"


def test_guard_modules_follow_the_lane_naming_convention() -> None:
    """Lane directory and `test_wave<N>_<topic>.py` shape; each scenario's wave-vs-module check is in
    `test_guard_every_scenario_id_is_planned_and_implemented_once`, beside the walk that finds it."""
    lanes = {"sub", "unit", "cli", "live", "inproc", "inproc_long", "host"}
    for path in package_files():
        if path.name.startswith("test_") and path.parent != PACKAGE:
            assert path.parent.name in lanes, f"{path} is not in a lane directory {sorted(lanes)}"
            assert re.match(r"^test_wave[1-9]_[A-Za-z0-9_]+\.py$", path.name), f"{path.name} must be test_wave<N>_<topic>.py"


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


def test_guard_no_js_synthesised_user_action_outside_js_functions() -> None:
    """Review finding 8: JS-synthesised user actions anywhere in a module (module level, async
    def, lambdas), whether the script is a literal, an f-string, a concatenation or a name
    bound to one; plus Playwright's `dispatch_event`. Only a `js_*` function may hold one.

    The guard and its proof are one test because the scanner is this test's own closure, not a
    module-level helper (`tests/boundaries/test_one_definition_site.py` counts a module-level
    source-reading function as a boundary rule). Arrival first: the planted spellings (parsed,
    never run) must each be caught before the package scan's emptiness means anything.
    """

    def string_parts(node: ast.AST) -> list[str]:
        """The literal text of a string expression: a constant, an f-string's constant parts, a concatenation."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            return ["".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return string_parts(node.left) + string_parts(node.right)
        return []

    def assigned_strings(scope: ast.AST, name: str) -> list[str]:
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
                found.extend(string_parts(value))
        return found

    def enclosing_function(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current
            current = parents.get(current)
        return None

    def js_action_offenders(tree: ast.Module, where: str) -> list[str]:
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        offenders: list[str] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            function = enclosing_function(node, parents)
            if function is not None and function.name.startswith("js_"):
                continue
            label = f"{where}:{node.lineno} in {function.name if function else '<module>'}"
            if node.func.attr in SYNTHETIC_EVENT_ATTRS:
                offenders.append(f"{label}: {node.func.attr}()")
                continue
            if node.func.attr not in EVAL_ATTRS:
                continue
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                texts = string_parts(arg)
                if isinstance(arg, ast.Name):
                    texts = assigned_strings(function, arg.id) if function is not None else []
                    texts += assigned_strings(tree, arg.id)
                if any(JS_USER_ACTION.search(text) for text in texts):
                    offenders.append(label)
        return offenders

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

    offenders: list[str] = []
    for path in package_files():
        if path.name == "test_harness_guards.py":
            continue
        offenders.extend(js_action_offenders(ast.parse(path.read_text(encoding="utf-8")), str(path.relative_to(PACKAGE))))
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
    """Refused when a qa6 item is selected to RUN; not when qa6 is only collected or deselected.

    The run half selects one inert, fast node, so a broken refusal costs one shim-text read
    rather than recursing into this whole file. The two controls are what a whole-tree
    `--collect-only` (tests/boundaries/test_collected_node_ids.py) and the default lane need.
    """
    refusal = "waves are ordered"
    inert = "tests/qa6/test_harness_guards.py::test_guard_shims_carry_no_signal_or_teardown_verb"
    done = _pytest("-m", "qa6", inert, randomly=True)
    assert done.returncode != 0 and "no:randomly" in (done.stdout + done.stderr), (
        "proof_randomly.running_qa6_is_refused", done.returncode, done.stdout[-400:])
    collected = _pytest("--collect-only", "-m", "qa6", "tests/qa6/test_harness_guards.py", randomly=True)
    assert collected.returncode == 0 and refusal not in collected.stdout + collected.stderr, (
        "proof_randomly.collect_only_is_not_refused", collected.returncode, collected.stderr[-400:])
    deselected = _pytest(inert, randomly=True)
    assert deselected.returncode == 5 and refusal not in deselected.stdout + deselected.stderr, (
        "proof_randomly.deselected_qa6_is_not_refused", deselected.returncode, deselected.stderr[-400:])


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
    """Only sandbox.py spells XDG_* or passes home=REAL_HOME; nothing execs the user's claude link.

    `only_described` is this test's own closure, not a module-level helper: a module-level
    source-reading function is a boundary rule to `tests/boundaries/test_one_definition_site.py`.
    """

    def only_described(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
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
                if not only_described(node, parents):
                    offenders.append(f"{where}:{node.lineno} uses REAL_CLAUDE_BIN outside a message (exec run.real_claude)")
    assert not offenders, f"ad-hoc real-HOME env or real-engine exec: {offenders}"


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
    from .tmuxctl import effective_socket, pane_argv_offenders, product_argv_offenders

    pid = 424242
    ours = f"shepherd-m3-q6{pid}-3"
    ours_env = f"{paths.TMUX_SOCKET_DIR}/{ours},12345,0"
    default_path = f"{paths.TMUX_SOCKET_DIR}/default"
    planted: list[dict[str, object]] = [
        {"argv": [TMUX, "display-message", "-p", "#{client_termtype}"], "tmux": ours_env},
        {"argv": [TMUX, "-L", "shepherd", "list-sessions"], "tmux": ours_env},
        {"argv": [TMUX, "show", "-gv", "focus-events"], "tmux": f"{paths.TMUX_SOCKET_DIR}/default,1,0"},
        {"argv": [TMUX, "-S", "/elsewhere/shepherd-m3-q6424242-3", "ls"], "tmux": ours_env},
        {"argv": [TMUX, "-V"], "tmux": ours_env},
    ]
    flagged = [entry["argv"] for entry in pane_argv_offenders(planted, pid)]
    problems: list[str] = []
    if planted[0]["argv"] in flagged or planted[4]["argv"] in flagged:
        problems.append("proof_pane_argv.allows_our_socket_via_TMUX")
    for index, label in ((1, "flags_user_socket_in_pane"), (2, "flags_default_via_TMUX"), (3, "flags_foreign_S_path")):
        if planted[index]["argv"] not in flagged:
            problems.append(f"proof_pane_argv.{label}")
    if effective_socket([TMUX, "-V"], None) is not None or effective_socket([TMUX, "ls"], None) != "default":
        problems.append("proof_pane_argv.version_contacts_nothing_and_bare_is_default")
    reviewer = {
        "reviewer_S_beats_L": ([TMUX, "-L", ours, "-S", default_path, "kill-server"], "default"),
        "reviewer_last_L_wins": ([TMUX, "-L", ours, "-L", "default", "kill-server"], "default"),
        "reviewer_clustered_uL": ([TMUX, "-uL", "default", "kill-server"], "default"),
        "reviewer_clustered_2uL": ([TMUX, "-2uL", "shepherd", "ls"], "shepherd"),
    }
    for label, (argv, reached) in reviewer.items():
        if effective_socket(argv, ours_env) != reached:
            problems.append(f"proof_pane_argv.{label}: reaches {effective_socket(argv, ours_env)!r}, tmux reaches {reached!r}")
        if argv not in [entry["argv"] for entry in pane_argv_offenders([{"argv": argv, "tmux": ours_env}], pid)]:
            problems.append(f"proof_pane_argv.{label}_flagged_in_pane")
        if product_argv_offenders([argv], pid) != [argv]:
            problems.append(f"proof_pane_argv.{label}_flagged_as_product_argv")
    allowed = {
        "ours_plain": [TMUX, "-L", ours, "ls"],
        "ours_clustered": [TMUX, "-uL", ours, "ls"],
        "ours_fused": [TMUX, f"-L{ours}", "ls"],
        "ours_after_a_foreign_L": [TMUX, "-L", "default", "-L", ours, "ls"],
        "ours_S_beats_a_foreign_L": [TMUX, "-L", "shepherd", "-S", f"{paths.TMUX_SOCKET_DIR}/{ours}", "ls"],
        "ours_after_a_valued_global": [TMUX, "-f", "/dev/null", "-L", ours, "ls"],
    }
    for label, argv in allowed.items():
        if product_argv_offenders([argv], pid):
            problems.append(f"proof_pane_argv.allows_{label}")
    refused = {
        "valued_global_eats_L": [TMUX, "-f", "-L", ours, "ls"],
        "double_dash_stops_options": [TMUX, "--", "-L", ours],
        "missing_value": [TMUX, "-L"],
        "unknown_option": [TMUX, "-Z", "-L", ours, "ls"],
        "no_server_but_not_plain_V": [TMUX, "-uV"],
        "relative_S_dot": [TMUX, "-S", f"./{ours}", "ls"],
        "relative_S_bare": [TMUX, "-S", ours, "ls"],
        "unicode_digit_L": [TMUX, "-L", f"shepherd-m3-q6{pid}-\u0663", "ls"],
    }
    for label, argv in refused.items():
        if product_argv_offenders([argv], pid) != [argv]:
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
        # review N2: a relative -S resolves from the CLIENT's cwd (never ours), and only ASCII digits
        ("relative_S_dot_in_socket_dir", ["-S", f"./{ours}", "ls"], None),
        ("relative_S_bare", ["-S", ours, "ls"], None),
        ("unicode_digit_L", ["-L", f"shepherd-m3-q6{pid}-\u0663", "ls"], None),
    ]
    #: Independent of the Python judge: these shapes must be refused by BOTH (review N2).
    must_refuse = {"relative_S_dot_in_socket_dir", "relative_S_bare", "unicode_digit_L"}
    #: Run from the socket dir itself, where `./<ours>` would realpath to our socket.
    cwd_for = {"relative_S_dot_in_socket_dir": str(paths.TMUX_SOCKET_DIR)}
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
            done = subprocess.run([str(shim), *words], env=env, capture_output=True, text=True, timeout=15, check=False,
                                  cwd=cwd_for.get(label, str(base)))
            after = exec_log.read_text(encoding="utf-8") if exec_log.exists() else ""
            logs_after = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in (product_log, pane_log) if p.exists())
            execed = after != before
            python_allows = argv_violation([TMUX, *words], tmux_env, pid) is None
            if label in must_refuse and python_allows:
                problems.append(f"proof_tmux_shim.judge_refuses_{label}")
            if python_allows and done.stderr:
                problems.append(f"proof_tmux_shim.allowed_calls_add_no_stderr: {label}: {done.stderr!r}")
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
    """A FAIL(harness_error) makes the gate INCOMPLETE, never RED or GREEN (review 7); a runner crash is
    INCOMPLETE with no product FAIL (H6) and RED, crash first, beside one (hunter N3)."""
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
    if decide_status(clean, ok_exit, [], planned, runner_crash="RuntimeError: x").status != "INCOMPLETE":
        problems.append("proof_gate.runner_crash_is_incomplete")
    with_fail = decide_status(real, ok_exit, [], planned, runner_crash="RuntimeError: planted crash")
    if with_fail.status != "RED" or not with_fail.reasons[0].startswith("the runner crashed: RuntimeError: planted crash"):
        problems.append(f"proof_gate.crash_with_product_fail_is_red_crash_first: {with_fail.status} {with_fail.reasons[:2]}")
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


def test_proof_claude_sessions_guard() -> None:
    """Round 7: a live user session rewriting its own `<pid>.json` is attributed, not a change;
    any other added, removed or moved entry is a change. Pure (planted listings)."""
    from .hostprobe import claude_session_changes

    start: dict[str, object] = {"100.json": 1.0, "100.ab.key": 2.0, "200.json": 3.0}
    problems: list[str] = []
    if claude_session_changes(start, dict(start), set())[0]:
        problems.append("proof_sessions.unchanged_is_not_a_change")
    user_moved = {**start, "100.json": 9.0}
    changes, attributed = claude_session_changes(start, user_moved, {100})
    if changes or "100.json" not in attributed:
        problems.append("proof_sessions.user_session_state_is_attributed")
    if "100.json" not in claude_session_changes(start, user_moved, set())[0]:
        problems.append("proof_sessions.non_user_move_is_a_change")
    added = {**start, "300.json": 4.0}
    if "300.json" not in claude_session_changes(start, added, {100, 200})[0]:
        problems.append("proof_sessions.new_foreign_pid_is_a_change")
    removed = {k: v for k, v in start.items() if k != "200.json"}
    if "200.json" not in claude_session_changes(start, removed, {100})[0]:
        problems.append("proof_sessions.removed_non_user_is_a_change")
    assert not problems, f"claude sessions guard: {problems}"


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


# ----- remfix 3: publication, product sockets, teardown, probes (hunter N1-N6, review N1-N5) ------------


def _dummy_baseline() -> Baseline:
    return Baseline(
        settings_sha="x", claude_projects={}, claude_sessions={}, shepherd_data={}, real_tmpdir_shepherd={},
        claude_json_mtime=None, tmux_dir={}, tmux_user_sockets_present={}, tmux_pids=[], tmux_server_pids=[],
        port_owner_pids=[], shepherd_daemons=[], local_tree={})


def test_proof_publication_survives_torn_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hunter N1 / review N4: the REAL `run._finish` publishes with a torn record line, a torn
    harness-problem line and a torn teardown-problem line, counting each as a problem; and when
    publication itself raises, the last resort writes an INCOMPLETE run file and a history line
    carrying both exceptions.

    Only the four finalizer steps that touch the host (ledger copy, worktree, teardown, host checks)
    are replaced by recorders; everything from `fill_missing` to `write_report` is the real code,
    writing into a temp report dir. Nothing is started, signalled or removed.
    """
    import argparse

    from . import run as runner

    touched: list[str] = []
    for name in ("_copy_ledgers", "_remove_worktree", "_post_teardown_checks"):
        monkeypatch.setattr(runner, name, lambda *_a, _n=name: touched.append(_n))
    monkeypatch.setattr(runner, "_teardown", lambda _state: touched.append("_teardown"))
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qa6torn-", dir="/tmp") as scratch:
        report_dir = Path(scratch) / "runs"

        def state_for(run_id: str) -> runner.RunState:
            run = RunContext(pid=424242, run_id=run_id, run0=Path(scratch) / "run0-absent", run_dir=report_dir / run_id)
            (run.run_dir / "records").mkdir(parents=True)
            good = {"id": SCENARIOS[0].id, "verdict": "PASS", "lane_process": "sub-w1"}
            (run.run_dir / "records" / "sub-w1.jsonl").write_text(json.dumps(good) + "\n" + '{"id": "A2", "verd',
                                                                  encoding="utf-8")
            (run.run_dir / "harness-problems.jsonl").write_text('{"where": "x", "prob', encoding="utf-8")
            run.teardown_problems.write_text('{"where": "y"', encoding="utf-8")
            return runner.RunState(args=argparse.Namespace(report_dir=report_dir, lane=[]), run=run,
                                   baseline=_dummy_baseline(), reached="T4", selected={1})

        code = -1
        try:
            code = runner._finish(state_for("qa6-guard-torn"), "qa6-guard-torn", None)
        except Exception as escaped:  # noqa: BLE001 - the named assertion below says what went wrong
            problems.append(f"proof_publication.torn_record_still_publishes: _finish raised {escaped!r}")
        run_file = report_dir / "qa6-guard-torn.json"
        payload = json.loads(run_file.read_text(encoding="utf-8")) if run_file.exists() else {}
        if code != 1 or payload.get("status") != "INCOMPLETE":
            problems.append(f"proof_publication.torn_record_still_publishes: code={code} status={payload.get('status')}")
        harness = [str(p) for p in payload.get("harness_problems", [])]
        if not any("malformed record line" in p and "sub-w1.jsonl" in p for p in harness):
            problems.append(f"proof_publication.torn_record_line_is_a_problem: {harness[:5]}")
        if not any("malformed problem line" in p and "harness-problems.jsonl" in p for p in harness):
            problems.append(f"proof_publication.torn_problem_line_is_reported: {harness[:5]}")
        teardown_listed = [str(p) for p in payload.get("teardown_problems", [])]
        if not any("malformed problem line" in p and "teardown-problems.jsonl" in p for p in teardown_listed):
            problems.append(f"proof_publication.torn_teardown_line_is_reported: {teardown_listed[:5]}")
        if touched != ["_copy_ledgers", "_remove_worktree", "_teardown", "_post_teardown_checks"]:
            problems.append(f"proof_publication.every_step_ran: {touched}")

        def broken_publish(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("planted publication failure (a pure raise)")

        monkeypatch.setattr(runner, "write_report", broken_publish)
        crash = "KeyError: 'planted crash in the waves'\nTraceback ..."
        try:
            code = runner._finish(state_for("qa6-guard-last"), "qa6-guard-last", crash)
        except Exception as escaped:  # noqa: BLE001 - the named assertion below says what went wrong
            problems.append(f"proof_publication.last_resort_writes_run_file: _finish raised {escaped!r}")
        last = report_dir / "qa6-guard-last.json"
        text = last.read_text(encoding="utf-8") if last.exists() else ""
        if code != 1 or '"INCOMPLETE"' not in text or "planted publication failure" not in text or "planted crash" not in text:
            problems.append(f"proof_publication.last_resort_writes_run_file: code={code} text={text[:300]!r}")
        history = (report_dir / "qa6-history.jsonl").read_text(encoding="utf-8") if (report_dir / "qa6-history.jsonl").exists() else ""
        lines = [json.loads(line) for line in history.splitlines() if line.strip()]
        last_line = next((line for line in lines if line.get("run_id") == "qa6-guard-last"), None)
        reasons = " ".join(str(r) for r in (last_line or {}).get("reasons", []))
        if last_line is None or last_line.get("status") != "INCOMPLETE" or "planted publication failure" not in reasons \
                or "planted crash" not in reasons:
            problems.append(f"proof_publication.last_resort_history_carries_both_exceptions: {last_line}")
    assert not problems, f"publication: {problems}"


class _SocketFaults:
    """One loopback listener that answers 200 once, then misbehaves in the chosen `mode`."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.port = int(self.listener.getsockname()[1])
        self.served = 0
        self.stop = threading.Event()
        self.held: list[socket.socket] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stop.is_set():
            try:
                conn, _addr = self.listener.accept()
            except OSError:
                return
            conn.recv(65536)
            self.served += 1
            if self.served == 1:
                if self.mode == "refused":
                    self.listener.close()  # BEFORE the answer: the client's next connect is refused, never queued
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
                conn.close()
                if self.mode == "refused":
                    return
                continue
            if self.mode == "reset":
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
                conn.close()
            elif self.mode == "disconnect":
                conn.close()
            elif self.mode == "garbage":
                conn.sendall(b"NOT-HTTP garbage\r\n\r\n")
                conn.close()
            else:  # "hang": hold the connection open, never answer
                self.held.append(conn)

    def close(self) -> None:
        self.stop.set()
        for conn in self.held:
            conn.close()
        self.listener.close()  # idempotent: the "refused" mode already closed it
        self.thread.join(timeout=5)


def test_proof_product_socket_failures() -> None:
    """Hunter N2: a socket failure from `Client.request` on the product's port is product-side —
    FAIL when this client answered earlier in the scenario, else BLOCKED — for a refused connection,
    a reset, `RemoteDisconnected`, a garbled status line (`http.client.HTTPException`) and a timeout;
    the original socket type is still catchable; a harness exception stays `harness_error`.

    Loopback listeners in this process only; nothing else is contacted.
    """
    import http.client

    from .httpclient import Client
    from .verdict import ProductUnreachable, begin_scenario, classify_outcome

    expected_type: dict[str, type[BaseException]] = {
        "refused": ConnectionRefusedError, "reset": ConnectionResetError, "disconnect": ConnectionResetError,
        "garbage": http.client.HTTPException, "hang": TimeoutError,
    }
    problems: list[str] = []
    for mode, original in expected_type.items():
        server = _SocketFaults(mode)
        try:
            begin_scenario()
            client = Client(server.port)
            first = client.request("GET", "/api/fleet", timeout_s=2.0)
            if first.status != 200:
                problems.append(f"proof_product_socket.{mode}_control_answered: {first.status}")
            try:
                client.request("GET", "/api/fleet", timeout_s=0.6)
                problems.append(f"proof_product_socket.{mode}_raises: the second request answered")
                continue
            except BaseException as error:  # noqa: BLE001 - classified below; anything unexpected is named
                caught: BaseException = error
            if not isinstance(caught, ProductUnreachable) or not isinstance(caught, original):
                problems.append(f"proof_product_socket.{mode}_is_product_side_and_keeps_its_type: {caught!r}")
                continue
            clean = Recorder("S")
            clean.check("control", True, 1, 1)
            verdict, kind, _reason = classify_outcome(caught, "call", clean, is_scenario=True)
            want_kind = "bound" if mode == "hang" else "assert"
            if (verdict, kind) != ("FAIL", want_kind):
                problems.append(f"proof_product_socket.{mode}_after_answer_is_fail: {(verdict, kind)}")
        finally:
            server.close()
    begin_scenario()
    fresh = Client(1)  # port 1: nothing listens; no answer this scenario
    try:
        fresh.request("GET", "/api/fleet", timeout_s=1.0)
        problems.append("proof_product_socket.refused_without_answer_raises")
    except ConnectionRefusedError as error:
        if classify_outcome(error, "call", Recorder("R"), is_scenario=True)[0] != "BLOCKED":
            problems.append(f"proof_product_socket.refused_without_answer_is_blocked: {classify_outcome(error, 'call', Recorder('R'), is_scenario=True)}")
    server = _SocketFaults("refused")
    try:
        begin_scenario()
        client = Client(server.port)
        client.request("GET", "/api/fleet", timeout_s=2.0)
        begin_scenario()  # a NEW scenario: the earlier answer proves nothing about this one
        try:
            client.request("GET", "/api/fleet", timeout_s=1.0)
        except ConnectionRefusedError as error:
            if classify_outcome(error, "call", Recorder("E"), is_scenario=True)[0] != "BLOCKED":
                problems.append("proof_product_socket.answer_in_an_earlier_scenario_does_not_count")
    finally:
        server.close()
    if classify_outcome(KeyError("x"), "call", Recorder("K"), is_scenario=True)[1] != "harness_error":
        problems.append("proof_product_socket.harness_exception_stays_harness_error")
    assert not problems, f"product socket failures: {problems}"


def test_proof_teardown_keeps_what_it_found() -> None:
    """Hunter N5: a teardown step that raises keeps the problems earlier steps found, and the later
    steps still run; a torn pid-ledger line is reported and the other entries are still read. Pure
    (fake steps; a temp ledger file). No pid is signalled."""
    from .teardown import LeakReport, ledger_entries, run_steps

    ran: list[str] = []

    def finds_a_leak(report: LeakReport) -> None:
        ran.append("first")
        report.problems.append("planted leak: pid 4242 still alive at teardown")

    def raises_midway(report: LeakReport) -> None:
        ran.append("second")
        report.problems.append("planted leak found before the raise")
        raise OSError("planted rmtree failure (a pure raise)")

    problems: list[str] = []
    try:
        report = run_steps(LeakReport(), [("find", finds_a_leak), ("raise", raises_midway),
                                          ("after", lambda r: ran.append("third"))])
    except Exception as escaped:  # noqa: BLE001 - the named assertion below says what went wrong
        raise AssertionError(f"proof_teardown.raising_step_keeps_found_problems: run_steps raised {escaped!r}") from escaped
    joined = " | ".join(report.problems)
    if "pid 4242" not in joined or "found before the raise" not in joined or "planted rmtree failure" not in joined:
        problems.append(f"proof_teardown.raising_step_keeps_found_problems: {report.problems}")
    if ran != ["first", "second", "third"]:
        problems.append(f"proof_teardown.later_steps_still_run: {ran}")
    with tempfile.TemporaryDirectory(prefix="qa6ledger-", dir="/tmp") as scratch:
        ledger = Path(scratch) / "pids.jsonl"
        ledger.write_text(json.dumps({"pid": 4242, "kind": "controld"}) + "\n" + '{"pid": 43', encoding="utf-8")
        found: list[str] = []
        try:
            entries = ledger_entries(ledger, found)
        except Exception as escaped:  # noqa: BLE001 - the named assertion below says what went wrong
            raise AssertionError(f"proof_teardown.torn_ledger_line_is_reported: raised {escaped!r}") from escaped
        if [entry.get("pid") for entry in entries] != [4242] or not any("line 2" in p for p in found):
            problems.append(f"proof_teardown.torn_ledger_line_is_reported: entries={entries} problems={found}")
    assert not problems, f"teardown: {problems}"


def test_proof_pid_probes_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hunter N6: `ps -p` exit 1 with empty output is "gone"; any other failure is `ProbeUnknown`,
    and the sweep reads an unknown owner as LIVE (it never removes on an unknown). Pure: `run` is
    replaced; the sweep's decision is asked of `owner_dead`, never of `sweep_dead_runs`."""
    from . import hostprobe, teardown

    answers = {"gone": subprocess.CompletedProcess(["ps"], 1, "", ""),
               "error": subprocess.CompletedProcess(["ps"], 1, "", "ps: Invalid process id: x"),
               "crash": subprocess.CompletedProcess(["ps"], 2, "", ""),
               "alive": subprocess.CompletedProcess(["ps"], 0, "/usr/bin/python3 x\n", "")}
    chosen = ["gone"]
    monkeypatch.setattr(hostprobe, "run", lambda argv, timeout_s=15.0: answers[chosen[0]])
    problems: list[str] = []
    if hostprobe.process_args(4242) is not None or hostprobe.process_cwd(4242) is not None or hostprobe.open_files(4242):
        problems.append("proof_pid_probes.gone_is_none")
    if teardown.owner_dead(4242)[0] is not True:
        problems.append("proof_pid_probes.sweep_dead_owner_is_dead")
    chosen[0] = "alive"
    if hostprobe.process_args(4242) != "/usr/bin/python3 x" or teardown.owner_dead(4242)[0] is not False:
        problems.append("proof_pid_probes.alive_is_alive")
    for label in ("error", "crash"):
        chosen[0] = label
        for probe in (hostprobe.process_args, hostprobe.process_cwd, hostprobe.open_files):
            try:
                probe(4242)
                problems.append(f"proof_pid_probes.{label}_is_unknown_not_gone: {probe.__name__} answered")
            except hostprobe.ProbeUnknown:
                pass
        if teardown.owner_dead(4242)[0] is not False:
            problems.append(f"proof_pid_probes.sweep_unknown_owner_is_not_dead: {label}")
    assert not problems, f"pid probes: {problems}"


def test_proof_unseeded_excuse_is_list_sessions_only() -> None:
    """Review N3: the runner's post-lane Z2 scan excuses exactly `list-sessions` on the product's
    default runner socket in the UNSEEDED log; `kill-session` / `kill-server` there are violations.
    The argv are data in a temp log (nothing is executed)."""
    from shepherd.runner.tmux_cmd import DEFAULT_SOCKET

    from . import run as runner
    from .tmuxctl import unseeded_excused

    problems: list[str] = []
    listed = [TMUX, "-L", DEFAULT_SOCKET, "list-sessions", "-F", "#{session_name}"]
    for label, argv in (("kill_session_on_default_runner_is_flagged", [TMUX, "-L", DEFAULT_SOCKET, "kill-session", "-t", "x"]),
                        ("kill_server_on_default_runner_is_flagged", [TMUX, "-uL", DEFAULT_SOCKET, "kill-server"]),
                        ("list_sessions_on_user_socket_is_flagged", [TMUX, "-L", "shepherd", "list-sessions"])):
        if unseeded_excused(argv, DEFAULT_SOCKET):
            problems.append(f"proof_unseeded.{label}")
    if not unseeded_excused(listed, DEFAULT_SOCKET):
        problems.append("proof_unseeded.list_sessions_on_default_runner_is_excused")
    with tempfile.TemporaryDirectory(prefix="qa6unseeded-", dir="/tmp") as scratch:
        run = RunContext(pid=424242, run_id="qa6-guard", run0=Path(scratch), run_dir=Path(scratch) / "report")
        run.unseeded_tmux_argv_log.parent.mkdir(parents=True)
        run.unseeded_tmux_argv_log.write_text(json.dumps(listed) + "\n", encoding="utf-8")
        if runner.z2_offenders(run):
            problems.append(f"proof_unseeded.runner_excuses_list_sessions: {runner.z2_offenders(run)}")
        kill = [TMUX, "-L", DEFAULT_SOCKET, "kill-session", "-t", "x"]
        with open(run.unseeded_tmux_argv_log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(kill) + "\n")
        if len(runner.z2_offenders(run)) != 1:
            problems.append(f"proof_unseeded.runner_flags_kill_session_on_default_runner: {runner.z2_offenders(run)}")
    assert not problems, f"unseeded excuse: {problems}"


def test_proof_z3_servers_and_signalled() -> None:
    """Review N5: Z3 compares tmux SERVERS (a `tmux` whose parent is launchd), never every tmux
    client, and fails when the teardown signalled a pid that was alive at baseline. Pure (planted
    `ps` text and planted lists)."""
    from .hostprobe import signalled_baseline_pids, tmux_servers_from_table

    table = ("  1080     1 /opt/homebrew/bin/tmux\n"
             "  2001   733 /opt/homebrew/bin/tmux\n"
             "  2002     1 /usr/bin/python3\n"
             "  2003     1 tmux\n")
    problems: list[str] = []
    servers = tmux_servers_from_table(table)
    if servers != [1080, 2003]:
        problems.append(f"proof_z3.clients_are_not_servers: {servers}")
    baseline: dict[str, object] = {"tmux_pids": [1080, 2001], "tmux_server_pids": [1080],
                                   "shepherd_daemons": [[3001, "shepherd-controld"]], "port_owner_pids": [4001]}
    if signalled_baseline_pids([5001, 5002], baseline):
        problems.append("proof_z3.run_pids_are_not_baseline_pids")
    if signalled_baseline_pids([5001, 3001, 1080], baseline) != [1080, 3001]:
        problems.append(f"proof_z3.signalled_baseline_pid_is_seen: {signalled_baseline_pids([5001, 3001, 1080], baseline)}")
    assert not problems, f"z3: {problems}"


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


# ----- the settings guard (U2, INC-3) ------------------------------------------------------------

#: Independent source for U2: the value the owner named, spelled here from the plan (env-plan §3 / U2)
#: rather than read back from `paths`, so a drifted constant cannot agree with itself. Re-named by the
#: owner on 2026-09-27 (INC-3 accepted, ruling 28): the value below replaced 28067dc4…1b4c.
U2_OWNER_SHA = "f99112b6db8b5adb5014792c84e75cac806ec12ecb73a2dee3a1ef95a7f1c52b"
_SHA_A = "a" * 64
_SHA_B = "b" * 64


def test_proof_settings_mid_run_change_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """U2: after every lane the REAL `after_lane_stop` compares the sha against its run-start value.

    The sha reader is replaced by a planted value (the real file is never opened, never written);
    the host snapshot, link, ~/.local and Z2 checks are replaced by clean answers, so the settings
    check is the only thing that can stop the lane. Nothing is started.
    """
    import argparse

    from . import hostprobe, realclaude
    from . import run as runner

    current = [_SHA_A]
    monkeypatch.setenv(paths.ENV_RUN_SETTINGS_SHA, _SHA_A)
    monkeypatch.setattr(hostprobe, "sha256", lambda _path: current[0])
    monkeypatch.setattr(runner, "snapshot_host", lambda _run, _label: None)
    monkeypatch.setattr(realclaude, "link_change", lambda _run_dir: None)
    monkeypatch.setattr(runner, "local_tree_problem", lambda _run, _baseline, _snapshot: None)
    monkeypatch.setattr(runner, "z2_offenders", lambda _run: [])
    run, _root = _guard_run()
    state = runner.RunState(args=argparse.Namespace(report_dir=Path("/nonexistent-qa6-guard-report-dir"), lane=[]),
                            run=run, baseline=_dummy_baseline(), reached="T4", selected={1})
    problems: list[str] = []
    stopped = runner.after_lane_stop(state, 3, "sub")
    if stopped is not None or not runner.settings_ok():
        problems.append(f"proof_settings.unchanged_since_start_does_not_stop: {stopped!r}")
    current[0] = _SHA_B
    stopped = runner.after_lane_stop(state, 3, "sub")
    if stopped is None or "settings sha changed during wave 3 lane sub" not in stopped or "U2" not in stopped:
        problems.append(f"proof_settings.mid_run_change_stops: {stopped!r}")
    current[0] = U2_OWNER_SHA  # restored to the owner's value mid-run: still a change since run start
    stopped = runner.after_lane_stop(state, 3, "sub")
    if stopped is None or "settings sha changed" not in stopped:
        problems.append(f"proof_settings.owner_value_is_not_the_invariant: {stopped!r}")
    assert not problems, f"settings mid-run guard: {problems}"


def test_proof_settings_env_unset_uses_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare pytest (no runner export) expects the owner's value; the runner's capture replaces an
    inherited value with its own measurement and every lane env carries it. Pure (planted sha)."""
    from . import hostprobe
    from . import run as runner

    problems: list[str] = []
    monkeypatch.delenv(paths.ENV_RUN_SETTINGS_SHA, raising=False)
    if paths.expected_settings_sha() != U2_OWNER_SHA:
        problems.append(f"proof_settings.env_unset_uses_owner: {paths.expected_settings_sha()}")
    if paths.expected_settings_sha({}) != U2_OWNER_SHA or paths.expected_settings_sha(
            {paths.ENV_RUN_SETTINGS_SHA: ""}) != U2_OWNER_SHA:
        problems.append("proof_settings.empty_env_uses_owner")
    if paths.expected_settings_sha({paths.ENV_RUN_SETTINGS_SHA: _SHA_A}) != _SHA_A:
        problems.append("proof_settings.env_set_is_the_run_start")
    monkeypatch.setenv(paths.ENV_RUN_SETTINGS_SHA, "stale-inherited-from-the-caller")
    monkeypatch.setattr(hostprobe, "sha256", lambda _path: _SHA_B)
    captured = runner.capture_settings_sha()
    if captured != _SHA_B or os.environ.get(paths.ENV_RUN_SETTINGS_SHA) != _SHA_B or paths.expected_settings_sha() != _SHA_B:
        problems.append(f"proof_settings.capture_replaces_inherited_value: {captured} "
                        f"{os.environ.get(paths.ENV_RUN_SETTINGS_SHA)}")
    run, _root = _guard_run()
    exported = runner.lane_env(run, Path("/nonexistent-qa6-guard-report-dir"), 2, "unit").get(paths.ENV_RUN_SETTINGS_SHA)
    if exported != _SHA_B:
        problems.append(f"proof_settings.lane_env_exports_run_start: {exported!r}")
    assert not problems, f"settings expectation: {problems}"


def test_proof_settings_owner_mismatch_warns() -> None:
    """T1: unchanged-since-start passes; a sha other than the owner's adds a visible WARN row (never
    silence, never a stop); a change since run start stops. Pure."""
    from .preflight import settings_checks, warnings

    problems: list[str] = []
    rows = settings_checks(_SHA_B, _SHA_B, U2_OWNER_SHA)
    warned = [row for row in rows if row.warn]
    expected_line = f"owner-named sha (U2) differs: expected f99112b6…, actual {_SHA_B} — INC-3"
    if not warned or warned[0].warn != expected_line or warned[0].as_json().get("result") != "warn" \
            or not warnings(rows) or expected_line not in warnings(rows)[0]:
        problems.append(f"proof_settings.owner_mismatch_warns: {[row.as_json() for row in rows]}")
    if not all(row.ok and not row.stop for row in rows):
        problems.append(f"proof_settings.owner_mismatch_does_not_stop: {[row.as_json() for row in rows]}")
    same = settings_checks(U2_OWNER_SHA, U2_OWNER_SHA, U2_OWNER_SHA)
    if len(same) != 1 or not same[0].ok or warnings(same):
        problems.append(f"proof_settings.owner_match_is_silent: {[row.as_json() for row in same]}")
    changed = settings_checks(_SHA_B, _SHA_A, U2_OWNER_SHA)
    if changed[0].ok or not changed[0].stop or changed[0].as_json().get("result") != "fail":
        problems.append(f"proof_settings.change_since_start_stops_preflight: {changed[0].as_json()}")
    assert not problems, f"preflight settings rows: {problems}"


def test_proof_preflight_warn_is_published(monkeypatch: pytest.MonkeyPatch) -> None:
    """The REAL `run._finish` publishes the preflight's WARN lines in the run file, the markdown and the
    history line, and they do not change the status. The host-touching finalizer steps are recorders;
    everything from `fill_missing` to `write_report` is real, writing into a temp report dir."""
    import argparse

    from . import run as runner

    for name in ("_copy_ledgers", "_remove_worktree", "_post_teardown_checks", "_teardown"):
        monkeypatch.setattr(runner, name, lambda *_a: None)
    line = f"preflight T1 real settings sha (U2): owner-named sha (U2) differs: expected f99112b6…, actual {_SHA_B} — INC-3"
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qa6warn-", dir="/tmp") as scratch:
        report_dir = Path(scratch) / "runs"
        statuses: dict[str, object] = {}
        for run_id, warned in (("qa6-guard-warn", [line]), ("qa6-guard-nowarn", [])):
            run = RunContext(pid=424242, run_id=run_id, run0=Path(scratch) / "run0-absent", run_dir=report_dir / run_id)
            (run.run_dir / "records").mkdir(parents=True)
            state = runner.RunState(args=argparse.Namespace(report_dir=report_dir, lane=[]), run=run,
                                    baseline=_dummy_baseline(), reached="T4", selected={1}, warnings=warned)
            runner._finish(state, run_id, None)
            payload = json.loads((report_dir / f"{run_id}.json").read_text(encoding="utf-8"))
            statuses[run_id] = payload.get("status")
            if warned:
                markdown = (run.run_dir / "report.md").read_text(encoding="utf-8")
                history = [json.loads(h) for h in (report_dir / "qa6-history.jsonl").read_text(encoding="utf-8").splitlines()
                           if h.strip()]
                mine: dict[str, object] = next((h for h in history if h.get("run_id") == run_id), {})
                if payload.get("warnings") != [line] or f"WARN {line}" not in markdown or mine.get("warnings") != [line]:
                    problems.append(f"proof_settings.report_publishes_warn: warnings={payload.get('warnings')} "
                                    f"history={mine.get('warnings')} md_has_line={f'WARN {line}' in markdown}")
        if statuses["qa6-guard-warn"] != statuses["qa6-guard-nowarn"]:
            problems.append(f"proof_settings.warn_does_not_change_status: {statuses}")
    assert not problems, f"preflight WARN publication: {problems}"


# ----- oracle self-checks (qa6-rulings P1 REM-FIX 1) -----------------------------------------------


def test_guard_d12_unknown_is_not_a_classifier_fallback() -> None:
    """D12's `unknown` case passes only on a rule's answer, never on the classifier's own fallbacks.

    `verdict.py` answers `(0.0, "mechanical")` for a rule's `unknown` AND for an unreadable record
    or a turn with no ending; only `why` tells them apart.
    """
    from shepherd.signals.verdict import WHY_NO_ENDING, WHY_UNREADABLE

    from .sub.test_wave3_3_hooks import check_decision

    def failed(why: str) -> list[str]:
        rec = Recorder("D12-guard")
        check_decision(rec, "unknown", {"confidence": 0.0, "decided_by": "mechanical", "why": why})
        return [clause.name for clause in rec.failed]

    assert failed("the engine reported this stop as unknown") == []
    assert failed(WHY_UNREADABLE), "an unreadable stop record passed as a rule's unknown"
    assert failed(WHY_NO_ENDING), "a turn with no ending passed as a rule's unknown"


def test_guard_u7_legend_probe_cannot_compare_with_itself() -> None:
    """U7's legend-text probe sits inside a sentinel-coloured span, and the oracle refuses the sentinel.

    Inside the `.legend-key` alone, a mix that fails to resolve inherits the key's own colour and the
    clause compares the value under test with itself. The sentinel breaks that inheritance.
    """
    from .sub import test_wave6_2_flock as flock

    assert flock.PROBE_SENTINEL == "rgb(1, 2, 3)"
    wrapper = f"s.style.color = '{flock.PROBE_SENTINEL}'"
    assert wrapper in flock.PROBE_JS, "the probe is not wrapped in the sentinel span"
    assert "s.appendChild(p)" in flock.PROBE_JS and "e.appendChild(s)" in flock.PROBE_JS
    source = Path(flock.__file__).read_text(encoding="utf-8")
    assert "ui.legend_probe_resolved." in source and "!= PROBE_SENTINEL" in source, \
        "no clause refuses a probe that kept the sentinel colour"


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
                "sse_rig_parse_failure", "sse_rig_eof_after_control", "mutations_control", "auditprobe_absent",
                # remfix 3 (hunter N1-N6, review N1-N5)
                "report_torn_records", "run_problem_reader_torn", "run_last_resort", "report_crash_red",
                "httpclient_socket_wrap", "verdict_unreachable_after_answer", "httpclient_answer_epoch",
                "teardown_incremental", "teardown_ledger_torn", "hostprobe_pid_probe_unknown", "teardown_sweep_unknown",
                "shim_exec_warning", "shim_relative_S", "tmuxctl_relative_S", "paths_ascii_digits",
                "tmuxctl_unseeded_verb", "hostprobe_tmux_servers", "hostprobe_signalled_baseline",
                # re-qa-build round 5 (INC-3: the run-start settings sha)
                "run_settings_mid_run", "run_settings_owner_pin", "run_settings_lane_export",
                "paths_owner_fallback", "preflight_owner_warn", "report_warn_published"}
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
