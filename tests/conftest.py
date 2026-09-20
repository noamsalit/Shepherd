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
import shutil
import stat
import sys
import tempfile
import time
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


# ----- a `tmp_path` short enough to hold a Unix socket (E19, macOS G1) -------
#
# `sun_path` is 108 bytes on Linux and **104 on macOS** (this probe:
# `docs/probes/2026-09-20-macos-g1-capture.md` Result 1), so the usable budget
# is 107 and 103. Dozens of tests in this suite bind a real `AF_UNIX` socket
# under `tmp_path`, which means the *base pytest chooses* is load-bearing.
#
# On Linux it is `/tmp/pytest-of-<user>/pytest-<n>/` and nobody ever noticed.
# On macOS `tempfile.gettempdir()` is `$TMPDIR`, which is
# `/var/folders/1c/mgs46bfj23zd342sscpd8r_80000gn/T/` — 47 bytes before pytest
# adds anything — and the suite does not fail cleanly, it fails as
# `SocketPathTooLong` and `OSError: AF_UNIX path too long` in 60-odd tests that
# have nothing to do with path length.
#
# Passing `--basetemp=` on the command line fixes it and is not a fix: it makes
# a bare `pytest` wrong and puts the repair in the caller's memory. So the
# repo picks its own short base when the caller has not picked one, and
# `tests/test_tmp_socket_budget.py` asserts the headroom is really there rather
# than leaving it to luck.
#
# The base is unique per run (`mkdtemp`), so setting `basetemp` — which makes
# pytest `rm_rf` it first — can never touch another run's tree. pytest's own
# retention only applies to bases it numbered itself, so the retention below
# replaces it.
#
# Retention is by **age and by count**, with age as a floor under both, and
# that is not a style choice either way.
#
# Several tests in this suite run pytest as a subprocess
# (`tests/boundaries/test_collected_node_ids.py` collects the whole tree in a
# child), so more than one run of this conftest is live at once. A plain
# "keep the newest three" rule had each child delete the *parent's* base out
# from under it, and 30-odd tests that had nothing to do with temporary
# directories died on `FileNotFoundError` inside pytest's own `find_prefixed`.
# That argument is correct and is preserved: a concurrent run's base is by
# definition recent, and `RUN_GRACE_S` makes recent untouchable.
#
# **Amended 2026-09-20.** What it is not is an argument against a ceiling. Age
# alone, with nothing removing a base at session end, left 2.8 GB across 155
# bases here in one day. The floor protects concurrency; the ceiling
# (`RUN_KEEP_NEWEST`) bounds the disk. They are compatible because they act on
# disjoint sets: nothing inside the grace window is a candidate for either
# rule. `tests/test_temproot_policy.py` asserts both, and asserts the floor
# wins over the cap.

#: Every byte here is a byte a test cannot spend on a socket path, and on macOS
#: `/tmp` resolves through a symlink to `/private/tmp`, so this costs 21 bytes
#: and not 13. Per-uid because `/tmp` is shared.
SHORT_TEMPROOT_PARENT = Path("/tmp")
SHORT_TEMPROOT_NAME = f"shp-{os.getuid()}"

#: How long a run's base survives for post-mortem, once it is past the grace
#: window below.
RUN_RETENTION_S = 24 * 60 * 60

#: The floor the paragraph above argues for, stated as a number. **Nothing**
#: younger than this is ever removed, by age or by count, because a base that
#: young may belong to a pytest that is still running — including one this run
#: started. The full suite takes 94 s, so 15 min is ~10x cover for the slowest
#: child this tree spawns.
RUN_GRACE_S = 15 * 60

#: The ceiling the floor does not provide. Age alone left **2.8 GB across 155
#: bases** in a single day on this host (largest 218 MB / 1810 entries), because
#: nothing removes a base at session end and 24 h is a long time. Past the grace
#: window, only this many survive — enough that the last few runs are still
#: there for a post-mortem, few enough that a day of work is bounded.
RUN_KEEP_NEWEST = 8


