"""§7's ten rows — the environment contract, and the whole of it.

**This module is generated from env-plan §7 and nothing else.** The env plan
states rules in §2's prose and builds the manifest's `required_env`/`environment`
from §7, and a fact stated only in §2 does not reach the harness. That is exactly
how an earlier revision named the inherited `$TMUX` hazard in prose and shipped a
table that would not have unset it. Ten rows here; ten rows there.

**Five arrivals are asserted, not trusted.** A fixture that sets a variable and
does not read the seam back is happy to hand the real user's directories to the
thing under test:

* `XDG_DATA_HOME` / `XDG_CONFIG_HOME` — via `detect_host().dirs()`;
* `XDG_RUNTIME_DIR` — same;
* `TMUX` — **absent from `os.environ`**, not present-and-empty. It is inherited
  and non-empty on this host, and a command run inside tmux resolves to *that
  session's* socket, so `-L` on the session is not enough;
* `PLAYWRIGHT_BROWSERS_PATH` — via an `executable_path` that **exists on disk**.
  Left inherited, playwright derives the browser path from `XDG_CACHE_HOME`/`HOME`,
  which the four rows above redirect, and `executable_path` then resolves
  **without raising** to a file that is not there. The failure surfaces ~45 s
  later at the browser launch, looking like a chromium fault.

The other five are set and not separately asserted, which is stated rather than
left to be assumed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from shepherd.host.detect import detect_host

from .runroot import HarnessBlocked, RunRoot

#: Measured on this host by preflight: the playwright *package* is in the repo
#: `.venv`; the browser *binary* is not.
BROWSERS_PATH = Path("/root/.cache/ms-playwright")

#: Every variable this harness owns. `None` means **remove**, never set empty.
#: The distinction matters for `TMUX`: tmux treats an empty value as "not in a
#: session" on most paths, but `os.environ` carrying the key at all is a
#: difference a subprocess can see, and "unset" is what §7 says.
def plan(run: RunRoot) -> dict[str, str | None]:
    """The ten rows, as a mapping ready for `os.environ`."""
    return {
        "XDG_DATA_HOME": str(run.sub("xdg_data")),
        "XDG_CONFIG_HOME": str(run.sub("xdg_config")),
        "XDG_STATE_HOME": str(run.sub("xdg_state")),
        "XDG_CACHE_HOME": str(run.sub("xdg_cache")),
        "HOME": str(run.sub("home")),
        "TMPDIR": str(run.sub("tmp")),
        "XDG_RUNTIME_DIR": str(run.runtime_dir),
        "CLAUDE_CONFIG_DIR": str(run.sub("engine-config")),
        "PLAYWRIGHT_BROWSERS_PATH": str(BROWSERS_PATH),
        "TMUX": None,
    }


@contextmanager
def redirected(run: RunRoot) -> Iterator[dict[str, str | None]]:
    """Apply §7, assert the five arrivals, and put the environment back.

    The restore is unconditional and is not a `try`/`except` that swallows: the
    root `tests/conftest.py` guard re-reads `$CLAUDE_CONFIG_DIR` when the session
    ends, so a harness that leaked this environment would make that guard read
    the wrong directory and report the user's settings unchanged for the wrong
    reason.
    """
    rows = plan(run)
    saved = {name: os.environ.get(name) for name in rows}
    try:
        for name, value in rows.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        assert_arrivals(run)
        yield rows
    finally:
        for name, previous in saved.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def assert_arrivals(run: RunRoot) -> None:
    """Arrival, not trust — the five §7 says are checked."""
    dirs = detect_host().dirs()
    for label, directory in (("data_dir", dirs.data_dir), ("config_dir", dirs.config_dir)):
        if run.root not in directory.parents:
            raise HarnessBlocked(f"{label} escaped the run root: {directory}")
    if run.runtime_dir not in dirs.runtime_dir.parents and dirs.runtime_dir != run.runtime_dir:
        raise HarnessBlocked(f"runtime_dir escaped the short runtime dir: {dirs.runtime_dir}")

    if os.environ.get("TMUX") is not None:
        raise HarnessBlocked(
            "TMUX is still in the environment. It is inherited and non-empty on this "
            "host, and a tmux command that inherits it resolves to that session's own "
            "socket — so `-L` on the session is not enough."
        )

    executable = chromium_executable_path()
    if not executable.exists():
        raise HarnessBlocked(
            f"chromium's executable_path resolves to {executable}, which does not exist. "
            "PLAYWRIGHT_BROWSERS_PATH did not take effect — playwright derives the "
            "browser path from XDG_CACHE_HOME/HOME, both of which this harness redirects."
        )
    if BROWSERS_PATH not in executable.parents:
        raise HarnessBlocked(f"chromium resolved outside {BROWSERS_PATH}: {executable}")


def chromium_executable_path() -> Path:
    """Where playwright says the browser is, **under the current environment**.

    Resolved through the driver rather than spelled, and read *after* the
    redirect: this call is the one that a prerequisite check run under the
    inherited environment cannot make, and it is the difference between a
    preflight that can see its own harness's failure and one that cannot.
    """
    from playwright.sync_api import sync_playwright

    started = sync_playwright().start()
    try:
        return Path(started.chromium.executable_path)
    finally:
        started.stop()
