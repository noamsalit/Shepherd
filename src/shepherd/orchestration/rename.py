"""T20 — a rename, honestly: the ratchet, the `local only` marker, and the
write-back that **ships disabled** (D29, DP1, acceptance clause 12).

Three verbs and one record. The local rename always happens; the write-back is
built, is exercised in the live lane, and is **unreachable in production** while
`can_set_title` is `False` — M2's shape for `crashed`/`killed`/`derailed`.

**Nothing here flips the flag.** DP1 recommends **option 3** — `can_set_title` is
the engine's *ceiling* and the **call site** answers `ceiling and ownership is
OWNED and handle is not None` — **stated and not applied**. `rename_session`
evaluates that predicate for real, which is what makes the reversal one constant;
the constant still says `False`, and
`tests/engines/test_spawn_argv.py::test_can_set_title_ships_false` fails the
build if anyone flips it without a recorded approval.

**The ratchet is composed, not written again.** `store/sessions.py::apply_title`
**is** D29's one-way ratchet and `set_title_synced_at` is the column's only
writer. A second ratchet here would be a second precedence rule.

**`title_synced_at` comes from a read-back.** The engine writes `custom-title` +
`agent-name` itself when `/rename <title>` is typed over the pty, and its sidecar
then reports `name`/`nameSource:"user"` (data-schemas §"Session title",
`10-sidecar-after-rename.json`). The confirmation is a **read** of the engine's
own file through the parser that ships — Shepherd never writes into a file the
engine owns (principle 4, K3) — and an unconfirmed send leaves the session
`local only`, which is the difference between a degrade and a lie.

**The pane gate.** A slash command delivered mid-turn is enqueued and reaches the
model as *text* (E-M3-9), so `/rename` goes only to a prompt-ready pane with an
empty box. `write_policy.decide_write` is asked and not re-decided, with
`mailbox.turn_state` answering its first key field from the pane; the stored
`SessionState` is not an input here, so the **pessimistic** value is passed in its
place. Two readings are this module's own: `CLEAR_THEN_SEND` becomes
`REFUSE_INPUT_NOT_EMPTY` (clearing a draft is worth it to deliver a message, not
to set a title), and `QUEUE` means **not sent** — there is no rename mailbox.

**What a reviewer of DP1 must weigh.** This path does not ask `attached_clients`
before it types. `deliver_now` does — P3 captured a human at a second client
having their keystrokes submitted inside Shepherd's own prompt — and this path
would need the same precondition **before** the ceiling is ever flipped. It is
absent because the path is unreachable; it is named rather than left to notice.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shepherd.core.runner import EngineCapabilities, RunnerHandle, RunnerRefusal, WriteDecision
from shepherd.core.states import Ownership, SessionState, TitleSource
from shepherd.engines.claude_code.registry import (
    SESSIONS_DIRNAME, USER_NAME_SOURCE, SidecarProblem, parse_sidecar)
from shepherd.orchestration.mailbox import turn_state
from shepherd.orchestration.write_policy import decide_write
from shepherd.runner.base import Runner
from shepherd.store.db import Store

__all__ = [
    "LOCAL_ONLY_MARKER",
    "RENAME_COMMAND",
    "RenameOutcome",
    "confirm_engine_title",
    "drive_engine_rename",
    "rename_session",
]

#: §12's marker, verbatim (RD9): what the UI renders for a title the engine has
#: not confirmed, and the string a reviewer greps for when DP1 is decided.
LOCAL_ONLY_MARKER = "local only"

#: The engine's own verb. The title follows as one argument, and the engine
#: writes `custom-title` + `agent-name` itself — **no hook fires**
#: (data-schemas §"Session title": `hook events during /rename: []`).
RENAME_COMMAND = "/rename"

#: What submits the line. The same byte `deliver_now` presses, for the same
#: reason: it is the pane's own Enter, sent through the opaque byte channel.
SUBMIT = b"\r"

#: The title source a rename writes. The top of D29's rank, which is why the
#: engine's own title can never overwrite it afterwards.
USER_TITLE_SOURCE: TitleSource = "user"

#: The state passed to the write policy when the pane does not say otherwise.
#: **Pessimistic on purpose**: a turn we cannot see is a turn that is running,
#: and `turn_state` relaxes it only for an owned, prompt-ready pane.
_ASSUME_MID_TURN = SessionState.RUNNING


@dataclass(frozen=True)
class RenameOutcome:
    """What one rename did. `local_only` is the marker's own boolean: `True`
    whenever the engine has not confirmed the title, which today is always."""

    title: str
    source: TitleSource
    synced_at: str | None
    local_only: bool


def rename_session(
    *,
    store: Store,
    runner: Runner,
    handle: RunnerHandle | None,
    session_id: str,
    title: str,
    now: Callable[[], str],
    capabilities: EngineCapabilities,
    ownership: Ownership,
    config_dir: Path,
) -> RenameOutcome:
    """Rename a session locally, and — if the engine may be driven — ask it too.

    `config_dir` is the **engine's** config directory and is required rather than
    resolved: a default reaching the user's real `~/.claude` is the shape T10-R1
    was written about, and this verb is only ever called with a directory its
    caller chose.
    """
    row = store.apply_title(session_id, title, USER_TITLE_SOURCE)
    applied = RenameOutcome(
        title=row.title if row.title is not None else title,
        source=row.title_source,
        synced_at=row.title_synced_at,
        local_only=True,
    )

    # DP1 option 3's per-session predicate, in code. The ceiling is the engine's
    # (`False` today); OWNED and a handle are this session's, and they are what
    # keep the flip safe for the attached case it is wrong for (G-M3-5).
    if not (capabilities.can_set_title and ownership is Ownership.OWNED and handle is not None):
        return applied

    sent = drive_engine_rename(runner=runner, handle=handle, title=title)
    if sent is not WriteDecision.SEND_NOW:
        return applied

    pid = _pane_pid(runner, handle)
    if pid is None or not confirm_engine_title(config_dir=config_dir, pid=pid, title=title):
        # Sent, unconfirmed — and therefore still `local only`. A stamp here
        # would be exactly the silent half-success D29 forbids.
        return applied

    stamped = now()
    store.set_title_synced_at(session_id, stamped)
    return RenameOutcome(
        title=applied.title, source=applied.source, synced_at=stamped, local_only=False
    )


def drive_engine_rename(*, runner: Runner, handle: RunnerHandle, title: str) -> WriteDecision:
    """Type `/rename <title>` at a prompt-ready pane. Unreachable in production
    while `can_set_title` is `False`; see the module docstring.

    Returns the decision that was taken. Only `SEND_NOW` sent anything.
    """
    try:
        pane = runner.pane(handle)
    except RunnerRefusal:
        return WriteDecision.REFUSE_NO_PTY

    decision = decide_write(
        turn_state(_ASSUME_MID_TURN, pane, Ownership.OWNED), pane, Ownership.OWNED
    )
    if decision is WriteDecision.CLEAR_THEN_SEND:
        return WriteDecision.REFUSE_INPUT_NOT_EMPTY
    if decision is not WriteDecision.SEND_NOW:
        return decision

    runner.write(handle, f"{RENAME_COMMAND} {title}".encode())
    runner.write(handle, SUBMIT)
    return decision


def confirm_engine_title(*, config_dir: Path, pid: int, title: str) -> bool:
    """Did the engine accept this title? One read of its own sidecar, no clock.

    `True` only for the engine's `nameSource:"user"` carrying **this** name.
    Absent, truncated, torn mid-multibyte, or still `derived` all answer `False`:
    an unknown is never read as a yes (principle 5). A caller that needs to wait
    polls this; nothing here sleeps.
    """
    path = config_dir / SESSIONS_DIRNAME / f"{pid}.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    entry = parse_sidecar(raw)
    if isinstance(entry, SidecarProblem):
        return False
    return entry.name == title and entry.name_source == USER_NAME_SOURCE


def _pane_pid(runner: Runner, handle: RunnerHandle) -> int | None:
    """The pid the sidecar is named by, or `None` — never a guess."""
    try:
        return runner.probe(handle).pid
    except RunnerRefusal:
        return None