def short_temproot(
    parent: Path = SHORT_TEMPROOT_PARENT, name: str = SHORT_TEMPROOT_NAME
) -> Path | None:
    """A short, per-user directory to hold this run's base, or `None`.

    `None` — not a raise — when the root is not usable: an unusable `/tmp` is a
    reason to leave pytest's own default alone, never a reason to fail
    collection. Principle 5: the unknown is a value.

    **Usable means ours.** `/tmp` is world-writable and sticky, and
    `mkdir(exist_ok=True)` succeeds against a directory somebody else created,
    with whatever owner and mode they gave it. `os.access(root, W_OK)` cannot
    catch that — running as root (which this tree does on Linux) it answers
    True for every directory on the system. So the check is an explicit
    `lstat`: a real directory, owned by us, with no group or other bits at all.
    Anything else and an unprivileged local user who pre-created `/tmp/shp-0`
    would own a tree a root pytest then fills with fixtures and prunes inside.

    `lstat` rather than `stat` because a symlink pointing at a directory we own
    is still a redirect somebody else chose.
    """
    root = parent / name
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        status = root.lstat()
    except OSError:
        return None
    if not stat.S_ISDIR(status.st_mode):
        return None
    if status.st_uid != os.getuid():
        return None
    if status.st_mode & 0o077:
        return None
    return root


def prune_old_runs(
    root: Path,
    retention_s: float = RUN_RETENTION_S,
    grace_s: float = RUN_GRACE_S,
    keep_newest: int = RUN_KEEP_NEWEST,
) -> None:
    """Bound the tree by age **and** by count, with a grace window under both.

    A base is removable only once it is older than `grace_s` — that is the
    concurrency floor, and it is what makes this safe to run while a child
    pytest holds a base of its own. Among the removable ones, a base goes if it
    is older than `retention_s` *or* if it is not among the `keep_newest` most
    recent by mtime. A failed removal is never fatal.

    This is the *persistent* bound and it is lazy: it runs from the next
    session's `pytest_configure`, and nothing inside the grace window is a
    candidate. `remove_own_run` is the eager half and bounds the burst — see
    its docstring for why one cannot do both jobs.
    """
    now = time.time()
    removable: list[tuple[float, Path]] = []
    for child in root.iterdir():
        try:
            if not child.is_dir() or child.is_symlink():
                continue
            mtime = child.stat().st_mtime
        except OSError:  # pragma: no cover - a concurrent run removed it first
            continue
        if now - mtime > grace_s:
            removable.append((mtime, child))

    removable.sort(key=lambda entry: entry[0], reverse=True)
    for rank, (mtime, child) in enumerate(removable):
        if rank < keep_newest and now - mtime <= retention_s:
            continue
        shutil.rmtree(child, ignore_errors=True)


#: The one base **this** process created in `pytest_configure`, or `None` when
#: the caller supplied `--basetemp` (their directory, not ours) or no writable
#: root was found. `remove_own_run` is handed this and nothing else.
OWN_RUN_BASE: Path | None = None


def remove_own_run(base: Path | None, failed: int) -> None:
    """Remove *this* run's base at session end — one path, and only ours.

    `prune_old_runs` bounds the tree in steady state but cannot bound a
    **burst**: a base becomes a candidate only once it is older than
    `RUN_GRACE_S`, and the prune only runs when the *next* session starts, so a
    tight loop of runs — which `CLAUDE.md` rule 4 mandates for mutation work —
    keeps its whole population inside the grace window. Measured on 2026-09-20:
    1.3 GB across 64 bases created inside 18 minutes, roughly four per
    invocation because several tests collect the tree in a child pytest.

    A session knows it has finished. That is the fact `mtime` was being used to
    guess at, so this path needs no grace window — and it must not have one,
    because a grace window is what made the burst possible. What keeps it safe
    beside a concurrent child pytest is that it **never enumerates**: it is
    handed the single path this process created with `mkdtemp`, and a child
    pytest's base is a different `mkdtemp` result under the same root. The
    floor `prune_old_runs` provides is therefore untouched — nothing here can
    reach a base it did not create.

    A failed run keeps its base: the fixtures are the post-mortem, and that is
    the only reason a base outlives its session at all.
    """
    if base is None or failed:
        return
    shutil.rmtree(base, ignore_errors=True)


def pytest_configure(config: pytest.Config) -> None:
    """Choose a short `--basetemp` when the caller did not choose one."""
    global OWN_RUN_BASE
    if config.option.basetemp is not None:
        return
    root = short_temproot()
    if root is None:  # pragma: no cover - only on a host with no writable /tmp
        return
    try:
        prune_old_runs(root)
        own = Path(tempfile.mkdtemp(prefix="", dir=root))
    except OSError:  # pragma: no cover - only on a host with no writable /tmp
        return
    config.option.basetemp = str(own)
    OWN_RUN_BASE = own


def pytest_sessionfinish(session: pytest.Session) -> None:
    """The eager half of the temp-root policy; see `remove_own_run`."""
    remove_own_run(OWN_RUN_BASE, session.testsfailed)
