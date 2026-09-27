"""Wave 2, UNIT lane: H1-H5 — hook install/uninstall at the `hooks_config` module seam.

The product has no working caller for install (test-plan Difference 2: the CLI
cannot reach the tool, C-1; there is no HTTP route), so this tests the only code
that exists and says so. Every file is a sandbox file under the run root; the
real settings sha is re-read after each scenario (PP-8).

The dispatch entry is built exactly as the product builds it:
`build_hook_entry(host.control_socket("sessiond"), host.hook_dispatch(plan))`
with a `MacHost` whose `TMPDIR` is a sandbox instance's.

H1's written file is copied to `<run0>/artifacts/h1-settings.json` for C2
(`doctor --settings`, wave 2, sub lane) and C4 (wave 3): the intra-wave order
H1 → C2 is the lane order unit → cli → sub (test-plan §3, review pass 2
finding 11).
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from shepherd.engines.claude_code.events import SUBSCRIBED_EVENTS
from shepherd.engines.claude_code.hookd_command import HookEntry, build_hook_entry
from shepherd.engines.claude_code.hooks_config import (
    BACKUP_SUFFIX,
    InstallResult,
    install_hooks,
    uninstall_hooks,
)
from shepherd.host.mac import MacHost

from .. import hostprobe, paths
from ..sandbox import RunContext, mint_instance
from ..scenario import scenario
from ..verdict import Recorder

H1_ARTIFACT = "h1-settings.json"


@dataclass
class HooksEnv:
    root: Path
    entry: HookEntry
    socket: Path


@pytest.fixture(scope="module")
def hooks_env(qa6_run: RunContext) -> Iterator[HooksEnv]:
    instance = mint_instance(qa6_run)
    host = MacHost(environ={"HOME": str(instance.home), "TMPDIR": str(instance.tmpdir)})
    plan = host.control_socket("sessiond")
    entry = build_hook_entry(plan, host.hook_dispatch(plan))
    root = qa6_run.run0 / "hooks"
    root.mkdir(exist_ok=True)
    yield HooksEnv(root=root, entry=entry, socket=plan.path)


def expected_command(sock: Path) -> str:
    return f"perl -MTime::HiRes=alarm -e 'alarm 0.25; exec @ARGV or exit 0' nc -U {shlex.quote(str(sock))} || true"


def managed_value(command: str) -> list[dict[str, object]]:
    return [{"matcher": "*", "_shepherd_managed": True,
             "hooks": [{"type": "command", "command": command, "timeout": 5, "_shepherd_managed": True}]}]


def load(path: Path) -> dict[str, object]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError(f"{path} is not a JSON object")
    return {str(k): v for k, v in decoded.items()}


def backups(directory: Path) -> list[str]:
    return sorted(child.name for child in directory.iterdir() if BACKUP_SUFFIX in child.name)


def sha_clause(rec: Recorder) -> None:
    rec.equal("files.real_settings_sha", paths.expected_settings_sha(), hostprobe.sha256(paths.REAL_SETTINGS))


USER_CONTENT: dict[str, object] = {
    "model": "sonnet",
    "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(rm:*)"]},
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-own-hook"}]}]},
}


@scenario("H1")
def test_h1_install_into_missing_file(hooks_env: HooksEnv, qa6_run: RunContext, rec: Recorder) -> None:
    directory = hooks_env.root / "h1"
    directory.mkdir()
    target = directory / "settings.json"
    rec.check("given.absent", not target.exists(), "settings.json absent", target.exists())
    result = install_hooks(target, hooks_env.entry)
    rec.equal("api.refused_reason", None, result.refused_reason)
    rec.equal("api.backup_path_is_settings_path", str(target), str(result.backup_path))
    rec.check("files.exists", target.exists(), "exists", target.exists())
    if target.exists():
        settings = load(target)
        hooks = settings.get("hooks")
        keys = sorted(hooks) if isinstance(hooks, dict) else hooks
        rec.equal("files.one_key_per_subscribed_event", sorted(SUBSCRIBED_EVENTS), keys)
        rec.check("files.no_worktree_create", isinstance(hooks, dict) and "WorktreeCreate" not in hooks,
                  "WorktreeCreate absent", keys)
        command = expected_command(hooks_env.socket)
        rec.equal("files.command_is_the_macos_dispatch", command, hooks_env.entry.command)
        wrong = {event: value for event, value in (hooks.items() if isinstance(hooks, dict) else [])
                 if value != managed_value(command)}
        rec.check("files.every_value_exact", not wrong, managed_value(command), list(wrong.items())[:2])
        (qa6_run.artifacts / H1_ARTIFACT).write_bytes(target.read_bytes())
        (qa6_run.artifacts / "h1-dispatch.json").write_text(
            json.dumps({"command": hooks_env.entry.command, "socket": str(hooks_env.socket)}), encoding="utf-8")
    rec.equal("files.no_backup", [], backups(directory))
    sha_clause(rec)
    rec.finish()


@scenario("H2")
def test_h2_reinstall_is_byte_idempotent(hooks_env: HooksEnv, rec: Recorder) -> None:
    directory = hooks_env.root / "h2"
    directory.mkdir()
    target = directory / "settings.json"
    target.write_text(json.dumps(USER_CONTENT, indent=2) + "\n", encoding="utf-8")
    first = install_hooks(target, hooks_env.entry)
    i1 = target.read_bytes()
    second = install_hooks(target, hooks_env.entry)
    i2 = target.read_bytes()
    rec.equal("api.first_refused", None, first.refused_reason)
    rec.equal("api.second_refused", None, second.refused_reason)
    rec.check("files.i2_equals_i1", i1 == i2, "byte-identical", f"{len(i1)} vs {len(i2)} bytes")
    settings = load(target)
    hooks = settings.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    user_hooks = USER_CONTENT["hooks"]
    foreign = user_hooks["PreToolUse"][0] if isinstance(user_hooks, dict) else None
    rec.check("files.foreign_first_and_equal", isinstance(pre, list) and bool(pre) and pre[0] == foreign,
              "the foreign PreToolUse entry first, JSON-equal", pre[:2] if isinstance(pre, list) else pre)
    rec.equal("files.model_kept", USER_CONTENT["model"], settings.get("model"))
    rec.equal("files.permissions_kept", USER_CONTENT["permissions"], settings.get("permissions"))
    sha_clause(rec)
    rec.finish()


@scenario("H3")
def test_h3_uninstall_removes_only_ours(hooks_env: HooksEnv, rec: Recorder) -> None:
    target = hooks_env.root / "h2" / "settings.json"
    if not target.exists():
        rec.block("given.h2_state", "H2's file is absent")
        rec.finish()
        return
    first = uninstall_hooks(target)
    after_first = target.read_bytes()
    rec.equal("api.first_refused", None, first.refused_reason)
    rec.equal("files.json_equal_to_original", USER_CONTENT, load(target))
    second = uninstall_hooks(target)
    rec.equal("api.second_refused", None, second.refused_reason)
    rec.check("files.second_byte_identical", target.read_bytes() == after_first, "byte-identical to the first", "")
    rec.equal("api.second_removed_zero", 0, second.events_installed)
    sha_clause(rec)
    rec.finish()


#: Non-canonical on purpose: 4-space indent, trailing newline, unsorted keys.
H4_ORIGINAL = b'{\n    "zeta": 1,\n    "model": "opus",\n    "alpha": {\n        "b": 2,\n        "a": 1\n    }\n}\n'


@scenario("H4")
def test_h4_original_survives_two_installs(hooks_env: HooksEnv, rec: Recorder) -> None:
    directory = hooks_env.root / "h4"
    directory.mkdir()
    target = directory / "settings.json"
    target.write_bytes(H4_ORIGINAL)
    install_hooks(target, hooks_env.entry)
    install_hooks(target, hooks_env.entry)
    held = [name for name in backups(directory) if (directory / name).read_bytes() == H4_ORIGINAL]
    rec.check("files.clause1_a_backup_holds_original", bool(held),
              "after the second install some backup the product wrote holds bytes O",
              {name: (directory / name).read_bytes()[:80] for name in backups(directory)})
    uninstall_hooks(target)
    # Ruling 7 (BC-20): uninstall removes only our entries and restores no bytes (a byte
    # restore would lose the user's edits since install); the backup keeps O.
    backup = directory / ("settings.json" + BACKUP_SUFFIX)
    after = load(target)
    backup_bytes = backup.read_bytes() if backup.exists() else None
    rec.check("files.clause2_uninstall_removes_only_ours",
              after == json.loads(H4_ORIGINAL) and backup_bytes == H4_ORIGINAL,
              "after the uninstall the file is JSON-equal to O and the backup still holds bytes O",
              {"file": after, "backup": (backup_bytes or b"")[:160]})
    sha_clause(rec)
    rec.finish()


INVALID: tuple[tuple[str, bytes | None], ...] = (
    ("brace", b"{"),
    ("array", b"[]"),
    ("hooks_array", b'{"hooks": []}'),
    ("stop_string", b'{"hooks": {"Stop": "x"}}'),
    ("mode_000", b'{"model": "x"}\n'),
)


#: Ruling 23 (SD-10): an event value that is not an array of matchers is left untouched and
#: reported as a warning; the other events are installed. So this case is a partial install.
PARTIAL_INSTALL_CASE = "stop_string"


def stop_string_clauses(rec: Recorder, case: Path, content: bytes, result: InstallResult) -> None:
    """H5 `stop_string`: installed with a warning naming `Stop`, `Stop` still `"x"`, O backed up."""
    target = case / "settings.json"
    rec.equal(f"api.{PARTIAL_INSTALL_CASE}_installed", None, result.refused_reason)
    rec.check(f"api.{PARTIAL_INSTALL_CASE}_warning_names_stop",
              any("Stop" in warning for warning in result.warnings),
              "a warning naming Stop", list(result.warnings))
    hooks = load(target).get("hooks")
    rec.equal(f"files.{PARTIAL_INSTALL_CASE}_stop_untouched", "x",
              hooks.get("Stop") if isinstance(hooks, dict) else hooks)
    backup = case / ("settings.json" + BACKUP_SUFFIX)
    rec.equal(f"files.{PARTIAL_INSTALL_CASE}_backup_holds_original", content,
              backup.read_bytes() if backup.exists() else None)


@scenario("H5")
def test_h5_invalid_settings_refused_and_never_written(hooks_env: HooksEnv, rec: Recorder) -> None:
    """The refusal cases are refused and never written; `stop_string` is a partial install (ruling 23)."""
    directory = hooks_env.root / "h5"
    directory.mkdir()
    for name, content in INVALID:
        case = directory / name
        case.mkdir()
        target = case / "settings.json"
        target.write_bytes(content or b"")
        if name == "mode_000":
            target.chmod(0)
        before_mtime = target.stat().st_mtime_ns
        try:
            result = install_hooks(target, hooks_env.entry)
            refusal: str | None = result.refused_reason
            raised = ""
        except OSError as error:  # a raise is not the refusal the plan asks for; recorded as such
            refusal, raised = None, repr(error)
        finally:
            if name == "mode_000":
                target.chmod(0o600)  # H5 Cleanup: restore the mode
        if name == PARTIAL_INSTALL_CASE and not raised:
            stop_string_clauses(rec, case, content or b"", result)
            continue
        rec.check(f"api.{name}_refused", refusal is not None and bool(refusal.strip()),
                  "a refusal naming the problem (returned, not raised)", refusal or raised)
        rec.equal(f"files.{name}_bytes_unchanged", content, target.read_bytes())
        rec.equal(f"files.{name}_mtime_unchanged", before_mtime, target.stat().st_mtime_ns)
        rec.equal(f"files.{name}_no_backup", [], backups(case))
    control_dir = directory / "empty"
    control_dir.mkdir()
    control = control_dir / "settings.json"
    control.write_bytes(b"")
    result = install_hooks(control, hooks_env.entry)
    rec.equal("api.empty_control_installed", None, result.refused_reason)
    rec.check("files.empty_control_written", control.stat().st_size > 0, "installed", control.stat().st_size)
    sha_clause(rec)
    rec.finish()
