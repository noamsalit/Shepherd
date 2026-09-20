"""T17: the `shepherd` command — the second L5 consumer (D19, D35, ADR-3).

`cli/` is a consumer like any other: it reaches capabilities through `invoke()`
and it imports nothing below L4. The one thing it reads directly is the host
seam (L2), because `doctor`'s whole job is to report platform facts and a fact
laundered through a tool would be a fact nobody could check.

Exit codes are part of the contract — a CLI that always exits 0 cannot be
scripted:

* `0` the command did what it said;
* `1` the command failed, or `doctor` found something a human must fix;
* `64` the arguments were wrong (`sysexits.h` EX_USAGE).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TextIO

from shepherd.cli.commands import (
    Cli,
    run_doctor,
    run_install_hooks,
    run_status,
    run_uninstall_hooks,
)
from shepherd.cli.replay import run_replay
from shepherd.host.base import HostPlatform
from shepherd.host.detect import detect_host
from shepherd.toolsurface.registry import registered_tools
from shepherd.toolsurface.tools_engine import register_engine_tools_for
from shepherd.toolsurface.types import Audience, CallerContext

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 64

CALLER_ID = "cli"

#: The control socket `doctor` reports on. One name, so what `doctor` prints and
#: what the installer would write are the same plan.
SOCKET_NAME = "sessiond"

COMMANDS: tuple[str, ...] = (
    "status",
    "doctor",
    "install-hooks",
    "uninstall-hooks",
    "replay",
    "recompute",
)

#: `recompute` was M1's named stub for this capability, and its refusal text said
#: "nothing in this build replays a session's history". That sentence stopped
#: being true the day `replay` landed (review finding A2), and a CLI that keeps
#: asserting the absence of a capability it has is the same defect as one that
#: claims a capability it lacks. It is an **alias**, not a second command: one
#: implementation, so the two can never drift.
ALIASES: Mapping[str, str] = MappingProxyType({"recompute": "replay"})

USAGE = """usage: shepherd <command> [options]

commands:
  status                              the fleet, ordered by state
  doctor                              what this host can and cannot do
  install-hooks --settings PATH       merge our dispatcher entry into PATH
  uninstall-hooks --settings PATH     remove exactly our entries from PATH
  replay [--since DATE] [--apply]     re-run the current rules over the stop log
  recompute                           an alias of replay

options:
  --settings PATH   the settings file to read or change. Required, always:
                    there is no default, so no run of this command can reach
                    a file you did not name.
  --dry-run         print what would change and change nothing.
  --yes             apply the change. Without it, every write is a dry run.
  --since DATE      replay only stops on or after this date (YYYY-MM-DD).
  --apply           replay: overwrite the stop columns. Without it the diff is
                    still written and no column changes.
"""

SETTINGS_FLAG = "--settings"
SINCE_FLAG = "--since"

FLAGS_WITH_VALUES: tuple[str, ...] = (SETTINGS_FLAG, SINCE_FLAG)


@dataclass(frozen=True)
class Options:
    """One parsed command line."""

    command: str
    settings_path: str | None
    dry_run: bool
    assume_yes: bool
    since: str | None
    apply: bool


def parse(argv: Sequence[str]) -> tuple[Options | None, str]:
    """`(options, problem)`. A problem is an actionable sentence, never a trace."""
    if not argv:
        return None, "no command given"
    command = ALIASES.get(argv[0], argv[0])
    if command not in COMMANDS:
        return None, f"unknown command {argv[0]!r}"
    values: dict[str, str] = {}
    dry_run = False
    assume_yes = False
    apply_now = False
    rest = list(argv[1:])
    while rest:
        token = rest.pop(0)
        if token in FLAGS_WITH_VALUES:
            if not rest:
                return None, f"{token} needs a value"
            values[token] = rest.pop(0)
        elif token == "--dry-run":
            dry_run = True
        elif token == "--yes":
            assume_yes = True
        elif token == "--apply":
            apply_now = True
        else:
            return None, f"unknown option {token!r}"
    if dry_run and assume_yes:
        return None, "--dry-run and --yes ask for opposite things"
    return (
        Options(
            command=command,
            settings_path=values.get(SETTINGS_FLAG),
            dry_run=dry_run,
            assume_yes=assume_yes,
            since=values.get(SINCE_FLAG),
            apply=apply_now,
        ),
        "",
    )


def main(
    argv: Sequence[str],
    *,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    host: HostPlatform | None = None,
    correlation_id: str | None = None,
) -> int:
    """Parse, dispatch, return an exit code. Never raises on bad input."""
    options, problem = parse(argv)
    if options is None:
        print(f"shepherd: {problem}", file=err)
        print(USAGE, file=err, end="")
        return EXIT_USAGE
    cli = Cli(
        host=detect_host() if host is None else host,
        out=out,
        err=err,
        ctx=CallerContext(
            audience=Audience.HUMAN,
            caller_id=CALLER_ID,
            correlation_id=uuid.uuid4().hex if correlation_id is None else correlation_id,
        ),
        socket_name=SOCKET_NAME,
    )
    register_local_reads(cli.host)
    if options.command == "status":
        return run_status(cli)
    if options.command == "doctor":
        return run_doctor(cli, options.settings_path)
    if options.command == "install-hooks":
        return run_install_hooks(
            cli,
            options.settings_path,
            dry_run=options.dry_run,
            assume_yes=options.assume_yes,
        )
    if options.command == "uninstall-hooks":
        return run_uninstall_hooks(cli, options.settings_path, assume_yes=options.assume_yes)
    return run_replay(cli, options.since, options.apply)


def register_local_reads(host: HostPlatform) -> None:
    """The two facts a standalone `shepherd` process can answer for itself.

    `cli/` reaches capabilities through `invoke()` and nothing else (D19, D35),
    so with an empty registry every tool-backed line is *unknown* — honest, but
    not useful for the one command a user runs when something is wrong. The
    schema version and the engine version are read-only local projections that
    open no store and write nothing (§7 migration rule 3), so this process
    registers them for itself.

    A process that was handed a tool surface by someone else keeps exactly that
    one: this is a fallback for the empty case, never a merge. Re-registering a
    name is an error rather than a silent swap (ADR-7), and a consumer quietly
    adding a tool to a surface it did not compose is how a registry drifts.
    """
    if registered_tools():
        return
    register_engine_tools_for(host.dirs().data_dir)


def run() -> int:
    """The console entry point's body."""
    return main(sys.argv[1:])


if __name__ == "__main__":  # pragma: no cover - the process entry point
    raise SystemExit(run())
