"""T24's live lane: a real fork, and the target it must leave untouched.

`.venv/bin/pytest tests/e2e -m live -q`. Excluded from the default run.

**The claim (C-M3-10, P-M3-11).** `ask()` answers a question *about* a session by
forking its transcript with `--resume <id> --fork-session
--no-session-persistence`. The fork is a second engine process reading the same
JSONL file the target wrote, and the property M3 needs is that the target's
transcript is **byte-identical afterwards** — the engine appends to the fork's
own file, or to none at all, and never to the one we forked from. A fixture
cannot show this: it needs a real transcript, a real second process, and the real
`--fork-session` semantics BLOCKER-T1-2 corrected the plan about.

**Arrival before property.** A sha256 that is unchanged is also unchanged when
nothing ran. So this module asserts, in order: the target transcript **exists**
and is non-empty; the fork process **really answered** (a `session_id` came back
in the result JSON and it is a different id from the target's); and only then
that the target's bytes did not move. Revision 1's vacuous `count == 1` is the
precedent for why that order is not decoration.

**No tmux.** This module starts no terminal multiplexer, names no socket, and
needs neither: an ask target is a row in the store with an `engine_session_id`,
and the fork is a `-p` process. CLAUDE.md's rules 1-4 are satisfied by absence
here, and `tests/boundaries/test_tmux_blast_radius.py` asserts that over the tree.

**Isolation** is the lane's: the user's real `CLAUDE_CONFIG_DIR` (an isolated one
has no credentials), a throwaway working directory, an explicit throwaway
`--settings`, Shepherd's own XDG dirs relocated, and the autouse per-test sha256
guard on `~/.claude/settings.json`. The residue is the engine's own: a trust
entry and a transcript under `~/.claude/projects/-tmp-…`. Nothing is deleted (K3).
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from e2e.conftest import LIVE_MODEL, Throwaway, real_config_dir

from shepherd.core.runner import RunnerRefusal
from shepherd.core.states import Origin, SessionState
from shepherd.engines.claude_code.spawn import capabilities, resolve_binary
from shepherd.engines.claude_code.transcript import locate_transcript
from shepherd.orchestration.ask import ask_session
from shepherd.runner.local import CommandResult
from shepherd.store.db import Store, open_store

pytestmark = pytest.mark.live

#: Short on purpose. This lane proves a fork leaves its target alone, not that
#: the engine can think.
TARGET_PROMPT = "Reply with exactly: SHEPHERD_ASK_TARGET"
TARGET_MARKER = "SHEPHERD_ASK_TARGET"
QUESTION = "In one word, what did you just reply?"

#: A ceiling on waiting for a condition, never an assertion about elapsed time.
TRANSCRIPT_CEILING_S = 60.0
POLL_S = 0.5

#: The fork's own deadline, in the units `ask_session` takes. Generous: a fork
#: that is merely slow must not be reported as a fork that did not answer.
FORK_TIMEOUT_MS = 180_000

SESSION_ID = "01JBQ8Z9XKME5RT3VWNY6P0DFJ"
NOW = "2026-09-17T12:00:00.000000+00:00"


def await_value[T](probe: Callable[[], T | None], message: str, ceiling_s: float) -> T:
    deadline = time.monotonic() + ceiling_s
    while time.monotonic() < deadline:
        found = probe()
        if found is not None:
            return found
        time.sleep(POLL_S)
    raise AssertionError(f"{message} (waited {ceiling_s}s)")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_fork(argv: list[str], *, timeout_ms: int) -> CommandResult:
    """`ask()`'s process seam, spelled exactly as `toolsurface/compose.py` does.

    The kill happens where the child is held — `subprocess.run(timeout=)` kills
    before it raises — and every failure crosses back as a `RunnerRefusal`, the
    one exception `ask_session` is written to receive.
    """
    try:
        completed = subprocess.run(
            argv, capture_output=True, check=False, timeout=timeout_ms / 1000
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RunnerRefusal(f"the fork could not be run to completion: {error}") from error
    return CommandResult(rc=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def test_the_target_transcript_is_unchanged(throwaway: Throwaway, tmp_path: Path) -> None:
    """C-M3-10 / P-M3-11: sha256 of the target's transcript, before and after.

    Four arrivals are asserted before the property, because each of them is a way
    this test could otherwise pass having checked nothing: the target run
    succeeded, its transcript exists and is non-empty, `can_fork` is really true
    for this engine (a `False` would downgrade the ask to the mailbox and fork
    nothing at all), and the fork really answered with an engine session id of
    its own.
    """
    # ----- 1. a real target: one authenticated run, and its real transcript.
    completed = throwaway.run(TARGET_PROMPT)
    assert completed.returncode == 0, completed.stderr
    assert TARGET_MARKER in completed.stdout, completed.stdout
    assert "Not logged in" not in completed.stdout + completed.stderr

    projects_root = real_config_dir() / "projects"
    slug_root = projects_root
    target_path = await_value(
        lambda: _newest_transcript(slug_root, throwaway.workdir),
        f"the engine wrote no transcript for a run in {throwaway.workdir}",
        TRANSCRIPT_CEILING_S,
    )
    before = digest(target_path)
    size_before = target_path.stat().st_size
    assert size_before > 0, target_path
    engine_session_id = target_path.stem

    # ----- 2. the store row the ask needs. Owned and engine-bound, or
    #         `ask_session` refuses with `there is no owned, engine-bound
    #         session` and forks nothing.
    store: Store = open_store(tmp_path / "data" / "shepherd.db")
    try:
        workspace = store.upsert_workspace("shepherd-live-ask", str(throwaway.workdir))
        store.create_owned_session(
            session_id=SESSION_ID,
            engine_session_id=engine_session_id,
            workspace_id=workspace.id,
            repo_id=None,
            cwd=str(throwaway.workdir),
            started_at=NOW,
            origin=Origin.ORCHESTRATOR,
            parent_session_id=None,
            depth=0,
            ephemeral=False,
            title=None,
            title_source="brief",
            handle=None,
            model=LIVE_MODEL,
            effort=None,
        )

        # ----- 3. `can_fork` is the engine's, read rather than asserted into
        #         existence: with `False` the ask queues a mailbox message and
        #         no fork happens, which would make the sha256 below vacuous.
        engine = capabilities(pane_driver_available=True)
        assert engine.can_fork is True, engine

        result = ask_session(
            store=store,
            run_fork=run_fork,
            now=lambda: NOW,
            binary=resolve_binary(),
            projects_root=projects_root,
            can_fork=engine.can_fork,
            session_id=SESSION_ID,
            question=QUESTION,
            timeout_ms=FORK_TIMEOUT_MS,
        )

        # ----- 4. the fork really ran and really answered.
        assert result.method == "fork", result
        assert result.from_fork_of == engine_session_id, result
        assert result.refusal is None, result.refusal
        assert result.text, f"the fork returned no text: {result}"

        ask_rows = [
            row
            for row in store.list_sessions()
            if row.origin is Origin.ASK_FORK and row.parent_session_id == SESSION_ID
        ]
        assert len(ask_rows) == 1, ask_rows
        forked = ask_rows[0]
        assert forked.engine_session_id is not None, (
            "the fork reported no session id, so nothing proves a second engine "
            "session existed at all"
        )
        assert forked.engine_session_id != engine_session_id, (
            "the fork reported the target's own id: this was a resume, not a fork"
        )
        assert forked.state is SessionState.STOPPED
        assert forked.ephemeral is True  # DP2: never on the fleet page
    finally:
        store.close()

    # ----- 5. …and only now the property: the target's bytes did not move.
    assert target_path.is_file(), "the fork deleted the target's transcript"
    assert digest(target_path) == before, (
        f"the fork wrote into the target's transcript {target_path}: "
        f"{size_before} -> {target_path.stat().st_size} bytes"
    )

    # The fork's own transcript is `--no-session-persistence`'s business
    # (BLOCKER-T1-2) and is reported, never deleted (K3): `ask_session` bumps
    # `ASK_FORK_RESIDUE` and writes the path down if one was left.
    assert locate_transcript(projects_root, engine_session_id) == target_path


def _newest_transcript(projects_root: Path, workdir: Path) -> Path | None:
    """The most recently written `*.jsonl` under the project dir for `workdir`.

    Located by walking the projects root rather than by reversing the slug: the
    engine's project-directory name is lossy and this lane never reconstructs it
    (`locate_transcript` globs for the same reason). Scoped to files written
    since this process started, so the user's own transcripts cannot be picked up
    — F10 again: the real config dir means their work is in the same directory.
    """
    if not projects_root.is_dir():
        return None
    found = [
        path
        for path in projects_root.rglob("*.jsonl")
        if path.stat().st_mtime > _STARTED and _names_workdir(path, workdir)
    ]
    if not found:
        return None
    return max(found, key=lambda path: path.stat().st_mtime)


def _names_workdir(path: Path, workdir: Path) -> bool:
    """Does this transcript's first readable entry name our throwaway cwd?

    Read from the file's own `cwd` field rather than from its directory name, so
    a transcript that merely landed in a similarly-named folder is not mistaken
    for ours. A torn line is skipped, never raised (D25).
    """
    import json

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    for line in raw.splitlines():
        try:
            entry: object = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("cwd") == str(workdir):
            return True
    return False


#: Anything written before this module was imported belongs to somebody else.
_STARTED = time.time()
