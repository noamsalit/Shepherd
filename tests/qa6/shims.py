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

TEMPLATES = paths.QA6_DIR / "shims"
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


def write_shims(run: RunContext) -> None:
    pane_log = str(run.pane_tmux_argv_log)
    tmux_text = _render("tmux.sh.in", {"TMUX_LOG": str(run.tmux_argv_log), "PANE_LOG": pane_log, "TMUX": str(paths.TMUX_BIN)})
    for directory in (run.shims, run.shims_live, run.shims_d9):
        _write(directory / "tmux", tmux_text)
    _write(run.shims_unseeded / "tmux",
           _render("tmux.sh.in", {"TMUX_LOG": str(run.unseeded_tmux_argv_log), "PANE_LOG": pane_log,
                                  "TMUX": str(paths.TMUX_BIN)}))
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
        [str(run.shims / "tmux"), "-V"], capture_output=True, text=True, timeout=10, check=False
    )
    if done.returncode != 0 or not done.stdout.startswith("tmux "):
        raise AssertionError(f"tmux shim self-test failed: {done.returncode} {done.stdout!r} {done.stderr!r}")
    seen["tmux"] = done.stdout.strip()
    # The claude self-test wrote one argv line; clear it so O1/O10/O12 count
    # only the product's invocations. The tmux `-V` line stays: it is exactly
    # the argv Z2's `-V` exception covers.
    run.claude_argv_log.write_text("", encoding="utf-8")
    return seen
