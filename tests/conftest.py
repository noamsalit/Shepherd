"""P13/K3: the real user `settings.json` is never touched — mechanically.

The user's rule is absolute: no test may read, write, move or back up the real
`~/.claude/settings.json`. A promise is not a guarantee, so this module makes it
an observation. The guard records, once per session:

  * the sha256 of the real file (or `ABSENT` when it does not exist — the
    missing case is a value, not a crash, principle 5), and
  * the names of every `settings.json*` sibling in the real config directory,

and asserts both are unchanged when the session ends. The sibling listing is
what catches the *backup* half of the rule: a `settings.json.shepherd-backup`
appearing beside the real file changes nothing's content and would otherwise be
invisible.

Reading the real file's bytes to hash it is the one contact P13 itself
prescribes ("records the real file's sha256 before the suite"); nothing here
ever opens it for writing, renames it, or copies it anywhere.
"""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

#: The digest stands in for "this file does not exist" so an absent file and an
#: empty file are never confused, and a file that *appears* mid-suite fails.
#: `tests/boundaries/` is not a package, so its shared AST walker (`_imports`) is
#: importable only while a boundaries module is being collected. It is put on the
#: path here so **every** suite can reach it, which is what makes RD-T5-5's rule
#: enforceable: a boundary predicate that lives in one place can only be *used*
#: from one place if that place is reachable. `tests/toolsurface/test_client.py`
#: is the first caller — §T22-6's convergence, D19's master predicate.
sys.path.insert(0, str(Path(__file__).resolve().parent / "boundaries"))

ABSENT = "absent"

SETTINGS_NAME = "settings.json"


def real_config_dir() -> Path:
    """Where the user's real settings live: `$CLAUDE_CONFIG_DIR` or `~/.claude`."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


@dataclass(frozen=True)
class SettingsObservation:
    """Everything the guard knows about a settings file it must never change."""

    path: Path
    digest: str
    siblings: tuple[str, ...]


def observe_settings(config_dir: Path) -> SettingsObservation:
    """Hash `<config_dir>/settings.json` and list its siblings. Read-only."""
    path = config_dir / SETTINGS_NAME
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, NotADirectoryError):
        digest = ABSENT
    try:
        siblings = tuple(
            sorted(
                child.name
                for child in config_dir.iterdir()
                if child.name.startswith(SETTINGS_NAME)
            )
        )
    except (FileNotFoundError, NotADirectoryError):
        siblings = ()
    return SettingsObservation(path=path, digest=digest, siblings=siblings)


@pytest.fixture(scope="session")
def settings_observer() -> Callable[[Path], SettingsObservation]:
    """The observer itself, so a test can prove the guard is not vacuous."""
    return observe_settings


@pytest.fixture(scope="session")
def real_user_settings(real_user_settings_guard: SettingsObservation) -> SettingsObservation:
    """The session's pre-image of the real file, for tests that assert on it."""
    return real_user_settings_guard


@pytest.fixture(scope="session", autouse=True)
def real_user_settings_guard() -> Iterator[SettingsObservation]:
    """Autouse, session-scoped: the whole suite runs between these two reads."""
    before = observe_settings(real_config_dir())
    yield before
    after = observe_settings(real_config_dir())
    assert after.digest == before.digest, (
        f"the real user settings file changed during this suite: {before.path}"
    )
    assert after.siblings == before.siblings, (
        f"a file appeared or vanished beside the real user settings file: {before.path}"
    )


# ----- the runtime half of the same guard (M3 T22) ---------------------------
#
# The digest guard above observes the *outcome*: it hashes the real file before
# the suite and again after, so a write that happens and is undone inside the
# suite is invisible to it, and a write whose bytes round-trip (T10-R1: a planted
# `path.write_text(path.read_text())` that ran on every default test run for
# hours) changes nothing it can see. That incident is what this is for.
#
# `sys.addaudithook` observes the *act*. CPython raises an `open` audit event for
# every `io.open` and every `os.open`, before the file is touched, carrying the
# path and the mode, and an audit hook cannot be removed once installed. So the
# question "did anything in this suite open the user's real settings file for
# writing?" becomes an observation with an exit code rather than a docstring.
#
# **Its negative control is built in and cannot rot.** The digest guard above
# opens the real file exactly twice, for reading, once per session. If the hook
# were dead — wrong path, wrong event name, never installed — the recorded count
# would be zero, and the session-end assertion below fails on that. A hook that
# fires on nothing is the failure this whole file exists to prevent.

