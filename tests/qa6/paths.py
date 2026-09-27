"""Every fixed path and constant the harness names, spelled once.

Pure constants: computing a `Path` touches nothing. The real home is resolved
through `pwd`, not `$HOME`, so a pytest process launched with a redirected
`HOME` still knows where the user's real files are (it must never write them,
but Z1 and the settings guard must read them).
"""

from __future__ import annotations

import os
import pwd
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

REPO: Final[Path] = Path(__file__).resolve().parents[2]
QA6_DIR: Final[Path] = REPO / "tests" / "qa6"
VENV_BIN: Final[Path] = REPO / ".venv" / "bin"
PYTHON: Final[Path] = VENV_BIN / "python"
PYTEST: Final[Path] = VENV_BIN / "pytest"
CONTROLD_BIN: Final[Path] = VENV_BIN / "shepherd-controld"
SESSIOND_BIN: Final[Path] = VENV_BIN / "shepherd-sessiond"
SHEPHERD_BIN: Final[Path] = VENV_BIN / "shepherd"

#: Absolute, so the harness's own tmux calls never go through the logging shim
#: (Z2 reads the shim log as "what the product ran").
TMUX_BIN: Final[Path] = Path("/opt/homebrew/bin/tmux")
PERL_BIN: Final[Path] = Path("/usr/bin/perl")
NC_BIN: Final[Path] = Path("/usr/bin/nc")
LSOF_BIN: Final[Path] = Path("/usr/sbin/lsof")
PS_BIN: Final[Path] = Path("/bin/ps")
PGREP_BIN: Final[Path] = Path("/usr/bin/pgrep")
GIT_BIN: Final[Path] = Path("/usr/bin/git")
SLEEP_BIN: Final[Path] = Path("/bin/sleep")
CAT_BIN: Final[Path] = Path("/bin/cat")
SHASUM_BIN: Final[Path] = Path("/usr/bin/shasum")
CAFFEINATE_BIN: Final[Path] = Path("/usr/bin/caffeinate")

REAL_HOME: Final[Path] = Path(pwd.getpwuid(os.getuid()).pw_dir)
REAL_CLAUDE_DIR: Final[Path] = REAL_HOME / ".claude"
REAL_SETTINGS: Final[Path] = REAL_CLAUDE_DIR / "settings.json"
REAL_CLAUDE_JSON: Final[Path] = REAL_HOME / ".claude.json"
REAL_CLAUDE_BIN: Final[Path] = REAL_HOME / ".local" / "bin" / "claude"
REAL_SHEPHERD_DATA: Final[Path] = REAL_HOME / "Library" / "Application Support" / "Shepherd"
BROWSERS_PATH: Final[Path] = REAL_HOME / "Library" / "Caches" / "ms-playwright"

#: U2: the owner named this exact value. A difference from it is a visible,
#: non-stopping preflight WARN; the stopping invariant is `expected_settings_sha()`:
#: unchanged since run start. INC-3: the real file moved from the first owner-named
#: value (28067dc4…1b4c) without any harness run having written it, and on 2026-09-27
#: the owner accepted the moved value as the new owner-named sha (ruling 28,
#: docs/plans/2026-09-27-qa6-owner-rulings.md).
OWNER_SETTINGS_SHA: Final[str] = (
    "f99112b6db8b5adb5014792c84e75cac806ec12ecb73a2dee3a1ef95a7f1c52b"
)

#: The real settings sha the runner measured ONCE at run start, before preflight
#: and before any lane, and exported to every lane process (`run.capture_settings_sha`).
ENV_RUN_SETTINGS_SHA: Final[str] = "QA6_RUN_SETTINGS_SHA"


def expected_settings_sha(environ: Mapping[str, str] | None = None) -> str:
    """The sha every settings check compares against: the run-start sha, else U2's owner value.

    The run's invariant is "the sha at every check == the sha at run start": the
    harness never writes the real settings, so any change during a run stops it.
    A bare pytest of one test (no runner, so no exported value) keeps the owner's
    value, exactly as before. An empty value counts as unset.
    """
    source = os.environ if environ is None else environ
    return source.get(ENV_RUN_SETTINGS_SHA) or OWNER_SETTINGS_SHA

#: R1: the user's WatchTower daemon. The ONE place this number is spelled; a
#: guard test greps the package for it everywhere else.
FORBIDDEN_PORT: Final[int] = 8787

#: The tmux socket directory for this uid (tmux's default `/private/tmp/tmux-<uid>`).
TMUX_SOCKET_DIR: Final[Path] = Path(f"/private/tmp/tmux-{os.getuid()}")

#: The user's own tmux sockets: never contacted by any client command here.
USER_TMUX_SOCKETS: Final[tuple[str, ...]] = ("default", "shepherd")

WORKFLOW_ID: Final[str] = "wf-20260923T182839Z-9adb11fc"
DEFAULT_REPORT_DIR: Final[Path] = REPO / ".cc10x" / "qa" / WORKFLOW_ID / "runs"
SETUP_RECORD: Final[Path] = REPO / ".cc10x" / "qa" / "env" / "Shepherd-macos" / "setup.md"

PROBES: Final[Path] = REPO / "docs" / "probes"
PROMPT_READY_FRAME: Final[Path] = (
    PROBES / "2026-09-20-macos-pane" / "01-prompt-ready-normal-screen.ansi"
)
BARE_SHELL_FRAME: Final[Path] = PROBES / "2026-09-20-macos-pane" / "02-bare-shell.ansi"
DIALOG_CAPTURE: Final[Path] = (
    PROBES / "2026-09-17-m3-tmux" / "p4-permission-20260917T110527Z" / "04a-1-dialog.ansi.txt"
)
TRUST_DIALOG_CAPTURE: Final[Path] = (
    PROBES / "2026-09-17-m3-tmux" / "p4-permission-20260917T110527Z" / "00-shepherd_p4-trust-dialog.txt"
)
SIDECAR_CAPTURE: Final[Path] = (
    PROBES / "2026-09-14-schemas" / "tmux-tui" / "run-20260914T154946Z" / "03-sidecar-after-stop.json"
)
HOOKS_LIVE: Final[Path] = PROBES / "2026-09-14-schemas" / "hooks" / "live"

#: Run-root naming. `/tmp` is `/private/tmp` on macOS; both spellings are
#: matched wherever a process argv or cwd is compared (review pass 1 finding 8).
RUN_ROOT_PREFIX: Final[str] = "shq6-"
TMP_SPELLINGS: Final[tuple[str, ...]] = ("/tmp", "/private/tmp")


def run_root(pid: int, k: int) -> Path:
    """`/tmp/shq6-<pid>-<k>` — short on purpose (the 103-byte socket budget)."""
    return Path("/tmp") / f"{RUN_ROOT_PREFIX}{pid}-{k}"


def runner_socket_name(pid: int, k: int) -> str:
    """`shepherd-m3-q6<pid>-<k>`: matches the product's only kill-server pattern."""
    return f"shepherd-m3-q6{pid}-{k}"


def runner_socket_pattern(pid: int) -> re.Pattern[str]:
    """The backstop pattern teardown refuses anything outside of (env-plan §9 step 5).

    ASCII digits only (review N2): `\\d` matches any Unicode digit (`٣`), which the shim's
    `[0-9]` refuses, so the two judges would disagree.
    """
    return re.compile(rf"^shepherd-m3-q6{pid}-[0-9]+$")
