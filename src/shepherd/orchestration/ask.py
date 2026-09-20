"""T15 — `ask()`: D13's synchronous question, answered by a headless fork (DP7).

The fork is a **separate `-p` process with its own session id**, so the target is
never interrupted, never written to and never read from: §9's "fork the target,
ask the fork" without §9's letter, which would open a second pane (DP7 explains
why not). Nothing here touches a terminal, so the one mind-reading capability
still answers on a host with no pane driver.

## Clause 6's "never deletes a file the engine owns", and why it is not a no-op

`--no-session-persistence` means the normal path leaves **no** fork transcript at
all (P2, `p2-fork-20260917T110431Z/03-project-listing.txt`). Residue therefore
means the flag was dropped or ignored — a regression — and it is **named** (its
path goes into the durable `app_state` record) and **counted**
(`AnomalyKind.ASK_FORK_RESIDUE`) and **left exactly where it is**. K3 forbids the
delete and D13's "discard" means the session, not the file: Shepherd does not
remove a file a user may want, and the engine owns every byte under its own
config directory. This module names no write verb at all.

**The inversion is deliberate (BLOCKER-T1-2, router note).** T2 defined the
member as *"P2 says a fork transcript is left"*, which fires on the normal path
and is silent on the regression. A counter nobody can hit and a counter that
fires every time are both lies (K9), so the trigger is "residue was found".

## The row, and the verb that binds it

The row is created **unbound** (`origin=ask_fork` is the one origin
`create_owned_session` permits that for) and bound afterwards from **the result
object's own `session_id`** — `bind_engine_session_id`, the conditional write for
an unbound row, whose rowcount is honoured and recorded. Not
`rebind_engine_session_id`: that is C14's move of an existing binding, and one
verb could not express both (blocker T4-1).

`--session-id <uuid>` is still passed, because P2 proved it is accepted and
returned verbatim — that is what makes the fork's transcript name predictable, so
a run that dies before printing anything can still be swept for residue. Binding
from the *reported* id rather than the requested one costs nothing and is correct
whichever way a future engine answers; the P2-`unknown` case (a **live
interactive** target with `--session-id`) therefore needs no second branch.

**Recorded deviation from the plan's `Produces`: three required injections and a
widened process seam.** `binary` and `projects_root` are values, not lookups —
`resolve_binary` would answer a `PATH` question at the wrong moment (T11's
precedent) and the engine's config home has been a required argument at every
call site since T10-R1. `can_fork` likewise arrives as a value: reading the
engine's capability record here is forbidden and
`capabilities(pane_driver_available=)` has exactly one permitted caller
(`tests/boundaries/test_capability_degrade.py`), and a fork needs no pane driver
anyway. And `run_fork` is `RunArgv` **plus `timeout_ms`**: T8's shape is
`Callable[[list[str]], CommandResult]`, which cannot carry a deadline, and
`ask()` cannot kill a process it never holds. The kill happens where the child
does — `subprocess.run(argv, timeout=...)` kills before it raises — so the
timeout has to cross this seam or a fleet machine leaks one process per call.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from shepherd.core.anomalies import AnomalyKind
from shepherd.core.clock import parse_stamp
from shepherd.core.ids import new_ulid
from shepherd.core.mailbox import MailboxOrigin
from shepherd.core.runner import RunnerRefusal
from shepherd.core.states import Origin, SessionState
from shepherd.core.stops import DecidedBy, StopReason, Verdict
from shepherd.core.fold_types import FoldDelta
from shepherd.engines.claude_code.fork import ForkResult, fork_argv, parse_fork_result
from shepherd.engines.claude_code.transcript import locate_transcript
from shepherd.orchestration.mailbox import queue_message
from shepherd.runner.local import CommandResult
from shepherd.signals.stop_rules import BUCKET_OF, default_actions
from shepherd.store.db import Store

__all__ = ["ASK_RECORD_PREFIX", "AskResult", "ForkRunner", "ask_session"]

#: The durable record of one ask, under `app_state`. It is the **named** half of
#: "named and counted": a count says how many, this says which file.
ASK_RECORD_PREFIX = "ask_fork."

#: §8's synchronous budget. A default a caller may raise, never a constant buried
#: in the call — a question worth two minutes is not worth ten.
ASK_TIMEOUT_MS = 120_000

_MAILBOX_REFUSAL = (
    "can_fork is False for this engine, so the question was queued in the mailbox "
    "for the session to answer at its next turn boundary instead of forked"
)
_NO_TARGET = "there is no owned, engine-bound session {!r} to fork from"
_ASK_CONFIDENCE = 1.0


@dataclass(frozen=True)
class AskResult:
    """What one question got, and **how**.

    `method` has no absent value: principle 5 at the return type, so a downgrade
    to the mailbox can never be silent. `text` is `None` whenever the answer did
    not arrive, and `refusal` then says why in words a caller can act on.
    """

    text: str | None
    method: Literal["fork", "mailbox"]
    from_fork_of: str
    duration_ms: int
    refusal: str | None


class ForkRunner(Protocol):
    """T8's `RunArgv` with the one thing a deadline needs. See the module note."""

    def __call__(self, argv: list[str], *, timeout_ms: int) -> CommandResult: ...