#: Every `open` of the real settings file seen this session: `(mode, flags)`.
#: A module global because an audit hook outlives any fixture.
SETTINGS_OPENS: list[tuple[str | None, int | None]] = []

_WRITE_MODE_CHARS = frozenset("wax+")

#: `os.open` reports intent in flags rather than in a mode string.
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND


def open_is_a_write(mode: str | None, flags: int | None) -> bool:
    """Both spellings of intent. Unknown is treated as a write, not as safe."""
    if mode is not None:
        return bool(_WRITE_MODE_CHARS & set(mode))
    if flags is not None:
        return bool(flags & _WRITE_FLAGS)
    return True


def _install_settings_audit_hook() -> None:
    target = str(real_config_dir() / SETTINGS_NAME)

    def _hook(event: str, args: tuple[object, ...]) -> None:
        if event != "open" or not args:
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):
            return
        if os.fspath(path) != target:
            return
        mode = args[1] if len(args) > 1 and isinstance(args[1], str) else None
        flags = args[2] if len(args) > 2 and isinstance(args[2], int) else None
        SETTINGS_OPENS.append((mode, flags))

    sys.addaudithook(_hook)


_install_settings_audit_hook()


@pytest.fixture(scope="session", autouse=True)
def no_write_ever_reaches_the_real_settings_file() -> Iterator[None]:
    """Zero writes, and a non-zero number of reads proving the hook is alive."""
    yield
    writes = [record for record in SETTINGS_OPENS if open_is_a_write(*record)]
    assert writes == [], (
        f"something opened {real_config_dir() / SETTINGS_NAME} for writing: {writes}"
    )
    assert SETTINGS_OPENS, (
        "the audit hook recorded no open of the real settings file at all —"
        " the guard above reads it twice per session, so zero means the hook is"
        " dead and its zero-writes result proves nothing"
    )


#: PID 1 is the init system. `SIGINT` delivered there is how the kernel spells
#: Ctrl+Alt+Del, and systemd's default handler for it is `reboot.target`.
#:
#: On 2026-09-17 the M3 verifier planted `os.kill(1, signal.SIGINT)` into a
#: shadow copy of `runner/local.py` to prove P-M3-7's lint catches it. The lint
#: does catch it — statically. But the suite *executes* the module it is
#: scanning, `interrupt()` ran before the lint test did, and the host rebooted:
#: 66 days of uptime and three live sessions, gone.
#:
#: The lesson is not "ban the literal 1". It is that a static guard cannot
#: protect against code it has not scanned yet, so the net has to be a runtime
#: one. Same reasoning as the settings-file guard above: a promise is not a
#: guarantee, so this makes it an observation.
#:
#: Signals to real child processes are untouched — only pids that can never be
#: a test's own child are refused.
UNSIGNALABLE_PIDS: frozenset[int] = frozenset({0, 1, -1})


class SignalToInit(AssertionError):
    """Raised instead of delivering a signal that could reach init."""


@pytest.fixture(scope="session", autouse=True)
def no_signal_ever_reaches_init() -> Iterator[None]:
    """`os.kill`/`os.killpg` refuse pids that are not a child of this suite.

    `0` is "every process in my group", `-1` is "every process I may signal",
    and `1` is init. None of the three is ever a test's own subprocess, and all
    three are reachable by a one-character slip in a planted mutation.
    """
    real_kill, real_killpg = os.kill, os.killpg

    def guarded_kill(pid: int, sig: int, /) -> None:
        if pid in UNSIGNALABLE_PIDS:
            raise SignalToInit(
                f"refused os.kill({pid}, {sig}): pid {pid} is init or a process"
                " group, never a child of this suite. See the note in"
                " tests/conftest.py — this signal rebooted the host once."
            )
        real_kill(pid, sig)

    def guarded_killpg(pgid: int, sig: int, /) -> None:
        if pgid in UNSIGNALABLE_PIDS:
            raise SignalToInit(f"refused os.killpg({pgid}, {sig}): would reach init")
        real_killpg(pgid, sig)

    os.kill, os.killpg = guarded_kill, guarded_killpg
    try:
        yield
    finally:
        os.kill, os.killpg = real_kill, real_killpg
