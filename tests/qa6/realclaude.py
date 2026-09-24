"""The real `claude` engine: where it is, how live lanes reach it, and whether the user's link moved.

**INC-1 (2026-09-24, unrepaired, not ours to repair).** A STAGE B smoke run gave
a real-HOME `claude` TUI pane a sandboxed `XDG_DATA_HOME`; the engine's
auto-updater installed itself under the run root and re-pointed the user's
`~/.local/bin/claude` there; teardown removed the root and the user's link now
dangles. The harness therefore never relies on that link, and never touches it:

* **Resolution** (`resolve`), once per run, at mint time:
  1. `QA6_REAL_CLAUDE` if set (an explicit choice is never guessed past: an
     invalid value resolves to nothing);
  2. else `shutil.which("claude")` if it resolves to an existing executable;
  3. else the newest executable under `~/.local/share/claude/versions/*`
     (the INC-1 fallback, and the record says so).
  A candidate whose real path lies inside any qa6 run root is refused.
* **Exposure** (`install`): `<run0>/bin/claude`, a symlink to the resolved
  binary, created inside the run root and removed with it. `sandbox.child_path`
  puts `<run0>/bin` on PATH for `path_mode="live"` only, and every direct exec
  of the real engine uses `run.real_claude`. Nothing outside the run root is
  created or changed.
* **The link guard** (`record_link_start`, `link_change`): the state of the
  user's `~/.local/bin/claude` (lstat + readlink + realpath: reads only) is
  measured at run START and written to `<run_dir>/claude-link-start.json`.
  It is compared against that — never against "healthy" (at the time of
  writing it is dangling). A change during the run is a stop for the runner
  and BLOCKED for every live module, with `REPAIR_MESSAGE`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from . import paths
from .sandbox import RunContext
from .verdict import Blocked

ENV_REAL_CLAUDE: Final[str] = "QA6_REAL_CLAUDE"
VERSIONS_DIR: Final[Path] = paths.REAL_HOME / ".local" / "share" / "claude" / "versions"
RESOLUTION_FILE: Final[str] = "real-claude.json"
LINK_START_FILE: Final[str] = "claude-link-start.json"
LINK_KEYS: Final[tuple[str, ...]] = ("is_symlink", "target", "resolved", "exists")

REPAIR_MESSAGE: Final[str] = (
    f"the user's {paths.REAL_CLAUDE_BIN} changed during this run; the harness never modifies it and no live "
    "scenario may run until a human has inspected it (INC-1's repair, for the human: "
    f"`ln -sfn {VERSIONS_DIR}/<version> {paths.REAL_CLAUDE_BIN}`)"
)

_VERSION = re.compile(r"^\d+(?:\.\d+)*$")


@dataclass(frozen=True)
class Resolution:
    """Which real engine this run uses, and why. `path is None` = none was usable."""

    path: str | None
    source: str
    why: str
    inc1_fallback: bool

    def as_json(self) -> dict[str, object]:
        return {"path": self.path, "source": self.source, "why": self.why, "inc1_fallback": self.inc1_fallback}


def _usable(candidate: str) -> str | None:
    """The candidate's real path, if it is an executable file outside every qa6 run root."""
    real = os.path.realpath(candidate)
    if f"/{paths.RUN_ROOT_PREFIX}" in real:
        return None
    if not os.path.isfile(real) or not os.access(real, os.X_OK):
        return None
    return real


def _version_key(name: str) -> tuple[int, ...]:
    return tuple(int(part) for part in name.split(".")) if _VERSION.match(name) else ()


def newest_version(versions_dir: Path = VERSIONS_DIR) -> str | None:
    """The highest-versioned executable under `versions_dir` (semantic order, not mtime)."""
    if not versions_dir.is_dir():
        return None
    names = sorted((entry.name for entry in versions_dir.iterdir() if _version_key(entry.name)),
                   key=_version_key, reverse=True)
    for name in names:
        real = _usable(str(versions_dir / name))
        if real is not None:
            return real
    return None