def _elapsed(started: str, finished: str) -> int:
    """Milliseconds between two reads of the **one** injected clock.

    `0` when a stamp could not be parsed. Both stamps go into the `app_state`
    record either way, so an unreadable clock is visible rather than inferred
    from a suspiciously round duration.
    """
    first, last = parse_stamp(started), parse_stamp(finished)
    if first is None or last is None:
        return 0
    return int((last - first).total_seconds() * 1000)


def _verdict(reason: StopReason, why: str) -> Verdict:
    """A declared verdict, using M2's own bucket and action tables."""
    return Verdict(
        stop_reason=reason,
        bucket=BUCKET_OF[reason],
        why=why,
        confidence=_ASK_CONFIDENCE,
        decided_by=DecidedBy.DECLARED,
        next_actions=default_actions(
            reason, confidence=_ASK_CONFIDENCE, missing=(), waiting_on=None
        ),
        waiting_on=None,
        missing=(),
    )


def _finish(store: Store, ask_id: str, verdict: Verdict, at: str, exit_code: int | None) -> None:
    """The ask row's ending. `apply_stop_verdict` is still the only stop writer;
    the fold carries the state column, which that verb does not touch."""
    store.apply_fold_delta(ask_id, FoldDelta(state=SessionState.STOPPED, last_event_at=at))
    store.apply_stop_verdict(ask_id, verdict, at, exit_code)


def _residue(projects_root: Path, candidates: tuple[str, ...], target: str) -> Path | None:
    """The fork's transcript, if `--no-session-persistence` did not hold.

    Looked for under **both** the id we asked for and the id the engine reported:
    if `--session-id` were ever ignored the file carries the engine's, and
    searching only for ours would report a clean run on exactly the regression
    this exists to catch. The **target's** id is excluded by name — the one file
    in this directory that is never residue is the one we forked from.
    """
    for engine_session_id in candidates:
        if engine_session_id == target:
            continue
        found = locate_transcript(projects_root, engine_session_id)
        if found is not None:
            return found
    return None


