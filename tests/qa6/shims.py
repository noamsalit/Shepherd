"""Render the shim templates into a run root and prove each one runs.

The templates in `tests/qa6/shims/*.sh.in` are text; this module substitutes
absolute paths into them and writes them 0755 into `<run0>/shims`,
`<run0>/shims-live` (logging tmux only) and `<run0>/shims-d9` (counting claude +
logging tmux). Their **fidelity** — that the fake engine's pane classifies as
PROMPT_READY with the product's own classifier — is scenario W5, not this file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import paths
from .sandbox import RunContext

#: Beside this file (not `paths.QA6_DIR`): a mutation proof renders the templates of its temp copy.
TEMPLATES = Path(__file__).resolve().parent / "shims"
SELFTEST_MARKERS = {
    "claude": "QA6-FAKE-CLAUDE-SELFTEST",
    "claude-d9": "QA6-D9-CLAUDE-SELFTEST",
}


def _render(template: str, values: dict[str, str]) -> str:
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    left = re.findall(r"@[A-Z_]+@", text)
    if left:
        raise AssertionError(f"unrendered placeholder(s) {left} in {template}")
    return text


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def forks_log(run: RunContext) -> Path:
    return run.shims_d9 / "forks.log"


def tmux_shim_text(run_pid: int, product_log: Path, pane_log: Path, real_tmux: Path) -> str:
    """The logging-and-refusing tmux shim for run `run_pid` (shims/tmux.sh.in)."""
    return _render("tmux.sh.in", {"TMUX_LOG": str(product_log), "PANE_LOG": str(pane_log), "TMUX": str(real_tmux),
                                  "RUN_PID": str(run_pid), "SOCKET_DIR": str(paths.TMUX_SOCKET_DIR)})


def write_shims(run: RunContext) -> None:
    tmux_text = tmux_shim_text(run.pid, run.tmux_argv_log, run.pane_tmux_argv_log, paths.TMUX_BIN)
    for directory in (run.shims, run.shims_live, run.shims_d9):
        _write(directory / "tmux", tmux_text)
    _write(run.shims_unseeded / "tmux",
           tmux_shim_text(run.pid, run.unseeded_tmux_argv_log, run.pane_tmux_argv_log, paths.TMUX_BIN))
    _write(
        run.shims / "claude",
        _render(
            "claude.sh.in",
            {
                "CLAUDE_LOG": str(run.claude_argv_log),
                "FRAME": str(paths.PROMPT_READY_FRAME),
                "DIALOG": str(paths.DIALOG_CAPTURE),
            },
        ),
    )
    _write(run.shims_d9 / "claude", _render("claude_d9.sh.in", {"FORKS_LOG": str(forks_log(run))}))


def selftest(run: RunContext) -> dict[str, str]:
    """Run each shim's self-test argv; return name → first stdout line.

    The d9 self-test appends one line to `forks.log`; the file is truncated
    afterwards so D9 counts only the product's forks.
    """
    seen: dict[str, str] = {}
    for name, shim in (("claude", run.shims / "claude"), ("claude-d9", run.shims_d9 / "claude")):
        done = subprocess.run(
            [str(shim), "--qa6-selftest"], capture_output=True, text=True, timeout=10, check=False
        )
        seen[name] = done.stdout.strip()
        if done.returncode != 0 or seen[name] != SELFTEST_MARKERS[name]:
            raise AssertionError(f"shim {shim} self-test failed: rc={done.returncode} out={done.stdout!r} err={done.stderr!r}")
    forks_log(run).write_text("", encoding="utf-8")
    done = subprocess.run(
        [str(run.shims / "tmux"), "-V"], capture_output=True, text=True, timeout=10, check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"},
    )
    if done.returncode != 0 or not done.stdout.startswith("tmux "):
        raise AssertionError(f"tmux shim self-test failed: {done.returncode} {done.stdout!r} {done.stderr!r}")
    seen["tmux"] = done.stdout.strip()
    seen["tmux-refusal"] = selftest_refusal(run)
    # The claude self-test wrote one argv line; clear it so O1/O10/O12 count
    # only the product's invocations. The tmux `-V` line stays: it is exactly
    # the argv Z2's `-V` exception covers.
    run.claude_argv_log.write_text("", encoding="utf-8")
    return seen


#: A socket name no user server has: if the refusal were broken, real tmux would only answer
#: "no server running" (a client never creates a socket for `list-sessions`).
SELFTEST_FOREIGN_SOCKET = "qa6-shim-selftest-refusal"


def selftest_refusal(run: RunContext) -> str:
    """The production-rendered shim (real tmux behind it) refuses a foreign socket, and fails closed.

    Rendered into `<run0>/shims-selftest/` with its own logs, so nothing it writes reaches the
    product log Z2 reads. (1) `-L qa6-shim-selftest-refusal list-sessions` must exit 97 with the
    refusal on stderr and be logged. (2) `-V` with an unwritable log must exit 98 and print no
    version: the call never reached tmux unrecorded. `test_proof_tmux_shim_refuses` proves the full
    battery against a fake binary; this proves the file the product actually runs.
    """
    directory = run.run0 / "shims-selftest"
    directory.mkdir(mode=0o700, exist_ok=True)
    product_log, pane_log = directory / "tmux-argv.log", directory / "pane-tmux-argv.log"
    shim = directory / "tmux"
    _write(shim, tmux_shim_text(run.pid, product_log, pane_log, paths.TMUX_BIN))
    env = {"PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8"}
    refused = subprocess.run([str(shim), "-L", SELFTEST_FOREIGN_SOCKET, "list-sessions"], capture_output=True,
                             text=True, timeout=10, check=False, env=env)
    logged = product_log.read_text(encoding="utf-8") if product_log.exists() else ""
    if refused.returncode != 97 or "refused" not in refused.stderr or SELFTEST_FOREIGN_SOCKET not in logged:
        raise AssertionError(f"tmux shim refusal self-test failed: rc={refused.returncode} err={refused.stderr!r} "
                             f"logged={logged!r}")
    blind = directory / "unwritable"
    blind.mkdir(mode=0o700, exist_ok=True)
    _write(shim, tmux_shim_text(run.pid, blind, pane_log, paths.TMUX_BIN))
    closed = subprocess.run([str(shim), "-V"], capture_output=True, text=True, timeout=10, check=False, env=env)
    if closed.returncode != 98 or closed.stdout:
        raise AssertionError(f"tmux shim fail-closed self-test failed: rc={closed.returncode} out={closed.stdout!r} "
                             f"err={closed.stderr!r}")
    return f"refused rc=97 ({refused.stderr.strip()[:120]}); unloggable rc=98"