def resolve(environ: Mapping[str, str], versions_dir: Path = VERSIONS_DIR) -> Resolution:
    """The three-step rule in the module doc. Reads only."""
    explicit = environ.get(ENV_REAL_CLAUDE)
    if explicit:
        real = _usable(explicit)
        if real is not None:
            return Resolution(real, ENV_REAL_CLAUDE, f"{ENV_REAL_CLAUDE}={explicit} -> {real}", False)
        return Resolution(None, "unresolved", f"{ENV_REAL_CLAUDE}={explicit} is set but is not an executable file "
                          "outside every qa6 run root; an explicit choice is never guessed past", False)
    found = shutil.which("claude", path=environ.get("PATH", ""))
    if found is not None:
        real = _usable(found)
        if real is not None:
            return Resolution(real, "which", f"shutil.which('claude') -> {found} -> {real}", False)
        which_note = f"shutil.which('claude') -> {found}, whose real path is not usable ({os.path.realpath(found)})"
    else:
        which_note = "shutil.which('claude') found nothing on PATH"
    link = link_state()
    link_note = (f"the user's {paths.REAL_CLAUDE_BIN} is a dangling symlink -> {link['target']} (INC-1, unrepaired)"
                 if link["is_symlink"] and not link["exists"] else f"the user's link: {link}")
    fallback = newest_version(versions_dir)
    if fallback is not None:
        return Resolution(fallback, "versions_fallback",
                          f"{which_note}; {link_note}; using the newest {versions_dir}/* executable: {fallback}", True)
    return Resolution(None, "unresolved", f"{which_note}; {link_note}; no executable under {versions_dir}", True)


def install(run: RunContext, resolution: Resolution) -> None:
    """Create `<run0>/bin/claude` -> the resolved binary and write the run's record of it."""
    record = resolution.as_json()
    if resolution.path is not None:
        run.real_claude_bin_dir.mkdir(mode=0o700, exist_ok=True)
        os.symlink(resolution.path, run.real_claude)
        pointed = os.readlink(run.real_claude)
        if pointed != resolution.path or not run.real_claude.exists():
            raise AssertionError(f"{run.real_claude} -> {pointed}, expected {resolution.path}")
        record["exposed_as"] = str(run.real_claude)
    text = json.dumps(record, indent=1, sort_keys=True)
    (run.run0 / RESOLUTION_FILE).write_text(text, encoding="utf-8")
    run.run_dir.mkdir(parents=True, exist_ok=True)
    (run.run_dir / RESOLUTION_FILE).write_text(text, encoding="utf-8")


def load(run: RunContext) -> Resolution:
    """The resolution `install` recorded for this run (lane processes read it, never re-resolve)."""
    source = run.run0 / RESOLUTION_FILE
    if not source.exists():
        return Resolution(None, "unresolved", f"{source} does not exist (the run was minted without it)", False)
    decoded: object = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError(f"{source} is not an object")
    path = decoded.get("path")
    return Resolution(path if isinstance(path, str) else None, str(decoded.get("source")),
                      str(decoded.get("why")), decoded.get("inc1_fallback") is True)


def require(run: RunContext) -> Path:
    """`<run0>/bin/claude`, or `Blocked` naming why no real engine is available to this run."""
    resolution = load(run)
    if resolution.path is None or not run.real_claude.exists():
        raise Blocked(f"no real claude engine for this run: {resolution.why}")
    return run.real_claude


# ----- the link guard ---------------------------------------------------------------------------


def link_state(link: Path = paths.REAL_CLAUDE_BIN) -> dict[str, object]:
    """The user's link, read-only: lstat, readlink, realpath, existence of the target."""
    is_symlink = link.is_symlink()
    resolved = os.path.realpath(link)
    return {
        "is_symlink": is_symlink,
        "target": os.readlink(link) if is_symlink else None,
        "resolved": resolved,
        "exists": Path(resolved).exists(),
        "inside_a_run_root": f"/{paths.RUN_ROOT_PREFIX}" in resolved,
    }


def record_link_start(run_dir: Path) -> dict[str, object]:
    """Write the run-start link state once; a later call returns the first measurement."""
    target = run_dir / LINK_START_FILE
    existing = start_link_state(run_dir)
    if existing is not None:
        return existing
    run_dir.mkdir(parents=True, exist_ok=True)
    state = link_state()
    target.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    return state


def start_link_state(run_dir: Path) -> dict[str, object] | None:
    source = run_dir / LINK_START_FILE
    if not source.exists():
        return None
    decoded: object = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError(f"{source} is not an object")
    return {str(key): value for key, value in decoded.items()}


def compare(start: Mapping[str, object], now: Mapping[str, object]) -> str | None:
    """`None` when the link is as it was at run start; else the change and the repair message."""
    changed = {key: (start.get(key), now.get(key)) for key in LINK_KEYS if start.get(key) != now.get(key)}
    if not changed:
        return None
    return f"{REPAIR_MESSAGE}. Changed: {changed}"


def link_change(run_dir: Path) -> str | None:
    """Compare the user's link now against this run's start. A missing start record is itself a stop."""
    start = start_link_state(run_dir)
    if start is None:
        return f"no {LINK_START_FILE} in {run_dir}: the run-start state of {paths.REAL_CLAUDE_BIN} was never measured"
    return compare(start, link_state())
