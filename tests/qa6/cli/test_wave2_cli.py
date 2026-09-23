"""Wave 2, CLI lane (no daemon): C3 (install-hooks dry run, then --yes) and C5 (usage errors).

The shipped `.venv/bin/shepherd` as a subprocess with the allow-listed sandbox
env of a fresh instance root (no controld is started: C3 and C5 need none).
C3 keeps the spec's oracle and is predicted to FAIL (C-1: the tool is not
registered in the CLI process).
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from .. import hostprobe, paths
from ..sandbox import InstanceRoot, RunContext, mint_instance, sandbox_env
from ..scenario import scenario
from ..verdict import Recorder

CLI_TIMEOUT_S = 30.0


@dataclass
class CliEnv:
    root: InstanceRoot
    env: dict[str, str]
    hooks: Path


@dataclass(frozen=True)
class Ran:
    argv: tuple[str, ...]
    rc: int
    stdout: str
    stderr: str


@pytest.fixture(scope="module")
def cli_env(qa6_run: RunContext) -> Iterator[CliEnv]:
    root = mint_instance(qa6_run)
    hooks = qa6_run.run0 / "hooks"
    hooks.mkdir(exist_ok=True)
    yield CliEnv(root=root, env=sandbox_env(qa6_run, root), hooks=hooks)


def shepherd(cli: CliEnv, *args: str) -> Ran:
    argv = (str(paths.SHEPHERD_BIN), *args)
    done = subprocess.run(list(argv), env=cli.env, cwd=str(cli.root.cwd), capture_output=True, text=True,
                          timeout=CLI_TIMEOUT_S, check=False)
    return Ran(argv, done.returncode, done.stdout, done.stderr)


@scenario("C3")
def test_c3_install_hooks_dry_run_then_yes(cli_env: CliEnv, rec: Recorder) -> None:
    directory = cli_env.hooks / "c3"
    directory.mkdir()
    target = directory / "settings.json"
    dry = shepherd(cli_env, "install-hooks", "--settings", str(target), "--dry-run")
    rec.note(f"dry run: rc={dry.rc} stdout={dry.stdout!r} stderr={dry.stderr!r}")
    rec.equal("proc.dry_run_exit", 0, dry.rc)
    rec.check("proc.dry_run_would_install", "would install" in dry.stdout, "stdout contains 'would install'", dry.stdout[:300])
    rec.check("proc.dry_run_changed_nothing", "this run changed nothing. Pass --yes to apply it." in dry.stdout,
              "the dry-run sentence", dry.stdout[:300])
    rec.check("files.absent_after_dry_run", not target.exists(), "absent", target.exists())
    rec.equal("logs.dry_run_stderr_empty", "", dry.stderr)
    applied = shepherd(cli_env, "install-hooks", "--settings", str(target), "--yes")
    rec.note(f"--yes: rc={applied.rc} stdout={applied.stdout!r} stderr={applied.stderr!r}")
    rec.equal("proc.yes_exit", 0, applied.rc)
    rec.check("proc.yes_installed", "installed" in applied.stdout, "stdout contains 'installed'", applied.stdout[:300])
    rec.check("files.managed_entries_after_yes", target.exists() and "_shepherd_managed" in target.read_text(encoding="utf-8"),
              "the managed entries (H1's shape)", target.exists())
    rec.equal("logs.yes_stderr_empty", "", applied.stderr)
    rec.equal("files.real_settings_sha", paths.EXPECTED_SETTINGS_SHA, hostprobe.sha256(paths.REAL_SETTINGS))
    rec.finish()


def usage_argvs(target: str) -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("empty", ()),
        ("unknown_command", ("frobnicate",)),
        ("dash_dash_help", ("--help",)),
        ("dash_h", ("-h",)),
        ("status_bogus_flag", ("status", "--bogus")),
        ("settings_without_value", ("install-hooks", "--settings")),
        ("dry_run_and_yes", ("install-hooks", "--settings", target, "--dry-run", "--yes")),
        ("invalid_since_date", ("replay", "--since", "2026-13-45")),
        ("install_hooks_no_settings", ("install-hooks",)),
    ]


PARSE_ERRORS = frozenset({"empty", "unknown_command", "dash_dash_help", "dash_h", "status_bogus_flag",
                          "settings_without_value", "dry_run_and_yes"})


@scenario("C5")
def test_c5_usage_errors_exit_64(cli_env: CliEnv, rec: Recorder) -> None:
    directory = cli_env.hooks / "c5"
    directory.mkdir()
    target = directory / "settings.json"
    for name, args in usage_argvs(str(target)):
        ran = shepherd(cli_env, *args)
        rec.note(f"{name}: argv={list(args)} rc={ran.rc} stdout={ran.stdout[:200]!r} stderr={ran.stderr[:300]!r}")
        rec.equal(f"proc.{name}_exit_64", 64, ran.rc)
        rec.equal(f"proc.{name}_stdout_empty", "", ran.stdout)
        rec.check(f"logs.{name}_prefix", ran.stderr.startswith("shepherd: "), "stderr begins 'shepherd: '", ran.stderr[:120])
        if name in PARSE_ERRORS:
            rec.check(f"logs.{name}_usage", "usage: shepherd <command>" in ran.stderr, "the usage text", ran.stderr[:200])
        if name == "dash_dash_help":
            rec.check("logs.help_names_unknown_command", "unknown command '--help'" in ran.stderr,
                      "names unknown command '--help' (O48)", ran.stderr[:200])
        if name == "dry_run_and_yes":
            rec.check("logs.names_both_flags", "--dry-run" in ran.stderr and "--yes" in ran.stderr,
                      "names --dry-run and --yes", ran.stderr[:200])
        if name == "install_hooks_no_settings":
            rec.check("logs.names_settings", "--settings" in ran.stderr, "names --settings", ran.stderr[:200])
        if name == "invalid_since_date":
            rec.check("logs.names_the_date_invalid", "2026-13-45" in ran.stderr and "invalid" in ran.stderr.lower(),
                      "names the date as invalid", ran.stderr[:300])
    rec.check("files.never_created", not target.exists(), "<f> never created", target.exists())
    rec.finish()
