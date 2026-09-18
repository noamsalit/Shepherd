"""T10 — the argv an owned Claude Code session is started with, the engine's
capability record, and where its binary is.

Module functions, not a `Protocol` with one implementation (DP6/N5, D9's own
mistake). Pure except `resolve_binary`, which searches `PATH`. The fourth member
M3 needs — the trust pre-flight — lives in `trust.py`: reading the engine's
config and building an argv are two jobs, and the 250-line cap said so (T10-R2).

The argv's shape is the gap-fill probe's, not a guess —
`<claude> --session-id <uuid> [--name <t>] [--model <m>] [--effort <e>] [-- <brief>]`,
every element a **separate word** (A9: one command string goes through `sh -c`,
which expanded `$()` and stripped the quotes), the brief behind `--` (A11: a
brief starting with `-` otherwise dies with `error: unknown option`), and the
whole command under the **measured** 16 324-byte ceiling (A10) — over which the
spawn is **refused**, never truncated, because half an instruction is worse than
none. No `--settings` is passed: §16's M3 spawns no queue workers, and the live
lane adds its own.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, replace
from pathlib import Path

from shepherd.core.runner import (
    TMUX_COMMAND_LIMIT_B, EngineCapabilities, RunnerRefusal, SessionSpec, command_size)

__all__ = ["SPAWN_RULES", "SpawnRule", "capabilities", "command_size",
           "resolve_binary", "spawn_argv"]

SESSION_ID_FLAG = "--session-id"
NAME_FLAG = "--name"
MODEL_FLAG = "--model"
EFFORT_FLAG = "--effort"

#: Everything after this is a positional, whatever it starts with.
SEPARATOR = "--"

BINARY_NAME = "claude"

# ----- the evidence table -----

@dataclass(frozen=True)
class SpawnRule:
    """One row: `evidence` is `<data-schemas.md section> · <what backs it>`, and
    `test_every_spawn_rule_cites_an_existing_section` (P-M3-16) asserts the section
    is really in the document and every capture cited is really on disk."""

    name: str
    evidence: str


_ARGV_SECTION = "Brief passed as argv through `tmux new-session` (`EngineAdapter.spawn_argv`)"
_TITLE_SECTION = "Session title: /rename and --name (custom-title, agent-name, session_title, pane_title)"
_START_SECTION = "SessionStart payload (TUI: startup, compact, fork, named spawn)"
_EFFORT_SECTION = "`--effort` flag: accepted values, invalid values, what reaches the API"
_ARGV_RUN = "gap-fill/argv-20260914T173100Z"
_LIMITS_RUN = "gap-fill/argv-limits-20260914T173342Z"
_SUPP_RUN = "tmux-tui/supp-20260914T155346Z"

SPAWN_RULES: tuple[SpawnRule, ...] = (
    SpawnRule(
        name=SESSION_ID_FLAG,
        evidence=(
            f"{_START_SECTION} · the hook's session_id equals the requested uuid: "
            f"{_SUPP_RUN}/02-sessionstart-and-sidecar.txt, {_SUPP_RUN}/spawn-cmd.txt"
        ),
    ),
    SpawnRule(
        name=NAME_FLAG,
        evidence=f"{_TITLE_SECTION} · spawned with --name: {_SUPP_RUN}/spawn-cmd.txt",
    ),
    SpawnRule(
        name=MODEL_FLAG,
        evidence=f"{_ARGV_SECTION} · pane_cmdline, byte-exact: {_ARGV_RUN}/results.json",
    ),
    SpawnRule(
        name=EFFORT_FLAG,
        evidence=(
            f"{_EFFORT_SECTION} · the ladder --help prints: "
            "gap-fill/effort-20260914T171533Z/claude-help.txt"
        ),
    ),
    SpawnRule(
        name=SEPARATOR,
        evidence=(
            f"{_ARGV_SECTION} · prompt_equals_brief true as argv words and false as one "
            f"command string: {_ARGV_RUN}/results.json; unknown option without the "
            f"separator: {_LIMITS_RUN}/claude-dash-brief.stderr"
        ),
    ),
    SpawnRule(
        name="brief size ceiling",
        evidence=(
            f"{_ARGV_SECTION} · largest accepted 16324, smallest rejected 16325: "
            f"{_LIMITS_RUN}/tmux-argv-limit.txt"
        ),
    ),
)


# ----- the capability record -----

#: §6's record for this engine. `can_set_title` is **`False`** — D29's literal.
#: DP1 recommends `True` for owned sessions and is **NOT APPLIED**; flipping it
#: needs the recorded approval the plan's Task 20 checkpoint describes.
#: `can_spawn` is `True` here because the engine itself can be started; the
#: pane-driver-absent degrade (D-5) is applied through `capabilities()`.
#:
#: **Private, and out of `__all__` (T10-R2).** Task 11's `Consumes` line names
#: this constant, so a builder following the plan literally would read the
#: un-degraded record and D-5 would never fire. `capabilities()` is the only way
#: out of this module.
_CLAUDE_CODE_CAPABILITIES = EngineCapabilities(
    can_spawn=True,
    can_steer=True,
    can_fork=True,
    can_set_title=False,
    has_hooks=True,
    effort_ladder=("low", "medium", "high", "xhigh", "max"),
    transcript_format="jsonl",
)


def capabilities(*, pane_driver_available: bool) -> EngineCapabilities:
    """The record with D-5's degrade applied: no pane driver, no owned spawn.
    The availability comes in as a value because *whether a pane can be opened* is
    the runner's fact and this module is the engine's."""
    return replace(_CLAUDE_CODE_CAPABILITIES, can_spawn=pane_driver_available)


# ----- the argv -----

def spawn_argv(spec: SessionSpec, binary: str, *, frame_bytes: int) -> list[str]:
    """The argv for one owned session. Pure: no clock, no path, no process.

    Raises `RunnerRefusal` when the command would exceed the measured ceiling.

    **`frame_bytes` is the runner's fact, injected exactly as
    `capabilities(pane_driver_available=)` injects the pane driver's.** tmux's
    limit is on the whole client→server message, and this module's argv is only
    the tail of it: `LocalRunner.start` prepends
    `new-session -d -s <name> -c <cwd> -x <cols> -y <rows> [-e K=V]*`, which is
    ~106 bytes of framing plus two words per environment variable, and `spec.env`
    is unbounded. Counting only the `claude` argv accepted a 16 261-byte brief
    whose real command was 16 430 bytes and which real tmux 3.4 refused with
    `command too long` (T10-R2). The engine keeps the message — the actionable
    advice needs the brief, and the brief is the engine's — and stops owning a
    number it cannot see.
    """
    argv = [binary, SESSION_ID_FLAG, spec.engine_session_id]
    for flag, value in (
        (NAME_FLAG, spec.title),
        (MODEL_FLAG, spec.model),
        (EFFORT_FLAG, spec.effort),
    ):
        if value is not None:
            argv += [flag, value]
    if spec.brief is not None:
        argv += [SEPARATOR, spec.brief]

    size = command_size(argv) + frame_bytes
    if size > TMUX_COMMAND_LIMIT_B:
        raise RunnerRefusal(
            f"the spawn command is {size} bytes ({frame_bytes} of them the runner's own "
            f"framing) and the measured ceiling is {TMUX_COMMAND_LIMIT_B}: the brief is "
            f"refused, never truncated — send it after the session is up, or shorten it "
            f"by {size - TMUX_COMMAND_LIMIT_B} bytes"
        )
    return argv


# ----- the binary -----

PATH_ENV = "PATH"


def _search_space() -> tuple[str, str]:
    """The directories `shutil.which` will really search, and how to say so.

    `which` does **not** report `''` for an unset `PATH`: it falls back to
    `confstr("CS_PATH")` (then `os.defpath`), so the old message named a search
    space that was never searched. A `PATH` that is set and **empty** is the
    opposite case — `which` searches nothing at all and returns `None` before
    looking anywhere.
    """
    configured = os.environ.get(PATH_ENV)
    if configured is None:
        fallback = os.confstr("CS_PATH") or os.defpath
        return fallback, f"{PATH_ENV} is unset, so {fallback!r} (CS_PATH) was searched"
    if configured == "":
        return "", f"{PATH_ENV} is set and empty, so nothing was searched"
    return configured, f"{PATH_ENV}={configured!r}"


def _why_not(search_path: str) -> str:
    """Why `which` said no. Four causes, and three are not "not on PATH".

    `shutil.which() is None` means absent, present-but-not-executable, a
    directory, or a dangling symlink — and reporting all four as "not on PATH"
    sends the human who just ran `ls` and saw the binary off to debug the wrong
    system.
    """
    for entry in search_path.split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / BINARY_NAME
        try:
            mode = candidate.stat().st_mode
        except FileNotFoundError:
            if candidate.is_symlink():
                return f"{candidate} is a dangling symlink"
            continue
        except OSError as error:
            return f"{candidate} cannot be read: {error}"
        if stat.S_ISDIR(mode):
            return f"{candidate} is a directory, not an executable"
        if not os.access(candidate, os.X_OK):
            return f"{candidate} is not executable (mode {stat.S_IMODE(mode):04o})"
    return f"no {BINARY_NAME} in any entry of the search path"


def resolve_binary() -> str:
    """The absolute path of `claude` on this `PATH`. Raises `RunnerRefusal`.

    Resolved **before** the spawn (E-M3-14): a user manager's `PATH` has no
    `~/.local/bin`, so a pane started with the bare name dies 127 with no exit code
    anyone can read (C1). An unresolvable binary is a refusal, not a dead pane.

    The refusal names the **cause**, not just the outcome, and the search space
    it really searched.
    """
    found = shutil.which(BINARY_NAME)
    if found is None:
        searched, space = _search_space()
        raise RunnerRefusal(
            f"{BINARY_NAME!r} cannot be resolved: {_why_not(searched)} ({space}) — "
            "a unit's PATH does not include ~/.local/bin, so the binary must be "
            "resolved before the spawn"
        )
    return os.path.abspath(found)