def ask_session(
    *,
    store: Store,
    run_fork: ForkRunner,
    now: Callable[[], str],
    binary: str,
    projects_root: Path,
    can_fork: bool,
    session_id: str,
    question: str,
    timeout_ms: int = ASK_TIMEOUT_MS,
) -> AskResult:
    """Ask one owned session one question. Every failure is an `AskResult`."""
    started = now()
    row = store.get_owned_session(session_id)
    if row is None or row.engine_session_id is None:
        return AskResult(
            text=None,
            method="fork",
            from_fork_of="",
            duration_ms=_elapsed(started, now()),
            refusal=_NO_TARGET.format(session_id),
        )
    # E-M3-33: the parent link is **our** row's column. The engine writes no
    # `forkedFrom` field; its only trace of a parent is the original `sessionId`
    # left on copied entries, which is the transcript — and this never reads it.
    from_fork_of = row.engine_session_id

    if not can_fork:
        queue_message(
            store=store,
            session_id=session_id,
            body=question,
            origin=MailboxOrigin.SESSION,
            idempotency_key=f"{ASK_RECORD_PREFIX}{new_ulid()}",
            now=now,
        )
        return AskResult(
            text=None,
            method="mailbox",
            from_fork_of=from_fork_of,
            duration_ms=_elapsed(started, now()),
            refusal=_MAILBOX_REFUSAL,
        )

    ask_id, fork_session_id = new_ulid(), str(uuid.uuid4())
    # DP2: ephemeral **from birth**, so the ask is never on the fleet page — not
    # even for the window between the row and the process. Unbound, because the
    # id that matters is the one the run reports (A25).
    store.create_owned_session(
        session_id=ask_id,
        engine_session_id=None,
        workspace_id=row.workspace_id,
        repo_id=row.repo_id,
        cwd=row.cwd or "",
        started_at=started,
        origin=Origin.ASK_FORK,
        parent_session_id=session_id,
        depth=row.depth + 1,
        ephemeral=True,
        title=None,
        title_source="brief",
        handle=None,
        model=row.model,
        effort=None,
    )

    argv = fork_argv(
        binary=binary,
        engine_session_id=from_fork_of,
        question=question,
        fork_session_id=fork_session_id,
    )
    completed: CommandResult | None = None
    killed: str | None = None
    try:
        completed = run_fork(argv, timeout_ms=timeout_ms)
    except RunnerRefusal as refused:
        killed = (
            f"the fork did not answer within {timeout_ms} ms and was killed, so the "
            f"question is unanswered rather than pending: {refused.reason}"
        )
    finished = now()

    parsed = None if completed is None else parse_fork_result(completed.stdout)
    reported = () if parsed is None else (parsed.session_id,)
    left = _residue(projects_root, (fork_session_id, *reported), from_fork_of)
    if left is not None:
        store.bump_anomaly(str(AnomalyKind.ASK_FORK_RESIDUE.value))

    bound = 0 if parsed is None else store.bind_engine_session_id(ask_id, parsed.session_id)
    store.set_app_state(
        f"{ASK_RECORD_PREFIX}{ask_id}",
        {
            "parent_session_id": session_id,
            "requested_session_id": fork_session_id,
            "engine_session_id": None if parsed is None else parsed.session_id,
            "bound": bound == 1,
            # The **named** half of clause 6. Never a handle to delete it by:
            # the path is written down so a human can decide, and that is all.
            "residue_path": None if left is None else str(left),
            "started_at": started,
            "finished_at": finished,
        },
    )

    refusal, text, reason, why = _outcome(completed, parsed, killed)
    _finish(
        store,
        ask_id,
        _verdict(reason, why),
        finished,
        None if completed is None else completed.rc,
    )
    return AskResult(
        text=text,
        method="fork",
        from_fork_of=from_fork_of,
        duration_ms=_elapsed(started, finished),
        refusal=refusal,
    )


def _outcome(
    completed: CommandResult | None, parsed: ForkResult | None, killed: str | None
) -> tuple[str | None, str | None, StopReason, str]:
    """`(refusal, text, stop_reason, why)` — the four ways one ask can end.

    A killed fork is `killed` because Shepherd killed it and says so; the three
    unreadable endings are `unknown`, which is the value principle 5 reserves for
    an answer nobody can name — never a `completed` with empty text.
    """
    if killed is not None or completed is None:
        gone = killed or "the fork produced no result at all"
        return (gone, None, StopReason.KILLED, gone)
    if parsed is None:
        unreadable = (
            "the fork printed no readable result object, so the answer is unknown: "
            f"rc {completed.rc}, {len(completed.stdout)} bytes on stdout"
        )
        return (unreadable, None, StopReason.UNKNOWN, unreadable)
    if completed.rc != 0 or parsed.is_error:
        errored = (
            f"the fork reported an error: rc {completed.rc}, subtype {parsed.subtype!r}, "
            f"is_error {parsed.is_error}"
        )
        return (errored, None, StopReason.UNKNOWN, errored)
    return (
        None,
        parsed.result,
        StopReason.COMPLETED,
        f"the fork answered in one turn (subtype {parsed.subtype!r})",
    )
